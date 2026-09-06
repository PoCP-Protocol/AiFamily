"""DittoAvatarProvider + media verification tests (FAMILY-MEDIA-003).

These tests never download models or run real neural inference.
"""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import pytest

from backend.intelligence.media_factory.benchmark import BenchmarkRunner
from backend.intelligence.media_factory.contracts import (
    CANONICAL_AUDIO_SHA256,
    CANONICAL_IDENTITY_SHA256,
    DITTO_GATE1_ARTIFACT_NAME,
    REAL_GATE1_ARTIFACT_NAME,
    AvatarRenderRequest,
    FamiliAvatarBenchmarkInput,
    MediaFactoryError,
    sha256_file,
)
from backend.intelligence.media_factory.ditto_remote_package import (
    RECOMMENDED_GPU_SPEC,
    build_remote_execution_package,
)
from backend.intelligence.media_factory.gpu_gate import (
    GpuInfo,
    evaluate_gpu_gate,
    evaluate_vram_mib,
)
from backend.intelligence.media_factory.human_gate import empty_human_review_template
from backend.intelligence.media_factory.media_verify import (
    MediaProbeResult,
    frames_are_static_suspect,
    require_verified_avatar_mp4,
)
from backend.intelligence.media_factory.providers.avatar import AvatarProviderRegistry
from backend.intelligence.media_factory.providers.ditto import DittoAvatarProvider
from backend.intelligence.media_factory.providers.fixture import FixtureAvatarProvider


def _write_minimal_png(path: Path, *, width: int = 8, height: int = 8) -> None:
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + (b"\x7f" * width) for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _write_minimal_wav(path: Path, *, duration_s: float = 0.1, rate: int = 16000) -> None:
    nframes = int(rate * duration_s)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * nframes)


def _fail_gpu() -> GpuInfo:
    return GpuInfo(
        model="GeForce GT 730",
        vram_total_mib=2048,
        driver_version="456.71",
        cuda_reported="11.1",
        source="test",
    )


def _pass_gpu() -> GpuInfo:
    return GpuInfo(
        model="NVIDIA A100",
        vram_total_mib=40960,
        driver_version="550.00",
        cuda_reported="12.1",
        source="test",
    )


def _engine_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    engine = tmp_path / "ditto-talkinghead"
    engine.mkdir()
    (engine / "inference.py").write_text("# stub\n", encoding="utf-8")
    py = tmp_path / "ditto-python"
    py.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    model = tmp_path / "checkpoints"
    (model / "ditto_pytorch" / "models").mkdir(parents=True)
    (model / "ditto_cfg").mkdir(parents=True)
    (model / "ditto_cfg" / "v0.4_hubert_cfg_pytorch.pkl").write_bytes(b"pkl")
    return engine, py, model


def test_ditto_provider_is_real_provider() -> None:
    provider = DittoAvatarProvider(gpu_probe=_fail_gpu)
    assert provider.provider_id == "ditto"
    assert provider.capabilities.neural_avatar is True
    assert provider.capabilities.gate1_eligible is True
    assert provider.capabilities.realtime is False
    health = provider.health()
    assert health["real_neural_avatar"] is True
    assert health["synthetic_fixture"] is False
    assert health["first_smoke_backend"] == "pytorch"


def test_ditto_provider_rejects_missing_engine_root(tmp_path: Path) -> None:
    image = tmp_path / "id.png"
    audio = tmp_path / "a.wav"
    _write_minimal_png(image)
    _write_minimal_wav(audio)
    provider = DittoAvatarProvider(
        engine_root="",
        python_executable=str(tmp_path / "missing-python"),
        model_root=tmp_path / "missing-models",
        expected_image_sha256=sha256_file(image),
        expected_audio_sha256=sha256_file(audio),
        gpu_probe=_pass_gpu,
    )
    with pytest.raises(MediaFactoryError, match="MISSING_ENGINE_ROOT"):
        provider.render(
            AvatarRenderRequest(
                source_image=image,
                source_audio=audio,
                output_path=tmp_path / DITTO_GATE1_ARTIFACT_NAME,
                benchmark_run_id="r1",
            )
        )


def test_ditto_provider_rejects_asset_hash_mismatch(tmp_path: Path) -> None:
    image = tmp_path / "id.png"
    audio = tmp_path / "a.wav"
    _write_minimal_png(image)
    _write_minimal_wav(audio)
    engine, py, model = _engine_tree(tmp_path)
    provider = DittoAvatarProvider(
        engine_root=engine,
        python_executable=str(py),
        model_root=model,
        expected_image_sha256=CANONICAL_IDENTITY_SHA256,
        expected_audio_sha256=CANONICAL_AUDIO_SHA256,
        gpu_probe=_pass_gpu,
    )
    with pytest.raises(MediaFactoryError, match="ASSET_HASH_MISMATCH"):
        provider.prepare(source_image=image)
    with pytest.raises(MediaFactoryError, match="ASSET_HASH_MISMATCH"):
        provider.render(
            AvatarRenderRequest(
                source_image=image,
                source_audio=audio,
                output_path=tmp_path / DITTO_GATE1_ARTIFACT_NAME,
                benchmark_run_id="r1",
            )
        )


