"""Tests for preference tracking with drift detection."""

from __future__ import annotations

import json
from unittest.mock import patch

from robothor.memory.preferences import (
    _format_summary,
    _match_existing,
    get_stale_preferences,
)


class TestMatchExisting:
    def test_no_match_returns_none(self):
        prefs = [{"preference": "Prefers dark mode"}]
        assert _match_existing(prefs, "Enjoys peanut butter") is None

    def test_exact_match(self):
        prefs = [{"preference": "Prefers dark mode"}]
        assert _match_existing(prefs, "prefers dark mode") is not None

    def test_substring_match(self):
        prefs = [{"preference": "Prefers dark mode"}]
        # New phrasing contains the existing one
        assert _match_existing(prefs, "Prefers dark mode over light") is not None


class TestFormatSummary:
    def test_empty_preferences(self):
        assert _format_summary([]).startswith("No tracked")

    def test_orders_by_confidence(self):
        prefs = [
            {"preference": "Low conf pref", "confidence": 0.3},
            {"preference": "High conf pref", "confidence": 0.9},
        ]
        summary = _format_summary(prefs)
        assert summary.index("High conf pref") < summary.index("Low conf pref")

    def test_stale_marker(self):
        prefs = [{"preference": "Stale thing", "confidence": 0.5, "stale": True}]
        assert "[STALE]" in _format_summary(prefs)


class TestStaleReadback:
    """get_stale_preferences should return only stale entries from the block."""

    def test_returns_only_stale(self):
        fake_block = {
            "content": json.dumps(
                {
                    "preferences": [
                        {"preference": "A", "stale": False},
                        {"preference": "B", "stale": True},
                        {"preference": "C"},  # missing → treat as not stale
                    ]
                }
            )
        }
        with patch("robothor.memory.preferences.read_block", return_value=fake_block):
            result = get_stale_preferences(tenant_id="test")
        assert [p["preference"] for p in result] == ["B"]


class TestPersistenceRoundtrip:
    """_load_preferences + _save_preferences handles empty/corrupt block gracefully."""

    def test_load_empty_block(self):
        from robothor.memory.preferences import _load_preferences

        with patch("robothor.memory.preferences.read_block", return_value={"content": ""}):
            assert _load_preferences("test") == []

    def test_load_corrupt_block(self):
        from robothor.memory.preferences import _load_preferences

        with patch(
            "robothor.memory.preferences.read_block",
            return_value={"content": "not json"},
        ):
            assert _load_preferences("test") == []
