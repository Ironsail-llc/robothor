"""Tests for the in-conversation todo list system (Claude Code parity)."""

from __future__ import annotations

import pytest

from robothor.engine.todolist import TodoItem, TodoList

# ── Unit tests: TodoList data model ──


class TestTodoListValidation:
    def test_rejects_empty_list(self) -> None:
        error = TodoList.validate([])
        assert error is not None
        assert "empty" in error

    def test_rejects_multiple_in_progress(self) -> None:
        items = [
            TodoItem("A", "Doing A", "in_progress"),
            TodoItem("B", "Doing B", "in_progress"),
        ]
        error = TodoList.validate(items)
        assert error is not None
        assert "in_progress" in error

    def test_allows_one_in_progress(self) -> None:
        items = [
            TodoItem("A", "Doing A", "in_progress"),
            TodoItem("B", "Doing B", "pending"),
        ]
        assert TodoList.validate(items) is None

    def test_allows_zero_in_progress(self) -> None:
        items = [
            TodoItem("A", "Doing A", "pending"),
            TodoItem("B", "Doing B", "completed"),
        ]
        assert TodoList.validate(items) is None

    def test_rejects_empty_content(self) -> None:
        items = [TodoItem("", "Doing A", "pending")]
        error = TodoList.validate(items)
        assert error is not None
        assert "content" in error

    def test_rejects_whitespace_content(self) -> None:
        items = [TodoItem("   ", "Doing A", "pending")]
        error = TodoList.validate(items)
        assert error is not None
        assert "content" in error

    def test_rejects_empty_active_form(self) -> None:
        items = [TodoItem("A", "", "pending")]
        error = TodoList.validate(items)
        assert error is not None
        assert "active_form" in error

    def test_rejects_invalid_status(self) -> None:
        items = [TodoItem("A", "Doing A", "unknown")]
        error = TodoList.validate(items)
        assert error is not None
        assert "invalid status" in error


class TestTodoListReplace:
    def test_returns_old_and_new(self) -> None:
        tl = TodoList(items=[TodoItem("Old", "Working on Old", "in_progress")])
        result = tl.replace([TodoItem("New", "Working on New", "pending")])

        assert "error" not in result
        assert len(result["oldTodos"]) == 1
        assert result["oldTodos"][0]["content"] == "Old"
        assert len(result["newTodos"]) == 1
        assert result["newTodos"][0]["content"] == "New"

    def test_auto_clears_on_all_completed(self) -> None:
        tl = TodoList(
            items=[
                TodoItem("A", "Doing A", "in_progress"),
                TodoItem("B", "Doing B", "pending"),
            ]
        )
        result = tl.replace(
            [
                TodoItem("A", "Doing A", "completed"),
                TodoItem("B", "Doing B", "completed"),
            ]
        )

        assert "error" not in result
        assert tl.items == []
        assert len(result["newTodos"]) == 2
        assert all(t["status"] == "completed" for t in result["newTodos"])

    def test_does_not_clear_when_not_all_completed(self) -> None:
        tl = TodoList(items=[])
        tl.replace(
            [
                TodoItem("A", "Doing A", "completed"),
                TodoItem("B", "Doing B", "pending"),
            ]
        )
        assert len(tl.items) == 2

    def test_resets_turns_since_use(self) -> None:
        tl = TodoList(items=[])
        tl._turns_since_use = 15
        tl.replace([TodoItem("A", "Doing A", "pending")])
        assert tl._turns_since_use == 0

    def test_returns_error_on_invalid_input(self) -> None:
        tl = TodoList(items=[])
        result = tl.replace([TodoItem("", "X", "pending")])
        assert "error" in result


class TestVerificationNudge:
    def test_nudge_when_all_done_no_verify(self) -> None:
        tl = TodoList(items=[])
        result = tl.replace(
            [
                TodoItem("Fix bug", "Fixing bug", "completed"),
                TodoItem("Run tests", "Running tests", "completed"),
                TodoItem("Update docs", "Updating docs", "completed"),
            ]
        )
        assert result.get("verificationNudgeNeeded") is True

    def test_no_nudge_with_verify_item(self) -> None:
        tl = TodoList(items=[])
        result = tl.replace(
            [
                TodoItem("Fix bug", "Fixing bug", "completed"),
                TodoItem("Run tests", "Running tests", "completed"),
                TodoItem("Verify changes", "Verifying changes", "completed"),
            ]
        )
        assert result.get("verificationNudgeNeeded") is None

    def test_no_nudge_under_three_items(self) -> None:
        tl = TodoList(items=[])
        result = tl.replace(
            [
                TodoItem("Fix bug", "Fixing bug", "completed"),
                TodoItem("Run tests", "Running tests", "completed"),
            ]
        )
        assert result.get("verificationNudgeNeeded") is None

    def test_no_nudge_when_not_all_completed(self) -> None:
        tl = TodoList(items=[])
        result = tl.replace(
            [
                TodoItem("Fix bug", "Fixing bug", "completed"),
                TodoItem("Run tests", "Running tests", "completed"),
                TodoItem("Deploy", "Deploying", "pending"),
            ]
        )
        assert result.get("verificationNudgeNeeded") is None


