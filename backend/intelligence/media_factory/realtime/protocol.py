"""Famili Realtime Avatar Protocol V0 — provider-neutral events (ADR-0019).

These events describe *what happened in a session*, not how bytes reached a
browser. That separation is the point: the same event stream must be able to
travel over WebSocket control frames today and over a WebRTC data channel later
without either the provider contract or the orchestrator changing. Transport
bindings live in `transport.py` and are not importable from here.

Every event carries `session_id`, `trace_id` and a monotonic `sequence`, and
turn-scoped events carry `turn_id`. A realtime stream that reports only
`success=true` is undebuggable — when a turn stalls at frame 3, the question is
always "which turn, which sequence, which trace", and an envelope that cannot
answer it is not a protocol.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from backend.intelligence.media_factory.realtime.contracts import (
    REALTIME_CONTRACT_VERSION,
    AvatarFrame,
    RealtimeAvatarError,
)

REALTIME_PROTOCOL_VERSION = "FAMILI_REALTIME_AVATAR_PROTOCOL_V0"


class RealtimeEventType(StrEnum):
    SESSION_STARTED = "session.started"
    AUDIO_ACCEPTED = "audio.accepted"
    AVATAR_FIRST_FRAME = "avatar.first_frame"
    AVATAR_FRAME = "avatar.frame"
    TURN_COMPLETED = "turn.completed"
    SESSION_CANCELLED = "session.cancelled"
    SESSION_CLOSED = "session.closed"
    PROVIDER_ERROR = "provider.error"


#: Events whose meaning is scoped to a single turn rather than the session.
TURN_SCOPED_EVENTS: frozenset[RealtimeEventType] = frozenset(
    {
        RealtimeEventType.AUDIO_ACCEPTED,
        RealtimeEventType.AVATAR_FIRST_FRAME,
        RealtimeEventType.AVATAR_FRAME,
        RealtimeEventType.TURN_COMPLETED,
    }
)


@dataclass(frozen=True, slots=True)
class RealtimeEvent:
    """One protocol event, independent of any transport."""

    event_type: RealtimeEventType
    session_id: str
    sequence: int
    trace_id: str
    emitted_at_ms: int
    turn_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    binary_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.session_id or not self.trace_id:
            raise RealtimeAvatarError("every realtime event requires session_id and trace_id")
        if self.sequence < 0:
            raise RealtimeAvatarError("event sequence must be >= 0")
        if self.event_type in TURN_SCOPED_EVENTS and not self.turn_id:
            raise RealtimeAvatarError(
                f"{self.event_type.value} is turn-scoped and requires a turn_id"
            )

    def to_envelope(self) -> dict[str, Any]:
        """The control-plane representation (JSON-serialisable).

        Frame pixels never travel in here. A frame event carries its shape and a
        `binary_ref`; the bytes go over the transport's binary channel, which is
        what makes the same envelope viable for WebSocket and WebRTC alike.
        """
        return {
            "protocol_version": REALTIME_PROTOCOL_VERSION,
            "contract_version": REALTIME_CONTRACT_VERSION,
            "type": self.event_type.value,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "trace_id": self.trace_id,
            "sequence": self.sequence,
            "emitted_at_ms": self.emitted_at_ms,
            "binary_ref": self.binary_ref,
            "payload": dict(self.payload),
        }


def frame_event_payload(frame: AvatarFrame) -> dict[str, Any]:
    """Control-plane description of a frame, without its pixels."""
    return {
        "frame_index": frame.frame_index,
        "frame_sequence": frame.sequence,
        "presentation_time_ms": frame.presentation_time_ms,
        "width": frame.width,
        "height": frame.height,
        "frame_format": frame.frame_format,
        "payload_bytes": None if frame.payload is None else len(frame.payload),
        "real_neural_inference": frame.real_neural_inference,
    }


class RealtimeEventEmitter:
    """Assigns protocol sequence numbers and enforces the once-only rules.

    `avatar.first_frame` may be emitted at most once per turn. It is the event a
    latency budget is measured against, so a second one would silently reset
    whatever downstream consumer is timing the turn — better to fail here than
    to publish two first frames.
    """

    def __init__(
        self,
        *,
        session_id: str,
        trace_id: str,
        clock: Any = None,
    ) -> None:
        self.session_id = session_id
        self.trace_id = trace_id
        self._clock = clock or (lambda: int(time.monotonic() * 1000))
        self._sequence = 0
        self._events: list[RealtimeEvent] = []
        self._first_frame_turns: set[str] = set()

    @property
    def events(self) -> tuple[RealtimeEvent, ...]:
        return tuple(self._events)

    @property
    def next_sequence(self) -> int:
        return self._sequence

    def emit(
        self,
        event_type: RealtimeEventType,
        *,
        turn_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        binary_ref: str | None = None,
    ) -> RealtimeEvent:
        if event_type is RealtimeEventType.AVATAR_FIRST_FRAME:
            if turn_id in self._first_frame_turns:
                raise RealtimeAvatarError(
                    f"DUPLICATE_FIRST_FRAME: avatar.first_frame already emitted for turn "
                    f"{turn_id!r} in session {self.session_id!r}"
                )
            self._first_frame_turns.add(str(turn_id))

        event = RealtimeEvent(
            event_type=event_type,
            session_id=self.session_id,
            sequence=self._sequence,
            trace_id=self.trace_id,
            emitted_at_ms=int(self._clock()),
            turn_id=turn_id,
            payload=dict(payload or {}),
            binary_ref=binary_ref,
        )
        self._sequence += 1
        self._events.append(event)
        return event

    def first_frame_emitted_for(self, turn_id: str) -> bool:
        return turn_id in self._first_frame_turns

    def events_of_type(self, event_type: RealtimeEventType) -> tuple[RealtimeEvent, ...]:
        return tuple(e for e in self._events if e.event_type is event_type)
