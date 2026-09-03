"""Gate1 Offline Avatar Benchmark Foundation (ADR-0018).

SOURCE_CONCEPT (AUTOavantar, selective reimplementation — do not copy trees):
  - isolated run directories / artifact manifests
  - provider load/unload lifecycle as a *boundary*, not HeyGem binding
  - provenance fields on every artifact

LICENSE_NOTE: AUTOavantar root has no OSS LICENSE file; only concepts are reused.

This package must never write Family canonical truth (R9).
"""

from __future__ import annotations

from backend.intelligence.media_factory.benchmark import (
    BenchmarkRunner,
    default_runs_root,
)
from backend.intelligence.media_factory.contracts import (
    DITTO_GATE1_ARTIFACT_NAME,
    REAL_GATE1_ARTIFACT_NAME,
    AvatarProviderCapabilities,
    AvatarRenderRequest,
    AvatarRenderResult,
    FamiliAvatarBenchmarkInput,
    Gate1Verdict,
)
from backend.intelligence.media_factory.human_gate import (
    GATE1_WEIGHTS,
    HumanReviewScores,
    evaluate_gate1,
)
from backend.intelligence.media_factory.providers import (
    AvatarProvider,
    AvatarProviderRegistry,
    DittoAvatarProvider,
    FixtureAvatarProvider,
)

__all__ = [
    "GATE1_WEIGHTS",
    "DITTO_GATE1_ARTIFACT_NAME",
    "REAL_GATE1_ARTIFACT_NAME",
    "AvatarProvider",
    "AvatarProviderCapabilities",
    "AvatarProviderRegistry",
    "AvatarRenderRequest",
    "AvatarRenderResult",
    "BenchmarkRunner",
    "DittoAvatarProvider",
    "FamiliAvatarBenchmarkInput",
    "FixtureAvatarProvider",
    "Gate1Verdict",
    "HumanReviewScores",
    "default_runs_root",
    "evaluate_gate1",
]
