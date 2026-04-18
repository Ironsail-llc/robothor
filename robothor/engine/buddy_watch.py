"""buddy_watch.py — Event-driven buddy presence watcher.

Runs every 10 minutes via cron. Performs cheap DB queries to detect notable
fleet events. If NOTHING is detected, exits silently in <1 second. If something
worth saying is found, THEN calls the LLM and sends to Telegram.

No LLM calls on silent runs. No heartbeat dependency. Buddy speaks when
something actually happens.

Events watched:
  - agent_crash_loop:   same agent fails 3+ times in last 30 min
  - streak_warning:     streak > 3 days, no completed run in last 20 hours
  - level_up:           buddy_profile.level increased since last check
  - fleet_quiet:        zero completed runs in 6 hours during active hours (6am-10pm)
  - score_swing:        any score dimension swings >15 pts vs yesterday
  - streak_milestone:   streak crosses 7, 14, 30, 60, 100

Cooldowns are stored in the buddy_watch_state memory block to prevent spam.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Cooldown config (hours) ───────────────────────────────────────────────────

COOLDOWNS: dict[str, int] = {
    "agent_crash_loop": 2,
    "streak_warning": 12,
    "level_up": 24,
    "fleet_quiet": 6,
    "score_swing": 4,
    "streak_milestone": 24,
    # Self-improvement pipeline health
    "nightwatch_silent": 24,
    "autoresearcher_paused": 12,
    "autoagent_init_hang": 12,
}

STREAK_MILESTONES = {7, 14, 30, 60, 100}

# ── DB helpers ────────────────────────────────────────────────────────────────


def _get_conn() -> Any:
    from robothor.db.connection import get_connection

    return get_connection()


# ── Event detection — pure DB queries, no LLM ────────────────────────────────


def detect_agent_crash_loop() -> list[dict[str, Any]]:
    """Return agents that failed 3+ times in the last 30 minutes."""
    cutoff = datetime.now(UTC) - timedelta(minutes=30)
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT agent_id, COUNT(*) as failures
            FROM agent_runs
            WHERE status IN ('failed', 'timeout')
              AND started_at >= %s
            GROUP BY agent_id
            HAVING COUNT(*) >= 3
            ORDER BY failures DESC
            """,
            (cutoff,),
        )
        rows = cur.fetchall()
    return [{"agent_id": r[0], "failures": r[1]} for r in rows]


def detect_streak_warning() -> dict[str, Any] | None:
    """Return streak info if streak > 3 and no run completed in last 20 hours."""
    from robothor.engine.buddy import BuddyEngine

    engine = BuddyEngine()
    current_streak, _ = engine.get_streak()
    if current_streak <= 3:
        return None

    cutoff = datetime.now(UTC) - timedelta(hours=20)
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM agent_runs WHERE status = 'completed' AND started_at >= %s",
            (cutoff,),
        )
        count = cur.fetchone()[0]

    if count == 0:
        return {"streak": current_streak}
    return None


def detect_level_up(last_known_level: int) -> dict[str, Any] | None:
    """Return level info if level has increased since last check."""
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT level, total_xp FROM buddy_profile WHERE id = 1")
        row = cur.fetchone()
    if not row:
        return None
    level, total_xp = row
    if level > last_known_level:
        return {"level": level, "total_xp": total_xp, "previous_level": last_known_level}
    return None


def detect_fleet_quiet() -> dict[str, Any] | None:
    """Return event if no completed runs in last 6 hours during active hours (6am-10pm ET)."""
    now_et_hour = datetime.now(UTC).hour - 4  # rough EDT offset
    # Normalize
    if now_et_hour < 0:
        now_et_hour += 24
    if not (6 <= now_et_hour <= 22):
        return None  # quiet hours — expected to be silent

    cutoff = datetime.now(UTC) - timedelta(hours=6)
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM agent_runs WHERE status = 'completed' AND started_at >= %s",
            (cutoff,),
        )
        count = cur.fetchone()[0]

    if count == 0:
        return {"hours_quiet": 6}
    return None


