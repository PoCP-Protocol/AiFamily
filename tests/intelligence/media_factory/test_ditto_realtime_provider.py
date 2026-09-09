"""DittoRealtimeAvatarProvider tests — no GPU, no engine, no network.

REAL_DITTO_ONLINE_SMOKE=NOT_RUN. Nothing here runs Ditto. The transport double
below deliberately attests `real_neural_inference=False`, and the central
assertion of this file is that the adapter carries that answer through to every
frame and every metric instead of upgrading it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    IdentitySpec,
    RealtimeAvatarError,
    RealtimeProviderUnavailableError,
    RealtimeSessionSpec,
)
from backend.intelligence.media_factory.realtime.ditto_provider import (
    DITTO_FINAL_DRAIN_MAX_POLLS,
    DITTO_REALTIME_ENV_VARS,
    DittoRealtimeAvatarProvider,
    RemoteEngineAttestation,
    RemoteFrameBatch,
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

    It can also be slow on purpose. `frame_delay_polls` holds a frame back for a
    number of polls, which is the behaviour a real GPU has and an eager double
    does not: inference finishes *after* the push that started it returned. That
    is the case the progressive seam exists for, so the double has to be able to
    reproduce it.
    """

    def __init__(
        self,
        *,
        reachable: bool = True,
        online_mode: bool = True,
        real_neural_inference: bool = False,
        frames_per_push: int = 2,
        frame_delay_polls: int = 0,
        frames_after_end_turn: int = 0,
        drain_completes: bool = True,
        attest_raises: bool = False,
        end_turn_raises: bool = False,
        drain_raises: bool = False,
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
        self.frame_delay_polls = frame_delay_polls
        self.frames_after_end_turn = frames_after_end_turn
        self.drain_completes = drain_completes
        self.attest_raises = attest_raises
        self.end_turn_raises = end_turn_raises
        self.drain_raises = drain_raises
        self.calls: list[str] = []
        #: Lets a test observe what the session had emitted at the moment the
        #: node was called — the only way to assert ordering across the seam.
        self.on_call: Callable[[str], None] | None = None
        self._available: list[RemoteFramePayload] = []
        self._pending: list[list[object]] = []

    # ------------------------------------------------------------- bookkeeping

    def _note(self, name: str) -> None:
        self.calls.append(name)
        if self.on_call is not None:
            self.on_call(name)

    def _take(self) -> tuple[RemoteFramePayload, ...]:
        """Hand over what is ready, then age everything still cooking by one poll."""
        ready = tuple(self._available)
        self._available.clear()
        still_pending: list[list[object]] = []
        for entry in self._pending:
            remaining = int(entry[0]) - 1
            if remaining <= 0:
                self._available.append(entry[1])  # type: ignore[arg-type]
            else:
                still_pending.append([remaining, entry[1]])
        self._pending = still_pending
        return ready

    def _produce(self, count: int, *, delay_polls: int) -> None:
        for _ in range(count):
            payload = RemoteFramePayload(payload=b"\x00\x01\x02")
            if delay_polls > 0:
                self._pending.append([delay_polls, payload])
            else:
                self._available.append(payload)

    # ---------------------------------------------------------------- transport

    def attest(self) -> RemoteEngineAttestation:
        if self.attest_raises:
            raise ConnectionError("node unreachable")
        self._note("attest")
        return self.attestation

    def prepare_identity(self, *, image_locator: str, image_sha256: str) -> str:
        self._note("prepare_identity")
        return f"node-identity:{image_sha256[:8]}"

    def open_session(self, *, session_id: str, identity_handle: str, target_fps: int) -> None:
        self._note("open_session")

    def push_audio(self, *, session_id: str, chunks: Sequence[AudioChunk]) -> None:
        self._note(f"push_audio:{len(chunks)}")
        self._produce(self.frames_per_push, delay_polls=self.frame_delay_polls)

    def poll_frames(self, *, session_id: str) -> Sequence[RemoteFramePayload]:
        self._note("poll_frames")
        return self._take()

    def end_turn(self, *, session_id: str, turn_id: str) -> None:
        self._note("end_turn")
        if self.end_turn_raises:
            raise ConnectionError("node dropped the turn")
        self._produce(self.frames_after_end_turn, delay_polls=0)

    def drain_turn(self, *, session_id: str, turn_id: str) -> RemoteFrameBatch:
        self._note("drain_turn")
        if self.drain_raises:
            raise ConnectionError("node stopped answering mid-drain")
        return RemoteFrameBatch(frames=self._take(), turn_complete=self.drain_completes)

    def close_session(self, *, session_id: str) -> None:
        self._note("close_session")


def _chunk(sequence: int, *, turn_id: str = "turn-1") -> AudioChunk:
    return AudioChunk(
        session_id="sess-remote",
        turn_id=turn_id,
        sequence=sequence,
        presentation_time_ms=sequence * 100,
        payload=PCM16_100MS_AT_16K,
    )


def _spec(**overrides: object) -> RealtimeSessionSpec:
    kwargs: dict[str, object] = {
        "session_id": "sess-remote",
        "identity_handle": "node-identity:abcd1234",
        "trace_id": "trace-remote",
        "target_fps": 25,
    }
    kwargs.update(overrides)
    return RealtimeSessionSpec(**kwargs)  # type: ignore[arg-type]


def _second_spec() -> RealtimeSessionSpec:
    return _spec(session_id="sess-remote-2", trace_id="trace-remote-2")


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
    assert completion.drain_complete is True
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
    # Cancel-then-close is one shutdown, so the node hears about it once.
    assert node.calls.count("close_session") == 1
    cancelled = [e for e in session.events() if e.event_type is RealtimeEventType.SESSION_CANCELLED]
    assert len(cancelled) == 1


def test_provider_close_closes_remote_sessions() -> None:
    provider, node = _remote_provider()
    session = provider.start_session(_spec())
    provider.close()
    assert session.state is _S.CLOSED
    assert "close_session" in node.calls


# ------------------------------------------------------- session capacity release
#
# A session that has ended must stop costing capacity. The bug this section
# guards was invisible in a single-session test and fatal in a long-lived
# process: the provider counted sessions it had already closed, so the second
# conversation of the day was refused with SESSION_LIMIT.


def test_closing_a_session_frees_the_slot_for_the_next_one() -> None:
    provider, _node = _remote_provider()
    first = provider.start_session(_spec())
    assert provider.active_session_count == 1

    first.close()
    assert provider.active_session_count == 0

    second = provider.start_session(_second_spec())
    assert second is not first
    assert provider.active_session_count == 1


def test_cancelling_a_session_frees_the_slot_for_the_next_one() -> None:
    provider, _node = _remote_provider()
    first = provider.start_session(_spec())
    first.push_audio_chunk(_chunk(0))
    first.cancel(reason="user_barge_in")
    assert provider.active_session_count == 0

    second = provider.start_session(_second_spec())
    assert second.state is _S.READY


def test_health_open_sessions_counts_only_live_sessions() -> None:
    provider, _node = _remote_provider()
    assert provider.health()["open_sessions"] == 0
    session = provider.start_session(_spec())
    assert provider.health()["open_sessions"] == 1
    session.close()
    assert provider.health()["open_sessions"] == 0


def test_provider_close_empties_the_registry() -> None:
    provider, node = _remote_provider()
    session = provider.start_session(_spec())
    provider.close()
    assert session.state is _S.CLOSED
    assert provider.active_session_count == 0
    assert node.calls.count("close_session") == 1
    # And the freed capacity is real, not just reported.
    provider.start_session(_second_spec())
    assert provider.active_session_count == 1


def test_closing_twice_releases_once_and_closes_the_node_once() -> None:
    provider, node = _remote_provider()
    session = provider.start_session(_spec())
    session.close()
    session.close()
    assert session.state is _S.CLOSED
    assert provider.active_session_count == 0
    assert node.calls.count("close_session") == 1
    closed = [e for e in session.events() if e.event_type is RealtimeEventType.SESSION_CLOSED]
    assert len(closed) == 1


def test_a_stale_session_cannot_evict_its_replacement() -> None:
    """Release is by identity, not by session_id.

    Reached through the internal hook on purpose: the ordering it defends
    against — an old handle releasing after its id has been reused — is exactly
    what a public API cannot be made to do on demand, and leaving it untested
    would leave the identity check looking like defensive noise.
    """
    provider, _node = _remote_provider()
    stale = provider.start_session(_spec())
    stale.close()
    replacement = provider.start_session(_spec())

    provider._release_session(stale)

    assert provider.active_session_count == 1
    assert provider._sessions["sess-remote"] is replacement


def test_a_failed_session_stops_occupying_the_provider() -> None:
    provider, node = _remote_provider()
    session = provider.start_session(_spec())
    session.fail("engine reported a decode failure")
    assert session.state is _S.ERROR
    assert provider.active_session_count == 0
    assert node.calls.count("close_session") == 1


# --------------------------------------------------------- progressive frames
#
# A real GPU has not finished inference by the time the audio push returns. If
# the only poll happens inside that push, the frame it eventually produces waits
# on the node for an unrelated later push to collect it — which, at the end of a
# reply, never comes.


def test_a_frame_produced_after_the_push_still_reaches_the_consumer() -> None:
    provider, node = _remote_provider(frames_per_push=1, frame_delay_polls=1)
    session = provider.start_session(_spec())

    session.push_audio_chunk(_chunk(0))
    assert node.calls.count("poll_frames") == 1
    assert session.queue_depth == 0

    frame = session.read_frame()
    assert frame is not None
    assert frame.frame_index == 0
    assert frame.is_first_frame is True
    # No further audio was pushed; the frame arrived because read_frame asked.
    assert node.calls.count("push_audio:1") == 1
    assert node.calls.count("poll_frames") == 2


def test_repeated_reads_do_not_replay_a_remote_frame() -> None:
    provider, _node = _remote_provider(frames_per_push=1, frame_delay_polls=1)
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))

    assert session.read_frame() is not None
    assert session.read_frame() is None
    assert session.read_frame() is None

    frames = [e for e in session.events() if e.event_type is RealtimeEventType.AVATAR_FRAME]
    assert len(frames) == 1