class TestReminderInjection:
    def test_should_remind_after_interval(self) -> None:
        tl = TodoList(items=[TodoItem("A", "Doing A", "pending")])
        for _ in range(10):
            tl.record_turn(used_todo=False)
        assert tl.should_remind() is True

    def test_should_not_remind_before_interval(self) -> None:
        tl = TodoList(items=[TodoItem("A", "Doing A", "pending")])
        for _ in range(9):
            tl.record_turn(used_todo=False)
        assert tl.should_remind() is False

    def test_resets_on_use(self) -> None:
        tl = TodoList(items=[TodoItem("A", "Doing A", "pending")])
        for _ in range(8):
            tl.record_turn(used_todo=False)
        tl.record_turn(used_todo=True)
        assert tl._turns_since_use == 0
        assert tl.should_remind() is False

    def test_max_reminders(self) -> None:
        tl = TodoList(items=[TodoItem("A", "Doing A", "pending")])
        for _ in range(3):
            for _ in range(10):
                tl.record_turn(used_todo=False)
            assert tl.should_remind() is True
            tl.format_reminder()

        for _ in range(10):
            tl.record_turn(used_todo=False)
        assert tl.should_remind() is False

    def test_no_remind_when_empty(self) -> None:
        tl = TodoList(items=[])
        for _ in range(20):
            tl.record_turn(used_todo=False)
        assert tl.should_remind() is False

    def test_format_reminder_includes_items(self) -> None:
        tl = TodoList(items=[TodoItem("Fix bug", "Fixing bug", "in_progress")])
        tl._turns_since_use = 10
        reminder = tl.format_reminder()
        assert "Fix bug" in reminder
        assert "NEVER mention" in reminder


class TestDisplayFormatting:
    def test_format_for_telegram(self) -> None:
        tl = TodoList(
            items=[
                TodoItem("Fix bug", "Fixing bug", "completed"),
                TodoItem("Run tests", "Running tests", "in_progress"),
                TodoItem("Deploy", "Deploying", "pending"),
            ]
        )
        result = tl.format_for_telegram()
        assert "<b>Checklist:</b>" in result
        assert "\u2705" in result
        assert "\U0001f504" in result
        assert "\u2b1c" in result
        assert "<s>Fix bug</s>" in result
        assert "<b>Run tests</b>" in result

    def test_format_empty_returns_empty_string(self) -> None:
        tl = TodoList(items=[])
        assert tl.format_for_telegram() == ""

    def test_get_active_form(self) -> None:
        tl = TodoList(
            items=[
                TodoItem("A", "Doing A", "completed"),
                TodoItem("B", "Doing B", "in_progress"),
            ]
        )
        assert tl.get_active_form() == "Doing B"

    def test_get_active_form_none_when_no_in_progress(self) -> None:
        tl = TodoList(items=[TodoItem("A", "Doing A", "pending")])
        assert tl.get_active_form() is None

    def test_progress_summary(self) -> None:
        tl = TodoList(
            items=[
                TodoItem("A", "A", "completed"),
                TodoItem("B", "B", "completed"),
                TodoItem("C", "C", "pending"),
            ]
        )
        assert tl.progress_summary() == "2/3 done"


class TestSerialization:
    def test_to_dict_from_dict_roundtrip(self) -> None:
        original = TodoList(
            items=[
                TodoItem("Fix bug", "Fixing bug", "in_progress"),
                TodoItem("Run tests", "Running tests", "pending"),
            ]
        )
        original._turns_since_use = 5
        original._reminder_count = 1

        data = original.to_dict()
        restored = TodoList.from_dict(data)

        assert len(restored.items) == 2
        assert restored.items[0].content == "Fix bug"
        assert restored.items[0].status == "in_progress"
        assert restored.items[1].content == "Run tests"
        assert restored._turns_since_use == 5
        assert restored._reminder_count == 1

    def test_from_dict_handles_camel_case(self) -> None:
        restored = TodoList.from_dict(
            {
                "items": [
                    {"content": "A", "activeForm": "Doing A", "status": "pending"},
                ]
            }
        )
        assert restored.items[0].active_form == "Doing A"


