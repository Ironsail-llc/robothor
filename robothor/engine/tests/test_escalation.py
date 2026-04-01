"""Tests for graduated escalation."""

from __future__ import annotations

import pytest

from robothor.engine.escalation import (
    HARD_ABORT_TOTAL_ERRORS,
    THRESHOLD_DIFFERENT_STRATEGY,
    THRESHOLD_REDUCE_SCOPE,
    THRESHOLD_STOP,
    EscalationManager,
)
from robothor.engine.models import ErrorType


class TestEscalationManager:
    def test_no_escalation_below_threshold(self):
        mgr = EscalationManager()
        mgr.record_error()
        mgr.record_error()
        assert mgr.get_escalation_message() is None

    def test_different_strategy_at_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert msg is not None
        assert "DIFFERENT" in msg.upper()

    def test_reduce_scope_at_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_REDUCE_SCOPE):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert msg is not None
        assert "REDUCE SCOPE" in msg.upper()

    def test_stop_at_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert msg is not None
        assert "STOP" in msg.upper()

    def test_stop_only_issued_once(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        msg1 = mgr.get_escalation_message()
        assert msg1 is not None
        assert "STOP" in msg1.upper()

        mgr.record_error()
        msg2 = mgr.get_escalation_message()
        # After stop is issued once, no more stop messages
        assert msg2 is None or "STOP" not in msg2.upper()

    def test_success_resets_consecutive(self):
        mgr = EscalationManager()
        mgr.record_error()
        mgr.record_error()
        mgr.record_success()
        assert mgr.consecutive_errors == 0
        assert mgr.total_errors == 2  # total doesn't reset

    def test_should_abort_at_hard_ceiling(self):
        mgr = EscalationManager()
        for _ in range(HARD_ABORT_TOTAL_ERRORS):
            mgr.record_error()
        assert mgr.should_abort() is True

    def test_should_not_abort_below_ceiling(self):
        mgr = EscalationManager()
        for _ in range(HARD_ABORT_TOTAL_ERRORS - 1):
            mgr.record_error()
        assert mgr.should_abort() is False


class TestEscalationManagerInitialState:
    """Verify the default state of a freshly created manager."""

    def test_initial_counters_are_zero(self):
        mgr = EscalationManager()
        assert mgr.consecutive_errors == 0
        assert mgr.total_errors == 0

    def test_initial_stop_not_issued(self):
        mgr = EscalationManager()
        assert mgr._stop_issued is False

    def test_initial_last_error_type(self):
        mgr = EscalationManager()
        assert mgr._last_error_type == ErrorType.UNKNOWN

    def test_initial_error_type_counts_empty(self):
        mgr = EscalationManager()
        assert mgr._error_type_counts == {}

    def test_no_escalation_with_zero_errors(self):
        mgr = EscalationManager()
        assert mgr.get_escalation_message() is None

    def test_should_not_abort_with_zero_errors(self):
        mgr = EscalationManager()
        assert mgr.should_abort() is False

    def test_not_at_change_strategy_threshold_initially(self):
        mgr = EscalationManager()
        assert mgr.at_change_strategy_threshold is False


class TestRecordErrorWithTypes:
    """Test error type tracking in record_error."""

    def test_error_type_stored_as_last(self):
        mgr = EscalationManager()
        mgr.record_error(ErrorType.AUTH)
        assert mgr._last_error_type == ErrorType.AUTH

    def test_last_error_type_updates_on_each_call(self):
        mgr = EscalationManager()
        mgr.record_error(ErrorType.AUTH)
        mgr.record_error(ErrorType.RATE_LIMIT)
        assert mgr._last_error_type == ErrorType.RATE_LIMIT

    def test_error_type_counts_single_type(self):
        mgr = EscalationManager()
        mgr.record_error(ErrorType.TIMEOUT)
        mgr.record_error(ErrorType.TIMEOUT)
        mgr.record_error(ErrorType.TIMEOUT)
        assert mgr._error_type_counts[ErrorType.TIMEOUT] == 3

    def test_error_type_counts_multiple_types(self):
        mgr = EscalationManager()
        mgr.record_error(ErrorType.AUTH)
        mgr.record_error(ErrorType.RATE_LIMIT)
        mgr.record_error(ErrorType.AUTH)
        mgr.record_error(ErrorType.NOT_FOUND)
        assert mgr._error_type_counts == {
            ErrorType.AUTH: 2,
            ErrorType.RATE_LIMIT: 1,
            ErrorType.NOT_FOUND: 1,
        }

    def test_default_error_type_is_unknown(self):
        mgr = EscalationManager()
        mgr.record_error()
        assert mgr._last_error_type == ErrorType.UNKNOWN
        assert mgr._error_type_counts[ErrorType.UNKNOWN] == 1

    @pytest.mark.parametrize("error_type", list(ErrorType))
    def test_all_error_types_tracked(self, error_type: ErrorType):
        mgr = EscalationManager()
        mgr.record_error(error_type)
        assert mgr._last_error_type == error_type
        assert mgr._error_type_counts[error_type] == 1
        assert mgr.total_errors == 1
        assert mgr.consecutive_errors == 1


class TestAtChangeStrategyThreshold:
    """Test the at_change_strategy_threshold property."""

    def test_false_below_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY - 1):
            mgr.record_error()
        assert mgr.at_change_strategy_threshold is False

    def test_true_at_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY):
            mgr.record_error()
        assert mgr.at_change_strategy_threshold is True

    def test_true_above_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY + 2):
            mgr.record_error()
        assert mgr.at_change_strategy_threshold is True

    def test_resets_after_success(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY):
            mgr.record_error()
        assert mgr.at_change_strategy_threshold is True
        mgr.record_success()
        assert mgr.at_change_strategy_threshold is False


