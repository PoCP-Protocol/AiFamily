"""Transport bindings for the realtime avatar protocol (ADR-0019 §Transport).

This module maps protocol events onto a wire. It is the *only* place in the
realtime package allowed to know about WebSocket or WebRTC, and nothing in
`contracts.py`, `provider.py` or the provider implementations may import it —
`tests/architecture/test_realtime_boundaries.py` enforces that.

Why the separation is structural rather than a naming convention: the source
repository shipped a realtime session layer whose provider semantics were welded
to its WebSocket handler, and the visible result was that `WebSocket PASS` got
read as `digital human works` (ADR-0018 §Context, failure mode 3). Making the
provider contract unable to reach the transport means a future WebRTC binding is
an addition here, not a rewrite of the providers.

V0 declares one implemented binding shape (WebSocket control + binary payload)
and one planned binding (WebRTC). "Declared" means the frame/channel mapping is
frozen; it does not mean a server exists — no HTTP or WebSocket server is part
of FAMILY-REALTIME-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.intelligence.media_factory.realtime.protocol import (
    REALTIME_PROTOCOL_VERSION,
    RealtimeEvent,
    RealtimeEventType,
)

TransportKind = Literal["WEBSOCKET", "WEBRTC"]
TransportStatus = Literal["BINDING_DECLARED", "PLANNED"]


@dataclass(frozen=True, slots=True)
class TransportBinding:
    """How protocol events and frame payloads map onto one transport."""

    kind: TransportKind
    status: TransportStatus
    control_channel: str
    payload_channel: str
    server_implemented: bool
    notes: str

    def to_manifest(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "control_channel": self.control_channel,
            "payload_channel": self.payload_channel,
            "server_implemented": self.server_implemented,
            "notes": self.notes,
        }


WEBSOCKET_V0 = TransportBinding(
    kind="WEBSOCKET",
    status="BINDING_DECLARED",
    control_channel="text frames carrying RealtimeEvent.to_envelope() JSON",
    payload_channel="binary frames keyed by envelope.binary_ref",
    server_implemented=False,
    notes=(
        "Audio in and frames out both use binary frames; the text channel stays "
        "human-readable so a stalled turn can be diagnosed from a capture alone."
    ),
)

WEBRTC_PLANNED = TransportBinding(
    kind="WEBRTC",
    status="PLANNED",
    control_channel="data channel carrying the same envelope JSON",
    payload_channel="media tracks (opus audio / encoded video) instead of binary frames",
    server_implemented=False,
    notes=(
        "Deferred past FAMILY-REALTIME-001. The envelope is already transport-neutral, "
        "so adding this binding must not require changing any provider."
    ),
)

TRANSPORT_BINDINGS: tuple[TransportBinding, ...] = (WEBSOCKET_V0, WEBRTC_PLANNED)


def binding_for(kind: TransportKind) -> TransportBinding:
    for binding in TRANSPORT_BINDINGS:
        if binding.kind == kind:
            return binding
    raise ValueError(f"unknown transport kind: {kind}")


def encode_control_frame(event: RealtimeEvent) -> dict[str, Any]:
    """Render one event for the control channel of any declared binding."""
    return event.to_envelope()


def binary_ref_for_frame(*, session_id: str, turn_id: str, frame_sequence: int) -> str:
    """The reference an envelope uses to point at bytes on the payload channel."""
    return f"frame://{session_id}/{turn_id}/{frame_sequence}"


def transport_manifest() -> dict[str, Any]:
    return {
        "protocol_version": REALTIME_PROTOCOL_VERSION,
        "event_types": [e.value for e in RealtimeEventType],
        "bindings": [binding.to_manifest() for binding in TRANSPORT_BINDINGS],
        "server_implemented": False,
    }
