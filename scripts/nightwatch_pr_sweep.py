#!/usr/bin/env python3
"""Nightwatch PR sweep — surface open, stuck, or stale agent-authored PRs.

Writes a compact status markdown file that Main reads in its heartbeat warmup so
that Nightwatch-authored PRs don't sit un-merged for days.

Runs via cron (see brain/crontab). Output: brain/memory/nightwatch-backlog.md.

No LLM involvement. Pure gh CLI + markdown rendering.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE = Path(os.environ.get("ROBOTHOR_WORKSPACE", Path.home() / "robothor"))
OUTPUT_PATH = WORKSPACE / "brain" / "memory" / "nightwatch-backlog.md"

# PRs authored by these GitHub logins are agent-authored and belong in the sweep.
# `ROBOTHOR_AGENT_AUTHORS` env var overrides (comma-separated).
DEFAULT_AGENT_AUTHORS = ("robothor-nightwatch", "robothor-bot", "app/robothor")
AGENT_AUTHORS = tuple(
    a.strip()
    for a in os.environ.get("ROBOTHOR_AGENT_AUTHORS", ",".join(DEFAULT_AGENT_AUTHORS)).split(",")
    if a.strip()
)

# Labels that promote any PR into the sweep even if not agent-authored.
AGENT_LABELS = ("nightwatch", "autoresearch", "robothor")

STALE_DAYS = 3


def _gh_json(args: list[str]) -> list[dict]:
    result = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=WORKSPACE,
    )
    return json.loads(result.stdout or "[]")


def _age_days(created_at: str, now: datetime) -> int:
    created = datetime.fromisoformat(created_at)
    return (now - created).days


def _should_include(pr: dict) -> bool:
    author = (pr.get("author") or {}).get("login", "")
    if any(a in author for a in AGENT_AUTHORS):
        return True
    labels = {lbl.get("name", "") for lbl in pr.get("labels", []) or []}
    return bool(labels & set(AGENT_LABELS))


def _ci_summary(pr: dict) -> str:
    checks = pr.get("statusCheckRollup") or []
    if not checks:
        return "no-ci"
    failing = [c for c in checks if c.get("conclusion") in ("FAILURE", "CANCELLED", "TIMED_OUT")]
    pending = [c for c in checks if c.get("status") in ("QUEUED", "IN_PROGRESS", "PENDING")]
    if failing:
        return f"fail({len(failing)})"
    if pending:
        return f"pending({len(pending)})"
    return "green"


def collect_prs() -> list[dict]:
    """Return agent-authored or agent-labeled open non-draft PRs across the repo."""
    fields = [
        "number",
        "title",
        "author",
        "createdAt",
        "updatedAt",
        "isDraft",
        "labels",
        "additions",
        "deletions",
        "statusCheckRollup",
        "url",
    ]
    raw = _gh_json(["pr", "list", "--state", "open", "--limit", "100", "--json", ",".join(fields)])
    return [pr for pr in raw if not pr.get("isDraft") and _should_include(pr)]


def render(prs: list[dict]) -> str:
    now = datetime.now(UTC)
    ts = now.isoformat(timespec="seconds")

    if not prs:
        return (
            f"# Nightwatch PR Backlog\n\n"
            f"Last sweep: {ts}\n"
            f"Open agent-authored PRs: 0\n\n"
            "Nothing to babysit. All agent-authored PRs have landed or been closed.\n"
        )

    lines = [
        "# Nightwatch PR Backlog",
        "",
        f"Last sweep: {ts}",
        f"Open agent-authored PRs: {len(prs)}",
        "",
        "| # | Age | Diff | CI | Title | Author |",
        "|---|-----|------|------|-------|--------|",
    ]
    for pr in sorted(prs, key=lambda p: p.get("createdAt", "")):
        age = _age_days(pr["createdAt"], now)
        stale = " ⚠️" if age >= STALE_DAYS else ""
        diff = f"+{pr.get('additions', 0)}/-{pr.get('deletions', 0)}"
        ci = _ci_summary(pr)
        title = (pr["title"][:60] + "…") if len(pr["title"]) > 60 else pr["title"]
        author = (pr.get("author") or {}).get("login", "?")
        lines.append(
            f"| [#{pr['number']}]({pr['url']}) | {age}d{stale} | {diff} | {ci} | {title} | {author} |"
        )

    lines.append("")
    lines.append(
        "Merge candidates: CI green, diff <200 lines, age <7 days. "
        "Main's heartbeat should merge these, or explicitly decide why not."
    )
    lines.append(
        f"Stale (≥{STALE_DAYS}d with no merge) PRs need escalation — either merge, close, or surface to Philip."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    try:
        prs = collect_prs()
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"gh failed: {exc.stderr}\n")
        return 1
    except FileNotFoundError:
        sys.stderr.write("gh CLI not found on PATH\n")
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render(prs))
    print(f"wrote {len(prs)} PR(s) to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
