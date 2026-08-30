"""Compatibility facade for the Model Gateway provenance contract.

``AiProvenance`` already has one canonical definition in ``contracts.py``.
This module is intentionally only a narrow import seam for consumers that need
to construct a gateway provenance record; it does not introduce a second
provenance model, persistence layer, audit writer, or business-state operation.

The similarly named ``backend.packages.contracts.evidence.Provenance`` belongs
to evidence grading in product domains.  It is a different concept and is not
re-exported here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    DataClass,
    TokenUsage,
)

ModelGatewayProvenance = AiProvenance
"""Explicit name for the gateway provenance type without duplicating it."""


@dataclass(frozen=True, slots=True)
class ModelDraftIdentity:
    """Stable draft and provenance references derived from one runtime id."""

    draft_id: str
    provenance_ref: str

    @classmethod
    def from_run_id(cls, run_id: str) -> ModelDraftIdentity:
        """Create server-owned references without accepting a blank or huge id."""

        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("model draft run_id is required")
        value = run_id.strip()
        if len(value) > 128:
            raise ValueError("model draft run_id is too long")
        return cls(draft_id=f"draft:{value}", provenance_ref=f"model-draft:{value}")


def build_provenance(
    *,
    provider_id: str,
    model: str,
    model_version: str,
    prompt_version: str,
    schema_version: str,
    context_snapshot_ref: str,
    latency_ms: int,
    data_class: DataClass,
    use_case: str,
    confidence: float | None = None,
    token_usage: TokenUsage | None = None,
    generated_at: datetime | None = None,
) -> AiProvenance:
    """Build the canonical, complete provenance value object.

    Required identity fields remain required here as they are in
    ``AiProvenance``.  Validation is deliberately delegated to that canonical
    constructor so the facade cannot drift from the gateway contract.
    """

    values: dict[str, object] = {
        "provider_id": provider_id,
        "model": model,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "context_snapshot_ref": context_snapshot_ref,
        "latency_ms": latency_ms,
        "data_class": data_class,
        "use_case": use_case,
        "confidence": confidence,
        "token_usage": token_usage,
    }
    if generated_at is not None:
        values["generated_at"] = generated_at
    return AiProvenance(**values)  # type: ignore[arg-type]


__all__ = [
    "AiProvenance",
    "ModelDraftIdentity",
    "ModelGatewayProvenance",
    "build_provenance",
]
