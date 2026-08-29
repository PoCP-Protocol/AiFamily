"""FastAPI dependency wiring. Real auth/repository/interpretation-provider
implementations are injected by `apps/family_api` at process startup; this
module defines the shape (`FamilyContext`) and default-raising stubs so the
domain package has no hard dependency on any concrete infra choice.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from ..application.commands import AssessmentCommandHandler
from ..application.growth_hypothesis_commands import GrowthHypothesisCommandHandler
from ..application.queries import AssessmentQueryHandler


@dataclass(frozen=True)
class FamilyContext:
    tenant_id: str
    family_id: str
    person_id: str


def get_family_context() -> FamilyContext:
    raise HTTPException(status_code=500, detail="get_family_context_not_wired")


def get_command_handler() -> AssessmentCommandHandler:
    raise HTTPException(status_code=500, detail="command_handler_not_wired")


def get_query_handler() -> AssessmentQueryHandler:
    raise HTTPException(status_code=500, detail="query_handler_not_wired")


def get_growth_hypothesis_handler() -> GrowthHypothesisCommandHandler:
    raise HTTPException(status_code=500, detail="growth_hypothesis_handler_not_wired")