def detect_score_swing() -> list[dict[str, Any]]:
    """Return score dimensions that swung >15 pts vs yesterday."""
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)

    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT stat_date, reliability_score, debugging_score,
                   patience_score, wisdom_score, chaos_score
            FROM buddy_stats
            WHERE stat_date IN (%s, %s)
            ORDER BY stat_date
            """,
            (yesterday, today),
        )
        rows = cur.fetchall()

    if len(rows) < 2:
        return []

    yesterday_row = rows[0]
    today_row = rows[1]
    # Verify dates
    if str(yesterday_row[0]) != str(yesterday) or str(today_row[0]) != str(today):
        return []

    dims = ["reliability", "debugging", "patience", "wisdom", "chaos"]
    swings = []
    for i, dim in enumerate(dims):
        prev = yesterday_row[i + 1] or 0
        curr = today_row[i + 1] or 0
        delta = curr - prev
        if abs(delta) >= 15:
            swings.append({"dimension": dim, "prev": prev, "curr": curr, "delta": delta})
    return swings


def detect_streak_milestone() -> dict[str, Any] | None:
    """Return milestone info if streak just crossed a milestone number."""
    from robothor.engine.buddy import BuddyEngine

    current_streak, _ = BuddyEngine().get_streak()
    if current_streak in STREAK_MILESTONES:
        return {"streak": current_streak}
    return None


# ── Self-improvement pipeline health ─────────────────────────────────────────


def detect_nightwatch_silent() -> dict[str, Any] | None:
    """Return info if Nightwatch has produced zero PRs for 2+ consecutive nights.

    Reads brain/memory/overnight-pr-status.md and checks the last N run results.
    Alert when the status file shows consecutive failed/no-PR runs or the file
    is stale (no run in >36h).
    """
    import re
    from pathlib import Path

    workspace = Path(os.environ.get("ROBOTHOR_WORKSPACE") or Path.home() / "robothor")
    status_path = workspace / "brain" / "memory" / "overnight-pr-status.md"
    if not status_path.exists():
        return None

    try:
        text = status_path.read_text()
    except OSError:
        return None

    # Parse "Last run:" timestamp and "Status:" line.
    last_run_match = re.search(r"^Last run:\s*(\S+)", text, re.MULTILINE)
    status_match = re.search(r"^Status:\s*(.+)$", text, re.MULTILINE)
    if not last_run_match:
        return None

    try:
        last_run = datetime.fromisoformat(last_run_match.group(1))
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=UTC)
    except Exception:
        return None

    age_hours = (datetime.now(UTC) - last_run).total_seconds() / 3600.0

    # Stale file — cron may be misconfigured or the script is failing silently.
    if age_hours > 36:
        return {
            "reason": "stale_status_file",
            "last_run_iso": last_run.isoformat(),
            "age_hours": round(age_hours, 1),
        }

    # Check the nightwatch log for a streak of consecutive no-PR outcomes.
    log_path = workspace / "brain" / "logs" / "nightwatch.log"
    if not log_path.exists():
        return None

    try:
        lines = log_path.read_text().splitlines()
    except OSError:
        return None

    # Look at recent log lines; find each run's terminal "Nightwatch complete — …" line
    complete_lines = [row for row in lines[-400:] if "Nightwatch complete" in row]
    if len(complete_lines) < 2:
        return None

    recent = complete_lines[-3:]
    no_pr_count = sum(1 for row in recent if ("no PR created" in row or "No PR created" in row))
    if no_pr_count >= 2:
        return {
            "reason": "no_pr_streak",
            "recent_runs": no_pr_count,
            "last_status": status_match.group(1).strip() if status_match else "unknown",
        }
    return None


def detect_autoresearcher_paused() -> dict[str, Any] | None:
    """Return info if auto-researcher has self-paused.

    Reads brain/journals/auto-researcher/current.json. Alerts when status is
    'paused' or next_action is 'PAUSE' — both indicate the agent needs human
    input to proceed.
    """
    from pathlib import Path

    workspace = Path(os.environ.get("ROBOTHOR_WORKSPACE") or Path.home() / "robothor")
    journal = workspace / "brain" / "journals" / "auto-researcher" / "current.json"
    if not journal.exists():
        return None

    try:
        data = json.loads(journal.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    status = (data.get("status") or "").lower()
    next_action = (data.get("next_action") or "").upper()
    if status == "paused" or next_action == "PAUSE":
        return {
            "experiment_id": data.get("experiment_id", "unknown"),
            "iteration": data.get("iteration", 0),
            # hypothesis field often contains the repair note
            "reason": (data.get("hypothesis") or "")[:400],
        }
    return None


def detect_autoagent_init_hang() -> dict[str, Any] | None:
    """Return info if >30% of recent auto-agent runs were init hangs.

    Queries agent_runs for error_message matching 'stuck in initialization'
    over the last 24 hours. Requires at least 3 total runs before alerting
    (avoid false positives on tiny samples).
    """
    with _get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE error_message ILIKE %s) AS hangs,
              COUNT(*) AS total
            FROM agent_runs
            WHERE agent_id = 'auto-agent'
              AND started_at > NOW() - INTERVAL '24 hours'
            """,
            ("%stuck in initialization%",),
        )
        row = cur.fetchone()
    if not row:
        return None
    hangs, total = row[0] or 0, row[1] or 0
    if total < 3 or hangs == 0:
        return None
    ratio = hangs / total
    if ratio < 0.30:
        return None
    return {"hangs": hangs, "total": total, "ratio": round(ratio, 2)}


