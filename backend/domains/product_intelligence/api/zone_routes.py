"""FastAPI routes for the Product Zone (Three-Zone Strategy Engine)
governance lifecycle — `application/zone_commands.py`. Same conventions as
`api/routes.py`: `context: ActorContext = Depends(get_actor_context)` on
every route, `_raise_http` error-code mapping, not mounted into any app yet
(no owning app exists in this PR — see `api/dependencies.py` docstring).

Does NOT define `GET /product-intelligence/portfolio/zones` or any other
cross-assessment/portfolio query — that is explicitly Agent D's scope per
the task brief. This module only has single-`ProductZoneAssessment`
CRUD-lifecycle routes (create/score/submit/approve/reject/get-by-id).

`get_zone_repository` is a new dependency defined in THIS file, not added
to the shared `api/dependencies.py` — that module is common to every Agent
touching this domain's API layer, and this Agent's file-ownership scope
(per the task brief) is limited to files it may create fresh. Wiring a real
`_session_factory` for this dependency is deferred to whichever future PR
bootstraps an owning app (same deferral as `api/dependencies.py`'s own
`get_repository`).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..application import zone_commands
from ..application.context import ActorContext
from ..application.ports import ProductIntelligenceRepositoryPort
from ..application.zone_ports import ZoneAssessmentRepositoryPort
from ..domain.errors import ProductIntelligenceDomainError
from ..infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from ..infrastructure.zone_sqlalchemy_repository import SqlAlchemyZoneAssessmentRepository
from . import zone_requests as req
from .dependencies import get_actor_context, get_repository
from .zone_responses import ZoneAssessmentResponse

router = APIRouter(prefix="/product-intelligence", tags=["product-intelligence-zone"])

_ERROR_STATUS = {
    "ProductIntelligenceValidationError": 400,
    "ProductIntelligenceForbiddenError": 403,
    "ProductIntelligenceNotFoundError": 404,
}

_zone_session_factory = None  # set by the owning app at startup; not configured in this PR


def _raise_http(exc: ProductIntelligenceDomainError) -> NoReturn:
    status = _ERROR_STATUS.get(type(exc).__name__, 400)
    raise HTTPException(status_code=status, detail=exc.code) from exc


async def get_zone_repository() -> AsyncGenerator[ZoneAssessmentRepositoryPort, None]:
    if _zone_session_factory is None:
        raise RuntimeError("product_intelligence zone session factory not configured — no owning app exists yet")
    async with _zone_session_factory() as session:  # type: AsyncSession
        async with SqlAlchemyUnitOfWork(session):
            yield SqlAlchemyZoneAssessmentRepository(session)


@router.post(
    "/product-concepts/{product_concept_id}/zone-assessments",
    response_model=ZoneAssessmentResponse,
)
async def create_zone_assessment(
    product_concept_id: str,
    body: req.CreateZoneAssessmentRequest,
    repo: ZoneAssessmentRepositoryPort = Depends(get_zone_repository),
    product_intelligence_repo: ProductIntelligenceRepositoryPort = Depends(get_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        return await zone_commands.create_zone_assessment(
            repo,
            product_intelligence_repo,
            context,
            product_concept_id=product_concept_id,
            zone_policy_version_id=body.zone_policy_version_id,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)


@router.post(
    "/zone-assessments/{assessment_id}/score",
    response_model=ZoneAssessmentResponse,
)
async def score_zone_assessment(
    assessment_id: str,
    body: req.ScoreZoneAssessmentRequest,
    repo: ZoneAssessmentRepositoryPort = Depends(get_zone_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        dimension_assessments = [d.model_dump(exclude_none=True) for d in body.dimension_assessments]
        return await zone_commands.score_zone_assessment(
            repo,
            context,
            assessment_id=assessment_id,
            dimension_assessments=dimension_assessments,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)


@router.post(
    "/zone-assessments/{assessment_id}/submit-review",
    response_model=ZoneAssessmentResponse,
)
async def submit_zone_review(
    assessment_id: str,
    repo: ZoneAssessmentRepositoryPort = Depends(get_zone_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        return await zone_commands.submit_zone_review(repo, context, assessment_id=assessment_id)
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)


@router.post(
    "/zone-assessments/{assessment_id}/approve",
    response_model=ZoneAssessmentResponse,
)
async def approve_zone_assessment(
    assessment_id: str,
    body: req.ApproveZoneAssessmentRequest,
    repo: ZoneAssessmentRepositoryPort = Depends(get_zone_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        return await zone_commands.approve_zone_assessment(
            repo,
            context,
            assessment_id=assessment_id,
            approved_zone=body.approved_zone,
            review_reason=body.review_reason,
            override_reason=body.override_reason,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)


@router.post(
    "/zone-assessments/{assessment_id}/reject",
    response_model=ZoneAssessmentResponse,
)
async def reject_zone_assessment(
    assessment_id: str,
    body: req.RejectZoneAssessmentRequest,
    repo: ZoneAssessmentRepositoryPort = Depends(get_zone_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        return await zone_commands.reject_zone_assessment(
            repo, context, assessment_id=assessment_id, review_reason=body.review_reason,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)


@router.get(
    "/zone-assessments/{assessment_id}",
    response_model=ZoneAssessmentResponse,
)
async def get_zone_assessment(
    assessment_id: str,
    repo: ZoneAssessmentRepositoryPort = Depends(get_zone_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        return await repo.load_zone_assessment(assessment_id, context.tenant_scope)
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)
