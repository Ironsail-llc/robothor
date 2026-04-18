"""Thread pool — ordered view of open multi-beat work for the main heartbeat.

A "thread" is a ``crm_tasks`` row tagged ``thread`` that represents ongoing work
spanning multiple heartbeat cycles — research questions, stuck experiments,
broken agents, overdue reports, PR follow-through. This module reads the pool;
creation is inline via ``update_task(tags=[..., 'thread'])`` from heartbeat
instructions.

Priority order (first → last):
1. Philip-blocked: ``requires_human`` AND status = REVIEW
2. SLA-breached: ``sla_deadline_at < now``
3. Most-escalated: ``escalation_count`` desc
4. Oldest-touched: ``COALESCE(updated_at, created_at)`` asc

Injected into Main's warmup via ``register_agent_context_hook``. Never raises —
a failing hook silently returns ``None``.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from robothor.constants import DEFAULT_TENANT

if TYPE_CHECKING:
    from robothor.engine.models import AgentConfig

logger = logging.getLogger(__name__)

MAX_THREADS = 8
MAX_TITLE_CHARS = 60
MAX_LINE_CHARS = 140

# Acceptance blocks: fenced ```accept … ``` inside a task body.
# Each non-blank, non-comment line is an independent shell command run
# via subprocess. ALL must exit 0 for acceptance to pass.
_ACCEPT_BLOCK_RE = re.compile(
    r"```accept\s*\n(?P<body>.*?)\n```",
    re.DOTALL,
)
ACCEPT_TIMEOUT_SECONDS = 30

# Pending-sub-agent marker — inserted into a thread body by Main when it
# spawns a sub-agent to advance the thread. Filters out the thread from
# list_threads() so the next heartbeat doesn't spawn a duplicate.
# Format: <!-- pending: run=<run_id> ts=<iso8601> -->
_PENDING_MARKER_RE = re.compile(
    r"<!--\s*pending:\s*run=(?P<run_id>[\w\-]+)\s+ts=(?P<ts>[\w:\.\-\+T]+)\s*-->"
)
PENDING_EXPIRY_SECONDS = 1800  # match sub_agent_timeout_seconds default


@dataclass(frozen=True)
class Thread:
    """One thread-tagged open task with derived status signals."""

    id: str
    title: str
    status: str
    priority: str
    age_days: int
    stale_days: int
    requires_human: bool
    sla_breached: bool
    escalation_count: int
    open_children: int
    total_children: int
    assigned_to_agent: str | None

    @property
    def short_id(self) -> str:
        return self.id[:8]


_LIST_SQL = """
SELECT
  t.id::text,
  t.title,
  t.status,
  COALESCE(t.priority, 'normal'),
  t.requires_human,
  COALESCE(t.escalation_count, 0),
  t.assigned_to_agent,
  GREATEST(0, EXTRACT(DAY FROM (NOW() - t.created_at))::int) AS age_days,
  GREATEST(0, EXTRACT(DAY FROM (NOW() - COALESCE(t.updated_at, t.created_at)))::int) AS stale_days,
  (t.sla_deadline_at IS NOT NULL AND t.sla_deadline_at < NOW()) AS sla_breached,
  (
    SELECT COUNT(*) FROM crm_tasks c
    WHERE c.parent_task_id = t.id AND c.deleted_at IS NULL
  ) AS total_children,
  (
    SELECT COUNT(*) FROM crm_tasks c
    WHERE c.parent_task_id = t.id AND c.deleted_at IS NULL AND c.status != 'DONE'
  ) AS open_children,
  t.body
FROM crm_tasks t
WHERE t.deleted_at IS NULL
  AND t.tenant_id = %s
  AND t.status != 'DONE'
  AND 'thread' = ANY(t.tags)
ORDER BY
  CASE WHEN t.requires_human AND t.status = 'REVIEW' THEN 0 ELSE 1 END,
  CASE WHEN t.sla_deadline_at IS NOT NULL AND t.sla_deadline_at < NOW() THEN 0 ELSE 1 END,
  COALESCE(t.escalation_count, 0) DESC,
  COALESCE(t.updated_at, t.created_at) ASC
