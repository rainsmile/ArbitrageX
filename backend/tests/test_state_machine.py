"""Tests for the generic StateMachine and factory functions."""

from __future__ import annotations

import pytest

from app.core.state_machine import (
    EXECUTION_TRANSITIONS,
    LEG_TRANSITIONS,
    InvalidStateTransition,
    StateMachine,
    StateTransition,
    create_execution_sm,
    create_leg_sm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_sm() -> StateMachine:
    """Minimal state machine for testing."""
    return StateMachine(
        name="test",
        initial_state="A",
        transitions={"A": {"B", "C"}, "B": {"C"}, "C": set()},
    )


# ---------------------------------------------------------------------------
# Basic transitions
# ---------------------------------------------------------------------------

class TestStateMachineTransitions:
    def test_initial_state(self):
        sm = _simple_sm()
        assert sm.state == "A"
        assert sm.name == "test"

    def test_valid_transition(self):
        sm = _simple_sm()
        record = sm.transition("B", reason="go to B")
        assert sm.state == "B"
        assert isinstance(record, StateTransition)
        assert record.from_state == "A"
        assert record.to_state == "B"
        assert record.reason == "go to B"

    def test_chain_transitions(self):
        sm = _simple_sm()
        sm.transition("B")
        sm.transition("C")
        assert sm.state == "C"

    def test_invalid_transition_raises(self):
        sm = _simple_sm()
        sm.transition("B")
        # B -> A is not in the transition map
        with pytest.raises(InvalidStateTransition):
            sm.transition("A")

    def test_terminal_state_has_no_transitions(self):
        sm = _simple_sm()
        sm.transition("B")
        sm.transition("C")
        assert sm.is_terminal is True
        with pytest.raises(InvalidStateTransition):
            sm.transition("A")

    def test_non_terminal_state(self):
        sm = _simple_sm()
        assert sm.is_terminal is False

    def test_allowed_transitions(self):
        sm = _simple_sm()
        assert sm.allowed_transitions == {"B", "C"}

    def test_can_transition(self):
        sm = _simple_sm()
        assert sm.can_transition("B") is True
        assert sm.can_transition("X") is False


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestTransitionHistory:
    def test_history_records_all_transitions(self):
        sm = _simple_sm()
        sm.transition("B")
        sm.transition("C")
        history = sm.history
        assert len(history) == 2
        assert history[0].from_state == "A"
        assert history[0].to_state == "B"
        assert history[1].from_state == "B"
        assert history[1].to_state == "C"

    def test_transition_count(self):
        sm = _simple_sm()
        assert sm.transition_count() == 0
        sm.transition("B")
        assert sm.transition_count() == 1

    def test_history_is_copy(self):
        sm = _simple_sm()
        sm.transition("B")
        h = sm.history
        h.clear()
        assert sm.transition_count() == 1  # internal list unaffected


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

class TestCallbacks:
    def test_on_enter_callback(self):
        sm = _simple_sm()
        calls = []
        sm.on_enter("B", lambda old, new, rec: calls.append(("enter_B", old, new)))
        sm.transition("B")
        assert len(calls) == 1
        assert calls[0] == ("enter_B", "A", "B")

    def test_on_exit_callback(self):
        sm = _simple_sm()
        calls = []
        sm.on_exit("A", lambda old, new, rec: calls.append(("exit_A", old, new)))
        sm.transition("B")
        assert len(calls) == 1
        assert calls[0] == ("exit_A", "A", "B")

    def test_callback_exception_does_not_break_transition(self):
        sm = _simple_sm()
        sm.on_enter("B", lambda o, n, r: 1 / 0)  # raises ZeroDivisionError
        sm.transition("B")  # should not raise
        assert sm.state == "B"


# ---------------------------------------------------------------------------
# Factory: execution state machine
# ---------------------------------------------------------------------------

class TestExecutionStateMachine:
    def test_create_execution_sm(self):
        sm = create_execution_sm("abc123")
        assert sm.state == "CREATED"
        assert "exec:" in sm.name

    def test_happy_path(self):
        sm = create_execution_sm("test-id")
        sm.transition("RISK_CHECKING")
        sm.transition("READY")
        sm.transition("EXECUTING")
        sm.transition("COMPLETED")
        assert sm.state == "COMPLETED"
        assert sm.is_terminal is True

    def test_risk_rejection_path(self):
        sm = create_execution_sm("test-id")
        sm.transition("RISK_CHECKING")
        sm.transition("RISK_REJECTED")
        assert sm.is_terminal is True

    def test_executing_to_failed(self):
        sm = create_execution_sm("test-id")
        sm.transition("RISK_CHECKING")
        sm.transition("READY")
        sm.transition("EXECUTING")
        sm.transition("FAILED")
        assert sm.is_terminal is True


# ---------------------------------------------------------------------------
# Factory: leg state machine
# ---------------------------------------------------------------------------

class TestLegStateMachine:
    def test_create_leg_sm(self):
        sm = create_leg_sm("leg-001")
        assert sm.state == "PENDING"
        assert "leg:" in sm.name

    def test_happy_path(self):
        sm = create_leg_sm("leg-001")
        sm.transition("SUBMITTING")
        sm.transition("SUBMITTED")
        sm.transition("FILLED")
        assert sm.state == "FILLED"
        assert sm.is_terminal is True

    def test_partial_fill_to_filled(self):
        sm = create_leg_sm("leg-001")
        sm.transition("SUBMITTING")
        sm.transition("SUBMITTED")
        sm.transition("PARTIAL_FILLED")
        sm.transition("FILLED")
        assert sm.is_terminal is True

    def test_pending_to_cancelled(self):
        sm = create_leg_sm("leg-001")
        sm.transition("CANCELLED")
        assert sm.is_terminal is True


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_invalid_initial_state_raises(self):
        with pytest.raises(ValueError, match="Initial state"):
            StateMachine(name="bad", initial_state="NONEXISTENT", transitions={"A": {"B"}})

    def test_metadata_in_transition(self):
        sm = _simple_sm()
        record = sm.transition("B", reason="test", extra_key="extra_val")
        assert record.metadata["extra_key"] == "extra_val"

    def test_time_in_current_state(self):
        sm = _simple_sm()
        # No transitions yet
        assert sm.time_in_current_state() == 0.0
        sm.transition("B")
        elapsed = sm.time_in_current_state()
        assert elapsed >= 0.0
