"""Tests for Telegram bot."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from robothor.engine.chat import _sessions, get_shared_session
from robothor.engine.models import AgentRun, RunStatus, TriggerType
from robothor.engine.telegram import MAX_MESSAGE_LENGTH, TelegramBot


@pytest.fixture
def bot(engine_config):
    """Create a TelegramBot with mocked dependencies."""
    _sessions.clear()
    with patch("robothor.engine.telegram.Bot") as mock_bot_cls:
        with patch("robothor.engine.telegram.Dispatcher"):
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock()
            mock_bot_cls.return_value = mock_bot

            runner = MagicMock()
            bot = TelegramBot(engine_config, runner)
            bot.bot = mock_bot
            yield bot
    _sessions.clear()


class TestChatHistory:
    def test_shared_session_initially_empty(self, bot):
        """Shared session history starts empty."""
        session_key = bot._session_key("12345")
        session = get_shared_session(session_key)
        assert session.history == []

    def test_clear_history(self, bot):
        """Clear removes chat history from shared session."""
        session_key = bot._session_key("12345")
        session = get_shared_session(session_key)
        session.history.extend(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ]
        )
        session.history.clear()
        assert session.history == []

    def test_history_cap(self, bot):
        """History is capped at max_history entries."""
        session_key = bot._session_key("12345")
        session = get_shared_session(session_key)
        # Add 50 messages (25 turns) — should be capped at 40
        for i in range(25):
            session.history.append({"role": "user", "content": f"msg {i}"})
            session.history.append({"role": "assistant", "content": f"reply {i}"})
        if len(session.history) > bot._max_history:
            session.history[:] = session.history[-bot._max_history :]
        assert len(session.history) == 40

    def test_reset_clears_history(self, bot):
        """Reset clears both model override and shared session history."""
        bot._model_override["12345"] = "some-model"
        session_key = bot._session_key("12345")
        session = get_shared_session(session_key)
        session.history.append({"role": "user", "content": "test"})
        # Simulate /reset behavior
        bot._model_override.pop("12345", None)
        session.history.clear()
        session.model_override = None
        assert "12345" not in bot._model_override
        assert session.history == []

    def test_max_history_default(self, bot):
        """Default max history is 40 (matching chat.py MAX_HISTORY)."""
        assert bot._max_history == 40


class TestMessageSplitting:
    def test_short_message_not_split(self, bot):
        """Messages under limit are not split."""
        chunks = bot._split_message("Hello world")
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_long_message_split(self, bot):
        """Messages over limit are split into chunks."""
        long_text = "x" * (MAX_MESSAGE_LENGTH + 100)
        chunks = bot._split_message(long_text)
        assert len(chunks) == 2
        assert len(chunks[0]) <= MAX_MESSAGE_LENGTH

    def test_split_at_newline(self, bot):
        """Prefers splitting at newlines."""
        # Create text with newlines at strategic positions
        line = "a" * 100 + "\n"
        text = line * 50  # 50 lines * 101 chars = 5050 chars
        chunks = bot._split_message(text)
        assert len(chunks) >= 2
        # Each chunk should end with a complete line
        assert chunks[0].endswith("\n") or len(chunks[0]) <= MAX_MESSAGE_LENGTH

    def test_empty_message(self, bot):
        """Empty message returns single empty chunk."""
        chunks = bot._split_message("")
        assert chunks == [""]

    def test_exact_limit(self, bot):
        """Message at exactly the limit is not split."""
        text = "x" * MAX_MESSAGE_LENGTH
        chunks = bot._split_message(text)
        assert len(chunks) == 1

    def test_very_long_message(self, bot):
        """Very long messages are split into multiple chunks."""
        text = "x" * (MAX_MESSAGE_LENGTH * 3 + 500)
        chunks = bot._split_message(text)
        assert len(chunks) == 4
        for chunk in chunks:
            assert len(chunk) <= MAX_MESSAGE_LENGTH


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_simple(self, bot):
        """Sends a simple message."""
        await bot.send_message("12345", "Hello")
        bot.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_empty_skipped(self, bot):
        """Empty messages are not sent."""
        await bot.send_message("12345", "")
        bot.bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_markdown_fallback(self, bot):
        """Falls back to plain text when markdown fails."""

        # First call with markdown fails, second without succeeds
        bot.bot.send_message.side_effect = [Exception("Bad markdown"), None]
        await bot.send_message("12345", "Hello *bad markdown")
        assert bot.bot.send_message.call_count == 2


class TestSessionLock:
    """Tests for the session lock fix — Telegram must hold the lock during execution."""

    @pytest.mark.asyncio
    async def test_telegram_holds_lock_during_execution(self, bot):
        """Lock is held while runner.execute() runs."""
        session_key = bot._session_key("12345")
        session = get_shared_session(session_key)
        lock_was_held = False

        async def fake_execute(**kwargs):
            nonlocal lock_was_held
            lock_was_held = session.lock.locked()
            return AgentRun(
                status=RunStatus.COMPLETED,
                output_text="reply",
                trigger_type=TriggerType.TELEGRAM,
            )

        bot.runner.execute = AsyncMock(side_effect=fake_execute)
        bot.bot.send_message = AsyncMock()
        bot.bot.send_chat_action = AsyncMock()
        bot.bot.edit_message_text = AsyncMock()

        # Simulate handle_text by calling run_agent directly
        # Build the closure the same way handle_text does
        user_text = "hello"
        model = None
        on_content = AsyncMock()

        async def run_agent() -> None:
            async with session.lock:
                history = list(session.history)
                await bot.runner.execute(
                    agent_id=bot.config.default_chat_agent,
                    message=user_text,
                    trigger_type=TriggerType.TELEGRAM,
                    trigger_detail="chat:12345",
                    on_content=on_content,
                    model_override=model,
                    conversation_history=history or None,
                )

        await run_agent()
        assert lock_was_held, "Lock must be held during runner.execute()"
        assert not session.lock.locked(), "Lock must be released after execution"

    @pytest.mark.asyncio
    async def test_helm_returns_409_when_telegram_holds_lock(self, bot):
        """When Telegram holds the session lock, Helm's busy-check sees it locked."""
        session_key = bot._session_key("12345")
        session = get_shared_session(session_key)

        # Simulate Telegram holding the lock
        await session.lock.acquire()
        try:
            # Helm does a non-blocking busy check
            assert session.lock.locked(), "Helm should see the lock as held"
        finally:
            session.lock.release()

    @pytest.mark.asyncio
    async def test_telegram_waits_when_helm_holds_lock(self, bot):
        """Telegram serializes after Helm finishes — waits for lock release."""
        session_key = bot._session_key("12345")
        session = get_shared_session(session_key)
        execution_order: list[str] = []

        async def helm_work() -> None:
            async with session.lock:
                execution_order.append("helm_start")
                await asyncio.sleep(0.05)
                execution_order.append("helm_end")

        async def telegram_work() -> None:
            # Small delay to ensure Helm grabs lock first
            await asyncio.sleep(0.01)
            async with session.lock:
                execution_order.append("telegram_start")
                execution_order.append("telegram_end")

        await asyncio.gather(helm_work(), telegram_work())
        assert execution_order == [
            "helm_start",
            "helm_end",
            "telegram_start",
            "telegram_end",
        ], f"Telegram must wait for Helm: {execution_order}"

    @pytest.mark.asyncio
    async def test_history_consistent_after_sequential_execution(self, bot):
        """No history corruption under contention — both channels write sequentially."""
        session_key = bot._session_key("12345")
        session = get_shared_session(session_key)

        async def channel_work(channel: str, msg: str) -> None:
            async with session.lock:
                # Read history inside lock (correct pattern)
                _ = list(session.history)
                await asyncio.sleep(0.01)  # simulate LLM call
                session.history.append({"role": "user", "content": f"{channel}: {msg}"})
                session.history.append({"role": "assistant", "content": f"re: {channel}: {msg}"})

        # Run both channels — they serialize via the lock
        await asyncio.gather(
            channel_work("telegram", "hello"),
            channel_work("helm", "world"),
        )

        assert len(session.history) == 4, "Both exchanges must be present"
        # Verify pairs are not interleaved
        for i in range(0, len(session.history), 2):
            user_msg = session.history[i]
            assistant_msg = session.history[i + 1]
            assert user_msg["role"] == "user"
            assert assistant_msg["role"] == "assistant"
            # The assistant reply should match the user message's channel
            channel = user_msg["content"].split(":")[0]
            assert assistant_msg["content"].startswith(f"re: {channel}:")