LIMIT %s
"""


def list_threads(
    tenant_id: str = DEFAULT_TENANT,
    limit: int = MAX_THREADS,
    include_pending: bool = False,
) -> list[Thread]:
    """Return open thread-tagged tasks ordered by staleness priority.

    By default, threads with an unexpired pending-sub-agent marker in their
    body are filtered out so the same thread isn't spawned twice in adjacent
    heartbeats. Pass ``include_pending=True`` to see them (useful for the
    stall classifier in Stage 3).

    Fast enough (<50ms on typical fleet) to run in a 100ms warmup hook budget.
    """
    from robothor.db.connection import get_connection

    # Fetch more than `limit` so post-filter of pending threads can still
    # surface `limit` non-pending ones.
    fetch_limit = limit * 2 if not include_pending else limit
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(_LIST_SQL, (tenant_id, fetch_limit))
        rows = cur.fetchall()

    threads: list[Thread] = []
    for r in rows:
        body = r[12]
        if not include_pending and is_pending(body):
            continue
        threads.append(
            Thread(
                id=r[0],
                title=r[1] or "(untitled)",
                status=r[2],
                priority=r[3],
                requires_human=bool(r[4]),
                escalation_count=int(r[5]),
                assigned_to_agent=r[6],
                age_days=int(r[7]),
                stale_days=int(r[8]),
                sla_breached=bool(r[9]),
                total_children=int(r[10]),
                open_children=int(r[11]),
            )
        )
        if len(threads) >= limit:
            break
    return threads


def format_thread_pool(threads: list[Thread]) -> str:
    """Format threads as a compact text block for warmup injection.

    Always returns a non-empty string — an empty pool produces a prompt to
    promote ongoing work; a non-empty pool produces one line per thread.
    """
    if not threads:
        return (
            "--- THREAD POOL ---\n"
            "(empty) No open threads tagged `thread`. If you notice multi-heartbeat "
            "work slipping through the cracks (research, stuck experiments, overdue "
            "reports, stale PRs), promote it: update_task(id, tags=[..., 'thread'])."
        )

    lines = ["--- THREAD POOL — advance, close, escalate, or propose at least one per beat ---"]
    for t in threads:
        title = t.title
        if len(title) > MAX_TITLE_CHARS:
            title = title[: MAX_TITLE_CHARS - 1] + "…"

        markers: list[str] = []
        if t.requires_human and t.status == "REVIEW":
            markers.append("🧑PHILIP")
        if t.sla_breached:
            markers.append("⏰SLA")
        if t.escalation_count > 0:
            markers.append(f"↑{t.escalation_count}")
        if t.total_children:
            done = t.total_children - t.open_children
            markers.append(f"kids:{done}/{t.total_children}")

        marker_str = " ".join(markers)
        assignee = f" @{t.assigned_to_agent}" if t.assigned_to_agent else ""
        line = (
            f"[{t.short_id}][{t.status}][{t.stale_days}d] {title}"
            + (f"  {marker_str}" if marker_str else "")
            + assignee
        )
        if len(line) > MAX_LINE_CHARS:
            line = line[: MAX_LINE_CHARS - 1] + "…"
        lines.append(line)
    return "\n".join(lines)


def _thread_pool_context(config: AgentConfig) -> str | None:
    """Agent context hook — inject thread pool view for main agent heartbeat.

    Returns None for any agent other than main so other agents' warmups aren't
    cluttered. Swallows all exceptions to match the warmup contract.
    """
    if config.id != "main":
        return None
    try:
        tenant_id = os.environ.get("ROBOTHOR_TENANT_ID", "") or DEFAULT_TENANT
        threads = list_threads(tenant_id=tenant_id)
        return format_thread_pool(threads)
    except Exception as exc:
        logger.debug("Thread pool hook failed: %s", exc)
        return None


# ─── Acceptance blocks (Stage 2) ──────────────────────────────────────


def parse_accept_block(body: str | None) -> list[str]:
    """Extract shell commands from a ``` ```accept … ``` ``` fenced block in a
    task body.

    Non-blank, non-comment (``#``-prefixed) lines become individual commands.
    Returns an empty list if no accept block is present.
    """
    if not body:
        return []
    m = _ACCEPT_BLOCK_RE.search(body)
    if not m:
        return []
    return [
        line.strip()
        for line in m.group("body").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def run_accept(
    commands: list[str],
    cwd: str | os.PathLike[str] | None = None,
    timeout: int = ACCEPT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Execute an acceptance block.

    Each command runs in its own shell. All must exit 0 for ``passed: True``.
    Returns a dict suitable for recording in ``crm_task_history.metadata``.
    """
    if not commands:
        return {"passed": True, "failures": [], "ran": 0}

    failures: list[dict[str, object]] = []
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            failures.append(
                {"command": cmd, "exit_code": None, "error": f"timeout after {timeout}s"}
            )
            continue
        if result.returncode != 0:
            failures.append(
                {
                    "command": cmd,
                    "exit_code": result.returncode,
                    "stdout": (result.stdout or "")[-400:],
                    "stderr": (result.stderr or "")[-400:],
                }
            )
    return {"passed": not failures, "failures": failures, "ran": len(commands)}


# ─── Pending sub-agent marker (Stage 2) ───────────────────────────────


def is_pending(body: str | None, now_iso: str | None = None) -> bool:
    """Return True if the task body has a non-expired pending marker.

    A pending thread is in flight — some prior heartbeat already spawned
    a sub-agent for it. The marker expires after PENDING_EXPIRY_SECONDS so
    a truly wedged sub-agent doesn't block the thread forever.
    """
    if not body:
        return False
    m = _PENDING_MARKER_RE.search(body)
    if not m:
        return False
    try:
        from datetime import UTC, datetime

        ts = datetime.fromisoformat(m.group("ts"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return (now - ts).total_seconds() < PENDING_EXPIRY_SECONDS
    except (ValueError, TypeError):
        return False


def pending_marker(run_id: str, ts_iso: str | None = None) -> str:
    """Render a pending marker for insertion into a task body."""
    from datetime import UTC, datetime

    ts = ts_iso or datetime.now(UTC).isoformat(timespec="seconds")
    return f"<!-- pending: run={run_id} ts={ts} -->"