def test_ditto_provider_marks_real_neural_avatar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "id.png"
    audio = tmp_path / "a.wav"
    _write_minimal_png(image)
    _write_minimal_wav(audio)
    engine, py, model = _engine_tree(tmp_path)
    img_sha = sha256_file(image)
    aud_sha = sha256_file(audio)

    def fake_invoke(*, request: AvatarRenderRequest, raw_out: Path, logs_dir: Path) -> Path:
        raw_out.write_bytes(b"fake-mp4-bytes-for-unit-test")
        (logs_dir / "note.txt").write_text("mocked\n", encoding="utf-8")
        return raw_out

    def fake_verify(path: Path) -> MediaProbeResult:
        return MediaProbeResult(
            path=path,
            exists=True,
            size_bytes=path.stat().st_size,
            duration_seconds=8.8,
            has_video_stream=True,
            has_audio_stream=True,
            fps=25.0,
            width=512,
            height=512,
            frame_count=220,
            artifact_sha256=sha256_file(path),
            static_video_suspected=False,
            gate1_media_eligible=True,
            details={},
        )

    monkeypatch.setattr(
        "backend.intelligence.media_factory.providers.ditto.require_verified_avatar_mp4",
        fake_verify,
    )
    provider = DittoAvatarProvider(
        engine_root=engine,
        python_executable=str(py),
        model_root=model,
        expected_image_sha256=img_sha,
        expected_audio_sha256=aud_sha,
        gpu_probe=_pass_gpu,
        invoke_inference=fake_invoke,
    )
    out = tmp_path / DITTO_GATE1_ARTIFACT_NAME
    result = provider.render(
        AvatarRenderRequest(
            source_image=image,
            source_audio=audio,
            output_path=out,
            benchmark_run_id="mock-ok",
        )
    )
    assert result.real_neural_avatar is True
    assert result.synthetic_fixture is False
    assert result.gate1_eligible is True
    assert result.provider_id == "ditto"
    assert result.provenance["inference_completed"] is True
    assert result.provenance["artifact_verified"] is True
    assert out.is_file()


def test_ditto_provider_does_not_run_when_gpu_gate_fails(tmp_path: Path) -> None:
    image = tmp_path / "id.png"
    audio = tmp_path / "a.wav"
    _write_minimal_png(image)
    _write_minimal_wav(audio)
    engine, py, model = _engine_tree(tmp_path)
    called = {"n": 0}

    def boom(*, request: AvatarRenderRequest, raw_out: Path, logs_dir: Path) -> Path:
        called["n"] += 1
        raise AssertionError("inference must not start")

    provider = DittoAvatarProvider(
        engine_root=engine,
        python_executable=str(py),
        model_root=model,
        expected_image_sha256=sha256_file(image),
        expected_audio_sha256=sha256_file(audio),
        gpu_probe=_fail_gpu,
        invoke_inference=boom,
    )
    with pytest.raises(MediaFactoryError, match="GPU_GATE_FAIL"):
        provider.render(
            AvatarRenderRequest(
                source_image=image,
                source_audio=audio,
                output_path=tmp_path / DITTO_GATE1_ARTIFACT_NAME,
                benchmark_run_id="blocked",
            )
        )
    assert called["n"] == 0
    assert not (tmp_path / DITTO_GATE1_ARTIFACT_NAME).exists()


def test_output_requires_video_stream(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "audio_only.mp4"
    path.write_bytes(b"0" * 9000)

    def fake_probe(_path: Path) -> dict:
        return {
            "streams": [{"codec_type": "audio", "codec_name": "aac"}],
            "format": {"duration": "1.0", "format_name": "mp4"},
        }

    monkeypatch.setattr(
        "backend.intelligence.media_factory.media_verify._run_ffprobe",
        fake_probe,
    )
    monkeypatch.setattr(
        "backend.intelligence.media_factory.media_verify._sample_frame_digests",
        lambda *_a, **_k: [],
    )
    with pytest.raises(MediaFactoryError, match="output_requires_video_stream"):
        require_verified_avatar_mp4(path)


def test_static_video_is_not_gate1_eligible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert frames_are_static_suspect(["aaa", "aaa", "aaa"]) is True
    assert frames_are_static_suspect(["aaa", "bbb"]) is False

    path = tmp_path / "still.mp4"
    path.write_bytes(b"0" * 9000)

    def fake_probe(_path: Path) -> dict:
        return {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 64,
                    "height": 64,
                    "avg_frame_rate": "25/1",
                    "nb_frames": "100",
                },
                {"codec_type": "audio"},
            ],
            "format": {"duration": "4.0", "format_name": "mp4"},
        }

    monkeypatch.setattr(
        "backend.intelligence.media_factory.media_verify._run_ffprobe",
        fake_probe,
    )
    monkeypatch.setattr(
        "backend.intelligence.media_factory.media_verify._sample_frame_digests",
        lambda *_a, **_k: ["same", "same", "same"],
    )
    with pytest.raises(MediaFactoryError, match="STATIC_VIDEO_SUSPECTED"):
        require_verified_avatar_mp4(path)