def test_first_frame_is_announced_once_across_all_three_frame_paths() -> None:
    provider, _node = _remote_provider(
        frames_per_push=1,
        frame_delay_polls=1,
        frames_after_end_turn=1,
    )
    session = provider.start_session(_spec())

    session.push_audio_chunk(_chunk(0))  # push path: nothing ready yet
    assert session.read_frame() is not None  # progressive path
    session.push_audio_chunk(_chunk(1))
    completion = session.end_turn()  # final drain path

    first_frames = [
        e for e in session.events() if e.event_type is RealtimeEventType.AVATAR_FIRST_FRAME
    ]
    frames = [e for e in session.events() if e.event_type is RealtimeEventType.AVATAR_FRAME]
    assert len(first_frames) == 1
    assert completion.frames_emitted == 3
    assert len(frames) == 3
    assert [e.payload["frame_index"] for e in frames] == [0, 1, 2]


def test_a_node_that_fails_a_progressive_poll_fails_the_session() -> None:
    provider, node = _remote_provider(frames_per_push=0)
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))

    def _explode(*, session_id: str) -> Sequence[RemoteFramePayload]:
        raise ConnectionError("node closed the stream")

    node.poll_frames = _explode  # type: ignore[method-assign]
    with pytest.raises(RealtimeAvatarError, match="PROGRESSIVE_POLL_FAILED"):
        session.read_frame()
    assert session.state is _S.ERROR
    assert provider.active_session_count == 0


