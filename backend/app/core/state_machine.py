"""Generic finite state machine with strict transition validation and audit logging."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from loguru import logger


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class StateTransition:
    """Record of a single state transition."""
    from_state: str
    to_state: str
    timestamp: datetime
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InvalidStateTransition(Exception):
    """Raised when a transition violates the allowed transition map."""
    pass


# ---------------------------------------------------------------------------
# StateMachine
# ---------------------------------------------------------------------------

class StateMachine:
    """Finite state machine with strict transition rules.

    Maintains a history of all transitions and supports on_enter / on_exit
    callbacks for each state.
    """

    def __init__(
        self,
        name: str,
        initial_state: str,
        transitions: dict[str, set[str]],
    ) -> None:
        """
        Args:
            name: identifier for logging
            initial_state: starting state
            transitions: {from_state: {allowed_to_states}}
        """
        if initial_state not in transitions:
            raise ValueError(
                f"Initial state '{initial_state}' is not in the transition map. "
                f"Known states: {set(transitions.keys())}"
            )
        self._name = name
        self._state = initial_state
        self._transitions = transitions
        self._history: list[StateTransition] = []
        self._on_enter: dict[str, list[Callable]] = {}
        self._on_exit: dict[str, list[Callable]] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> str:
        return self._state

    @property
    def history(self) -> list[StateTransition]:
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        """True if the current state has no outgoing transitions."""
        return not self._transitions.get(self._state)

    @property
    def allowed_transitions(self) -> set[str]:
        """Set of states reachable from the current state."""
        return set(self._transitions.get(self._state, set()))

    # ------------------------------------------------------------------
    # Transition logic
    # ------------------------------------------------------------------

    def can_transition(self, to_state: str) -> bool:
        """Check whether transitioning to *to_state* is allowed."""
        allowed = self._transitions.get(self._state, set())
        return to_state in allowed

    def transition(
        self,
        to_state: str,
        reason: str = "",
        **metadata: Any,
    ) -> StateTransition:
        """Execute a state transition.

        Raises :class:`InvalidStateTransition` if the transition is not
        permitted by the transition map.
        """
        if not self.can_transition(to_state):
            allowed = self._transitions.get(self._state, set())
            raise InvalidStateTransition(
                f"[{self._name}] Cannot transition from '{self._state}' to '{to_state}'. "
                f"Allowed: {allowed}"
            )

        old_state = self._state
        record = StateTransition(
            from_state=old_state,
            to_state=to_state,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            metadata=metadata,
        )

        # Fire on_exit callbacks for the old state
        for cb in self._on_exit.get(old_state, []):
            try:
                cb(old_state, to_state, record)
            except Exception:
                logger.opt(exception=True).warning(
                    "[{}] on_exit callback failed for state {}",
                    self._name, old_state,
                )

        self._state = to_state
        self._history.append(record)

        # Fire on_enter callbacks for the new state
        for cb in self._on_enter.get(to_state, []):
            try:
                cb(old_state, to_state, record)
            except Exception:
                logger.opt(exception=True).warning(
                    "[{}] on_enter callback failed for state {}",
                    self._name, to_state,
                )

        logger.info(
            "[{}] {} -> {} ({})",
            self._name, old_state, to_state, reason or "no reason",
        )
        return record

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_enter(self, state: str, callback: Callable) -> None:
        """Register a callback invoked when the machine enters *state*.

        The callback signature is ``(from_state, to_state, record)``.
        """
        self._on_enter.setdefault(state, []).append(callback)

    def on_exit(self, state: str, callback: Callable) -> None:
        """Register a callback invoked when the machine leaves *state*.

        The callback signature is ``(from_state, to_state, record)``.
        """
        self._on_exit.setdefault(state, []).append(callback)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def time_in_current_state(self) -> float:
        """Seconds elapsed since the last transition (or creation)."""
        if self._history:
            last = self._history[-1].timestamp
            return (datetime.now(timezone.utc) - last).total_seconds()
        return 0.0

    def transition_count(self) -> int:
        """Total number of transitions executed."""
        return len(self._history)

    def __repr__(self) -> str:
        return f"StateMachine(name={self._name!r}, state={self._state!r})"


# ---------------------------------------------------------------------------
# Transition maps
# ---------------------------------------------------------------------------

EXECUTION_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"RISK_CHECKING", "RISK_REJECTED", "ABORTED"},
    "RISK_CHECKING": {"READY", "RISK_REJECTED"},
    "RISK_REJECTED": set(),  # terminal
    "READY": {"EXECUTING", "ABORTED"},
    "EXECUTING": {"PARTIALLY_FILLED", "COMPLETED", "FAILED", "HEDGING"},
    "PARTIALLY_FILLED": {"COMPLETED", "FAILED", "HEDGING"},
    "HEDGING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),  # terminal
    "FAILED": set(),  # terminal
    "ABORTED": set(),  # terminal
}

LEG_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"SUBMITTING", "CANCELLED", "ABORTED"},
    "SUBMITTING": {"SUBMITTED", "FAILED"},
    "SUBMITTED": {"PARTIAL_FILLED", "FILLED", "CANCELLED", "FAILED"},
    "PARTIAL_FILLED": {"FILLED", "CANCELLED", "FAILED"},
    "FILLED": set(),  # terminal
    "CANCELLED": set(),  # terminal
    "FAILED": {"HEDGED"},
    "HEDGED": set(),  # terminal
    "ABORTED": set(),  # terminal
}


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def create_execution_sm(execution_id: str) -> StateMachine:
    """Create a state machine for tracking an execution lifecycle."""
    return StateMachine(
        name=f"exec:{execution_id[:12]}",
        initial_state="CREATED",
        transitions=EXECUTION_TRANSITIONS,
    )


def create_leg_sm(leg_id: str) -> StateMachine:
    """Create a state machine for tracking an individual execution leg."""
    return StateMachine(
        name=f"leg:{leg_id[:12]}",
        initial_state="PENDING",
        transitions=LEG_TRANSITIONS,
    )
