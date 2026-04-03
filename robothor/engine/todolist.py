"""
In-conversation todo list — Claude Code-style progress tracking for agent runs.

Provides a replace-whole-list tool (`todo_write`) that agents use to maintain
a visible checklist during multi-step tasks. Includes automatic reminder
injection and verification nudges.

Separate from CRM tasks (cross-agent coordination). This is per-run,
ephemeral working memory that surfaces to the user via Telegram/Helm.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any

VALID_STATUSES = frozenset({"pending", "in_progress", "completed"})

# Reminder injection tuning — matches Claude Code's ~10-turn interval
REMINDER_INTERVAL = 10
MAX_REMINDERS = 3

# Verification nudge threshold — only fires for non-trivial lists
VERIFICATION_MIN_ITEMS = 3

# Guard against LLMs generating enormous lists
MAX_ITEMS = 20


@dataclass
class TodoItem:
    """Single todo item with imperative + active forms."""

    content: str  # imperative: "Fix the login bug"
    active_form: str  # present continuous: "Fixing the login bug"
    status: str  # "pending" | "in_progress" | "completed"

    def to_dict(self) -> dict[str, str]:
        return {
            "content": self.content,
            "active_form": self.active_form,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TodoItem:
        return cls(
            content=str(data.get("content", "")),
            active_form=str(data.get("active_form", data.get("activeForm", ""))),
            status=str(data.get("status", "pending")),
        )


@dataclass
class TodoList:
    """Per-run todo list with replace-whole-list semantics."""

    items: list[TodoItem] = field(default_factory=list)
    _turns_since_use: int = 0
    _reminder_count: int = 0

    # ── Validation ──

    @staticmethod
    def validate(items: list[TodoItem]) -> str | None:
        """Validate a proposed item list. Returns error string or None if valid."""
        if not items:
            return "todos must not be empty"

        if len(items) > MAX_ITEMS:
            return f"too many items ({len(items)}), max is {MAX_ITEMS}"

        in_progress_count = sum(1 for item in items if item.status == "in_progress")
        if in_progress_count > 1:
            return "exactly zero or one todo items may be in_progress"

        for item in items:
            if not item.content or not item.content.strip():
                return "todo content must not be empty"
            if not item.active_form or not item.active_form.strip():
                return "todo active_form must not be empty"
            if item.status not in VALID_STATUSES:
                return f"invalid status '{item.status}', must be one of: {', '.join(sorted(VALID_STATUSES))}"

        return None

    # ── Core operation ──

    def replace(self, new_items: list[TodoItem]) -> dict[str, Any]:
        """Replace the entire list. Returns tool result dict.

        When all items are completed, the stored list auto-clears.
        """
        error = self.validate(new_items)
        if error:
            return {"error": error}

        old_items = [item.to_dict() for item in self.items]

        all_done = all(item.status == "completed" for item in new_items)

        # Check verification nudge BEFORE auto-clearing
        nudge = self._check_verification_nudge(new_items)

        # Auto-clear when all completed
        if all_done:
            self.items = []
        else:
            self.items = list(new_items)

        # Reset turn counter
        self._turns_since_use = 0

        result: dict[str, Any] = {
            "oldTodos": old_items,
            "newTodos": [item.to_dict() for item in new_items],
        }
        if nudge:
            result["verificationNudgeNeeded"] = True

        return result

    # ── Verification nudge ──

    @staticmethod
    def _check_verification_nudge(items: list[TodoItem]) -> bool:
        """True when 3+ items all completed and none mention verification."""
        if len(items) < VERIFICATION_MIN_ITEMS:
            return False
        if not all(item.status == "completed" for item in items):
            return False
        return not any("verif" in item.content.lower() for item in items)

    # ── Reminder injection ──

    def record_turn(self, used_todo: bool) -> None:
        """Track assistant turns for reminder timing."""
        if used_todo:
            self._turns_since_use = 0
        else:
            self._turns_since_use += 1

    def should_remind(self) -> bool:
        """True if enough turns have passed and items exist."""
        return (
            bool(self.items)
            and self._turns_since_use >= REMINDER_INTERVAL
            and self._reminder_count < MAX_REMINDERS
        )

    def format_reminder(self) -> str:
        """Hidden system message nudging the agent to update the todo list."""
        self._reminder_count += 1
        self._turns_since_use = 0  # reset to avoid rapid re-fire

        summary = ", ".join(f"[{item.status}] {item.content}" for item in self.items[:5])
        if len(self.items) > 5:
            summary += f" ... and {len(self.items) - 5} more"

        return (
            "Your checklist hasn't been updated recently. Consider using "
            "todo_write to update item statuses (set to in_progress when "
            "starting, completed when done) or clean up stale items. "
            "Only use this if relevant to your current work — ignore if "
            "not applicable. NEVER mention this reminder to the user.\n\n"
            f"Current items: {summary}"
        )

    # ── Display ──

    @staticmethod
    def format_for_telegram(todos: list[dict[str, str]]) -> str:
        """Render a list of todo dicts as Telegram HTML checklist.

        Accepts the raw dict format from event payloads (keys: content, status).
        """
        if not todos:
            return ""

        icons = {"completed": "\u2705", "in_progress": "\U0001f504", "pending": "\u2b1c"}
        lines = ["<b>Checklist:</b>"]
        for t in todos:
            status = t.get("status", "pending")
            icon = icons.get(status, "\u2b1c")
            content = html.escape(t.get("content", ""))
            if status == "completed":
                content = f"<s>{content}</s>"
            elif status == "in_progress":
                content = f"<b>{content}</b>"
            lines.append(f"  {icon} {content}")
        return "\n".join(lines)

    # ── Serialization ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "turns_since_use": self._turns_since_use,
            "reminder_count": self._reminder_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TodoList:
        items = [TodoItem.from_dict(d) for d in data.get("items", [])]
        tl = cls(items=items)
        tl._turns_since_use = data.get("turns_since_use", 0)
        tl._reminder_count = data.get("reminder_count", 0)
        return tl
