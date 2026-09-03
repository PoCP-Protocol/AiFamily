"""Gate1 media_factory foundation tests (FAMILY-MEDIA-002)."""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import pytest
import yaml

from backend.intelligence.media_factory.benchmark import BenchmarkRunner
from backend.intelligence.media_factory.contracts import (
    REAL_GATE1_ARTIFACT_NAME,
    AvatarRenderRequest,
    FamiliAvatarBenchmarkInput,
    MediaFactoryError,
    sha256_file,
)
from backend.intelligence.media_factory.human_gate import HumanReviewScores, evaluate_gate1
from backend.intelligence.media_factory.providers.avatar import AvatarProviderRegistry
from backend.intelligence.media_factory.providers.fixture import FixtureAvatarProvider


def _write_minimal_png(path: Path, *, width: int = 8, height: int = 8) -> None:
    # 1x1-ish uncompressed IHDR-only minimal is hard; write a tiny valid PNG via zlib.
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    # Greyscale PNG (color type 0): filter byte + width samples per row.
    raw = b"".join(b"\x00" + (b"\x7f" * width) for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _write_minimal_wav(path: Path, *, duration_s: float = 0.1, rate: int = 16000) -> None:
    nframes = int(rate * duration_s)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * nframes)


@pytest.fixture
def tiny_assets(tmp_path: Path) -> tuple[Path, Path]:
    image = tmp_path / "id.png"
    audio = tmp_path / "smoke.wav"
    _write_minimal_png(image)
    _write_minimal_wav(audio)
    return image, audio


def test_avatar_provider_contract(tiny_assets: tuple[Path, Path]) -> None:
    image, audio = tiny_assets
    provider = FixtureAvatarProvider()
    assert provider.provider_id == "fixture"
    assert provider.capabilities.gate1_eligible is False
    assert provider.capabilities.neural_avatar is False
    health = provider.health()
    assert health["ok"] is True
    prepared = provider.prepare(source_image=image)
    assert prepared["prepared"] is True
    out = tiny_assets[0].parent / "out.bin"
    result = provider.render(
        AvatarRenderRequest(
            source_image=image,
            source_audio=audio,
            output_path=out,
            benchmark_run_id="run-test",
        )
    )
    assert result.gate1_eligible is False
    assert result.synthetic_fixture is True
    assert result.real_neural_avatar is False
    assert "provenance" in result.to_manifest()


def test_benchmark_input_hashes_are_required(tiny_assets: tuple[Path, Path]) -> None:
    image, audio = tiny_assets
    with pytest.raises(MediaFactoryError, match="required"):
        FamiliAvatarBenchmarkInput(
            image_path=image,
            audio_path=audio,
            image_sha256="",
            audio_sha256="",
            image_width=1,
            image_height=1,
            audio_sample_rate_hz=16000,
            audio_channels=1,
            audio_duration_ms=100,
        )
    loaded = FamiliAvatarBenchmarkInput.from_paths(image, audio)
    assert len(loaded.image_sha256) == 64
    assert len(loaded.audio_sha256) == 64
    assert loaded.image_sha256 == sha256_file(image)


def test_benchmark_run_isolated(tiny_assets: tuple[Path, Path], tmp_path: Path) -> None:
    image, audio = tiny_assets
    registry = AvatarProviderRegistry()
    registry.register(FixtureAvatarProvider())
    runner = BenchmarkRunner(registry, runs_root=tmp_path / "runs")
    inp = FamiliAvatarBenchmarkInput.from_paths(image, audio)
    run_a = runner.run(provider_id="fixture", benchmark_input=inp, run_id="aaa")
    run_b = runner.run(provider_id="fixture", benchmark_input=inp, run_id="bbb")
    assert run_a != run_b
    assert (run_a / "input_manifest.json").is_file()
    assert (run_a / "provider_manifest.json").is_file()
    assert (run_a / "metrics.json").is_file()
    assert (run_a / "human_review.json").is_file()
    with pytest.raises(MediaFactoryError, match="already exists"):
        runner.run(provider_id="fixture", benchmark_input=inp, run_id="aaa")


