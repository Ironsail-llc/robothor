"""Tests for verbatim chat embedding (chat_store additions)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from robothor.engine.chat_store import (
    _embed_turns,
    search_chat_turns,
)


class TestEmbedTurns:
    @pytest.mark.asyncio
    async def test_skips_when_no_message_ids(self):
        # Should not raise or attempt any work
        await _embed_turns([], [])

    @pytest.mark.asyncio
    async def test_handles_embedding_failure(self, monkeypatch):
        from robothor.llm import ollama as llm_client

        async def _boom(texts):
            raise RuntimeError("ollama down")

        monkeypatch.setattr(llm_client, "get_embeddings_batch_async", _boom)
        # Should swallow and return without raising
        await _embed_turns([1, 2], ["hello", "world"])

    @pytest.mark.asyncio
    async def test_persists_successful_embeddings(self, monkeypatch):
        from robothor.llm import ollama as llm_client

        async def _fake_embed(texts):
            return [[0.1] * 1024 for _ in texts]

        monkeypatch.setattr(llm_client, "get_embeddings_batch_async", _fake_embed)

        captured = []

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql, params):
                captured.append((sql, params))

            def cursor(self, *a, **kw):
                return self

        class FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def cursor(self, *a, **kw):
                return FakeCursor()

            def commit(self):
                pass

        with patch("robothor.engine.chat_store.get_connection", return_value=FakeConn()):
            await _embed_turns([101, 102], ["user says", "assistant says"])

        # Expect 2 UPDATEs (one per message id)
        assert len(captured) == 2
        assert captured[0][1][1] == 101
        assert captured[1][1][1] == 102


class TestSearchChatTurnsDAL:
    """Unit test for result shaping — no DB required."""

    def test_shapes_results(self):
        fake_rows = [
            {
                "id": 1,
                "message": {"role": "user", "content": "Hello?"},
                "created_at": None,
                "session_key": "s1",
                "similarity": 0.7,
            }
        ]

        class FakeCursor:
            def __init__(self, rows):
                self._rows = rows

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def execute(self, *a, **k):
                pass

            def fetchall(self):
                return self._rows

        class FakeConn:
            def __init__(self, rows):
                self._rows = rows

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def cursor(self, *a, **k):
                return FakeCursor(self._rows)

        with patch(
            "robothor.engine.chat_store.get_connection",
            return_value=FakeConn(fake_rows),
        ):
            results = search_chat_turns([0.0] * 1024, limit=5, tenant_id="test")

        assert len(results) == 1
        r = results[0]
        assert r["role"] == "user"
        assert r["content"] == "Hello?"
        assert r["source"] == "chat_turn"
        assert r["session_key"] == "s1"