def test_a_node_that_fails_an_audio_push_fails_the_session() -> None:
    """All three engine-facing calls fail the same way, or one of them fails quietly."""
    provider, node = _remote_provider()
    session = provider.start_session(_spec())

    def _explode(*, session_id: str, chunks: Sequence[AudioChunk]) -> None:
        raise ConnectionError("node refused the audio")

    node.push_audio = _explode  # type: ignore[method-assign]
    with pytest.raises(RealtimeAvatarError, match="AUDIO_PUSH_FAILED"):
        session.push_audio_chunk(_chunk(0))
    assert session.state is _S.ERROR
    errors = [e for e in session.events() if e.event_type is RealtimeEventType.PROVIDER_ERROR]
    assert len(errors) == 1
    assert provider.active_session_count == 0


# ------------------------------------------------------------ turn finalisation


def test_final_buffered_audio_reaches_the_node_before_the_turn_is_closed() -> None:
    """The reorder buffer is flushed first, or the last words never get animated."""
    provider, node = _remote_provider(frames_per_push=1)
    session = provider.start_session(_spec())

    assert session.push_audio_chunk(_chunk(1)).disposition == "REORDERED_BUFFERED"
    assert "push_audio:1" not in node.calls

    session.end_turn()
    assert node.calls.index("push_audio:1") < node.calls.index("end_turn")


