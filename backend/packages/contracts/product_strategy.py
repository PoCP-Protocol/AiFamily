"""Product strategy contracts migrated from family-ai.

These models carry provenance and remain non-canonical strategy artifacts.
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
