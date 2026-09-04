"""Provider-neutral realtime avatar contracts (ADR-0019).

Nothing in this module may name a concrete engine. Ditto is one candidate
implementation of `RealtimeAvatarProvider`; replacing it must not require
touching this file, and generic application code must never learn an engine's
filesystem layout — identities travel as opaque locators and handles.

Frozen distinction (ADR-0018 §3, restated by ADR-0019): the Offline Media
Factory (`benchmark.py` + `providers/`) and the Realtime Avatar Runtime are two
different runtimes. This package must not reuse the offline Gate1 pipeline, and
the offline pipeline must not import this package.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.intelligence.media_factory.contracts import MediaFactoryError

REALTIME_CONTRACT_VERSION = "FAMILI_REALTIME_AVATAR_CONTRACT_V0"

# The single audio shape every realtime provider must accept. Providers may
# advertise more in their capabilities; none may advertise less.
REQUIRED_AUDIO_FORMAT = "PCM16"
REQUIRED_AUDIO_SAMPLE_RATE_HZ = 16000
REQUIRED_AUDIO_CHANNELS = 1
BYTES_PER_PCM16_SAMPLE = 2

AudioFormat = Literal["PCM16"]

FrameFormat = Literal[
    "RGB24",
    "BGR24",
    "JPEG",
    "PNG",
    # A provider that does not run real neural inference must say so in the
    # frame format itself, so a downstream consumer cannot mistake deterministic
    # test bytes for pixels an engine produced.
    "FIXTURE_SYNTHETIC",
]

ExecutionLocality = Literal["IN_PROCESS", "LOCAL_SUBPROCESS", "REMOTE_GPU_NODE"]

ChunkDisposition = Literal[
    "ACCEPTED",
    "DUPLICATE_IGNORED",
    "REORDERED_BUFFERED",
    "REJECTED_OUT_OF_WINDOW",
]


class RealtimeAvatarError(MediaFactoryError):
    """Base for realtime avatar failures. Realtime boundaries fail closed."""


class InvalidSessionTransitionError(RealtimeAvatarError):
    """An explicitly illegal session state transition was requested."""


class RealtimeProviderUnavailableError(RealtimeAvatarError):
    """The provider cannot serve a session (unconfigured, unreachable, refused)."""


class AudioChunkRejectedError(RealtimeAvatarError):
    """An audio chunk violated the required audio shape or session identity."""


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """One chunk of turn audio on its way to a provider.

    `sequence` is per turn and starts at 0. `presentation_time_ms` is the chunk's
    offset from the start of its turn, not wall-clock: it is what lets a consumer
    align frames to audio after reordering, and it survives transport retries.
    """

    session_id: str
    turn_id: str
    sequence: int
    presentation_time_ms: int
    payload: bytes
    sample_rate_hz: int = REQUIRED_AUDIO_SAMPLE_RATE_HZ
    channels: int = REQUIRED_AUDIO_CHANNELS
    audio_format: AudioFormat = REQUIRED_AUDIO_FORMAT
    is_final: bool = False

    def __post_init__(self) -> None:
        if not self.session_id or not self.turn_id:
            raise AudioChunkRejectedError("audio chunk requires session_id and turn_id")
        if self.sequence < 0:
            raise AudioChunkRejectedError(f"sequence must be >= 0, got {self.sequence}")
        if self.presentation_time_ms < 0:
            raise AudioChunkRejectedError(
                f"presentation_time_ms must be >= 0, got {self.presentation_time_ms}"
            )
        if self.audio_format != REQUIRED_AUDIO_FORMAT:
            raise AudioChunkRejectedError(
                f"audio_format must be {REQUIRED_AUDIO_FORMAT}, got {self.audio_format}"
            )
        if self.sample_rate_hz != REQUIRED_AUDIO_SAMPLE_RATE_HZ:
            raise AudioChunkRejectedError(
                f"sample_rate_hz must be {REQUIRED_AUDIO_SAMPLE_RATE_HZ}, got {self.sample_rate_hz}"
            )
        if self.channels != REQUIRED_AUDIO_CHANNELS:
            raise AudioChunkRejectedError(
                f"channels must be {REQUIRED_AUDIO_CHANNELS} (mono), got {self.channels}"
            )
        if len(self.payload) % BYTES_PER_PCM16_SAMPLE != 0:
            raise AudioChunkRejectedError(
                f"PCM16 payload must be an even number of bytes, got {len(self.payload)}"
            )

    @property
    def sample_count(self) -> int:
        return len(self.payload) // BYTES_PER_PCM16_SAMPLE

    @property
    def duration_ms(self) -> int:
        return int(round(self.sample_count * 1000 / self.sample_rate_hz))

    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()

    def to_manifest(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "sequence": self.sequence,
            "presentation_time_ms": self.presentation_time_ms,
            "audio_format": self.audio_format,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "sample_count": self.sample_count,
            "duration_ms": self.duration_ms,
            "payload_sha256": self.payload_sha256,
            "is_final": self.is_final,
        }


@dataclass(frozen=True, slots=True)
class AvatarFrame:
    """One progressive avatar frame.

    `payload` and `payload_ref` are mutually exclusive: an in-process provider
    hands over bytes, a remote provider hands over a reference the transport
    resolves on its binary channel. `real_neural_inference` travels with every
    single frame rather than being a session-level claim, because that is the
    field a Gate reviewer reads, and a per-frame answer cannot be back-filled.
    """

    session_id: str
    turn_id: str
    frame_index: int
    sequence: int
    presentation_time_ms: int
    width: int
    height: int
    frame_format: FrameFormat
    payload: bytes | None = None
    payload_ref: str | None = None
    is_first_frame: bool = False
    real_neural_inference: bool = False

    def __post_init__(self) -> None:
        if not self.session_id or not self.turn_id:
            raise RealtimeAvatarError("avatar frame requires session_id and turn_id")
        if self.frame_index < 0 or self.sequence < 0:
            raise RealtimeAvatarError("frame_index and sequence must be >= 0")
        if self.presentation_time_ms < 0:
            raise RealtimeAvatarError("presentation_time_ms must be >= 0")
        if self.width <= 0 or self.height <= 0:
            raise RealtimeAvatarError(f"frame dimensions must be positive, got {self.size}")
        if (self.payload is None) == (self.payload_ref is None):
            raise RealtimeAvatarError(
                "avatar frame must carry exactly one of payload / payload_ref"
            )
        if self.frame_format == "FIXTURE_SYNTHETIC" and self.real_neural_inference:
            raise RealtimeAvatarError(
                "FIXTURE_SYNTHETIC frames must never claim real_neural_inference=True"
            )

    @property
    def size(self) -> tuple[int, int]:
        return (self.width, self.height)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "frame_index": self.frame_index,
            "sequence": self.sequence,
            "presentation_time_ms": self.presentation_time_ms,
            "width": self.width,
            "height": self.height,
            "frame_format": self.frame_format,
            "payload_bytes": None if self.payload is None else len(self.payload),
            "payload_ref": self.payload_ref,
            "is_first_frame": self.is_first_frame,
            "real_neural_inference": self.real_neural_inference,
        }


@dataclass(frozen=True, slots=True)
class RealtimeProviderCapabilities:
    """What a provider will actually do, declared before anyone asks it to.

    `realtime_gate_eligible` is deliberately separate from
    `real_neural_inference`: a provider can be a genuine neural engine and still
    be ineligible for the realtime gate because no real online smoke has ever
    run against it. Collapsing the two is how "the adapter exists" becomes
    "realtime works".
    """

    provider_id: str
    streaming_audio_in: bool
    progressive_frames_out: bool
    interruption_supported: bool
    real_neural_inference: bool
    realtime_gate_eligible: bool
    execution_locality: ExecutionLocality
    max_concurrent_sessions: int
    accepted_audio_formats: tuple[str, ...] = (REQUIRED_AUDIO_FORMAT,)
    accepted_sample_rates_hz: tuple[int, ...] = (REQUIRED_AUDIO_SAMPLE_RATE_HZ,)
    emitted_frame_formats: tuple[FrameFormat, ...] = ()
    gate_ineligible_reason: str = ""

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise RealtimeAvatarError("capabilities require a provider_id")
        if self.max_concurrent_sessions < 1:
            raise RealtimeAvatarError("max_concurrent_sessions must be >= 1")
        if REQUIRED_AUDIO_FORMAT not in self.accepted_audio_formats:
            raise RealtimeAvatarError(
                f"every realtime provider must accept {REQUIRED_AUDIO_FORMAT}"
            )
        if REQUIRED_AUDIO_SAMPLE_RATE_HZ not in self.accepted_sample_rates_hz:
            raise RealtimeAvatarError(
                f"every realtime provider must accept {REQUIRED_AUDIO_SAMPLE_RATE_HZ} Hz"
            )
        if not self.emitted_frame_formats:
            raise RealtimeAvatarError("provider must declare at least one emitted frame format")
        if self.realtime_gate_eligible and not self.real_neural_inference:
            raise RealtimeAvatarError(
                "realtime_gate_eligible requires real_neural_inference — a fixture "
                "provider passing its tests is not a realtime avatar PASS"
            )
        if not self.realtime_gate_eligible and not self.gate_ineligible_reason:
            raise RealtimeAvatarError(
                "a gate-ineligible provider must state why, so the gap stays visible"
            )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "contract_version": REALTIME_CONTRACT_VERSION,
            "provider_id": self.provider_id,
            "streaming_audio_in": self.streaming_audio_in,
            "progressive_frames_out": self.progressive_frames_out,
            "interruption_supported": self.interruption_supported,
            "real_neural_inference": self.real_neural_inference,
            "realtime_gate_eligible": self.realtime_gate_eligible,
            "gate_ineligible_reason": self.gate_ineligible_reason,
            "execution_locality": self.execution_locality,
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "accepted_audio_formats": list(self.accepted_audio_formats),
            "accepted_sample_rates_hz": list(self.accepted_sample_rates_hz),
            "emitted_frame_formats": list(self.emitted_frame_formats),
        }


@dataclass(frozen=True, slots=True)
class IdentitySpec:
    """A request to prepare an identity, expressed without a filesystem path.

    `image_locator` is opaque to the caller and meaningful only to the provider:
    a local path for an in-process provider, a node-side path or object key for a
    remote one. This is the field that keeps ADR-0019's rule enforceable —
    generic application code must not know where an engine keeps its files.
    """

    identity_id: str
    image_locator: str
    image_sha256: str

    def __post_init__(self) -> None:
        if not self.identity_id:
            raise RealtimeAvatarError("identity_id is required")
        if not self.image_locator:
            raise RealtimeAvatarError("image_locator is required")
        if len(self.image_sha256) != 64:
            raise RealtimeAvatarError(
                f"image_sha256 must be 64 hex characters, got {len(self.image_sha256)}"
            )


@dataclass(frozen=True, slots=True)
class PreparedIdentity:
    """The provider's answer: a handle, plus what it will not claim."""

    identity_id: str
    identity_handle: str
    image_sha256: str
    provider_id: str
    real_neural_inference: bool
    prepare_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.identity_handle:
            raise RealtimeAvatarError("prepared identity requires a handle")

    def to_manifest(self) -> dict[str, Any]:
        return {
            "identity_id": self.identity_id,
            "identity_handle": self.identity_handle,
            "image_sha256": self.image_sha256,
            "provider_id": self.provider_id,
            "real_neural_inference": self.real_neural_inference,
            "prepare_ms": self.prepare_ms,
        }


