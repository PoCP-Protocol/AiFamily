"""Realtime provider contract tests — fixture provider and registry.

FIXTURE_REALTIME_GATE_ELIGIBLE=FALSE. Everything in this file runs against a
deterministic synthetic generator; none of it is evidence that a realtime avatar
exists. It is evidence that the contract, the state machine and the protocol
behave the same way for any provider that implements them.
"""

from __future__ import annotations

import pytest

from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    IdentitySpec,
    InvalidSessionTransitionError,
    RealtimeAvatarError,
    RealtimeSessionSpec,
)
from backend.intelligence.media_factory.realtime.fixture_provider import (
    FixtureRealtimeAvatarProvider,
)
from backend.intelligence.media_factory.realtime.protocol import RealtimeEventType
from backend.intelligence.media_factory.realtime.provider import (
    RealtimeAvatarProvider,
    RealtimeAvatarProviderRegistry,
    RealtimeAvatarSession,
)
from backend.intelligence.media_factory.realtime.session_state import RealtimeSessionState

_S = RealtimeSessionState

PCM16_100MS_AT_16K = b"\x00\x01" * 1600


def _chunk(sequence: int, *, turn_id: str = "turn-1", is_final: bool = False) -> AudioChunk:
    return AudioChunk(
        session_id="sess-1",
        turn_id=turn_id,
        sequence=sequence,
        presentation_time_ms=sequence * 100,
        payload=PCM16_100MS_AT_16K,
        is_final=is_final,
    )


def _session_spec(**overrides: object) -> RealtimeSessionSpec:
    kwargs: dict[str, object] = {
        "session_id": "sess-1",
        "identity_handle": "fixture:famili:abc",
        "trace_id": "trace-1",
        "target_fps": 10,
        "frame_width": 64,
        "frame_height": 64,
    }
    kwargs.update(overrides)
    return RealtimeSessionSpec(**kwargs)  # type: ignore[arg-type]


@pytest.fixture
def provider() -> FixtureRealtimeAvatarProvider:
    return FixtureRealtimeAvatarProvider()


# ------------------------------------------------------------ provider contract


