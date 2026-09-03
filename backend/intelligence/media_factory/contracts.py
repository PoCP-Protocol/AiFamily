"""Contracts for Gate1 offline avatar benchmark (ADR-0018).

Providers decide pixels. They do not decide Family identity, Principal replies,
or course logic. Hashes on inputs are mandatory so candidate engines can be
compared fairly.
"""

from __future__ import annotations

import hashlib
import struct
import wave
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GATE1_BENCHMARK_VERSION = "FAMILI_GATE1_BENCHMARK_V0"

# Frozen Gate1 identity + audio (governance/assets/FAMILI_V2_VISUAL_ASSET_REGISTRY.yaml).
CANONICAL_IDENTITY_SHA256 = "da7fe9d0ebc30b9f2aedd5fc55a08d04749d605e530137300e55719d498535aa"
CANONICAL_AUDIO_SHA256 = "bf0ecbe6af18235f872e1dc8f29061f4c67bb101a5de56bba3fd9efc0c684912"

REAL_GATE1_ARTIFACT_NAME = "FAMILI_REAL_AVATAR_V1.mp4"


class MediaFactoryError(Exception):
    """Fail-closed error for benchmark / provider boundaries."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise MediaFactoryError(f"not a PNG: {path}")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def wav_probe(path: Path) -> tuple[int, int, float]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_rate = handle.getframerate()
        frames = handle.getnframes()
        duration_s = frames / float(sample_rate) if sample_rate else 0.0
    return channels, sample_rate, duration_s


@dataclass(frozen=True, slots=True)
class FamiliAvatarBenchmarkInput:
    """Frozen input contract for one Gate1 run."""

    image_path: Path
    audio_path: Path
    image_sha256: str
    audio_sha256: str
    image_width: int
    image_height: int
    audio_sample_rate_hz: int
    audio_channels: int
    audio_duration_ms: int
    benchmark_version: str = GATE1_BENCHMARK_VERSION

    def __post_init__(self) -> None:
        if not self.image_sha256 or not self.audio_sha256:
            raise MediaFactoryError("image_sha256 and audio_sha256 are required")
        if len(self.image_sha256) != 64 or len(self.audio_sha256) != 64:
            raise MediaFactoryError("sha256 digests must be 64 hex characters")

    @classmethod
    def from_paths(
        cls,
        image_path: Path,
        audio_path: Path,
        *,
        expected_image_sha256: str | None = None,
        expected_audio_sha256: str | None = None,
        benchmark_version: str = GATE1_BENCHMARK_VERSION,
    ) -> FamiliAvatarBenchmarkInput:
        image = Path(image_path)
        audio = Path(audio_path)
        if not image.is_file():
            raise MediaFactoryError(f"image missing: {image}")
        if not audio.is_file():
            raise MediaFactoryError(f"audio missing: {audio}")

        image_sha = sha256_file(image)
        audio_sha = sha256_file(audio)
        if expected_image_sha256 is not None and image_sha != expected_image_sha256:
            raise MediaFactoryError(
                f"image sha256 mismatch: got {image_sha}, expected {expected_image_sha256}"
            )
        if expected_audio_sha256 is not None and audio_sha != expected_audio_sha256:
            raise MediaFactoryError(
                f"audio sha256 mismatch: got {audio_sha}, expected {expected_audio_sha256}"
            )

        width, height = png_dimensions(image)
        channels, sample_rate, duration_s = wav_probe(audio)
        return cls(
            image_path=image.resolve(),
            audio_path=audio.resolve(),
            image_sha256=image_sha,
            audio_sha256=audio_sha,
            image_width=width,
            image_height=height,
            audio_sample_rate_hz=sample_rate,
            audio_channels=channels,
            audio_duration_ms=int(round(duration_s * 1000)),
            benchmark_version=benchmark_version,
        )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "benchmark_version": self.benchmark_version,
            "image_path": str(self.image_path),
            "audio_path": str(self.audio_path),
            "image_sha256": self.image_sha256,
            "audio_sha256": self.audio_sha256,
            "image_dimensions": {
                "width": self.image_width,
                "height": self.image_height,
            },
            "audio": {
                "sample_rate_hz": self.audio_sample_rate_hz,
                "channels": self.audio_channels,
                "duration_ms": self.audio_duration_ms,
            },
        }


@dataclass(frozen=True, slots=True)
class AvatarProviderCapabilities:
    offline_render: bool
    realtime: bool
    neural_avatar: bool
    gate1_eligible: bool


@dataclass(frozen=True, slots=True)
class AvatarRenderRequest:
    source_image: Path
    source_audio: Path
    output_path: Path
    benchmark_run_id: str
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AvatarRenderResult:
    artifact_path: Path
    provider_id: str
    provider_version: str
    model: str
    model_version: str
    provenance: Mapping[str, Any]
    warnings: tuple[str, ...]
    runtime_seconds: float
    resolution: tuple[int, int] | None
    fps: float | None
    duration_seconds: float | None
    peak_vram_mb: float | None
    artifact_sha256: str
    synthetic_fixture: bool
    real_neural_avatar: bool
    gate1_eligible: bool

    def to_manifest(self) -> dict[str, Any]:
        return {
            "artifact_path": str(self.artifact_path),
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "model": self.model,
            "model_version": self.model_version,
            "provenance": dict(self.provenance),
            "warnings": list(self.warnings),
            "runtime_seconds": self.runtime_seconds,
            "resolution": (
                {"width": self.resolution[0], "height": self.resolution[1]}
                if self.resolution
                else None
            ),
            "fps": self.fps,
            "duration_seconds": self.duration_seconds,
            "peak_vram_mb": self.peak_vram_mb,
            "artifact_sha256": self.artifact_sha256,
            "synthetic_fixture": self.synthetic_fixture,
            "real_neural_avatar": self.real_neural_avatar,
            "gate1_eligible": self.gate1_eligible,
        }


@dataclass(frozen=True, slots=True)
class Gate1Verdict:
    gate1: str
    identity_hard_fail: bool
    weighted_score: float | None
    reason: str
