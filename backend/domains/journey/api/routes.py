from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..application.plan_service import JourneyPlanService, PhaseReviewDecision
from ..domain.errors import (
    JourneyConflictError,
    JourneyDomainError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)


@dataclass(frozen=True, slots=True)
class JourneyPlanActor:
    actor_id: str
    tenant_id: str
    family_id: str


class JourneyPlanActorResolver(Protocol):
    async def __call__(self, authorization: str | None) -> JourneyPlanActor: ...


class JourneyPlanFocusResolver(Protocol):
    async def __call__(self, actor: JourneyPlanActor, focus_id: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class JourneyPlanHttpDependencies:
    resolve_actor: JourneyPlanActorResolver
    resolve_focus: JourneyPlanFocusResolver
    service: JourneyPlanService


class CreatePlanBody(BaseModel):
    focus_id: str = Field(min_length=1, max_length=128)
    goal_text: str = Field(min_length=1, max_length=500)


class ReviewPhaseBody(BaseModel):
    decision: PhaseReviewDecision
    observation: str = Field(default="", max_length=2000)


def build_journey_plan_router(dependencies: JourneyPlanHttpDependencies) -> APIRouter:
    router = APIRouter(prefix="/families")

    async def actor_for(
        authorization: Annotated[str | None, Header()] = None,
    ) -> JourneyPlanActor:
        if not authorization:
            raise HTTPException(status_code=401, detail="authentication_required")
        return await dependencies.resolve_actor(authorization)

    @router.post("/{family_id}/growth/journey-plan")
    async def create_plan(
        family_id: str,
        body: CreatePlanBody,
        authorization: Annotated[str | None, Header()] = None,
        x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, object]:
        actor = await actor_for(authorization)
        _assert_scope(actor, family_id, x_tenant_id)
        key = _required_key(idempotency_key)
        focus = await dependencies.resolve_focus(actor, body.focus_id)
        if focus is None:
            raise HTTPException(status_code=404, detail="journey_focus_not_found")
        try:
            return dependencies.service.create_plan(
                tenant_id=actor.tenant_id,
                family_id=actor.family_id,
                actor_id=actor.actor_id,
                focus_id=body.focus_id,
                goal_text=body.goal_text,
                idempotency_key=key,
            )
        except JourneyDomainError as error:
            raise _http_error(error) from error

    @router.get("/{family_id}/growth/journey-plan/{plan_id}")
    async def read_plan(
        family_id: str,
        plan_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    ) -> dict[str, object]:
        actor = await actor_for(authorization)
        _assert_scope(actor, family_id, x_tenant_id)
        try:
            return dependencies.service.read_plan(
                tenant_id=actor.tenant_id, family_id=actor.family_id, plan_id=plan_id
            )
        except JourneyDomainError as error:
            raise _http_error(error) from error

    @router.post("/{family_id}/growth/journey-plan/{plan_id}/confirm")
    async def confirm_plan(
        family_id: str,
        plan_id: str,
        authorization: Annotated[str | None, Header()] = None,
        x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, object]:
        actor = await actor_for(authorization)
        _assert_scope(actor, family_id, x_tenant_id)
        try:
            return dependencies.service.confirm_plan(
                tenant_id=actor.tenant_id,
                family_id=actor.family_id,
                actor_id=actor.actor_id,
                plan_id=plan_id,
                idempotency_key=_required_key(idempotency_key),
            )
        except JourneyDomainError as error:
            raise _http_error(error) from error

    @router.post("/{family_id}/growth/journey-plan/{plan_id}/review")
    async def review_phase(
        family_id: str,
        plan_id: str,
        body: ReviewPhaseBody,
        authorization: Annotated[str | None, Header()] = None,
        x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, object]:
        actor = await actor_for(authorization)
        _assert_scope(actor, family_id, x_tenant_id)
        try:
            return dependencies.service.review_phase(
                tenant_id=actor.tenant_id,
                family_id=actor.family_id,
                actor_id=actor.actor_id,
                plan_id=plan_id,
                decision=body.decision,
                observation=body.observation,
                idempotency_key=_required_key(idempotency_key),
            )
        except JourneyDomainError as error:
            raise _http_error(error) from error

    return router


def _assert_scope(actor: JourneyPlanActor, family_id: str, tenant_id: str | None) -> None:
    if tenant_id is None or actor.tenant_id != tenant_id or actor.family_id != family_id:
        raise HTTPException(status_code=403, detail="tenant_family_scope_denied")


def _required_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise HTTPException(status_code=400, detail="invalid_idempotency_key")
    return value


def _http_error(error: JourneyDomainError) -> HTTPException:
    if isinstance(error, JourneyForbiddenError):
        status = 403
    elif isinstance(error, JourneyNotFoundError):
        status = 404
    elif isinstance(error, JourneyConflictError):
        status = 409
    elif isinstance(error, JourneyValidationError):
        status = 400
    else:
        status = 400
    return HTTPException(status_code=status, detail=error.code)
