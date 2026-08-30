"""Response DTOs for Product Factory draft endpoints.

Responses are intentionally explicit about their non-final status.  They do
not expose a method or field that could be interpreted as a business-fact
write; publication remains a separate human-gated command.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DraftEnvelopeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    status: Literal["DRAFT"] = "DRAFT"
    evidence_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    unknowns: tuple[str, ...]
    next_validation: str
    expires_at: datetime
    provenance_ref: str | None = None
    model_ref: str | None = None
    prompt_use_case_version: str | None = None
    confidence: float | None = None
    requires_human_confirmation: Literal[True] = True
    may_mutate_business_state: Literal[False] = False


class DemandFrameDraftResponse(DraftEnvelopeResponse):
    demand_id: str
    statement: str
    scenario: str
    source_refs: tuple[str, ...]
    target_segment: str
    locale: str
    purpose: str


class MarketInsightDraftResponse(DraftEnvelopeResponse):
    insight_id: str
    demand_ref: str
    statement: str
    source_refs: tuple[str, ...]
    competitor_evidence_refs: tuple[str, ...]
    segment_ref: str | None = None


class CompetitorEvidenceCardResponse(DraftEnvelopeResponse):
    evidence_id: str
    competitor_ref: str
    claim: str
    source_refs: tuple[str, ...]
    evidence_status: Literal["VERIFIED", "UNKNOWN", "STALE", "CONTRADICTED"]
    demand_ref: str | None = None
    market_insight_ref: str | None = None
    source_type: str


class ProductPackageDraftResponse(DraftEnvelopeResponse):
    draft_id: str
    # Deprecated compatibility slot.  Product Factory does not create a
    # ProductDefinition; this remains null until a human-gated adoption.
    product_definition_id: str | None = None
    concept_id: str
    product_kind: Literal["MICRO_CAMP", "SCALE_PLAN", "CUSTOM"]
    duration_days: int
    zone: str
    demand_ref: str
    market_insight_refs: tuple[str, ...]
    competitor_evidence_refs: tuple[str, ...]
    component_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]


__all__ = [
    "CompetitorEvidenceCardResponse",
    "DemandFrameDraftResponse",
    "DraftEnvelopeResponse",
    "MarketInsightDraftResponse",
    "ProductPackageDraftResponse",
]