@dataclass(frozen=True, slots=True)
class RealtimeSessionSpec:
    """Everything a provider needs to open a session, and nothing engine-specific.

    Engine tuning knobs (Ditto's `chunksize`, `smo_k_d`, backend selection) are
    deliberately absent: they belong to the provider's own configuration, not to
    the contract every provider must satisfy.
    """

    session_id: str
    identity_handle: str
    trace_id: str
    target_fps: int = 25
    frame_format: FrameFormat = "RGB24"
    frame_width: int = 512
    frame_height: int = 512
    sample_rate_hz: int = REQUIRED_AUDIO_SAMPLE_RATE_HZ
    reorder_window: int = 8
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id or not self.trace_id:
            raise RealtimeAvatarError("session spec requires session_id and trace_id")
        if not self.identity_handle:
            raise RealtimeAvatarError("session spec requires a prepared identity_handle")
        if self.target_fps < 1:
            raise RealtimeAvatarError(f"target_fps must be >= 1, got {self.target_fps}")
        if self.sample_rate_hz != REQUIRED_AUDIO_SAMPLE_RATE_HZ:
            raise RealtimeAvatarError(
                f"sample_rate_hz must be {REQUIRED_AUDIO_SAMPLE_RATE_HZ}, got {self.sample_rate_hz}"
            )
        if self.reorder_window < 0:
            raise RealtimeAvatarError("reorder_window must be >= 0")


