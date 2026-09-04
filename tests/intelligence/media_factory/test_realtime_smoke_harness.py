"""Remote Ditto online smoke harness tests (FAMILY-REALTIME-001 §12).

The harness is prepared, not executed. These tests exercise the WAV splitter on
a locally generated file and assert that the plan and the report both say
REAL_DITTO_ONLINE_SMOKE=NOT_RUN.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from backend.intelligence.media_factory.contracts import (
    CANONICAL_AUDIO_SHA256,
    CANONICAL_IDENTITY_SHA256,
)
from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunkRejectedError,
    RealtimeSessionSpec,
)
from backend.intelligence.media_factory.realtime.ditto_online_smoke import (
    SMOKE_HARNESS_ID,
    SUPPORTED_CHUNK_MS,
    build_ditto_online_smoke_plan,
    not_run_report,
    split_wav_to_chunks,
)
from backend.intelligence.media_factory.realtime.fixture_provider import (
    FixtureRealtimeAvatarProvider,
)
from backend.intelligence.media_factory.realtime.metrics import NOT_RUN


def _write_wav(
    path: Path,
    *,
    duration_s: float = 1.0,
    rate: int = 16000,
    channels: int = 1,
    sample_width: int = 2,
) -> Path:
    frames = int(rate * duration_s)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(rate)
        handle.writeframes(b"\x01\x00" * frames * channels)
    return path


def test_wav_splits_into_20ms_chunks(tmp_path: Path) -> None:
    wav = _write_wav(tmp_path / "smoke.wav", duration_s=1.0)
    chunks = split_wav_to_chunks(wav, session_id="s1", turn_id="t1", chunk_ms=20)

    assert len(chunks) == 50
    assert [c.sequence for c in chunks] == list(range(50))
    assert all(c.duration_ms == 20 for c in chunks)
    assert [c.presentation_time_ms for c in chunks[:3]] == [0, 20, 40]
    assert chunks[-1].is_final is True
    assert sum(c.is_final for c in chunks) == 1
    assert all(c.sample_rate_hz == 16000 and c.channels == 1 for c in chunks)


def test_wav_splits_into_40ms_chunks(tmp_path: Path) -> None:
    wav = _write_wav(tmp_path / "smoke.wav", duration_s=1.0)
    chunks = split_wav_to_chunks(wav, session_id="s1", turn_id="t1", chunk_ms=40)
    assert len(chunks) == 25
    assert all(c.duration_ms == 40 for c in chunks)
    assert SUPPORTED_CHUNK_MS == (20, 40)


def test_splitter_refuses_to_resample_or_downmix(tmp_path: Path) -> None:
    stereo = _write_wav(tmp_path / "stereo.wav", channels=2)
    with pytest.raises(AudioChunkRejectedError, match="mono"):
        split_wav_to_chunks(stereo, session_id="s1", turn_id="t1")

    resampled = _write_wav(tmp_path / "48k.wav", rate=48000)
    with pytest.raises(AudioChunkRejectedError, match="does not resample"):
        split_wav_to_chunks(resampled, session_id="s1", turn_id="t1")

    eight_bit = _write_wav(tmp_path / "8bit.wav", sample_width=1)
    with pytest.raises(AudioChunkRejectedError, match="PCM16"):
        split_wav_to_chunks(eight_bit, session_id="s1", turn_id="t1")


def test_splitter_rejects_unsupported_chunk_size_and_missing_file(tmp_path: Path) -> None:
    wav = _write_wav(tmp_path / "smoke.wav")
    with pytest.raises(AudioChunkRejectedError, match="chunk_ms"):
        split_wav_to_chunks(wav, session_id="s1", turn_id="t1", chunk_ms=33)
    with pytest.raises(AudioChunkRejectedError, match="missing"):
        split_wav_to_chunks(tmp_path / "nope.wav", session_id="s1", turn_id="t1")


def test_smoke_plan_is_a_plan_not_a_run() -> None:
    plan = build_ditto_online_smoke_plan(
        identity_locator="node://frozen/FAMILI_V2_IDENTITY_MASTER_R01.png",
        audio_locator="node://frozen/FAMILI_RDH_SMOKE_AUDIO_V0.wav",
        chunk_ms=40,
    )
    assert plan["harness_id"] == SMOKE_HARNESS_ID
    assert plan["execution"]["auto_executed_by_agent"] is False
    assert plan["execution"]["requires_human_operator"] is True
    assert plan["execution"]["REAL_DITTO_ONLINE_SMOKE"] == "NOT_RUN"

    assert plan["frozen_inputs"]["identity"]["sha256"] == CANONICAL_IDENTITY_SHA256
    assert plan["frozen_inputs"]["audio"]["sha256"] == CANONICAL_AUDIO_SHA256
    assert plan["chunking"]["chunk_ms"] == 40
    assert plan["upstream"]["verified_locally"] is False

    assert set(plan["record_fields"]) >= {
        "audio_chunk_count",
        "first_frame",
        "frame_count",
        "effective_fps",
        "first_frame_latency_ms",
        "total_runtime_ms",
        "errors",
    }
    forbidden = " ".join(plan["forbidden"]).lower()
    assert "purchase" in forbidden
    assert "ssh" in forbidden
    assert plan["node_boundary"]["node_may_write_family_truth"] is False
    assert plan["engine_isolation"]["engine_in_aifamily_worktree"] is False


def test_smoke_plan_rejects_unsupported_chunk_size() -> None:
    with pytest.raises(AudioChunkRejectedError, match="chunk_ms"):
        build_ditto_online_smoke_plan(
            identity_locator="node://a",
            audio_locator="node://b",
            chunk_ms=15,
        )


def test_unexecuted_report_reads_as_not_run() -> None:
    report = not_run_report(note="GPU node offline")
    manifest = report.to_manifest()
    assert manifest["REAL_DITTO_ONLINE_SMOKE"] == "NOT_RUN"
    assert manifest["executed"] is False
    for field_name in (
        "audio_chunk_count",
        "first_frame",
        "frame_count",
        "effective_fps",
        "first_frame_latency_ms",
        "total_runtime_ms",
        "real_neural_inference",
    ):
        assert manifest[field_name] == NOT_RUN, field_name
    assert manifest["errors"] == []


def test_split_chunks_drive_a_fixture_session_end_to_end(tmp_path: Path) -> None:
    """The harness output is a valid provider input — proven without a GPU.

    This is a plumbing check, not a smoke result: the provider is the fixture,
    so no frame here came from an engine.
    """
    wav = _write_wav(tmp_path / "smoke.wav", duration_s=0.4)
    chunks = split_wav_to_chunks(wav, session_id="sess-h", turn_id="turn-h", chunk_ms=40)
    assert len(chunks) == 10

    provider = FixtureRealtimeAvatarProvider()
    session = provider.start_session(
        RealtimeSessionSpec(
            session_id="sess-h",
            identity_handle="fixture:famili:abc",
            trace_id="trace-h",
            target_fps=25,
        )
    )
    for chunk in chunks:
        session.push_audio_chunk(chunk)
    completion = session.end_turn()

    assert completion.audio_chunks_consumed == 10
    assert completion.audio_duration_ms == 400
    assert completion.frames_emitted == 10
    assert session.metrics().real_neural_inference is False
    assert session.metrics().realtime_gate_eligible is False
