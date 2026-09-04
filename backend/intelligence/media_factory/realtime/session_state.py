"""Explicit realtime avatar session state machine (ADR-0019).

The transition table is data, not scattered `if` statements, for one reason: a
realtime session's illegal moves are the interesting ones. "Push audio into a
closed session" and "read frames from a session that never prepared an identity"
must fail loudly at the boundary rather than half-succeed and surface later as a
stalled stream.

Every transition not listed in `ALLOWED_TRANSITIONS` is illegal. There is no
permissive default.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from backend.intelligence.media_factory.realtime.contracts import InvalidSessionTransitionError


class RealtimeSessionState(StrEnum):
    CREATED = "CREATED"
    PREPARING = "PREPARING"
    READY = "READY"
    RECEIVING_AUDIO = "RECEIVING_AUDIO"
    GENERATING = "GENERATING"
    TURN_COMPLETING = "TURN_COMPLETING"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    ERROR = "ERROR"


#: States from which nothing further may happen.
TERMINAL_STATES: frozenset[RealtimeSessionState] = frozenset({RealtimeSessionState.CLOSED})

#: States in which the session is mid-turn and holds buffered work.
ACTIVE_TURN_STATES: frozenset[RealtimeSessionState] = frozenset(
    {
        RealtimeSessionState.RECEIVING_AUDIO,
        RealtimeSessionState.GENERATING,
        RealtimeSessionState.TURN_COMPLETING,
    }
)

_S = RealtimeSessionState

#: The whole state machine. `cancel()` is a session-level verb in V0: it takes
#: the session to CANCELLED, from which the only move is CLOSED. Turn-level
#: barge-in (cancel this reply, keep the session and start the next turn) is a
#: deliberate gap recorded in ADR-0019 rather than a transition invented here
#: without an orchestrator to drive it.
ALLOWED_TRANSITIONS: Mapping[RealtimeSessionState, frozenset[RealtimeSessionState]] = {
    _S.CREATED: frozenset({_S.PREPARING, _S.CANCELLED, _S.CLOSED, _S.ERROR}),
    _S.PREPARING: frozenset({_S.READY, _S.CANCELLED, _S.CLOSED, _S.ERROR}),
    _S.READY: frozenset({_S.RECEIVING_AUDIO, _S.CANCELLED, _S.CLOSED, _S.ERROR}),
    _S.RECEIVING_AUDIO: frozenset(
        {
            _S.RECEIVING_AUDIO,
            _S.GENERATING,
            _S.TURN_COMPLETING,
            _S.CANCELLED,
            _S.CLOSED,
            _S.ERROR,
        }
    ),
    _S.GENERATING: frozenset(
        {
            _S.GENERATING,
            _S.RECEIVING_AUDIO,
            _S.TURN_COMPLETING,
            _S.CANCELLED,
            _S.CLOSED,
            _S.ERROR,
        }
    ),
    _S.TURN_COMPLETING: frozenset({_S.READY, _S.CANCELLED, _S.CLOSED, _S.ERROR}),
    _S.CANCELLED: frozenset({_S.CLOSED}),
    _S.ERROR: frozenset({_S.CLOSED}),
    _S.CLOSED: frozenset(),
}


class SessionStateMachine:
    """Holds one session's state and refuses every unlisted move."""

    def __init__(self, *, session_id: str) -> None:
        self.session_id = session_id
        self._state = RealtimeSessionState.CREATED
        self._history: list[RealtimeSessionState] = [RealtimeSessionState.CREATED]

    @property
    def state(self) -> RealtimeSessionState:
        return self._state

    @property
    def history(self) -> tuple[RealtimeSessionState, ...]:
        return tuple(self._history)

    @property
    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def can_transition_to(self, target: RealtimeSessionState) -> bool:
        return target in ALLOWED_TRANSITIONS[self._state]

    def transition_to(self, target: RealtimeSessionState) -> RealtimeSessionState:
        if not self.can_transition_to(target):
            allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[self._state])
            raise InvalidSessionTransitionError(
                f"INVALID_SESSION_TRANSITION: session {self.session_id} cannot move "
                f"{self._state.value} -> {target.value}; allowed from "
                f"{self._state.value}: {allowed}"
            )
        self._state = target
        self._history.append(target)
        return target

    def require(self, *states: RealtimeSessionState) -> None:
        """Guard an operation on the states in which it is meaningful."""
        if self._state not in states:
            expected = sorted(s.value for s in states)
            raise InvalidSessionTransitionError(
                f"INVALID_SESSION_STATE: session {self.session_id} is "
                f"{self._state.value}; operation requires one of {expected}"
            )

    def to_manifest(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "state": self._state.value,
            "history": [s.value for s in self._history],
            "is_terminal": self.is_terminal,
        }
