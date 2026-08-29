"""API response DTOs — reuse the domain entities directly as response
models (same pattern acceptable at this PR's scale; assessment domain uses
dedicated response DTOs, but this domain's entities have no field that must
be hidden from the API, so no separate response type is introduced here).
"""
from __future__ import annotations

from pydantic import BaseModel

from ..domain.entities import (
    GrowthHypothesis,
    GrowthProblem,
    GrowthStrategy,
    MarketSignal,
    Opportunity,
    ProductConcept,
)
from ..domain.entities import CustomerInsight


class ProductConceptChainResponse(BaseModel):
    product_concept: ProductConcept
    growth_strategy: GrowthStrategy
    growth_problem: GrowthProblem
    growth_hypotheses: list[GrowthHypothesis]
    opportunity: Opportunity | None
    customer_insight: CustomerInsight | None
    market_signal: MarketSignal | None
