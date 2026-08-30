"""Dependency-injected HTTP adapter for the Journey MVP.

The router is not mounted by the baseline composition root yet. A caller must
provide a trusted actor resolver and a repository-backed ``JourneyService``;
there is no global fake/default. This keeps test and production route shapes
identical while leaving the PostgreSQL/Audit/Outbox composition gate explicit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..application.ports import JourneyActor
from ..application.service import JourneyService
from ..domain.errors import (
    JourneyConflictError,
    JourneyDomainError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)
from ..domain.models import PhaseReviewDecision

ActorResolver = Callable[[str | None, str], Awaitable[JourneyActor]]


class JourneyAuthenticationError(Exception):
    """Raised by the composition root when the bearer session is missing/invalid."""

    def __init__(self, code: str = "authentication_required") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class JourneyHttpDependencies:
    """Trusted dependencies required to expose the router."""

    resolve_actor: ActorResolver
    service: JourneyService


class CreateJourneyPlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority_id: str = Field(min_length=1, max_length=128)


class RecordJourneyActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_text: str = Field(min_length=1, max_length=500)


class ReviewJourneyPhaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PhaseReviewDecision
    notes: str | None = Field(default=None, max_length=500)


def build_journey_router(dependencies: JourneyHttpDependencies) -> APIRouter:
    """Build routes with explicit identity and service dependencies.

    The path family is only an assertion. ``resolve_actor`` remains the source
    of tenant/family/actor truth and the service performs a second scoped read.
    """

    router = APIRouter(prefix="/families", tags=["journey"])

    @router.get("/{family_id}/growth/journey-plan")
    async def get_journey_plan(
        family_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        actor = await _actor(dependencies, authorization, family_id)
        _assert_family(actor, family_id)
        return await _call(lambda: dependencies.service.get_current(actor))

    @router.post("/{family_id}/growth/onboardings/{onboarding_id}/journey-plan")
    async def create_journey_plan(
        family_id: str,
        onboarding_id: str,
        body: CreateJourneyPlanBody,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        actor = await _actor(dependencies, authorization, family_id)
        _assert_family(actor, family_id)
        key = _require_key(idempotency_key)
        return await _call(
            lambda: dependencies.service.create_plan(
                actor,
                onboarding_id=onboarding_id,
                priority_id=body.priority_id,
                idempotency_key=key,
            )
        )

    @router.get("/{family_id}/growth/journey-plans/{plan_id}")
    async def get_journey_plan_detail(
        family_id: str,
        plan_id: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        actor = await _actor(dependencies, authorization, family_id)
        _assert_family(actor, family_id)
        return await _call(lambda: dependencies.service.get_plan(actor, plan_id))

    @router.post("/{family_id}/growth/journey-plans/{plan_id}/confirm")
    async def confirm_journey_plan(
        family_id: str,
        plan_id: str,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        actor = await _actor(dependencies, authorization, family_id)
        _assert_family(actor, family_id)
        key = _require_key(idempotency_key)
        return await _call(
            lambda: dependencies.service.confirm_plan(actor, plan_id, idempotency_key=key)
        )

    @router.post("/{family_id}/growth/journey-plans/{plan_id}/actions")
    async def record_journey_action(
        family_id: str,
        plan_id: str,
        body: RecordJourneyActionBody,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        actor = await _actor(dependencies, authorization, family_id)
        _assert_family(actor, family_id)
        key = _require_key(idempotency_key)
        return await _call(
            lambda: dependencies.service.record_action(
                actor,
                plan_id,
                action_text=body.action_text,
                idempotency_key=key,
            )
        )

    @router.post("/{family_id}/growth/journey-plans/{plan_id}/phase-review")
    async def review_journey_phase(
        family_id: str,
        plan_id: str,
        body: ReviewJourneyPhaseBody,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        actor = await _actor(dependencies, authorization, family_id)
        _assert_family(actor, family_id)
        key = _require_key(idempotency_key)
        return await _call(
            lambda: dependencies.service.review_phase(
                actor,
                plan_id,
                decision=body.decision,
                notes=body.notes,
                idempotency_key=key,
            )
        )

    return router


async def _actor(
    dependencies: JourneyHttpDependencies, authorization: str | None, family_id: str
) -> JourneyActor:
    try:
        return await dependencies.resolve_actor(authorization, family_id)
    except JourneyAuthenticationError as error:
        raise HTTPException(status_code=401, detail=error.code) from error


def _assert_family(actor: JourneyActor, family_id: str) -> None:
    if actor.family_id != family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")


def _require_key(value: str | None) -> str:
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
    except JourneyDomainError as error:
        raise HTTPException(status_code=400, detail=error.code) from error


__all__ = [
    "CreateJourneyPlanBody",
    "JourneyAuthenticationError",
    "JourneyHttpDependencies",
    "RecordJourneyActionBody",
    "ReviewJourneyPhaseBody",
    "build_journey_router",
]
