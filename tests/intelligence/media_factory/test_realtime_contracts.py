"""Realtime avatar contract, protocol and metrics tests (FAMILY-REALTIME-001).

No GPU, no network, no engine. These tests cover the provider-neutral half of
the realtime foundation: the audio/frame shapes every provider must honour, the
event envelope, and the metrics schema's refusal to invent numbers.
"""

from __future__ import annotations

import pytest

from backend.intelligence.media_factory.realtime.contracts import (
    REALTIME_CONTRACT_VERSION,
    REQUIRED_AUDIO_SAMPLE_RATE_HZ,
    AudioChunk,
    AudioChunkRejectedError,
    AvatarFrame,
    IdentitySpec,
    PreparedIdentity,
    RealtimeAvatarError,
    RealtimeProviderCapabilities,
    RealtimeSessionSpec,
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
from backend.intelligence.media_factory.realtime.transport import (
    TRANSPORT_BINDINGS,
    binary_ref_for_frame,
    binding_for,
    encode_control_frame,
    transport_manifest,
)

PCM16_20MS_AT_16K = b"\x00\x01" * 320


def _chunk(**overrides: object) -> AudioChunk:
    kwargs: dict[str, object] = {
        "session_id": "s1",
        "turn_id": "t1",
        "sequence": 0,
        "presentation_time_ms": 0,
        "payload": PCM16_20MS_AT_16K,
    }
    kwargs.update(overrides)
    return AudioChunk(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------- AudioChunk


def test_audio_chunk_defaults_to_pcm16_mono_16k() -> None:
    chunk = _chunk()
    assert chunk.audio_format == "PCM16"
    assert chunk.channels == 1
    assert chunk.sample_rate_hz == REQUIRED_AUDIO_SAMPLE_RATE_HZ
    assert chunk.sample_count == 320
    assert chunk.duration_ms == 20
    assert len(chunk.payload_sha256) == 64
    assert chunk.to_manifest()["sequence"] == 0


def test_audio_chunk_carries_turn_and_presentation_time() -> None:
    chunk = _chunk(sequence=7, presentation_time_ms=140, turn_id="turn-2", is_final=True)
    assert chunk.turn_id == "turn-2"
    assert chunk.sequence == 7
    assert chunk.presentation_time_ms == 140
    assert chunk.is_final is True


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"sample_rate_hz": 48000}, "sample_rate_hz"),
        ({"channels": 2}, "mono"),
        ({"sequence": -1}, "sequence"),
        ({"presentation_time_ms": -5}, "presentation_time_ms"),
        ({"payload": b"\x00\x01\x02"}, "even number of bytes"),
        ({"turn_id": ""}, "session_id and turn_id"),
    ],
)
def test_audio_chunk_rejects_wrong_shape(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(AudioChunkRejectedError, match=match):
        _chunk(**overrides)


def test_audio_chunk_rejects_non_pcm16_format() -> None:
    with pytest.raises(AudioChunkRejectedError, match="audio_format"):
        AudioChunk(
            session_id="s1",
            turn_id="t1",
            sequence=0,
            presentation_time_ms=0,
            payload=PCM16_20MS_AT_16K,
            audio_format="OPUS",  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------- AvatarFrame


def test_avatar_frame_exposes_required_fields() -> None:
    frame = AvatarFrame(
        session_id="s1",
        turn_id="t1",
        frame_index=0,
        sequence=0,
        presentation_time_ms=0,
        width=512,
        height=512,
        frame_format="RGB24",
        payload=b"\x00" * 12,
        is_first_frame=True,
        real_neural_inference=True,
    )
    assert frame.size == (512, 512)
    manifest = frame.to_manifest()
    assert manifest["frame_index"] == 0
    assert manifest["presentation_time_ms"] == 0
    assert manifest["width"] == 512
    assert manifest["height"] == 512
    assert manifest["frame_format"] == "RGB24"
    assert manifest["payload_bytes"] == 12
    assert manifest["sequence"] == 0
    assert manifest["real_neural_inference"] is True


def test_avatar_frame_requires_exactly_one_payload_form() -> None:
    with pytest.raises(RealtimeAvatarError, match="exactly one of payload"):
        AvatarFrame(
            session_id="s1",
            turn_id="t1",
            frame_index=0,
            sequence=0,
            presentation_time_ms=0,
            width=8,
            height=8,
            frame_format="RGB24",
        )
    with pytest.raises(RealtimeAvatarError, match="exactly one of payload"):
        AvatarFrame(
            session_id="s1",
            turn_id="t1",
            frame_index=0,
            sequence=0,
            presentation_time_ms=0,
            width=8,
            height=8,
            frame_format="RGB24",
            payload=b"\x00",
            payload_ref="frame://s1/t1/0",
        )


def test_synthetic_frame_cannot_claim_real_neural_inference() -> None:
    with pytest.raises(RealtimeAvatarError, match="FIXTURE_SYNTHETIC"):
        AvatarFrame(
            session_id="s1",
            turn_id="t1",
            frame_index=0,
            sequence=0,
            presentation_time_ms=0,
            width=8,
            height=8,
            frame_format="FIXTURE_SYNTHETIC",
            payload=b"\x00",
            real_neural_inference=True,
        )


# -------------------------------------------------------------------- capabilities


def test_capabilities_must_accept_the_required_audio_shape() -> None:
    with pytest.raises(RealtimeAvatarError, match="PCM16"):
        RealtimeProviderCapabilities(
            provider_id="p",
            streaming_audio_in=True,
            progressive_frames_out=True,
            interruption_supported=False,
            real_neural_inference=False,
            realtime_gate_eligible=False,
            gate_ineligible_reason="test",
            execution_locality="IN_PROCESS",
            max_concurrent_sessions=1,
            accepted_audio_formats=("OPUS",),
            emitted_frame_formats=("RGB24",),
        )


def test_gate_eligibility_requires_real_neural_inference() -> None:
    with pytest.raises(RealtimeAvatarError, match="realtime_gate_eligible requires"):
        RealtimeProviderCapabilities(
            provider_id="p",
            streaming_audio_in=True,
            progressive_frames_out=True,
            interruption_supported=False,
            real_neural_inference=False,
            realtime_gate_eligible=True,
            execution_locality="IN_PROCESS",
            max_concurrent_sessions=1,
            emitted_frame_formats=("FIXTURE_SYNTHETIC",),
        )


def test_gate_ineligibility_must_state_a_reason() -> None:
    with pytest.raises(RealtimeAvatarError, match="must state why"):
        RealtimeProviderCapabilities(
            provider_id="p",
            streaming_audio_in=True,
            progressive_frames_out=True,
            interruption_supported=False,
            real_neural_inference=False,
            realtime_gate_eligible=False,
            execution_locality="IN_PROCESS",
            max_concurrent_sessions=1,
            emitted_frame_formats=("FIXTURE_SYNTHETIC",),
        )


def test_capabilities_manifest_declares_contract_version() -> None:
    caps = RealtimeProviderCapabilities(
        provider_id="p",
        streaming_audio_in=True,
        progressive_frames_out=True,
        interruption_supported=False,
        real_neural_inference=False,
        realtime_gate_eligible=False,
        gate_ineligible_reason="fixture",
        execution_locality="IN_PROCESS",
        max_concurrent_sessions=2,
        emitted_frame_formats=("FIXTURE_SYNTHETIC",),
    )
    assert caps.to_manifest()["contract_version"] == REALTIME_CONTRACT_VERSION


# ------------------------------------------------------------------------ identity


def test_identity_spec_uses_an_opaque_locator_not_a_path() -> None:
    spec = IdentitySpec(
        identity_id="famili", image_locator="node://identities/famili", image_sha256="a" * 64
    )
    assert spec.image_locator.startswith("node://")
    with pytest.raises(RealtimeAvatarError, match="64 hex"):
        IdentitySpec(identity_id="x", image_locator="node://x", image_sha256="short")


def test_prepared_identity_requires_a_handle() -> None:
    with pytest.raises(RealtimeAvatarError, match="requires a handle"):
        PreparedIdentity(
            identity_id="x",
            identity_handle="",
            image_sha256="a" * 64,
            provider_id="p",
            real_neural_inference=False,
        )


def test_session_spec_rejects_unsupported_sample_rate() -> None:
    with pytest.raises(RealtimeAvatarError, match="sample_rate_hz"):
        RealtimeSessionSpec(
            session_id="s1",
            identity_handle="h",
            trace_id="tr1",
            sample_rate_hz=44100,
        )


# ------------------------------------------------------------------------ protocol


def test_every_protocol_event_type_is_declared() -> None:
    assert {e.value for e in RealtimeEventType} == {
        "session.started",
        "audio.accepted",
        "avatar.first_frame",
        "avatar.frame",
        "turn.completed",
        "session.cancelled",
        "session.closed",
        "provider.error",
    }


def test_event_envelope_carries_correlation_fields_not_just_success() -> None:
    emitter = RealtimeEventEmitter(session_id="s1", trace_id="trace-9", clock=lambda: 1234)
    event = emitter.emit(
        RealtimeEventType.AVATAR_FRAME,
        turn_id="t1",
        payload={"frame_index": 3},
        binary_ref="frame://s1/t1/3",
    )
    envelope = event.to_envelope()
    assert envelope["session_id"] == "s1"
    assert envelope["turn_id"] == "t1"
    assert envelope["trace_id"] == "trace-9"
    assert envelope["sequence"] == 0
    assert envelope["type"] == "avatar.frame"
    assert envelope["emitted_at_ms"] == 1234
    assert envelope["protocol_version"] == REALTIME_PROTOCOL_VERSION
    assert envelope["binary_ref"] == "frame://s1/t1/3"
    assert "success" not in envelope


def test_event_sequence_is_monotonic() -> None:
    emitter = RealtimeEventEmitter(session_id="s1", trace_id="tr")
    emitter.emit(RealtimeEventType.SESSION_STARTED)
    emitter.emit(RealtimeEventType.AUDIO_ACCEPTED, turn_id="t1")
    emitter.emit(RealtimeEventType.SESSION_CLOSED)
    assert [e.sequence for e in emitter.events] == [0, 1, 2]


def test_turn_scoped_events_require_a_turn_id() -> None:
    with pytest.raises(RealtimeAvatarError, match="turn-scoped"):
        RealtimeEvent(
            event_type=RealtimeEventType.TURN_COMPLETED,
            session_id="s1",
            sequence=0,
            trace_id="tr",
            emitted_at_ms=0,
        )


def test_first_frame_event_cannot_be_emitted_twice_for_one_turn() -> None:
    emitter = RealtimeEventEmitter(session_id="s1", trace_id="tr")
    emitter.emit(RealtimeEventType.AVATAR_FIRST_FRAME, turn_id="t1")
    assert emitter.first_frame_emitted_for("t1") is True
    with pytest.raises(RealtimeAvatarError, match="DUPLICATE_FIRST_FRAME"):
        emitter.emit(RealtimeEventType.AVATAR_FIRST_FRAME, turn_id="t1")
    # A different turn gets its own first frame.
    emitter.emit(RealtimeEventType.AVATAR_FIRST_FRAME, turn_id="t2")
    assert len(emitter.events_of_type(RealtimeEventType.AVATAR_FIRST_FRAME)) == 2


# ----------------------------------------------------------------------- transport


def test_transport_declares_websocket_v0_and_planned_webrtc() -> None:
    kinds = {binding.kind: binding for binding in TRANSPORT_BINDINGS}
    assert kinds["WEBSOCKET"].status == "BINDING_DECLARED"
    assert kinds["WEBRTC"].status == "PLANNED"
    # No server ships in FAMILY-REALTIME-001.
    assert all(binding.server_implemented is False for binding in TRANSPORT_BINDINGS)
    assert transport_manifest()["server_implemented"] is False
    assert binding_for("WEBSOCKET") is kinds["WEBSOCKET"]
    with pytest.raises(ValueError, match="unknown transport kind"):
        binding_for("CARRIER_PIGEON")  # type: ignore[arg-type]


def test_control_frame_encoding_is_the_protocol_envelope() -> None:
    emitter = RealtimeEventEmitter(session_id="s1", trace_id="tr", clock=lambda: 5)
    event = emitter.emit(RealtimeEventType.SESSION_STARTED)
    assert encode_control_frame(event) == event.to_envelope()
    assert binary_ref_for_frame(session_id="s1", turn_id="t1", frame_sequence=4) == (
        "frame://s1/t1/4"
    )


# ------------------------------------------------------------------------- metrics


def test_unmeasured_metrics_are_not_run_not_zero() -> None:
    metrics = not_run_metrics(note="no GPU node")
    manifest = metrics.to_manifest()
    assert manifest["schema"] == REALTIME_METRICS_SCHEMA
    for field_name in (
        "identity_prepare_ms",
        "audio_chunk_to_motion_ms",
        "first_frame_latency_ms",
        "frame_interval_ms",
        "effective_fps",
        "dropped_frames",
        "queue_depth",
        "gpu_memory_mb",
    ):
        assert manifest[field_name] == NOT_RUN, field_name
    assert metrics.measured is False
    assert metrics.realtime_gate_eligible is False


def test_metrics_accept_unknown_for_attempted_but_unavailable() -> None:
    metrics = RealtimeMetrics(
        first_frame_latency_ms=41.5,
        gpu_memory_mb=UNKNOWN,
        source="REMOTE_GPU_NODE_ATTESTED",
        real_neural_inference=True,
    )
    assert metrics.measured is True
    assert metrics.realtime_gate_eligible is True
    assert metrics.to_manifest()["gpu_memory_mb"] == UNKNOWN


def test_metrics_reject_fabricated_or_illegal_values() -> None:
    with pytest.raises(RealtimeAvatarError, match="effective_fps"):
        RealtimeMetrics(effective_fps="25ish")  # type: ignore[arg-type]
    with pytest.raises(RealtimeAvatarError, match="must be >= 0"):
        RealtimeMetrics(first_frame_latency_ms=-1)


def test_fixture_measured_metrics_are_never_gate_eligible() -> None:
    metrics = RealtimeMetrics(
        effective_fps=25.0,
        source="FIXTURE_SYNTHETIC",
        real_neural_inference=False,
    )
    assert metrics.measured is True
    assert metrics.realtime_gate_eligible is False


def test_recorder_derives_fps_from_observed_frames() -> None:
    ticks = iter([0.0, 0.0, 0.1, 0.2, 0.3, 0.4])
    recorder = RealtimeMetricsRecorder(
        source="FIXTURE_SYNTHETIC",
        real_neural_inference=False,
        clock=lambda: next(ticks),
    )
    recorder.record_identity_prepare(12.0)
    recorder.start_turn()
    for _ in range(4):
        recorder.record_frame()
    snapshot = recorder.snapshot()
    assert snapshot.identity_prepare_ms == 12.0
    assert snapshot.first_frame_latency_ms == 0.0
    assert snapshot.frame_interval_ms == 100.0
    assert snapshot.effective_fps == 10.0
    assert snapshot.gpu_memory_mb == UNKNOWN


def test_recorder_reports_unknown_when_there_is_no_interval() -> None:
    recorder = RealtimeMetricsRecorder(source="FIXTURE_SYNTHETIC", real_neural_inference=False)
    recorder.start_turn()
    recorder.record_frame()
    snapshot = recorder.snapshot()
    assert snapshot.effective_fps == UNKNOWN
    assert snapshot.frame_interval_ms == UNKNOWN
    assert snapshot.identity_prepare_ms == UNKNOWN
