"""Product Strategy schemas — STRUCTURE_ONLY.

No TS predecessor. Authored directly against
`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md`
§4 (Signal→Insight chain) and §1 (already-approved P0 increment:
`GrowthHypothesis` gaining a `primary_contradiction_ref` field).

Every schema below carries a required `provenance: Provenance` field with no
default — see `evidence.py`. This is the type-level half of the "simulated
data cannot self-certify" guardrail; the behavioural half lives in
`domains/product_strategy/domain/entities.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from .evidence import Provenance

OpportunityStatus = Literal["INVEST", "EXPERIMENT", "WATCH", "MAINTAIN", "EXIT"]


class MarketSignal(BaseModel):
    signal_id: str
    raw_text: str
    observed_at: datetime
    provenance: Provenance


class SignalCluster(BaseModel):
    cluster_id: str
    signal_ids: list[str]
    label: str
    provenance: Provenance


class Trend(BaseModel):
    trend_id: str
    cluster_ids: list[str]
    description: str
    provenance: Provenance


class CustomerInsight(BaseModel):
    insight_id: str
    trend_id: str | None
    segment_ref: str | None
    statement: str
    provenance: Provenance


class GrowthProblem(BaseModel):
    problem_id: str
    symptom: str
    insight_id: str | None
    provenance: Provenance


class GrowthHypothesis(BaseModel):
    """Mirrors the already-approved P0 increment: existing Python-side
    `hypotheses` structures (per DRAFT doc §1) already gained a
    `primary_contradiction_ref` + confidence ordering field. This schema is
    the standalone-contract restatement of that shape for the skeleton
    domains that don't yet share the assessment domain's real entity module.
    """

    hypothesis_id: str
    problem_id: str
    statement: str
    primary_contradiction_ref: str | None = None
    confidence_rank: int | None = None
    provenance: Provenance


class Opportunity(BaseModel):
    opportunity_id: str
    problem_id: str
    status: OpportunityStatus
    customer_value: float | None = None
    market_momentum: float | None = None
    unmet_need: float | None = None
    evidence_strength: float | None = None
    strategic_fit: float | None = None
    capability_fit: float | None = None
    defensibility: float | None = None
    provenance: Provenance
