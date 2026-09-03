"""Minimal Gate1 benchmark runner.

SOURCE_CONCEPT: AUTOavantar isolates each task's outputs.
REIMPLEMENTATION_NOTE: filesystem run dirs + JSON manifests only; no SQLite/FIFO.

Supports fixture today; neural candidates are selected by provider_id via registry
without hardcoding Ditto/MuseTalk/HeyGem.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from backend.intelligence.media_factory.contracts import (
    DITTO_GATE1_ARTIFACT_NAME,
    REAL_GATE1_ARTIFACT_NAME,
    AvatarRenderRequest,
    FamiliAvatarBenchmarkInput,
    MediaFactoryError,
)
from backend.intelligence.media_factory.gpu_gate import evaluate_gpu_gate
from backend.intelligence.media_factory.human_gate import empty_human_review_template
from backend.intelligence.media_factory.provenance import build_run_provenance
from backend.intelligence.media_factory.providers.avatar import AvatarProviderRegistry


def default_runs_root(repo_root: Path | None = None) -> Path:
    """Benchmark artifacts stay out of git by default."""
    root = repo_root or Path.cwd()
    return root / "artifacts" / "media_factory" / "benchmark_runs"


class BenchmarkRunner:
    def __init__(
        self,
        registry: AvatarProviderRegistry,
        *,
        runs_root: Path,
        execution_target: str = "LOCAL",
    ) -> None:
        self._registry = registry
        self._runs_root = Path(runs_root)
        self._execution_target = execution_target

    def run(
        self,
        *,
        provider_id: str,
        benchmark_input: FamiliAvatarBenchmarkInput,
        run_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> Path:
        if not benchmark_input.image_sha256 or not benchmark_input.audio_sha256:
            raise MediaFactoryError("benchmark input hashes are required")

        provider = self._registry.get(provider_id)
        run_id = run_id or uuid.uuid4().hex
        run_dir = self._runs_root / run_id
        if run_dir.exists():
            raise MediaFactoryError(f"run directory already exists: {run_dir}")
        run_dir.mkdir(parents=True, exist_ok=False)

        caps = provider.capabilities
        if provider_id == "fixture":
            artifact_name = "fixture_output.bin"
        elif provider_id == "ditto":
            artifact_name = DITTO_GATE1_ARTIFACT_NAME
        elif caps.gate1_eligible and caps.neural_avatar:
            artifact_name = REAL_GATE1_ARTIFACT_NAME
        else:
            artifact_name = "output.mp4"
        if provider_id == "fixture" and artifact_name == REAL_GATE1_ARTIFACT_NAME:
            raise MediaFactoryError("fixture cannot use real Gate1 filename")

        output_path = run_dir / artifact_name
        logs_dir = run_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        input_manifest = benchmark_input.to_manifest()
        (run_dir / "input_manifest.json").write_text(
            json.dumps(input_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        runtime_manifest = {
            "benchmark_run_id": run_id,
            "provider_id": provider_id,
            "execution_target": self._execution_target,
            "gpu_gate": evaluate_gpu_gate().to_manifest(),
            "artifact_name": artifact_name,
        }
        (run_dir / "runtime_manifest.json").write_text(
            json.dumps(runtime_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        provider.prepare(source_image=benchmark_input.image_path)
        result = provider.render(
            AvatarRenderRequest(
                source_image=benchmark_input.image_path,
                source_audio=benchmark_input.audio_path,
                output_path=output_path,
                benchmark_run_id=run_id,
                config=config or {},
            )
        )

        if result.provenance is None:
            raise MediaFactoryError("provenance is required on AvatarRenderResult")

        run_provenance = build_run_provenance(
            benchmark_run_id=run_id,
            provider_id=provider.provider_id,
            input_manifest=input_manifest,
            execution_target=self._execution_target,
        )
        run_provenance["render_provenance"] = dict(result.provenance)
        (run_dir / "provenance.json").write_text(
            json.dumps(run_provenance, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        provider_manifest = {
            "provider_id": provider.provider_id,
            "capabilities": {
                "offline_render": caps.offline_render,
                "realtime": caps.realtime,
                "neural_avatar": caps.neural_avatar,
                "gate1_eligible": caps.gate1_eligible,
            },
            "health": provider.health(),
            "run_provenance": run_provenance,
            "render": result.to_manifest(),
        }
        (run_dir / "provider_manifest.json").write_text(
            json.dumps(provider_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        metrics = {
            "automatic": {
                "identity_similarity": "NOT_MEASURED",
                "lip_sync_score": "NOT_MEASURED",
                "temporal_stability": "NOT_MEASURED",
            },
            "runtime_seconds": result.runtime_seconds,
            "peak_vram_mb": result.peak_vram_mb,
            "note": "Automatic quality scores are NOT_MEASURED until a real evaluator exists.",
        }
        (run_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        human_review = empty_human_review_template()
        human_review["artifact_path"] = str(result.artifact_path)
        human_review["provider_id"] = provider.provider_id
        human_review["ditto_gate1_status"] = (
            "PENDING_HUMAN_REVIEW"
            if result.real_neural_avatar and result.gate1_eligible
            else "NOT_APPLICABLE"
        )
        (run_dir / "human_review.json").write_text(
            json.dumps(human_review, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        return run_dir