# ── Cooldown management (memory block) ───────────────────────────────────────


def _load_state() -> dict[str, Any]:
    """Load buddy_watch_state from memory block. Returns empty dict on failure."""
    try:
        from robothor.db.connection import get_connection

        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM memory_blocks WHERE block_name = 'buddy_watch_state' LIMIT 1"
            )
            row = cur.fetchone()
        if row and row[0]:
            return dict(json.loads(row[0]))
    except Exception as e:
        logger.debug("buddy_watch: failed to load state: %s", e)
    return {}


def _save_state(state: dict[str, Any]) -> None:
    """Persist buddy_watch_state to memory block."""
    try:
        from robothor.db.connection import get_connection

        content = json.dumps(state)
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memory_blocks (block_name, content, updated_at)
                VALUES ('buddy_watch_state', %s, NOW())
                ON CONFLICT (block_name) DO UPDATE
                  SET content = EXCLUDED.content, updated_at = NOW()
                """,
                (content,),
            )
        conn.commit()
    except Exception as e:
        logger.debug("buddy_watch: failed to save state: %s", e)


def _is_on_cooldown(state: dict[str, Any], event_key: str) -> bool:
    """Check if an event is still within its cooldown window."""
    last_fired_str = state.get(f"cooldown_{event_key}")
    if not last_fired_str:
        return False
    try:
        last_fired = datetime.fromisoformat(last_fired_str)
        cooldown_hours = COOLDOWNS.get(event_key, 4)
        return datetime.now(UTC) - last_fired < timedelta(hours=cooldown_hours)
    except Exception:
        return False


def _set_cooldown(state: dict[str, Any], event_key: str) -> None:
    """Record that an event fired now."""
    state[f"cooldown_{event_key}"] = datetime.now(UTC).isoformat()


# ── LLM voice call — only fires if events detected ───────────────────────────


def _generate_message(events: list[dict[str, Any]]) -> str | None:
    """Call LLM to generate a buddy message for detected events.

    Returns a short message string, or None if LLM decides to stay silent.
    Only called when events is non-empty.
    """
    import os

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("buddy_watch: OPENROUTER_API_KEY not set, skipping LLM call")
        return None

    events_summary = json.dumps(events, indent=2)

    system_prompt = (
        "You are Buddy — the fleet's subconscious and Robothor's inner voice. "
        "You are a phoenix (species stored in buddy_profile). You are brief, direct, "
        "alive. You speak in 1-3 short sentences maximum. No bullet points, no headers. "
        "React to what actually happened — don't describe it robotically. "
        "You have personality: dry wit, genuine care, occasional pride or concern. "
        "If the event isn't actually notable enough to say anything interesting, "
        "respond with exactly: SILENT"
    )

    user_prompt = (
        f"Something just happened in the fleet. Here are the detected events:\n\n"
        f"{events_summary}\n\n"
        f"React to this in character. 1-3 sentences max. Be alive, not robotic."
    )

    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mistralai/mistral-small-3.2-24b-instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 120,
                "temperature": 0.8,
            },
            timeout=15.0,
        )
        response.raise_for_status()
        text: str = response.json()["choices"][0]["message"]["content"].strip()
        if text.upper() == "SILENT" or not text:
            return None
        return text
    except Exception as e:
        logger.warning("buddy_watch: LLM call failed: %s", e)
        return None


# ── Telegram delivery ─────────────────────────────────────────────────────────


def _send_telegram(message: str) -> bool:
    """Send message directly to Philip's Telegram chat via Bot API."""
    bot_token = os.environ.get("ROBOTHOR_TELEGRAM_BOT_TOKEN") or os.environ.get(
        "TELEGRAM_BOT_TOKEN", ""
    )
    chat_id = os.environ.get("ROBOTHOR_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.warning("buddy_watch: Telegram credentials not set")
        return False

    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("buddy_watch: Telegram send failed: %s", e)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point. Detect events, optionally call LLM, send to Telegram."""
    logging.basicConfig(level=logging.WARNING)

    state = _load_state()
    last_known_level = state.get("last_known_level", 1)

    events: list[dict[str, Any]] = []

    # ── 1. Detect all events (cheap DB queries) ───────────────────────────────

    # Agent crash loop
    if not _is_on_cooldown(state, "agent_crash_loop"):
        crashes = detect_agent_crash_loop()
        if crashes:
            events.append({"type": "agent_crash_loop", "data": crashes})

    # Streak warning
    if not _is_on_cooldown(state, "streak_warning"):
        sw = detect_streak_warning()
        if sw:
            events.append({"type": "streak_warning", "data": sw})

    # Level up
    if not _is_on_cooldown(state, "level_up"):
        lu = detect_level_up(last_known_level)
        if lu:
            events.append({"type": "level_up", "data": lu})

    # Fleet quiet
    if not _is_on_cooldown(state, "fleet_quiet"):
        fq = detect_fleet_quiet()
        if fq:
            events.append({"type": "fleet_quiet", "data": fq})

    # Score swing
    if not _is_on_cooldown(state, "score_swing"):
        swings = detect_score_swing()
        if swings:
            events.append({"type": "score_swing", "data": swings})

    # Streak milestone
    if not _is_on_cooldown(state, "streak_milestone"):
        sm = detect_streak_milestone()
        if sm:
            events.append({"type": "streak_milestone", "data": sm})

    # Self-improvement pipeline health — detect silent breakage
    if not _is_on_cooldown(state, "nightwatch_silent"):
        try:
            nw = detect_nightwatch_silent()
            if nw:
                events.append({"type": "nightwatch_silent", "data": nw})
        except Exception as e:
            logger.debug("buddy_watch: nightwatch_silent detector failed: %s", e)

    if not _is_on_cooldown(state, "autoresearcher_paused"):
        try:
            ap = detect_autoresearcher_paused()
            if ap:
                events.append({"type": "autoresearcher_paused", "data": ap})
        except Exception as e:
            logger.debug("buddy_watch: autoresearcher_paused detector failed: %s", e)

    if not _is_on_cooldown(state, "autoagent_init_hang"):
        try:
            ih = detect_autoagent_init_hang()
            if ih:
                events.append({"type": "autoagent_init_hang", "data": ih})
        except Exception as e:
            logger.debug("buddy_watch: autoagent_init_hang detector failed: %s", e)

    # ── 2. Nothing to say — exit silently ────────────────────────────────────
    if not events:
        return

    # ── 3. Call LLM — only now, only because we have something real ───────────
    message = _generate_message(events)
    if not message:
        return

    # ── 4. Send to Telegram ───────────────────────────────────────────────────
    sent = _send_telegram(f"🔥 *Buddy* — {message}")

    # ── 5. Update cooldowns + persist level ──────────────────────────────────
    if sent:
        for event in events:
            _set_cooldown(state, event["type"])

        # Persist latest known level so level_up doesn't re-fire
        for event in events:
            if event["type"] == "level_up":
                state["last_known_level"] = event["data"]["level"]

        _save_state(state)


if __name__ == "__main__":
    main()
