"""DittoRealtimeAvatarProvider tests — no GPU, no engine, no network.

REAL_DITTO_ONLINE_SMOKE=NOT_RUN. Nothing here runs Ditto. The transport double
below deliberately attests `real_neural_inference=False`, and the central
assertion of this file is that the adapter carries that answer through to every
frame and every metric instead of upgrading it.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    IdentitySpec,
    RealtimeProviderUnavailableError,
    RealtimeSessionSpec,
)
from backend.intelligence.media_factory.realtime.ditto_provider import (
    DITTO_REALTIME_ENV_VARS,
    DittoRealtimeAvatarProvider,
    RemoteEngineAttestation,
    RemoteFramePayload,
)
from backend.intelligence.media_factory.realtime.gpu_node_boundary import (
    GPU_NODE_ALLOWED_STATE,
    GPU_NODE_FORBIDDEN_CANONICAL_STATE,
    assert_not_canonical_on_gpu_node,
    gpu_node_boundary_manifest,
    is_allowed_on_gpu_node,
)
from backend.intelligence.media_factory.realtime.protocol import RealtimeEventType
from backend.intelligence.media_factory.realtime.provider import RealtimeAvatarProvider
from backend.intelligence.media_factory.realtime.session_state import RealtimeSessionState

_S = RealtimeSessionState

PCM16_100MS_AT_16K = b"\x00\x01" * 1600

REMOTE_ENDPOINT = "wss://gpu-node.invalid/realtime"


class _NodeDouble:
    """A stand-in for a GPU node. It attests that it is not the real thing.

    This is the honest shape for a test double of a remote engine: it can prove
    the adapter's wiring works, and it cannot manufacture a real-inference claim
    because attestation is the node's statement, not the adapter's assumption.
    """

    def __init__(
        self,
        *,
        reachable: bool = True,
        online_mode: bool = True,
        real_neural_inference: bool = False,
        frames_per_push: int = 2,
        attest_raises: bool = False,
    ) -> None:
        self.attestation = RemoteEngineAttestation(
            endpoint=REMOTE_ENDPOINT,
            engine="ditto-talkinghead",
            upstream_commit="c3e47eee2e626500017a0556b470d6d4182f85e8",
            device="cuda",
            reachable=reachable,
            online_mode=online_mode,
            real_neural_inference=real_neural_inference,
            detail="" if reachable else "connection refused",
        )
        self.frames_per_push = frames_per_push
        self.attest_raises = attest_raises
        self.calls: list[str] = []

    def attest(self) -> RemoteEngineAttestation:
        if self.attest_raises:
            raise ConnectionError("node unreachable")
        self.calls.append("attest")
        return self.attestation

    def prepare_identity(self, *, image_locator: str, image_sha256: str) -> str:
        self.calls.append("prepare_identity")
        return f"node-identity:{image_sha256[:8]}"

    def open_session(self, *, session_id: str, identity_handle: str, target_fps: int) -> None:
        self.calls.append("open_session")

    def push_audio(self, *, session_id: str, chunks: Sequence[AudioChunk]) -> None:
        self.calls.append(f"push_audio:{len(chunks)}")

    def poll_frames(self, *, session_id: str) -> Sequence[RemoteFramePayload]:
        self.calls.append("poll_frames")
        return [RemoteFramePayload(payload=b"\x00\x01\x02") for _ in range(self.frames_per_push)]

    def end_turn(self, *, session_id: str, turn_id: str) -> None:
        self.calls.append("end_turn")

    def close_session(self, *, session_id: str) -> None:
        self.calls.append("close_session")


def _chunk(sequence: int, *, turn_id: str = "turn-1") -> AudioChunk:
    return AudioChunk(
        session_id="sess-remote",
        turn_id=turn_id,
        sequence=sequence,
        presentation_time_ms=sequence * 100,
        payload=PCM16_100MS_AT_16K,
    )


def _spec() -> RealtimeSessionSpec:
    return RealtimeSessionSpec(
        session_id="sess-remote",
        identity_handle="node-identity:abcd1234",
        trace_id="trace-remote",
        target_fps=25,
    )


def _remote_provider(**node_kwargs: object) -> tuple[DittoRealtimeAvatarProvider, _NodeDouble]:
    node = _NodeDouble(**node_kwargs)  # type: ignore[arg-type]
    provider = DittoRealtimeAvatarProvider(transport=node, endpoint=REMOTE_ENDPOINT, env={})
    return provider, node


# ------------------------------------------------------------------- unconfigured


def test_unconfigured_provider_fails_closed() -> None:
    provider = DittoRealtimeAvatarProvider(env={})
    assert provider.mode == "UNAVAILABLE"
    assert isinstance(provider, RealtimeAvatarProvider)

    health = provider.health()
    assert health["ok"] is False
    assert health["REAL_DITTO_ONLINE_SMOKE"] == "NOT_RUN"
    assert health["engine_in_aifamily_worktree"] is False
    assert health["weights_in_aifamily_worktree"] is False
    assert set(DITTO_REALTIME_ENV_VARS) == {
        "DITTO_ENGINE_ROOT",
        "DITTO_MODEL_ROOT",
        "DITTO_PYTHON",
        "DITTO_DEVICE",
        "DITTO_REALTIME_ENDPOINT",
    }

    with pytest.raises(RealtimeProviderUnavailableError, match="DITTO_REALTIME_UNCONFIGURED"):
        provider.start_session(_spec())
    with pytest.raises(RealtimeProviderUnavailableError, match="DITTO_REALTIME_UNCONFIGURED"):
        provider.prepare_identity(
            IdentitySpec(identity_id="famili", image_locator="node://x", image_sha256="a" * 64)
        )


def test_provider_reads_its_paths_from_the_environment_only() -> None:
    provider = DittoRealtimeAvatarProvider(
        env={
            "DITTO_ENGINE_ROOT": "/opt/aifamily-engines/ditto-talkinghead",
            "DITTO_MODEL_ROOT": "/opt/aifamily-engines/ditto-talkinghead/checkpoints",
            "DITTO_PYTHON": "/opt/aifamily-engines/ditto-talkinghead/.venv/bin/python",
            "DITTO_DEVICE": "cuda:0",
        }
    )
    assert provider.mode == "LOCAL_SUBPROCESS"
    assert provider.device == "cuda:0"
    assert provider.execution_locality == "LOCAL_SUBPROCESS"


def test_local_subprocess_mode_is_declared_but_refused() -> None:
    """Online mode needs a resident pipeline; a per-turn subprocess cannot do it."""
    provider = DittoRealtimeAvatarProvider(
        env={"DITTO_ENGINE_ROOT": "/opt/engine", "DITTO_MODEL_ROOT": "/opt/weights"}
    )
    with pytest.raises(
        RealtimeProviderUnavailableError,
        match="LOCAL_SUBPROCESS_NOT_IMPLEMENTED",
    ):
        provider.start_session(_spec())


def test_endpoint_without_transport_fails_closed() -> None:
    provider = DittoRealtimeAvatarProvider(endpoint=REMOTE_ENDPOINT, env={})
    assert provider.mode == "REMOTE_GPU_NODE"
    with pytest.raises(RealtimeProviderUnavailableError, match="TRANSPORT_MISSING"):
        provider.start_session(_spec())


def test_explicit_arguments_win_over_the_environment() -> None:
    provider = DittoRealtimeAvatarProvider(
        endpoint=REMOTE_ENDPOINT,
        env={"DITTO_REALTIME_ENDPOINT": "wss://ignored.invalid"},
    )
    assert provider.endpoint == REMOTE_ENDPOINT


# ---------------------------------------------------------------- unreachable GPU


def test_unreachable_gpu_node_fails_closed() -> None:
    provider, _node = _remote_provider(reachable=False)
    caps = provider.capabilities()
    assert caps.realtime_gate_eligible is False
    assert "REMOTE_GPU_UNAVAILABLE" in caps.gate_ineligible_reason
    with pytest.raises(RealtimeProviderUnavailableError, match="REMOTE_GPU_UNAVAILABLE"):
        provider.start_session(_spec())


def test_offline_batch_node_cannot_serve_a_realtime_session() -> None:
    provider, _node = _remote_provider(online_mode=False)
    assert "NOT_ONLINE" in provider.capabilities().gate_ineligible_reason
    with pytest.raises(RealtimeProviderUnavailableError, match="REMOTE_ENGINE_NOT_ONLINE"):
        provider.start_session(_spec())


def test_health_reports_a_raising_transport_instead_of_exploding() -> None:
    provider, _node = _remote_provider(attest_raises=True)
    health = provider.health()
    assert health["ok"] is False
    assert health["attestation"] is None
    assert provider.capabilities().realtime_gate_eligible is False


def test_session_limit_is_enforced() -> None:
    provider, _node = _remote_provider()
    provider.start_session(_spec())
    with pytest.raises(RealtimeProviderUnavailableError, match="SESSION_LIMIT"):
        provider.start_session(
            RealtimeSessionSpec(
                session_id="sess-2",
                identity_handle="node-identity:abcd1234",
                trace_id="trace-2",
            )
        )


# ------------------------------------------------------- attestation carries through


def test_provider_declares_itself_a_real_engine_but_not_gate_eligible() -> None:
    provider, _node = _remote_provider()
    caps = provider.capabilities()
    assert caps.real_neural_inference is True
    assert caps.realtime_gate_eligible is False
    assert caps.gate_ineligible_reason == "NODE_DID_NOT_ATTEST_REAL_NEURAL_INFERENCE"
    assert caps.execution_locality == "REMOTE_GPU_NODE"


def test_unattested_node_frames_never_claim_real_inference() -> None:
    provider, node = _remote_provider()
    provider.prepare_identity(
        IdentitySpec(
            identity_id="famili",
            image_locator="node://identities/famili.png",
            image_sha256="b" * 64,
        )
    )
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))

    frames = [session.read_frame(), session.read_frame()]
    assert all(f is not None for f in frames)
    assert all(f.real_neural_inference is False for f in frames if f is not None)
    assert session.metrics().source == "REMOTE_TRANSPORT_UNATTESTED"
    assert session.metrics().realtime_gate_eligible is False
    assert "push_audio:1" in node.calls
    assert "poll_frames" in node.calls


def test_attested_node_frames_are_marked_real() -> None:
    provider, _node = _remote_provider(real_neural_inference=True)
    assert provider.capabilities().realtime_gate_eligible is True
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))
    frame = session.read_frame()
    assert frame is not None
    assert frame.real_neural_inference is True
    assert session.metrics().source == "REMOTE_GPU_NODE_ATTESTED"


def test_prepared_identity_handle_comes_from_the_node() -> None:
    provider, node = _remote_provider()
    prepared = provider.prepare_identity(
        IdentitySpec(identity_id="famili", image_locator="node://x", image_sha256="c" * 64)
    )
    assert prepared.identity_handle == "node-identity:cccccccc"
    assert "prepare_identity" in node.calls


# ------------------------------------------------------------- session plumbing


def test_end_turn_notifies_the_node() -> None:
    provider, node = _remote_provider()
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))
    completion = session.end_turn()
    assert completion.frames_emitted == 2
    assert completion.first_frame_emitted is True
    assert node.calls.count("end_turn") == 1
    assert session.state is _S.READY


def test_cancel_and_close_release_the_node_session() -> None:
    provider, node = _remote_provider()
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))
    session.cancel(reason="barge_in")
    assert session.state is _S.CANCELLED
    session.close()
    assert session.state is _S.CLOSED
    assert node.calls.count("close_session") >= 1
    cancelled = [e for e in session.events() if e.event_type is RealtimeEventType.SESSION_CANCELLED]
    assert len(cancelled) == 1


def test_provider_close_closes_remote_sessions() -> None:
    provider, node = _remote_provider()
    session = provider.start_session(_spec())
    provider.close()
    assert session.state is _S.CLOSED
    assert "close_session" in node.calls


# ------------------------------------------------------------- GPU node boundary


def test_gpu_node_may_hold_only_ephemeral_media_state() -> None:
    assert set(GPU_NODE_ALLOWED_STATE) == {
        "avatar_engine_binaries",
        "avatar_model_weights",
        "temporary_avatar_session_state",
        "temporary_audio_chunks",
        "temporary_frame_buffers",
        "runtime_metrics",
        "ephemeral_caches",
    }
    assert is_allowed_on_gpu_node("temporary_frame_buffers") is True
    assert is_allowed_on_gpu_node("family_profile") is False


@pytest.mark.parametrize("state_name", sorted(GPU_NODE_FORBIDDEN_CANONICAL_STATE))
def test_business_truth_may_never_be_canonical_on_a_gpu_node(state_name: str) -> None:
    with pytest.raises(ValueError, match="GPU_NODE_BOUNDARY_VIOLATION"):
        assert_not_canonical_on_gpu_node(state_name)


def test_gpu_node_boundary_manifest_names_an_owner_for_every_forbidden_item() -> None:
    manifest = gpu_node_boundary_manifest()
    assert manifest["node_may_write_family_truth"] is False
    assert manifest["retention_policy"] == "EPHEMERAL_PER_SESSION"
    for state_name in manifest["forbidden_canonical_state"]:
        assert manifest["canonical_owner"][state_name].startswith("AiFamily")
    assert manifest["accepted_payloads"] == ["identity_reference_image", "turn_audio_chunks"]