def test_fixture_provider_satisfies_the_provider_protocol(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    assert isinstance(provider, RealtimeAvatarProvider)
    for verb in (
        "capabilities",
        "health",
        "prepare_identity",
        "start_session",
        "close",
    ):
        assert callable(getattr(provider, verb)), verb


def test_fixture_session_satisfies_the_session_protocol(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    assert isinstance(session, RealtimeAvatarSession)
    for verb in (
        "push_audio_chunk",
        "end_turn",
        "read_frame",
        "cancel",
        "close",
        "metrics",
        "events",
    ):
        assert callable(getattr(session, verb)), verb


def test_fixture_provider_reports_itself_ineligible(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    caps = provider.capabilities()
    assert caps.real_neural_inference is False
    assert caps.realtime_gate_eligible is False
    assert caps.gate_ineligible_reason
    assert caps.emitted_frame_formats == ("FIXTURE_SYNTHETIC",)

    health = provider.health()
    assert health["REAL_NEURAL_INFERENCE"] == "FALSE"
    assert health["REALTIME_GATE_ELIGIBLE"] == "FALSE"
    assert health["synthetic_fixture"] is True


def test_fixture_identity_prepare_returns_an_opaque_handle(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    prepared = provider.prepare_identity(
        IdentitySpec(
            identity_id="famili",
            image_locator="node://identities/famili.png",
            image_sha256="d" * 64,
        )
    )
    assert prepared.identity_handle.startswith("fixture:famili:")
    assert prepared.real_neural_inference is False
    assert prepared.to_manifest()["provider_id"] == "fixture_realtime"


# --------------------------------------------------------------- registry


def test_registry_fails_closed_on_unknown_provider(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    registry = RealtimeAvatarProviderRegistry()
    registry.register(provider)
    assert registry.list_ids() == ("fixture_realtime",)
    assert registry.get("fixture_realtime") is provider
    with pytest.raises(RealtimeAvatarError, match="unknown realtime avatar provider"):
        registry.get("does_not_exist")


def test_registry_reports_no_gate_eligible_providers_yet(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    registry = RealtimeAvatarProviderRegistry()
    registry.register(provider)
    assert registry.gate_eligible_ids() == ()


# ------------------------------------------------------------------ turn flow


def test_session_start_emits_session_started_and_reaches_ready(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    assert session.state is _S.READY
    assert session.state_history == (_S.CREATED, _S.PREPARING, _S.READY)
    started = [e for e in session.events() if e.event_type is RealtimeEventType.SESSION_STARTED]
    assert len(started) == 1
    assert started[0].payload["real_neural_inference"] is False


def test_ordered_chunks_produce_progressive_frames(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    assert session.state is _S.GENERATING
    assert session.turn_id == "turn-1"

    # 100 ms of audio at 10 fps is one frame, available before the turn ends.
    first = session.read_frame()
    assert first is not None
    assert first.frame_index == 0
    assert first.is_first_frame is True
    assert first.frame_format == "FIXTURE_SYNTHETIC"
    assert first.real_neural_inference is False
    assert session.read_frame() is None

    session.push_audio_chunk(_chunk(1))
    second = session.read_frame()
    assert second is not None
    assert second.frame_index == 1
    assert second.is_first_frame is False
    assert second.presentation_time_ms == 100


def test_frames_are_deterministic_for_the_same_session(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    payloads = []
    for _ in range(2):
        session = FixtureRealtimeAvatarProvider().start_session(_session_spec())
        session.push_audio_chunk(_chunk(0))
        frame = session.read_frame()
        assert frame is not None and frame.payload is not None
        payloads.append(frame.payload)
    assert payloads[0] == payloads[1]


def test_out_of_order_chunks_do_not_reorder_frames(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    assert session.push_audio_chunk(_chunk(1)).disposition == "REORDERED_BUFFERED"
    assert session.state is _S.RECEIVING_AUDIO
    assert session.read_frame() is None

    assert session.push_audio_chunk(_chunk(0)).disposition == "ACCEPTED"
    frames = [session.read_frame(), session.read_frame()]
    assert [f.frame_index for f in frames if f is not None] == [0, 1]


def test_duplicate_chunk_does_not_produce_a_second_frame(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    assert session.push_audio_chunk(_chunk(0)).disposition == "DUPLICATE_IGNORED"
    assert session.read_frame() is not None
    assert session.read_frame() is None


def test_first_frame_event_is_emitted_exactly_once_per_turn(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    for sequence in range(3):
        session.push_audio_chunk(_chunk(sequence))
    first_frames = [
        e for e in session.events() if e.event_type is RealtimeEventType.AVATAR_FIRST_FRAME
    ]
    frames = [e for e in session.events() if e.event_type is RealtimeEventType.AVATAR_FRAME]
    assert len(first_frames) == 1
    assert len(frames) == 3
    assert first_frames[0].turn_id == "turn-1"

    session.end_turn()
    session.push_audio_chunk(_chunk(0, turn_id="turn-2"))
    second_turn_first = [
        e
        for e in session.events()
        if e.event_type is RealtimeEventType.AVATAR_FIRST_FRAME and e.turn_id == "turn-2"
    ]
    assert len(second_turn_first) == 1


def test_turn_completion_reports_what_the_turn_actually_did(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    session.push_audio_chunk(_chunk(1, is_final=True))
    completion = session.end_turn()

    assert completion.turn_id == "turn-1"
    assert completion.audio_chunks_consumed == 2
    assert completion.audio_duration_ms == 200
    assert completion.frames_emitted == 2
    assert completion.first_frame_emitted is True
    assert completion.cancelled is False

    assert session.state is _S.READY
    assert session.turn_id is None
    completed = [e for e in session.events() if e.event_type is RealtimeEventType.TURN_COMPLETED]
    assert len(completed) == 1
    assert completed[0].payload["missing_audio_sequences"] == []


def test_turn_completion_reports_gaps_left_by_lost_chunks(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    session.push_audio_chunk(_chunk(2))
    completion = session.end_turn()
    assert completion.audio_chunks_consumed == 2
    completed = [e for e in session.events() if e.event_type is RealtimeEventType.TURN_COMPLETED]
    assert completed[0].payload["missing_audio_sequences"] == [1]


def test_a_second_turn_reuses_the_session(provider: FixtureRealtimeAvatarProvider) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    session.end_turn()
    session.push_audio_chunk(_chunk(0, turn_id="turn-2"))
    completion = session.end_turn()
    assert completion.turn_id == "turn-2"
    assert session.state is _S.READY


def test_mixing_turn_ids_inside_one_open_turn_is_refused(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    with pytest.raises(RealtimeAvatarError, match="still open"):
        session.push_audio_chunk(_chunk(0, turn_id="turn-2"))


def test_end_turn_without_an_open_turn_is_refused(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    with pytest.raises(InvalidSessionTransitionError, match="INVALID_SESSION_STATE"):
        session.end_turn()


# -------------------------------------------------------------- cancel / close


def test_cancel_drops_queued_frames_and_is_idempotent(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    session.push_audio_chunk(_chunk(1))

    session.cancel(reason="user_barge_in")
    assert session.state is _S.CANCELLED
    cancelled = [e for e in session.events() if e.event_type is RealtimeEventType.SESSION_CANCELLED]
    assert len(cancelled) == 1
    assert cancelled[0].payload["reason"] == "user_barge_in"
    assert cancelled[0].payload["dropped_frames"] == 2
    assert session.metrics().dropped_frames == 2

    session.cancel(reason="again")
    assert session.state is _S.CANCELLED
    assert (
        len([e for e in session.events() if e.event_type is RealtimeEventType.SESSION_CANCELLED])
        == 1
    )


def test_cancelled_session_refuses_audio_and_frames(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    session.cancel(reason="stop")
    with pytest.raises(InvalidSessionTransitionError):
        session.push_audio_chunk(_chunk(1))
    with pytest.raises(InvalidSessionTransitionError):
        session.read_frame()


def test_close_is_terminal_and_idempotent(provider: FixtureRealtimeAvatarProvider) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    session.close()
    assert session.state is _S.CLOSED
    closed = [e for e in session.events() if e.event_type is RealtimeEventType.SESSION_CLOSED]
    assert len(closed) == 1

    session.close()
    assert (
        len([e for e in session.events() if e.event_type is RealtimeEventType.SESSION_CLOSED]) == 1
    )
    with pytest.raises(InvalidSessionTransitionError):
        session.push_audio_chunk(_chunk(1))


def test_cancel_then_close_records_the_cancel_reason(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    session.cancel(reason="interrupted")
    session.close()
    closed = [e for e in session.events() if e.event_type is RealtimeEventType.SESSION_CLOSED]
    assert closed[0].payload["cancel_reason"] == "interrupted"


def test_provider_close_closes_open_sessions(provider: FixtureRealtimeAvatarProvider) -> None:
    session = provider.start_session(_session_spec())
    provider.close()
    assert session.state is _S.CLOSED
    assert provider.health()["open_sessions"] == 0


def test_provider_error_event_is_available(provider: FixtureRealtimeAvatarProvider) -> None:
    session = provider.start_session(_session_spec())
    session.fail("engine reported a decode failure")
    assert session.state is _S.ERROR
    errors = [e for e in session.events() if e.event_type is RealtimeEventType.PROVIDER_ERROR]
    assert len(errors) == 1
    assert errors[0].payload["provider_id"] == "fixture_realtime"


# ------------------------------------------------------------------- metrics


def test_fixture_metrics_are_measured_but_never_gate_eligible(
    provider: FixtureRealtimeAvatarProvider,
) -> None:
    session = provider.start_session(_session_spec())
    for sequence in range(3):
        session.push_audio_chunk(_chunk(sequence))
    metrics = session.metrics()
    assert metrics.source == "FIXTURE_SYNTHETIC"
    assert metrics.real_neural_inference is False
    assert metrics.realtime_gate_eligible is False
    assert metrics.gpu_memory_mb == "UNKNOWN"
    assert metrics.queue_depth == 3


def test_event_envelopes_are_json_shaped(provider: FixtureRealtimeAvatarProvider) -> None:
    session = provider.start_session(_session_spec())
    session.push_audio_chunk(_chunk(0))
    envelopes = session.event_envelopes()
    assert envelopes[0]["type"] == "session.started"
    assert {e["session_id"] for e in envelopes} == {"sess-1"}
    assert {e["trace_id"] for e in envelopes} == {"trace-1"}
    assert [e["sequence"] for e in envelopes] == list(range(len(envelopes)))
