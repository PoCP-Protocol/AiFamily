"""Provenance helpers for media artifacts.

SOURCE_CONCEPT: AUTOavantar records task/engine metadata beside outputs.
REIMPLEMENTATION_NOTE: rewritten as plain JSON-friendly dicts; no SQLite.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build_run_provenance(
    *,
    benchmark_run_id: str,
    provider_id: str,
    input_manifest: Mapping[str, Any],
    execution_target: str,
) -> dict[str, Any]:
    """Build mandatory provenance for a benchmark run.

    execution_target is LOCAL or REMOTE_GPU_NODE (boundary only; no cluster code).
    """
    if execution_target not in {"LOCAL", "REMOTE_GPU_NODE"}:
        raise ValueError(f"unsupported execution_target: {execution_target}")
    return {
        "benchmark_run_id": benchmark_run_id,
        "provider_id": provider_id,
        "recorded_at": utc_now_iso(),
        "execution_target": execution_target,
        "input_image_sha256": input_manifest.get("image_sha256"),
        "input_audio_sha256": input_manifest.get("audio_sha256"),
        "may_mutate_business_state": False,
        "writes_family_canonical_truth": False,
    }
