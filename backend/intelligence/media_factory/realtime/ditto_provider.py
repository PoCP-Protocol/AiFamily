"""DittoRealtimeAvatarProvider — remote-first adapter skeleton (ADR-0019).

The engine and its weights stay **outside** this worktree; this module holds no
Ditto source, no model files and no GPU dependency. It reads only environment
variables and speaks to the node through `DittoRealtimeTransport`, so the
AiFamily side runs and is testable on a machine with no CUDA at all.

Modes, decided from the environment:

* ``REMOTE_GPU_NODE``  — ``DITTO_REALTIME_ENDPOINT`` is set. The node runs the
  online pipeline; AiFamily pushes chunks and pulls frames. Generic application
  code never sees a Ditto path in this mode, which is the point of ADR-0019.
* ``LOCAL_SUBPROCESS`` — engine paths are set but no endpoint. Recognised and
  refused: Ditto's online mode needs a resident in-process pipeline with a frame
  hook, which a per-turn subprocess of `inference.py` cannot provide. Declaring
  the mode without implementing it is deliberate — see `KNOWN_GAPS` in
  ADR-0019.
* ``UNAVAILABLE``      — nothing configured. Every operation fails closed.

**Attestation, not assumption.** Frames are marked `real_neural_inference=True`
only when the remote node itself attests to running the real engine in online
mode. A test double therefore cannot manufacture a "real inference" claim: it
attests `real_neural_inference=False`, and every frame and metric it produces
carries that answer through unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from backend.intelligence.media_factory.contracts import (
    DITTO_UPSTREAM_COMMIT_PIN,
    DITTO_UPSTREAM_URL,
)
from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    AvatarFrame,
    ExecutionLocality,
    IdentitySpec,
    PreparedIdentity,
    RealtimeAvatarError,
    RealtimeProviderCapabilities,
    RealtimeProviderUnavailableError,
    RealtimeSessionSpec,
    TurnCompletion,
)
from backend.intelligence.media_factory.realtime.metrics import RealtimeMetricsRecorder
from backend.intelligence.media_factory.realtime.session import BaseRealtimeAvatarSession
from backend.intelligence.media_factory.realtime.session_state import RealtimeSessionState

DITTO_REALTIME_PROVIDER_ID = "ditto_realtime"

#: Every path this provider may learn comes from one of these. No default points
#: inside the AiFamily worktree.
DITTO_REALTIME_ENV_VARS: tuple[str, ...] = (
    "DITTO_ENGINE_ROOT",
    "DITTO_MODEL_ROOT",
    "DITTO_PYTHON",
    "DITTO_DEVICE",
    "DITTO_REALTIME_ENDPOINT",
)

DittoRealtimeMode = Literal["REMOTE_GPU_NODE", "LOCAL_SUBPROCESS", "UNAVAILABLE"]


@dataclass(frozen=True, slots=True)
class RemoteEngineAttestation:
    """What the GPU node says about itself, before AiFamily believes anything.

    `online_mode` and `real_neural_inference` are separate because the failure
    that matters is subtle: a node can legitimately run the real engine in
    offline batch mode and still be useless for a realtime turn.
    """

    endpoint: str
    engine: str
    upstream_commit: str
    device: str
    reachable: bool
    online_mode: bool
    real_neural_inference: bool
    detail: str = ""

    @property
    def realtime_gate_eligible(self) -> bool:
        return self.reachable and self.online_mode and self.real_neural_inference

    def to_manifest(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "engine": self.engine,
            "upstream_commit": self.upstream_commit,
            "device": self.device,
            "reachable": self.reachable,
            "online_mode": self.online_mode,
            "real_neural_inference": self.real_neural_inference,
            "realtime_gate_eligible": self.realtime_gate_eligible,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class RemoteFramePayload:
    """A frame as the node reports it — bytes or a reference, never both."""

    payload: bytes | None = None
    payload_ref: str | None = None


class DittoRealtimeTransport(Protocol):
    """The GPU-node boundary. Implementations live on the deployment side.

    Nothing here mentions HTTP or WebSocket: the transport binding is a separate
    concern (`transport.py`), and this Protocol is what a node integration must
    satisfy however it is wired.
    """

    def attest(self) -> RemoteEngineAttestation: ...

    def prepare_identity(self, *, image_locator: str, image_sha256: str) -> str: ...

    def open_session(self, *, session_id: str, identity_handle: str, target_fps: int) -> None: ...

    def push_audio(self, *, session_id: str, chunks: Sequence[AudioChunk]) -> None: ...

    def poll_frames(self, *, session_id: str) -> Sequence[RemoteFramePayload]: ...

    def end_turn(self, *, session_id: str, turn_id: str) -> None: ...

    def close_session(self, *, session_id: str) -> None: ...


class DittoRealtimeAvatarSession(BaseRealtimeAvatarSession):
    """Bridges consumed audio chunks to the remote node and back."""

    def __init__(
        self,
        *,
        spec: RealtimeSessionSpec,
        provider_id: str,
        metrics_recorder: RealtimeMetricsRecorder,
        transport: DittoRealtimeTransport,
        attestation: RemoteEngineAttestation,
    ) -> None:
        super().__init__(
            spec=spec,
            provider_id=provider_id,
            metrics_recorder=metrics_recorder,
            real_neural_inference=attestation.real_neural_inference,
            frame_format=spec.frame_format,
        )
        self._transport = transport
        self.attestation = attestation

    def _generate_frames(self, chunks: Sequence[AudioChunk]) -> Sequence[AvatarFrame]:
        self._transport.push_audio(session_id=self.session_id, chunks=list(chunks))
        remote_frames = self._transport.poll_frames(session_id=self.session_id)
        return [
            self._build_frame(payload=remote.payload, payload_ref=remote.payload_ref)
            for remote in remote_frames
        ]

    def end_turn(self) -> TurnCompletion:
        turn_id = self.turn_id
        completion = super().end_turn()
        if turn_id is not None:
            self._transport.end_turn(session_id=self.session_id, turn_id=turn_id)
        return completion

    def cancel(self, *, reason: str) -> None:
        super().cancel(reason=reason)
        self._transport.close_session(session_id=self.session_id)

    def close(self) -> None:
        already_closed = self.state is RealtimeSessionState.CLOSED
        super().close()
        if not already_closed:
            self._transport.close_session(session_id=self.session_id)


class DittoRealtimeAvatarProvider:
    """Realtime adapter for antgroup/ditto-talkinghead. Engine stays external."""

    provider_id = DITTO_REALTIME_PROVIDER_ID

    def __init__(
        self,
        *,
        transport: DittoRealtimeTransport | None = None,
        endpoint: str | None = None,
        engine_root: str | None = None,
        model_root: str | None = None,
        python_executable: str | None = None,
        device: str | None = None,
        provider_version: str = "0.1.0",
        upstream_commit: str = DITTO_UPSTREAM_COMMIT_PIN,
        env: dict[str, str] | None = None,
    ) -> None:
        source = env if env is not None else dict(os.environ)
        self.endpoint = endpoint or source.get("DITTO_REALTIME_ENDPOINT", "")
        self.engine_root = engine_root or source.get("DITTO_ENGINE_ROOT", "")
        self.model_root = model_root or source.get("DITTO_MODEL_ROOT", "")
        self.python_executable = python_executable or source.get("DITTO_PYTHON", "")
        self.device = device or source.get("DITTO_DEVICE", "cuda")
        self.provider_version = provider_version
        self.upstream_commit = upstream_commit
        self._transport = transport
        self._sessions: dict[str, DittoRealtimeAvatarSession] = {}

    # ------------------------------------------------------------------- mode

    @property
    def mode(self) -> DittoRealtimeMode:
        if self.endpoint:
            return "REMOTE_GPU_NODE"
        if self.engine_root and self.model_root:
            return "LOCAL_SUBPROCESS"
        return "UNAVAILABLE"

    @property
    def execution_locality(self) -> ExecutionLocality:
        return "LOCAL_SUBPROCESS" if self.mode == "LOCAL_SUBPROCESS" else "REMOTE_GPU_NODE"

    def attestation(self) -> RemoteEngineAttestation | None:
        """The node's own claim, or None when there is nobody to ask."""
        if self.mode != "REMOTE_GPU_NODE" or self._transport is None:
            return None
        return self._transport.attest()

    # ----------------------------------------------------------- capabilities

    def capabilities(self) -> RealtimeProviderCapabilities:
        attestation = self._safe_attestation()
        gate_eligible = attestation is not None and attestation.realtime_gate_eligible
        return RealtimeProviderCapabilities(
            provider_id=self.provider_id,
            streaming_audio_in=True,
            progressive_frames_out=True,
            # Turn-level barge-in is not implemented in V0; cancel ends the session.
            interruption_supported=False,
            real_neural_inference=True,
            realtime_gate_eligible=gate_eligible,
            gate_ineligible_reason=(
                "" if gate_eligible else self._gate_ineligible_reason(attestation)
            ),
            execution_locality=self.execution_locality,
            max_concurrent_sessions=1,
            emitted_frame_formats=("RGB24", "JPEG"),
        )

    def health(self) -> dict[str, object]:
        attestation = self._safe_attestation()
        return {
            "ok": attestation is not None and attestation.realtime_gate_eligible,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "mode": self.mode,
            "execution_locality": self.execution_locality,
            "endpoint_configured": bool(self.endpoint),
            "transport_configured": self._transport is not None,
            "engine_root_configured": bool(self.engine_root),
            "model_root_configured": bool(self.model_root),
            "python_configured": bool(self.python_executable),
            "device": self.device,
            "upstream_url": DITTO_UPSTREAM_URL,
            "upstream_commit_pin": self.upstream_commit,
            "engine_in_aifamily_worktree": False,
            "weights_in_aifamily_worktree": False,
            "REAL_DITTO_ONLINE_SMOKE": (
                "PENDING_NODE_REPORT" if attestation is not None else "NOT_RUN"
            ),
            "attestation": None if attestation is None else attestation.to_manifest(),
            "open_sessions": len(self._sessions),
            "environment_variables": list(DITTO_REALTIME_ENV_VARS),
        }

    # -------------------------------------------------------------- operations

    def prepare_identity(self, spec: IdentitySpec) -> PreparedIdentity:
        transport = self._require_transport()
        handle = transport.prepare_identity(
            image_locator=spec.image_locator,
            image_sha256=spec.image_sha256,
        )
        if not handle:
            raise RealtimeAvatarError("remote node returned an empty identity handle")
        attestation = transport.attest()
        return PreparedIdentity(
            identity_id=spec.identity_id,
            identity_handle=handle,
            image_sha256=spec.image_sha256,
            provider_id=self.provider_id,
            real_neural_inference=attestation.real_neural_inference,
        )

    def start_session(self, spec: RealtimeSessionSpec) -> DittoRealtimeAvatarSession:
        transport = self._require_transport()
        attestation = transport.attest()
        if not attestation.reachable:
            raise RealtimeProviderUnavailableError(
                f"REMOTE_GPU_UNAVAILABLE: node {attestation.endpoint or self.endpoint!r} "
                f"is not reachable ({attestation.detail or 'no detail reported'})"
            )
        if not attestation.online_mode:
            raise RealtimeProviderUnavailableError(
                "REMOTE_ENGINE_NOT_ONLINE: node does not attest online_mode; a realtime "
                "session cannot be served by an offline batch pipeline"
            )
        if len(self._sessions) >= self.capabilities().max_concurrent_sessions:
            raise RealtimeProviderUnavailableError(
                f"SESSION_LIMIT: {self.provider_id} serves "
                f"{self.capabilities().max_concurrent_sessions} concurrent session(s)"
            )

        transport.open_session(
            session_id=spec.session_id,
            identity_handle=spec.identity_handle,
            target_fps=spec.target_fps,
        )
        recorder = RealtimeMetricsRecorder(
            source=(
                "REMOTE_GPU_NODE_ATTESTED"
                if attestation.real_neural_inference
                else "REMOTE_TRANSPORT_UNATTESTED"
            ),
            real_neural_inference=attestation.real_neural_inference,
            note=(
                ""
                if attestation.real_neural_inference
                else "Node did not attest real neural inference; numbers prove nothing"
            ),
        )
        session = DittoRealtimeAvatarSession(
            spec=spec,
            provider_id=self.provider_id,
            metrics_recorder=recorder,
            transport=transport,
            attestation=attestation,
        )
        session.start()
        self._sessions[spec.session_id] = session
        return session

    def close(self) -> None:
        for session in list(self._sessions.values()):
            session.close()
        self._sessions.clear()

    # --------------------------------------------------------------- internals

    def _require_transport(self) -> DittoRealtimeTransport:
        mode = self.mode
        if mode == "UNAVAILABLE":
            raise RealtimeProviderUnavailableError(
                "DITTO_REALTIME_UNCONFIGURED: set DITTO_REALTIME_ENDPOINT for a remote "
                "GPU media compute node. The engine and its weights must stay outside "
                "the AiFamily worktree."
            )
        if mode == "LOCAL_SUBPROCESS":
            raise RealtimeProviderUnavailableError(
                "DITTO_REALTIME_LOCAL_SUBPROCESS_NOT_IMPLEMENTED: online mode needs a "
                "resident pipeline with a progressive frame hook, which a per-turn "
                "subprocess cannot provide. Use DITTO_REALTIME_ENDPOINT."
            )
        if self._transport is None:
            raise RealtimeProviderUnavailableError(
                f"DITTO_REALTIME_TRANSPORT_MISSING: endpoint {self.endpoint!r} is "
                "configured but no transport implementation was supplied"
            )
        return self._transport

    def _safe_attestation(self) -> RemoteEngineAttestation | None:
        """Attestation for reporting paths, which must never raise."""
        if self.mode != "REMOTE_GPU_NODE" or self._transport is None:
            return None
        try:
            return self._transport.attest()
        except Exception:
            # health() and capabilities() are the paths an operator reaches for
            # when the node is broken. They must report the breakage, not raise
            # into it — start_session() is where a failed attestation must bite.
            return None

    def _gate_ineligible_reason(self, attestation: RemoteEngineAttestation | None) -> str:
        if attestation is None:
            return f"REAL_DITTO_ONLINE_SMOKE=NOT_RUN; mode={self.mode}"
        if not attestation.reachable:
            return "REMOTE_GPU_UNAVAILABLE: node not reachable"
        if not attestation.online_mode:
            return "REMOTE_ENGINE_NOT_ONLINE: node does not attest online_mode"
        return "NODE_DID_NOT_ATTEST_REAL_NEURAL_INFERENCE"