class TestEscalationMessageContent:
    """Verify escalation message content details."""

    def test_change_strategy_includes_error_count(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert str(THRESHOLD_DIFFERENT_STRATEGY) in msg

    def test_reduce_scope_includes_error_count(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_REDUCE_SCOPE):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert str(THRESHOLD_REDUCE_SCOPE) in msg

    def test_stop_includes_error_count(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert str(THRESHOLD_STOP) in msg

    def test_stop_message_includes_summary_instructions(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert "Summarize" in msg or "summary" in msg.lower()
        assert "final response" in msg.lower()

    def test_change_strategy_message_mentions_different_tools(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert "different tools" in msg.lower()


class TestStopOnlyOnce:
    """Test that after stop is issued, subsequent calls fall through to lower levels."""

    def test_after_stop_falls_to_reduce_scope(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        msg1 = mgr.get_escalation_message()
        assert "STOP" in msg1

        # Additional error — stop was issued, consecutive >= THRESHOLD_REDUCE_SCOPE
        mgr.record_error()
        msg2 = mgr.get_escalation_message()
        # Should fall through to REDUCE SCOPE since _stop_issued is True
        assert msg2 is not None
        assert "REDUCE SCOPE" in msg2

    def test_stop_flag_persists_across_many_errors(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        mgr.get_escalation_message()  # consumes the stop

        for _ in range(5):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        # Still returns REDUCE SCOPE, never STOP again
        assert msg is not None
        assert "STOP" not in msg
        assert "REDUCE SCOPE" in msg


class TestSuccessResetCycle:
    """Test escalation resets after success and re-escalates on new errors."""

    def test_success_resets_then_re_escalates(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY):
            mgr.record_error()
        assert mgr.get_escalation_message() is not None

        mgr.record_success()
        assert mgr.get_escalation_message() is None

        # New error streak
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert msg is not None
        assert "CHANGE STRATEGY" in msg

    def test_success_does_not_reset_total_errors(self):
        mgr = EscalationManager()
        mgr.record_error()
        mgr.record_error()
        mgr.record_success()
        mgr.record_error()
        assert mgr.total_errors == 3
        assert mgr.consecutive_errors == 1

    def test_success_does_not_reset_error_type_counts(self):
        mgr = EscalationManager()
        mgr.record_error(ErrorType.AUTH)
        mgr.record_success()
        mgr.record_error(ErrorType.AUTH)
        assert mgr._error_type_counts[ErrorType.AUTH] == 2

    def test_success_does_not_reset_stop_issued_flag(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        mgr.get_escalation_message()  # triggers stop

        mgr.record_success()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        # Stop was already issued, so it falls to REDUCE SCOPE
        assert "STOP" not in msg
        assert "REDUCE SCOPE" in msg


class TestAbortWithInterleavedSuccess:
    """Test should_abort with non-consecutive errors interleaved with successes."""

    def test_abort_triggers_on_total_not_consecutive(self):
        mgr = EscalationManager()
        for i in range(HARD_ABORT_TOTAL_ERRORS):
            mgr.record_error()
            if i % 2 == 0:
                mgr.record_success()
        assert mgr.should_abort() is True

    def test_total_errors_accumulate_through_successes(self):
        mgr = EscalationManager()
        for _ in range(3):
            mgr.record_error()
        mgr.record_success()
        for _ in range(3):
            mgr.record_error()
        mgr.record_success()
        assert mgr.total_errors == 6
        assert mgr.consecutive_errors == 0


class TestEscalationThresholdBoundaries:
    """Verify exact boundary behavior at each threshold."""

    def test_one_below_change_strategy_is_none(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY - 1):
            mgr.record_error()
        assert mgr.get_escalation_message() is None

    def test_exact_change_strategy_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_DIFFERENT_STRATEGY):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert "CHANGE STRATEGY" in msg

    def test_one_below_reduce_scope_is_change_strategy(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_REDUCE_SCOPE - 1):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert "CHANGE STRATEGY" in msg

    def test_exact_reduce_scope_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_REDUCE_SCOPE):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert "REDUCE SCOPE" in msg

    def test_one_below_stop_is_reduce_scope(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP - 1):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert "REDUCE SCOPE" in msg

    def test_exact_stop_threshold(self):
        mgr = EscalationManager()
        for _ in range(THRESHOLD_STOP):
            mgr.record_error()
        msg = mgr.get_escalation_message()
        assert "STOP" in msg

    def test_threshold_ordering_is_correct(self):
        """Sanity check that threshold constants are in ascending order."""
        assert THRESHOLD_DIFFERENT_STRATEGY < THRESHOLD_REDUCE_SCOPE
        assert THRESHOLD_REDUCE_SCOPE < THRESHOLD_STOP
        assert THRESHOLD_STOP < HARD_ABORT_TOTAL_ERRORS


class TestMultipleSuccessCalls:
    """Edge case: calling record_success multiple times."""

    def test_multiple_successes_keep_consecutive_at_zero(self):
        mgr = EscalationManager()
        mgr.record_error()
        mgr.record_success()
        mgr.record_success()
        mgr.record_success()
        assert mgr.consecutive_errors == 0
        assert mgr.total_errors == 1