@dataclass(frozen=True, slots=True)
class AudioChunkAcceptance:
    """The provider's per-chunk answer.

    A boolean would not be enough to debug a realtime turn: the caller needs to
    know whether a chunk was consumed, buffered pending a gap, ignored as a
    duplicate, or refused for falling outside the reorder window.
    """

    session_id: str
    turn_id: str
    sequence: int
    disposition: ChunkDisposition
    next_expected_sequence: int
    buffered_chunks: int
    consumed_chunks: int

    @property
    def accepted(self) -> bool:
        return self.disposition in {"ACCEPTED", "REORDERED_BUFFERED", "DUPLICATE_IGNORED"}

    def to_manifest(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "sequence": self.sequence,
            "disposition": self.disposition,
            "accepted": self.accepted,
            "next_expected_sequence": self.next_expected_sequence,
            "buffered_chunks": self.buffered_chunks,
            "consumed_chunks": self.consumed_chunks,
        }


@dataclass(frozen=True, slots=True)
class TurnCompletion:
    """What `end_turn` reports once a turn has drained."""

    session_id: str
    turn_id: str
    audio_chunks_consumed: int
    audio_duration_ms: int
    frames_emitted: int
    first_frame_emitted: bool
    cancelled: bool = False

    def to_manifest(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "audio_chunks_consumed": self.audio_chunks_consumed,
            "audio_duration_ms": self.audio_duration_ms,
            "frames_emitted": self.frames_emitted,
            "first_frame_emitted": self.first_frame_emitted,
            "cancelled": self.cancelled,
        }
