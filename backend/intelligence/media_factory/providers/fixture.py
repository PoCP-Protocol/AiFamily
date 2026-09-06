"""FixtureAvatarProvider — contract harness only.

NOT a real neural avatar. GATE1_ELIGIBLE is always false.
Must never write FAMILI_REAL_AVATAR_V1.mp4.
"""

from __future__ import annotations

import time
from pathlib import Path

from backend.intelligence.media_factory.contracts import (
    REAL_GATE1_ARTIFACT_NAME,
    AvatarProviderCapabilities,
    AvatarRenderRequest,
    AvatarRenderResult,
    MediaFactoryError,
    sha256_file,
)


class FixtureAvatarProvider:
    """Synthetic provider for runner/provenance tests."""

    provider_id = "fixture"

    def __init__(self, *, provider_version: str = "0.1.0") -> None:
        self.provider_version = provider_version

    @property
    def capabilities(self) -> AvatarProviderCapabilities:
        return AvatarProviderCapabilities(
            offline_render=True,
            realtime=False,
            neural_avatar=False,
            gate1_eligible=False,
        )

    def health(self) -> dict[str, object]:
        return {
            "ok": True,
            "provider_id": self.provider_id,
            "real_neural_avatar": False,
            "gate1_eligible": False,
        }

    def prepare(self, *, source_image: object) -> dict[str, object]:
        path = Path(str(source_image))
        if not path.is_file():
            raise MediaFactoryError(f"prepare: image missing: {path}")
        return {"prepared": True, "source_image": str(path.resolve())}

    def render(self, request: AvatarRenderRequest) -> AvatarRenderResult:
        if request.output_path.name == REAL_GATE1_ARTIFACT_NAME:
            raise MediaFactoryError(f"fixture provider must not write {REAL_GATE1_ARTIFACT_NAME}")
        if not request.source_image.is_file() or not request.source_audio.is_file():
            raise MediaFactoryError("fixture render requires existing image and audio")

        started = time.perf_counter()
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        # Explicitly non-media synthetic bytes — metadata carries the truth.
        payload = (
            b"FAMILI_FIXTURE_AVATAR_ARTIFACT_V0\n"
            b"synthetic_fixture=true\n"
            b"real_neural_avatar=false\n"
            b"gate1_eligible=false\n"
        )
        request.output_path.write_bytes(payload)
        elapsed = time.perf_counter() - started
        digest = sha256_file(request.output_path)

        return AvatarRenderResult(
            artifact_path=request.output_path.resolve(),
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            model="fixture-noop",
            model_version="none",
            provenance={
                "synthetic_fixture": True,
                "real_neural_avatar": False,
                "gate1_eligible": False,
                "benchmark_run_id": request.benchmark_run_id,
            },
            warnings=("FIXTURE_ONLY: not a neural avatar; Gate1 ineligible",),
            runtime_seconds=elapsed,
            resolution=None,
            fps=None,
            duration_seconds=None,
            peak_vram_mb=None,
            artifact_sha256=digest,
            synthetic_fixture=True,
            real_neural_avatar=False,
            gate1_eligible=False,
        )
