"""Tests for the dedup module — cross-trigger agent deduplication."""

from robothor.engine.dedup import clear, is_running, release, running_agents, try_acquire


class TestDedup:
    def setup_method(self):
        clear()

    def teardown_method(self):
        clear()

    def test_acquire_succeeds(self):
        assert try_acquire("agent-1") is True
        assert is_running("agent-1") is True

    def test_duplicate_blocked(self):
        assert try_acquire("agent-1") is True
        assert try_acquire("agent-1") is False

    def test_release_allows_reacquire(self):
        assert try_acquire("agent-1") is True
        release("agent-1")
        assert is_running("agent-1") is False
        assert try_acquire("agent-1") is True

    def test_running_agents_returns_copy(self):
        try_acquire("a")
        try_acquire("b")
        agents = running_agents()
        assert agents == {"a", "b"}
        # Modifying the copy doesn't affect the original
        agents.add("c")
        assert "c" not in running_agents()

    def test_release_nonexistent_no_error(self):
        release("nonexistent")  # should not raise

    def test_multiple_agents_independent(self):
        assert try_acquire("agent-1") is True
        assert try_acquire("agent-2") is True
        assert is_running("agent-1") is True
        assert is_running("agent-2") is True
        release("agent-1")
        assert is_running("agent-1") is False
        assert is_running("agent-2") is True