def test_human_review_remains_pending() -> None:
    template = empty_human_review_template()
    assert template["status"] == "PENDING_HUMAN_REVIEW"
    assert template["gate1"] is None
    assert template["automatic_metrics"]["identity_similarity"] == "NOT_MEASURED"
    assert template["automatic_metrics"]["lip_sync_score"] == "NOT_MEASURED"


def test_fixture_and_ditto_are_not_confused() -> None:
    fixture = FixtureAvatarProvider()
    ditto = DittoAvatarProvider(gpu_probe=_fail_gpu)
    assert fixture.provider_id != ditto.provider_id
    assert fixture.capabilities.neural_avatar is False
    assert ditto.capabilities.neural_avatar is True
    assert fixture.capabilities.gate1_eligible is False
    assert ditto.capabilities.gate1_eligible is True
    registry = AvatarProviderRegistry()
    registry.register(fixture)
    registry.register(ditto)
    assert registry.get("fixture") is fixture
    assert registry.get("ditto") is ditto


def test_gpu_vram_policy_and_remote_package() -> None:
    assert evaluate_vram_mib(2048) == "FAIL"
    assert evaluate_vram_mib(10 * 1024) == "CONDITIONAL"
    assert evaluate_vram_mib(12 * 1024) == "PASS"
    gate = evaluate_gpu_gate(probe=_fail_gpu)
    assert gate.status == "FAIL"
    assert gate.local_real_inference_allowed is False
    package = build_remote_execution_package(
        image_locator="D:/Famili-V2-Reference/FAMILI_V2_IDENTITY_MASTER_R01.png",
        audio_locator="D:/Family/.../FAMILI_RDH_SMOKE_AUDIO_V0.wav",
    )
    assert package["first_smoke_backend"] == "pytorch"
    assert package["upstream"]["commit_sha"]
    assert RECOMMENDED_GPU_SPEC["RECOMMENDED_DEVELOPMENT"]["vram_gb"] == 16
    assert package["forbidden"]


def test_ditto_refuses_master_artifact_name(tmp_path: Path) -> None:
    image = tmp_path / "id.png"
    audio = tmp_path / "a.wav"
    _write_minimal_png(image)
    _write_minimal_wav(audio)
    engine, py, model = _engine_tree(tmp_path)
    provider = DittoAvatarProvider(
        engine_root=engine,
        python_executable=str(py),
        model_root=model,
        expected_image_sha256=sha256_file(image),
        expected_audio_sha256=sha256_file(audio),
        gpu_probe=_pass_gpu,
    )
    with pytest.raises(MediaFactoryError, match=REAL_GATE1_ARTIFACT_NAME):
        provider.render(
            AvatarRenderRequest(
                source_image=image,
                source_audio=audio,
                output_path=tmp_path / REAL_GATE1_ARTIFACT_NAME,
                benchmark_run_id="no-master",
            )
        )


def test_benchmark_writes_runtime_and_provenance_for_fixture(tmp_path: Path) -> None:
    image = tmp_path / "id.png"
    audio = tmp_path / "a.wav"
    _write_minimal_png(image)
    _write_minimal_wav(audio)
    registry = AvatarProviderRegistry()
    registry.register(FixtureAvatarProvider())
    runner = BenchmarkRunner(registry, runs_root=tmp_path / "runs")
    run_dir = runner.run(
        provider_id="fixture",
        benchmark_input=FamiliAvatarBenchmarkInput.from_paths(image, audio),
        run_id="fixture-runtime",
    )
    assert (run_dir / "runtime_manifest.json").is_file()
    assert (run_dir / "provenance.json").is_file()
    assert (run_dir / "logs").is_dir()
    human = json.loads((run_dir / "human_review.json").read_text(encoding="utf-8"))
    assert human["status"] == "PENDING_HUMAN_REVIEW"
    assert human["gate1"] is None
