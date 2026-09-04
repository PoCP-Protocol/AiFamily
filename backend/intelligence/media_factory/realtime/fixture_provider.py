"""FixtureRealtimeAvatarProvider — contract harness, never an avatar.

REAL_NEURAL_INFERENCE=FALSE
REALTIME_GATE_ELIGIBLE=FALSE

This provider exists so the session state machine, the reordering rules and the
protocol can be tested on a laptop with no GPU. It generates deterministic bytes
from a hash of `(session_id, turn_id, frame_index)`; they are not pixels, they
are not an avatar, and its frames say so in their own `frame_format`
(`FIXTURE_SYNTHETIC`).

**These tests passing is not a realtime avatar PASS.** The offline Gate1
equivalent of this rule is already in `providers/fixture.py`; the realtime
version is stricter because a realtime stream is easier to fake convincingly —
frames arriving on schedule look like success from the outside.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence

from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    AvatarFrame,
    IdentitySpec,
    PreparedIdentity,
    RealtimeProviderCapabilities,
    RealtimeSessionSpec,
)
from backend.intelligence.media_factory.realtime.metrics import RealtimeMetricsRecorder
from backend.intelligence.media_factory.realtime.session import BaseRealtimeAvatarSession

FIXTURE_PROVIDER_ID = "fixture_realtime"
FIXTURE_FRAME_PAYLOAD_BYTES = 64


class FixtureRealtimeAvatarSession(BaseRealtimeAvatarSession):
    """Emits `target_fps`-worth of deterministic frames per second of audio."""

    def _generate_frames(self, chunks: Sequence[AudioChunk]) -> Sequence[AvatarFrame]:
        audio_ms = sum(chunk.duration_ms for chunk in chunks)
        frame_count = (audio_ms * self.spec.target_fps) // 1000
        frames: list[AvatarFrame] = []
        for _ in range(frame_count):
            seed = f"{self.session_id}|{self._turn_id}|{self._turn_frame_index}"
            digest = hashlib.sha256(seed.encode("utf-8")).digest()
            payload = (digest * (FIXTURE_FRAME_PAYLOAD_BYTES // len(digest) + 1))[
                :FIXTURE_FRAME_PAYLOAD_BYTES
            ]
            frames.append(self._build_frame(payload=payload))
        return frames


class FixtureRealtimeAvatarProvider:
    """Deterministic local provider. Reports its own ineligibility everywhere."""

    provider_id = FIXTURE_PROVIDER_ID

    def __init__(
        self,
        *,
        provider_version: str = "0.1.0",
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.provider_version = provider_version
        self._clock = clock
        self._sessions: dict[str, FixtureRealtimeAvatarSession] = {}
        self._identities: dict[str, PreparedIdentity] = {}

    def capabilities(self) -> RealtimeProviderCapabilities:
        return RealtimeProviderCapabilities(
            provider_id=self.provider_id,
            streaming_audio_in=True,
            progressive_frames_out=True,
            interruption_supported=True,
            real_neural_inference=False,
            realtime_gate_eligible=False,
            gate_ineligible_reason=(
                "FIXTURE_ONLY: deterministic synthetic frames, no neural inference"
            ),
            execution_locality="IN_PROCESS",
            max_concurrent_sessions=8,
            emitted_frame_formats=("FIXTURE_SYNTHETIC",),
        )

    def health(self) -> dict[str, object]:
        return {
            "ok": True,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "REAL_NEURAL_INFERENCE": "FALSE",
            "REALTIME_GATE_ELIGIBLE": "FALSE",
            "synthetic_fixture": True,
            "open_sessions": len(self._sessions),
            "note": "Fixture tests passing must never be read as a realtime avatar PASS",
        }

    def prepare_identity(self, spec: IdentitySpec) -> PreparedIdentity:
        prepared = PreparedIdentity(
            identity_id=spec.identity_id,
            identity_handle=f"fixture:{spec.identity_id}:{spec.image_sha256[:12]}",
            image_sha256=spec.image_sha256,
            provider_id=self.provider_id,
            real_neural_inference=False,
            prepare_ms=0,
        )
        self._identities[prepared.identity_handle] = prepared
        return prepared

    def start_session(self, spec: RealtimeSessionSpec) -> FixtureRealtimeAvatarSession:
        recorder = RealtimeMetricsRecorder(
            source="FIXTURE_SYNTHETIC",
            real_neural_inference=False,
            clock=self._clock,
            note="Wall-clock timings of a synthetic generator, not of inference",
        )
        recorder.record_identity_prepare(0.0)
        session = FixtureRealtimeAvatarSession(
            spec=spec,
            provider_id=self.provider_id,
            metrics_recorder=recorder,
            real_neural_inference=False,
            frame_format="FIXTURE_SYNTHETIC",
        )
        session.start()
        self._sessions[spec.session_id] = session
        return session

    def close(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()