class TestApplyResult:
    def test_apply_result_updates_items(self) -> None:
        tl = TodoList(items=[TodoItem("Old", "Working", "pending")])
        tl._turns_since_use = 10
        tl.apply_result(
            {
                "newTodos": [
                    {"content": "New", "active_form": "Working on New", "status": "in_progress"}
                ]
            }
        )
        assert len(tl.items) == 1
        assert tl.items[0].content == "New"
        assert tl._turns_since_use == 0

    def test_apply_result_clears_on_all_done(self) -> None:
        tl = TodoList(items=[TodoItem("A", "A", "pending")])
        tl.apply_result({"newTodos": [{"content": "A", "active_form": "A", "status": "completed"}]})
        assert tl.items == []


# ── Integration tests: Tool filtering ──


class TestToolFiltering:
    def test_todo_write_in_constants(self) -> None:
        from robothor.engine.tools.constants import TODO_TOOLS

        assert "todo_write" in TODO_TOOLS

    def test_todo_write_schema_registered(self) -> None:
        from robothor.engine.tools.schemas import get_engine_schemas

        schemas = get_engine_schemas()
        assert "todo_write" in schemas
        schema = schemas["todo_write"]
        assert schema["function"]["name"] == "todo_write"
        params = schema["function"]["parameters"]
        assert "todos" in params["properties"]
        items_props = params["properties"]["todos"]["items"]["properties"]
        assert "content" in items_props
        assert "active_form" in items_props
        assert "status" in items_props


# ── Integration tests: Handler ──


class TestTodoWriteHandler:
    @pytest.mark.asyncio
    async def test_handler_validates_and_returns(self) -> None:
        from robothor.engine.tools.dispatch import ToolContext
        from robothor.engine.tools.handlers.todolist import _todo_write

        ctx = ToolContext(agent_id="test", tenant_id="test")
        result = await _todo_write(
            {
                "todos": [
                    {"content": "A", "active_form": "Doing A", "status": "pending"},
                ]
            },
            ctx,
        )
        assert result.get("_needs_apply") is True
        assert len(result["_validated_items"]) == 1

    @pytest.mark.asyncio
    async def test_handler_rejects_invalid(self) -> None:
        from robothor.engine.tools.dispatch import ToolContext
        from robothor.engine.tools.handlers.todolist import _todo_write

        ctx = ToolContext(agent_id="test", tenant_id="test")
        result = await _todo_write({"todos": []}, ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_handler_rejects_empty_content(self) -> None:
        from robothor.engine.tools.dispatch import ToolContext
        from robothor.engine.tools.handlers.todolist import _todo_write

        ctx = ToolContext(agent_id="test", tenant_id="test")
        result = await _todo_write(
            {"todos": [{"content": "", "active_form": "X", "status": "pending"}]},
            ctx,
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_handler_rejects_multiple_in_progress(self) -> None:
        from robothor.engine.tools.dispatch import ToolContext
        from robothor.engine.tools.handlers.todolist import _todo_write

        ctx = ToolContext(agent_id="test", tenant_id="test")
        result = await _todo_write(
            {
                "todos": [
                    {"content": "A", "active_form": "X", "status": "in_progress"},
                    {"content": "B", "active_form": "Y", "status": "in_progress"},
                ]
            },
            ctx,
        )
        assert "error" in result


# ── Telegram rendering ──


class TestTelegramRendering:
    def test_format_checklist_html(self) -> None:
        from robothor.engine.telegram import _format_checklist_html

        todos = [
            {"content": "Fix bug", "status": "completed"},
            {"content": "Run tests", "status": "in_progress"},
            {"content": "Deploy", "status": "pending"},
        ]
        result = _format_checklist_html(todos)
        assert "<b>Checklist:</b>" in result
        assert "<s>Fix bug</s>" in result
        assert "<b>Run tests</b>" in result
        assert "Deploy" in result

    def test_escapes_html(self) -> None:
        from robothor.engine.telegram import _format_checklist_html

        todos = [{"content": "<script>alert('xss')</script>", "status": "pending"}]
        result = _format_checklist_html(todos)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
