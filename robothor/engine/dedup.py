"""
Cross-trigger dedup — prevents concurrent runs of the same agent.

Uses a module-level set (safe since asyncio is single-threaded).
Shared between scheduler and hooks so both respect the same lock.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_running: set[str] = set()


def try_acquire(agent_id: str) -> bool:
    """Attempt to acquire the agent lock. Returns True if acquired."""
    if agent_id in _running:
        logger.debug("Dedup: %s already running, skipping", agent_id)
        return False
    _running.add(agent_id)
    return True


def release(agent_id: str) -> None:
    """Release the agent lock."""
    _running.discard(agent_id)


def is_running(agent_id: str) -> bool:
    """Check if an agent is currently running."""
    return agent_id in _running


def running_agents() -> set[str]:
    """Return a copy of the currently running agent IDs."""
    return _running.copy()


def clear() -> None:
    """Clear all locks. Only for testing."""
    _running.clear()
