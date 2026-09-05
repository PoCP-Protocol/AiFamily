from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.platform.persistence.session import (
    get_engine,
    is_postgres_url,
    resolve_database_url,
)

from ..application.service import JourneyActor, JourneyService
from ..domain.errors import (
    JourneyConflictError,
    JourneyDomainError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)
from ..domain.models import GrowthPriorityDecision, PhaseDecision
from ..infrastructure.actor_resolver import (
    JourneyAuthenticationError,
    SqlAlchemyJourneyActorResolver,
)
from ..infrastructure.application import build_postgres_journey_application

router = APIRouter(prefix="/families")


class CreatePlanBody(BaseModel):
    priority_id: str


class ReviewPhaseBody(BaseModel):
    decision: PhaseDecision


class ConfirmPriorityBody(BaseModel):
    draft_id: str
    decision: GrowthPriorityDecision


async def get_journey_actor(
    family_id: str, authorization: Annotated[str | None, Header()] = None
) -> JourneyActor:
    database_url = resolve_database_url()
    if not is_postgres_url(database_url):
        raise HTTPException(status_code=503, detail="journey_postgres_not_configured")
    resolver = SqlAlchemyJourneyActorResolver(get_engine(database_url))
    try:
        return await resolver.resolve(authorization, family_id)
    except JourneyAuthenticationError as error:
        raise HTTPException(status_code=401, detail=error.code) from error


def get_journey_service() -> JourneyService:
    database_url = resolve_database_url()
    if not is_postgres_url(database_url):
        raise HTTPException(status_code=503, detail="journey_postgres_not_configured")
    return build_postgres_journey_application(database_url)  # type: ignore[return-value]


def register_exception_handlers(app: FastAPI) -> None:
    statuses = {
        JourneyValidationError: 400,
        JourneyForbiddenError: 403,
        JourneyNotFoundError: 404,
        JourneyConflictError: 409,
    }

    @app.exception_handler(JourneyDomainError)
    async def _handle_journey_error(request, error: JourneyDomainError) -> JSONResponse:
        return JSONResponse(
            status_code=statuses.get(type(error), 400), content={"detail": error.code}
        )


def _scope(actor: JourneyActor, family_id: str) -> None:
    if actor.family_id != family_id:
        raise HTTPException(status_code=403, detail="family_access_denied")


def _idempotency(value: str | None) -> None:
    if value is None or not value.strip() or len(value) > 128:
        raise HTTPException(status_code=400, detail="invalid_idempotency_key")


@router.get("/{family_id}/growth/journey-plan")
async def get_journey_plan(
    family_id: str,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
) -> dict:
    _scope(actor, family_id)
    return await service.get_current(actor)


@router.get("/{family_id}/growth/onboardings/{onboarding_id}/priority")
async def get_growth_priority(
    family_id: str,
    onboarding_id: str,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
) -> dict:
    _scope(actor, family_id)
    return await service.get_growth_priority(actor, onboarding_id)


@router.post("/{family_id}/growth/onboardings/{onboarding_id}/priority/confirm")
async def confirm_growth_priority(
    family_id: str,
    onboarding_id: str,
    body: ConfirmPriorityBody,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _scope(actor, family_id)
    _idempotency(idempotency_key)
    return await service.confirm_growth_priority(
        actor,
        onboarding_id,
        body.draft_id,
        body.decision,
        idempotency_key or "",
        x_correlation_id or str(uuid4()),
    )


@router.get("/{family_id}/growth/onboardings/{onboarding_id}/plan-preview")
async def get_plan_preview(
    family_id: str,
    onboarding_id: str,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
) -> dict:
    _scope(actor, family_id)
    return await service.get_plan_preview(actor, onboarding_id)


@router.get("/{family_id}/growth/onboardings/{onboarding_id}/service-journey")
async def get_service_journey(
    family_id: str,
    onboarding_id: str,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
) -> dict:
    _scope(actor, family_id)
    return await service.get_service_journey(actor, onboarding_id)


@router.post("/{family_id}/growth/onboardings/{onboarding_id}/plan-preview/refresh")
async def refresh_plan_preview(
    family_id: str,
    onboarding_id: str,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _scope(actor, family_id)
    _idempotency(idempotency_key)
    return await service.refresh_plan_preview(
        actor, onboarding_id, idempotency_key or "", x_correlation_id or str(uuid4())
    )


@router.post("/{family_id}/growth/onboardings/{onboarding_id}/journey-plan")
async def create_journey_plan(
    family_id: str,
    onboarding_id: str,
    body: CreatePlanBody,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _scope(actor, family_id)
    _idempotency(idempotency_key)
    return await service.create(
        actor,
        onboarding_id,
        body.priority_id,
        idempotency_key or "",
        x_correlation_id or str(uuid4()),
    )


@router.post("/{family_id}/growth/journey-plans/{plan_id}/confirm")
async def confirm_journey_plan(
    family_id: str,
    plan_id: str,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _scope(actor, family_id)
    _idempotency(idempotency_key)
    return await service.confirm(
        actor, plan_id, idempotency_key or "", x_correlation_id or str(uuid4())
    )


@router.post("/{family_id}/growth/journey-plans/{plan_id}/phase-review")
async def review_journey_phase(
    family_id: str,
    plan_id: str,
    body: ReviewPhaseBody,
    actor: Annotated[JourneyActor, Depends(get_journey_actor)],
    service: Annotated[JourneyService, Depends(get_journey_service)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _scope(actor, family_id)
    _idempotency(idempotency_key)
    return await service.review(
        actor,
        plan_id,
        body.decision,
        idempotency_key or "",
        x_correlation_id or str(uuid4()),
    )
