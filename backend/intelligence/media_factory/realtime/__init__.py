"""Famili Realtime Avatar Runtime foundation (ADR-0019).

    chunked audio → RealtimeAvatarProvider → engine adapter → progressive frames

Frozen boundary: **Offline Media Factory != Realtime Avatar Runtime.** The
sibling modules in `backend/intelligence/media_factory/` implement the Gate1
offline benchmark; this package implements the realtime runtime. Neither may
import the other's pipeline, and this package is intentionally not re-exported
from `media_factory/__init__.py` so that importing the offline benchmark can
never drag a realtime session in (ADR-0018 §3, ADR-0019).

What exists here is the *foundation*: the provider contract, the session state
machine, protocol V0, a fixture provider, a remote-first Ditto adapter skeleton
and a prepared-but-unexecuted GPU smoke harness. What does not exist:
REAL_NEURAL_REALTIME_FRAMES. No realtime avatar frame has ever been produced by
a real engine through this package.
"""

from __future__ import annotations

from backend.intelligence.media_factory.realtime.contracts import (
    REALTIME_CONTRACT_VERSION,
    REQUIRED_AUDIO_CHANNELS,
    REQUIRED_AUDIO_FORMAT,
    REQUIRED_AUDIO_SAMPLE_RATE_HZ,
    AudioChunk,
    AudioChunkAcceptance,
    AudioChunkRejectedError,
    AvatarFrame,
    IdentitySpec,
    InvalidSessionTransitionError,
    PreparedIdentity,
    RealtimeAvatarError,
    RealtimeProviderCapabilities,
    RealtimeProviderUnavailableError,
    RealtimeSessionSpec,
    TurnCompletion,
)
from backend.intelligence.media_factory.realtime.ditto_online_smoke import (
    SMOKE_HARNESS_ID,
    SUPPORTED_CHUNK_MS,
    DittoOnlineSmokeReport,
    build_ditto_online_smoke_plan,
    not_run_report,
    split_wav_to_chunks,
)
from backend.intelligence.media_factory.realtime.ditto_provider import (
    DITTO_REALTIME_ENV_VARS,
    DittoRealtimeAvatarProvider,
    DittoRealtimeTransport,
    RemoteEngineAttestation,
    RemoteFramePayload,
)
from backend.intelligence.media_factory.realtime.fixture_provider import (
    FixtureRealtimeAvatarProvider,
)
from backend.intelligence.media_factory.realtime.gpu_node_boundary import (
    GPU_NODE_ALLOWED_STATE,
    GPU_NODE_FORBIDDEN_CANONICAL_STATE,
    assert_not_canonical_on_gpu_node,
    gpu_node_boundary_manifest,
)
from backend.intelligence.media_factory.realtime.metrics import (
    NOT_RUN,
    REALTIME_METRICS_SCHEMA,
    UNKNOWN,
    RealtimeMetrics,
    RealtimeMetricsRecorder,
    not_run_metrics,
)
from backend.intelligence.media_factory.realtime.protocol import (
    REALTIME_PROTOCOL_VERSION,
    RealtimeEvent,
    RealtimeEventEmitter,
    RealtimeEventType,
)
from backend.intelligence.media_factory.realtime.provider import (
    RealtimeAvatarProvider,
    RealtimeAvatarProviderRegistry,
    RealtimeAvatarSession,
)
from backend.intelligence.media_factory.realtime.session_state import (
    ALLOWED_TRANSITIONS,
    RealtimeSessionState,
    SessionStateMachine,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "DITTO_REALTIME_ENV_VARS",
    "GPU_NODE_ALLOWED_STATE",
    "GPU_NODE_FORBIDDEN_CANONICAL_STATE",
    "NOT_RUN",
    "REALTIME_CONTRACT_VERSION",
    "REALTIME_METRICS_SCHEMA",
    "REALTIME_PROTOCOL_VERSION",
    "REQUIRED_AUDIO_CHANNELS",
    "REQUIRED_AUDIO_FORMAT",
    "REQUIRED_AUDIO_SAMPLE_RATE_HZ",
    "SMOKE_HARNESS_ID",
    "SUPPORTED_CHUNK_MS",
    "UNKNOWN",
    "AudioChunk",
    "AudioChunkAcceptance",
    "AudioChunkRejectedError",
    "AvatarFrame",
    "DittoOnlineSmokeReport",
    "DittoRealtimeAvatarProvider",
    "DittoRealtimeTransport",
    "FixtureRealtimeAvatarProvider",
    "IdentitySpec",
    "InvalidSessionTransitionError",
    "PreparedIdentity",
    "RealtimeAvatarError",
    "RealtimeAvatarProvider",
    "RealtimeAvatarProviderRegistry",
    "RealtimeAvatarSession",
    "RealtimeEvent",
    "RealtimeEventEmitter",
    "RealtimeEventType",
    "RealtimeMetrics",
    "RealtimeMetricsRecorder",
    "RealtimeProviderCapabilities",
    "RealtimeProviderUnavailableError",
    "RealtimeSessionSpec",
    "RealtimeSessionState",
    "RemoteEngineAttestation",
    "RemoteFramePayload",
    "SessionStateMachine",
    "TurnCompletion",
    "assert_not_canonical_on_gpu_node",
    "build_ditto_online_smoke_plan",
    "gpu_node_boundary_manifest",
    "not_run_metrics",
    "not_run_report",
    "split_wav_to_chunks",
]
