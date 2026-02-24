"""Agent status routes — health tiers and cron job monitoring."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agents"])

# Cache for agent status (30s TTL)
_cache: dict = {"data": None, "expires": 0.0}
CACHE_TTL = 30

# Paths (overridable via env for testability)
JOBS_JSON_PATH = os.getenv(
    "OPENCLAW_JOBS_JSON",
    os.path.expanduser("~/.openclaw/cron/jobs.json"),
)
STATUS_DIR = os.getenv(
    "AGENT_STATUS_DIR",
    os.path.expanduser("~/clawd/memory"),
)

# Schedule-aware thresholds (seconds): yellow at 1.5x, red at 2x
SCHEDULE_INTERVALS: dict[str, int] = {
    "*/10": 600,
    "*/15": 900,
    "*/17": 1020,
    "*/30": 1800,
    "0": 3600,      # hourly
    "30": 3600,      # hourly at :30
    "45": 3600,      # hourly at :45
}


def _parse_interval_seconds(cron_expr: str) -> int:
    """Estimate interval in seconds from a cron expression."""
    parts = cron_expr.split()
    if len(parts) < 5:
        return 3600
    minute = parts[0]
    hour = parts[1]

    # */N minute interval
    if minute.startswith("*/"):
        try:
            return int(minute[2:]) * 60
        except ValueError:
            pass

    # Every N hours (e.g., */2 or 6-22/2)
    if hour.startswith("*/"):
        try:
            return int(hour[2:]) * 3600
        except ValueError:
            pass
    if "/" in hour:
        # Range with step like "6-22/2"
        try:
            step = int(hour.split("/")[1])
            return step * 3600
        except (ValueError, IndexError):
            pass

    # Specific comma-separated hours (e.g., "10,18")
    if "," in hour:
        hours = [int(h) for h in hour.split(",") if h.isdigit()]
        if len(hours) >= 2:
            diffs = [hours[i + 1] - hours[i] for i in range(len(hours) - 1)]
            avg_gap = sum(diffs) / len(diffs)
            return int(avg_gap * 3600)

    # Range-based hourly (e.g., "6-22" means once per hour within range)
    if "-" in hour and minute.isdigit():
        return 3600

    # Single specific hour (e.g., "30 6 * * *" = daily at 06:30)
    if minute.isdigit() and hour.isdigit():
        return 86400  # daily

    # Single minute value with range hours → hourly
    if minute.isdigit():
        return 3600

    return 3600  # default hourly


def _compute_health_tier(
    last_run_ts: float | None,
    interval_s: int,
    consecutive_errors: int,
    enabled: bool,
    run_count: int,
) -> str:
    """Compute health tier: healthy, degraded, failed, unknown."""
    if not enabled:
        return "unknown"
    if run_count < 3:
        return "unknown"
    if consecutive_errors >= 2:
        return "failed"

    if last_run_ts is None:
        return "unknown"

    age = time.time() - last_run_ts
    yellow_threshold = interval_s * 1.5
    red_threshold = interval_s * 2.0

    if age > red_threshold:
        return "failed"
    if age > yellow_threshold or consecutive_errors >= 1:
        return "degraded"
    return "healthy"


def _read_status_file(name: str) -> str | None:
    """Read a status markdown file, returning its content or None."""
    status_file = Path(STATUS_DIR) / f"{name}-status.md"
    try:
        if status_file.exists():
            content = status_file.read_text(encoding="utf-8").strip()
            # Return first 200 chars as summary
            return content[:200] if content else None
    except Exception as e:
        logger.debug("Failed to read status file %s: %s", status_file, e)
    return None


def _build_agent_status() -> dict:
    """Build agent status from jobs.json and status files."""
    agents: list[dict] = []
    summary = {"healthy": 0, "degraded": 0, "failed": 0, "unknown": 0, "total": 0}

    # Read jobs.json
    jobs: list[dict] = []
    try:
        jobs_path = Path(JOBS_JSON_PATH)
        if jobs_path.exists():
            with open(jobs_path) as f:
                data = json.load(f)
                jobs = data if isinstance(data, list) else data.get("jobs", [])
    except Exception as e:
        logger.warning("Failed to read jobs.json: %s", e)

    for job in jobs:
        name = job.get("name", "unknown")
        schedule_raw = job.get("schedule", "")
        enabled = job.get("enabled", True)

        # Schedule can be a dict {"kind":"cron","expr":"..."} or a string
        if isinstance(schedule_raw, dict):
            cron_expr = schedule_raw.get("expr", "")
            schedule_display = cron_expr
        else:
            cron_expr = str(schedule_raw)
            schedule_display = cron_expr

        interval_s = _parse_interval_seconds(cron_expr)

        # State is nested under "state" key
        state = job.get("state", {})
        last_run_ms = state.get("lastRunAtMs")
        last_run_ts = None
        last_run_str = None
        if last_run_ms:
            last_run_ts = last_run_ms / 1000.0
            last_run_str = datetime.fromtimestamp(last_run_ts, tz=timezone.utc).isoformat()

        last_duration = state.get("lastDurationMs")
        consecutive_errors = state.get("consecutiveErrors", 0)
        run_count = 10  # assume sufficient runs if not tracked

        tier = _compute_health_tier(last_run_ts, interval_s, consecutive_errors, enabled, run_count)
        summary[tier] = summary.get(tier, 0) + 1
        summary["total"] += 1

        # Read status file for summary text (use slug from job name)
        name_slug = name.lower().replace(" ", "-")
        status_summary = _read_status_file(name_slug)

        agents.append({
            "name": name,
            "schedule": schedule_display,
            "lastRun": last_run_str,
            "lastDuration": last_duration,
            "status": tier,
            "statusSummary": status_summary,
            "errorCount": consecutive_errors,
            "enabled": enabled,
        })

    return {"agents": agents, "summary": summary}


@router.get("/agents/status")
async def api_agent_status():
    """Get status of all agent cron jobs with health tiers."""
    now = time.time()
    if _cache["data"] and now < _cache["expires"]:
        return _cache["data"]

    result = _build_agent_status()
    _cache["data"] = result
    _cache["expires"] = now + CACHE_TTL
    return result
