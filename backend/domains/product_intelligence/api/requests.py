"""API request DTOs — acceptance chain only (Override #6 item 2).

PR-001R (chief-architect review on PR #27, item 3): `created_by` /
`tenant_scope` removed from every request — they come exclusively from the
authenticated `ActorContext` (see `dependencies.py::get_actor_context`),
never from the request body. `generated_by` removed too: it is always
derived from `context.actor_id` when `context.actor_type == "AI"` (see
`application/commands.py`), so a client cannot claim AI authorship for a
human-submitted request or vice versa. `ValidateGrowthHypothesisRequest`'s
`human_actor` field is replaced by `reason` — actor identity/type come from
`ActorContext`, not a client-supplied field.
"""
from __future__ import annotations

from pydantic import BaseModel


class CreateMarketSignalRequest(BaseModel):
    raw_text: str
    source_ref: str | None = None


class CreateCustomerInsightRequest(BaseModel):
    signal_id: str
    statement: str
    model_ref: str | None = None
    prompt_use_case_version: str | None = None
    confidence: float | None = None


class CreateOpportunityRequest(BaseModel):
    insight_id: str
    statement: str
    model_ref: str | None = None
    prompt_use_case_version: str | None = None
    confidence: float | None = None


class CreateGrowthProblemRequest(BaseModel):
    opportunity_id: str
    symptom: str


class CreateGrowthHypothesisRequest(BaseModel):
    problem_id: str
    statement: str
    model_ref: str | None = None
    prompt_use_case_version: str | None = None
    confidence: float | None = None


class CreateGrowthStrategyRequest(BaseModel):
    problem_id: str
    hypothesis_ids: list[str]
    statement: str
    model_ref: str | None = None
    prompt_use_case_version: str | None = None
    confidence: float | None = None


class CreateProductConceptRequest(BaseModel):
    strategy_id: str
    title: str
    description: str | None = None
    model_ref: str | None = None
    prompt_use_case_version: str | None = None
    confidence: float | None = None


class ValidateGrowthHypothesisRequest(BaseModel):
    reason: str
