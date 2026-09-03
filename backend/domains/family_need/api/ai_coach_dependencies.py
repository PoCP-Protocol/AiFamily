"""Dependency seam for the AI Coach HTTP route.

Same fail-closed convention as `dependencies.py` / `fulfillment_dependencies.py`
in this package: the default implementation raises 503 so an unwired process
cannot silently answer with a fabricated or unauthorised model call. Only a
composition root (`backend/apps/family_api/dev_wiring.py` for dev, or a future
production wiring module for real DeepSeek traffic) may override
`get_ai_coach_deps`.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from backend.domains.journey.application.outcome_loop import GrowthOutcomeLoop
from backend.intelligence.model_gateway.gateway import ModelGateway

from ..application.ports import FamilyNeedRepositoryPort


@dataclass(frozen=True)
class AiCoachDeps:
    """Everything the AI Coach route needs: a governed gateway plus the
    repository the domain-side context assembly reads from.

    `outcome_loop` is optional (`None` in a caller/test that does not wire
    journey continuity) — see `request_coach_perspective`'s own docstring
    for why the minimal signature stays supported."""

    gateway: ModelGateway
    repository: FamilyNeedRepositoryPort
    provider_id: str
    outcome_loop: GrowthOutcomeLoop | None = None


def get_ai_coach_deps() -> AiCoachDeps:
    raise HTTPException(status_code=503, detail="ai_coach_not_wired")


__all__ = ["AiCoachDeps", "get_ai_coach_deps"]