def test_fixture_provider_is_not_gate1_eligible() -> None:
    provider = FixtureAvatarProvider()
    assert provider.capabilities.gate1_eligible is False
    assert FixtureAvatarProvider().render  # existence
    result_caps = provider.capabilities
    assert result_caps.neural_avatar is False


def test_real_gate_filename_rejected_for_fixture(
    tiny_assets: tuple[Path, Path], tmp_path: Path
) -> None:
    image, audio = tiny_assets
    provider = FixtureAvatarProvider()
    with pytest.raises(MediaFactoryError, match=REAL_GATE1_ARTIFACT_NAME):
        provider.render(
            AvatarRenderRequest(
                source_image=image,
                source_audio=audio,
                output_path=tmp_path / REAL_GATE1_ARTIFACT_NAME,
                benchmark_run_id="x",
            )
        )


def test_identity_hard_fail_forces_gate_failure() -> None:
    review = HumanReviewScores(
        identity_preservation=5.0,
        lip_sync=5.0,
        motion_naturalness=5.0,
        temporal_face_stability=5.0,
        expression_quality=5.0,
        eye_blink_gaze=5.0,
        performance=5.0,
        identity_hard_fail=True,
        identity_hard_fail_reasons=("face becomes another person",),
    )
    verdict = evaluate_gate1(review)
    assert verdict.gate1 == "FAIL"
    assert verdict.identity_hard_fail is True
    assert verdict.weighted_score is None


def test_missing_provider_fails_closed() -> None:
    registry = AvatarProviderRegistry()
    with pytest.raises(MediaFactoryError, match="unknown avatar provider"):
        registry.get("ditto")


def test_provenance_required(tiny_assets: tuple[Path, Path], tmp_path: Path) -> None:
    image, audio = tiny_assets
    registry = AvatarProviderRegistry()
    registry.register(FixtureAvatarProvider())
    runner = BenchmarkRunner(registry, runs_root=tmp_path / "runs")
    run_dir = runner.run(
        provider_id="fixture",
        benchmark_input=FamiliAvatarBenchmarkInput.from_paths(image, audio),
        run_id="prov",
    )
    payload = json.loads((run_dir / "provider_manifest.json").read_text(encoding="utf-8"))
    assert payload["run_provenance"]["may_mutate_business_state"] is False
    assert payload["run_provenance"]["writes_family_canonical_truth"] is False
    assert payload["render"]["provenance"]
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["automatic"]["identity_similarity"] == "NOT_MEASURED"


def test_candidate_quality_scores_are_not_prepopulated() -> None:
    candidates_dir = (
        Path(__file__).resolve().parents[3]
        / "governance"
        / "media_factory"
        / "candidates"
    )
    active_expected = {"DITTO", "ECHOMIMIC_V3_FLASH", "SADTALKER"}
    deferred_expected = {"MUSETALK", "HEYGEM"}
    active_found: set[str] = set()
    deferred_found: set[str] = set()

    for path in sorted(candidates_dir.glob("*.yaml")):
        if path.name == "SHORTLIST.yaml":
            shortlist = yaml.safe_load(path.read_text(encoding="utf-8"))
            assert shortlist["winner"] == "UNKNOWN"
            assert shortlist["quality_scores_prepopulated"] is False
            assert set(shortlist["active_gate1_candidates"]) == active_expected
            assert set(shortlist["deferred_candidates"]) == deferred_expected
            continue

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["benchmark_status"] == "NOT_RUN"
        assert data.get("quality_scores") in (None, {})
        assert data.get("winner", "UNKNOWN") == "UNKNOWN"
        for key in ("identity_score", "lip_sync_score", "overall_score"):
            assert key not in data

        participation = data.get("gate1_participation")
        if participation == "ACTIVE":
            active_found.add(data["candidate_id"])
        elif participation == "DEFERRED":
            deferred_found.add(data["candidate_id"])
            assert data.get("deferred_class")
        else:
            raise AssertionError(f"{path.name}: gate1_participation must be ACTIVE or DEFERRED")

    assert active_found == active_expected
    assert deferred_found == deferred_expected