def test_the_node_is_finalised_and_drained_before_turn_completed_is_emitted() -> None:
    provider, node = _remote_provider(frames_after_end_turn=1)
    session = provider.start_session(_spec())

    seen_at: dict[str, tuple[str, ...]] = {}
    session_events = session.events
    node.on_call = lambda name: seen_at.setdefault(
        name, tuple(e.event_type.value for e in session_events())
    )

    session.push_audio_chunk(_chunk(0))
    completion = session.end_turn()

    assert node.calls.index("end_turn") < node.calls.index("drain_turn")
    assert "turn.completed" not in seen_at["end_turn"]
    assert "turn.completed" not in seen_at["drain_turn"]

    emitted = [e.event_type.value for e in session.events()]
    assert emitted[-1] == "turn.completed"
    # The frame the node only produced at end_turn is part of this turn.
    assert completion.frames_emitted == 3
    assert emitted.count("avatar.frame") == 3


def test_a_node_that_never_confirms_the_drain_is_reported_not_awaited() -> None:
    provider, node = _remote_provider(drain_completes=False)
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))

    completion = session.end_turn()

    assert node.calls.count("drain_turn") == DITTO_FINAL_DRAIN_MAX_POLLS
    assert completion.drain_complete is False
    errors = [e for e in session.events() if e.event_type is RealtimeEventType.PROVIDER_ERROR]
    assert len(errors) == 1
    assert "REMOTE_DRAIN_INCOMPLETE" in str(errors[0].payload["message"])
    completed = [e for e in session.events() if e.event_type is RealtimeEventType.TURN_COMPLETED]
    assert completed[0].payload["drain_complete"] is False
    assert completed[0].payload["final_drain_polls"] == DITTO_FINAL_DRAIN_MAX_POLLS
    assert session.state is _S.READY


def test_a_node_that_fails_at_end_turn_produces_no_completion() -> None:
    provider, node = _remote_provider(end_turn_raises=True)
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))

    with pytest.raises(RealtimeAvatarError, match="TURN_FINALIZATION_FAILED"):
        session.end_turn()

    assert session.state is _S.ERROR
    assert not [e for e in session.events() if e.event_type is RealtimeEventType.TURN_COMPLETED]
    errors = [e for e in session.events() if e.event_type is RealtimeEventType.PROVIDER_ERROR]
    assert len(errors) == 1
    assert provider.active_session_count == 0
    assert node.calls.count("close_session") == 1


def test_a_node_that_fails_mid_drain_produces_no_completion() -> None:
    provider, node = _remote_provider(drain_raises=True)
    session = provider.start_session(_spec())
    session.push_audio_chunk(_chunk(0))

    with pytest.raises(RealtimeAvatarError, match="TURN_FINALIZATION_FAILED"):
        session.end_turn()

    assert "drain_turn" in node.calls
    assert session.state is _S.ERROR
    assert not [e for e in session.events() if e.event_type is RealtimeEventType.TURN_COMPLETED]


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
