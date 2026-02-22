"""Tests for robothor.memory.blocks — agent memory block operations."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from robothor.memory.blocks import list_blocks, read_block, write_block


class TestReadBlock:
    def test_read_existing_block(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ("block content", datetime(2026, 1, 1, 12, 0))
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("robothor.memory.blocks.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
            result = read_block("persona")

        assert result["block_name"] == "persona"
        assert result["content"] == "block content"
        assert result["last_written_at"] == "2026-01-01T12:00:00"

    def test_read_missing_block(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("robothor.memory.blocks.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
            result = read_block("nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    def test_read_empty_name(self):
        result = read_block("")
        assert "error" in result
        assert "required" in result["error"]

    def test_read_updates_read_count(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = ("content", datetime(2026, 1, 1))
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("robothor.memory.blocks.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
            read_block("persona")

        sql = mock_cur.execute.call_args[0][0]
        assert "read_count" in sql
        assert "last_read_at" in sql


class TestWriteBlock:
    def test_write_block_success(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("robothor.memory.blocks.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
            result = write_block("persona", "new content")

        assert result["success"] is True
        assert result["block_name"] == "persona"

    def test_write_empty_name(self):
        result = write_block("", "content")
        assert "error" in result
        assert "required" in result["error"]

    def test_write_uses_upsert(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("robothor.memory.blocks.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
            write_block("test", "content")

        sql = mock_cur.execute.call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "write_count" in sql


class TestListBlocks:
    def test_list_blocks_returns_all(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            ("persona", 150, datetime(2026, 1, 1, 12, 0)),
            ("working_context", 300, datetime(2026, 1, 2, 8, 0)),
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("robothor.memory.blocks.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
            result = list_blocks()

        assert "blocks" in result
        assert len(result["blocks"]) == 2
        assert result["blocks"][0]["name"] == "persona"
        assert result["blocks"][0]["size"] == 150
        assert result["blocks"][1]["name"] == "working_context"

    def test_list_blocks_empty(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("robothor.memory.blocks.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
            result = list_blocks()

        assert result["blocks"] == []

    def test_list_blocks_null_timestamp(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [("test_block", 0, None)]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("robothor.memory.blocks.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
            result = list_blocks()

        assert result["blocks"][0]["last_written_at"] is None
