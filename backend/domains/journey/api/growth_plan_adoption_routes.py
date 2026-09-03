"""HTTP boundary for adopting a validated generative family growth plan."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..application.growth_plan_adoption import (
    AdoptGrowthPlanCommand,
    GrowthPlanActor,
    GrowthPlanAdoptionService,
)
from ..domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)

GrowthPlanActorResolver = Callable[[str | None, str], Awaitable[GrowthPlanActor]]


class GrowthPlanAuthenticationError(Exception):
    def __init__(self, code: str = "authentication_required") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class GrowthPlanAdoptionHttpDependencies:
    resolve_actor: GrowthPlanActorResolver
    service: GrowthPlanAdoptionService


class AdoptGrowthPlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_ref: str = Field(min_length=1, max_length=256)
    draft_version: int = Field(ge=1)
    selected_choices: dict[str, str]


def build_growth_plan_adoption_router(
    dependencies: GrowthPlanAdoptionHttpDependencies,
) -> APIRouter:
    router = APIRouter(prefix="/families", tags=["journey-growth-plan"])

    @router.get("/{family_id}/growth/generative-plan")
    async def get_current_growth_plan(
        family_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        actor = await _actor(dependencies, authorization, family_id)
        _assert_family(actor, family_id)
        return await _call(lambda: dependencies.service.get_current(actor))

    @router.post("/{family_id}/growth/generative-plan/adopt")
    async def adopt_growth_plan(
        family_id: str,
        body: AdoptGrowthPlanBody,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        actor = await _actor(dependencies, authorization, family_id)
        _assert_family(actor, family_id)
        return await _call(
            lambda: dependencies.service.adopt(
                AdoptGrowthPlanCommand(
                    actor=actor,
                    draft_ref=body.draft_ref,
                    draft_version=body.draft_version,
                    idempotency_key=_require_idempotency_key(idempotency_key),
                    selected_choices=body.selected_choices,
                )
            )
        )

    return router


async def _actor(
    dependencies: GrowthPlanAdoptionHttpDependencies,
    authorization: str | None,
    family_id: str,
) -> GrowthPlanActor:
    try:
        return await dependencies.resolve_actor(authorization, family_id)
    except GrowthPlanAuthenticationError as error:
        raise HTTPException(status_code=401, detail=error.code) from error


def _assert_family(actor: GrowthPlanActor, family_id: str) -> None:
    if actor.family_id != family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")


def _require_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip() or len(value) > 128:
        raise HTTPException(status_code=400, detail="invalid_idempotency_key")
    return value


async def _call(operation: Callable[[], Awaitable[dict]]) -> dict:
    try:
        return await operation()
    except JourneyValidationError as error:
        raise HTTPException(status_code=400, detail=error.code) from error
    except JourneyForbiddenError as error:
        raise HTTPException(status_code=403, detail=error.code) from error
    except JourneyNotFoundError as error:
        raise HTTPException(status_code=404, detail=error.code) from error
    except JourneyConflictError as error:
        raise HTTPException(status_code=409, detail=error.code) from error


__all__ = [
    "AdoptGrowthPlanBody",
    "GrowthPlanAdoptionHttpDependencies",
    "GrowthPlanAuthenticationError",
    "build_growth_plan_adoption_router",
]
