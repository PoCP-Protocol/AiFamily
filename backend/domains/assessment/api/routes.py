"""FastAPI routes — port of the assessment-related endpoints in
`family.controller.ts`:
  GET  :familyId/ui/02/assessment
  POST :familyId/assessments/sessions
  POST :familyId/assessments/sessions/:sessionId/responses
  POST :familyId/assessments/sessions/:sessionId/submit
  GET  :familyId/ui/03/growth-hypothesis
  POST :familyId/growth-hypotheses/decisions

Auth/family-context extraction is a thin FastAPI dependency
(`get_family_context`) mirroring the `@FamilyContext()`/`@ActorId()`
decorators — actual JWT/session verification is wired in `apps/family_api`,
not duplicated here.

Domain errors (`AssessmentDomainError` subclasses) are NOT caught here —
they propagate to the app-level exception handler registered in
`register_exception_handlers()` below, per FastAPI's own recommended
pattern (https://fastapi.tiangolo.com/tutorial/handling-errors/#install-
custom-exception-handlers — register on the exception type via
`@app.exception_handler(...)` rather than try/except in every route).
This was a deliberate refactor away from an earlier per-route try/except
that repeated the same three lines in all 6 handlers — the same mapping,
registered once, cannot be forgotten in a 7th route added later.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse

from ..application.commands import (
    AssessmentCommandHandler,
    MutationMeta,
    SaveAssessmentResponseCommand,
    StartAssessmentCommand,
    SubmitAssessmentCommand,
)
from ..application.growth_hypothesis_commands import DecideGrowthHypothesisCommand, GrowthHypothesisCommandHandler
from ..application.queries import AssessmentQueryHandler, GetUi02ProjectionQuery, GetUi03ProjectionQuery
from ..domain.errors import (
    AssessmentConflictError,
    AssessmentDomainError,
    AssessmentForbiddenError,
    AssessmentNotFoundError,
    AssessmentValidationError,
)
from .dependencies import FamilyContext, get_command_handler, get_family_context, get_growth_hypothesis_handler, get_query_handler
from .requests import DecideGrowthHypothesisRequestBody, SaveAssessmentResponseRequestBody, StartAssessmentRequestBody
from .responses import (
    AssessmentMutationReceiptResponse,
    GrowthHypothesisDecisionReceiptResponse,
    Ui02AssessmentProjectionResponse,
    Ui03GrowthHypothesisProjectionResponse,
)

router = APIRouter()

_ERROR_STATUS = {
    AssessmentValidationError: 400,
    AssessmentForbiddenError: 403,
    AssessmentNotFoundError: 404,
    AssessmentConflictError: 409,
}


def register_exception_handlers(app: FastAPI) -> None:
    """Call once from the FastAPI app that mounts this router
    (`apps/family_api/main.py`). One handler, one mapping table — every
    route in this file (and any added later) gets consistent error-code
    behavior without needing its own try/except.
    """

    @app.exception_handler(AssessmentDomainError)
    async def _handle_assessment_domain_error(request, error: AssessmentDomainError) -> JSONResponse:
        status_code = _ERROR_STATUS.get(type(error), 400)
        return JSONResponse(status_code=status_code, content={"detail": error.code})


@router.get("/{family_id}/ui/02/assessment", responses={200: {"model": Ui02AssessmentProjectionResponse}})
async def get_ui02_projection(
    family_id: str,
    context: FamilyContext = Depends(get_family_context),
    handler: AssessmentQueryHandler = Depends(get_query_handler),
) -> dict:
    if context.family_id != family_id:
        raise HTTPException(status_code=401, detail="real_family_session_required")
    return await handler.get_ui02_projection(GetUi02ProjectionQuery(family_id, context.tenant_id, context.person_id))


@router.post("/{family_id}/assessments/sessions", responses={200: {"model": AssessmentMutationReceiptResponse}})
async def start_assessment(
    family_id: str,
    body: StartAssessmentRequestBody,
    context: FamilyContext = Depends(get_family_context),
    handler: AssessmentCommandHandler = Depends(get_command_handler),
    x_correlation_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
    x_source: str | None = Header(default=None),
) -> dict:
    if context.family_id != family_id:
        raise HTTPException(status_code=401, detail="real_family_session_required")
    meta = MutationMeta(x_correlation_id or "", idempotency_key or "", x_source or "")
    return await handler.start(
        StartAssessmentCommand(family_id, context.tenant_id, context.person_id, body.subject_person_id, body.tool_ref, meta)
    )


@router.post(
    "/{family_id}/assessments/sessions/{session_id}/responses",
    responses={200: {"model": AssessmentMutationReceiptResponse}},
)
async def save_assessment_response(
    family_id: str,
    session_id: str,
    body: SaveAssessmentResponseRequestBody,
    context: FamilyContext = Depends(get_family_context),
    handler: AssessmentCommandHandler = Depends(get_command_handler),
    x_correlation_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
    x_source: str | None = Header(default=None),
) -> dict:
    if context.family_id != family_id:
        raise HTTPException(status_code=401, detail="real_family_session_required")
    meta = MutationMeta(x_correlation_id or "", idempotency_key or "", x_source or "")
    return await handler.save_response(
        SaveAssessmentResponseCommand(
            family_id,
            context.tenant_id,
            context.person_id,
            session_id,
            body.item_ref,
            body.response_type,
            body.response_value,
            meta,
        )
    )


@router.post(
    "/{family_id}/assessments/sessions/{session_id}/submit",
    responses={200: {"model": AssessmentMutationReceiptResponse}},
)
async def submit_assessment(
    family_id: str,
    session_id: str,
    context: FamilyContext = Depends(get_family_context),
    handler: AssessmentCommandHandler = Depends(get_command_handler),
    x_correlation_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
    x_source: str | None = Header(default=None),
) -> dict:
    if context.family_id != family_id:
        raise HTTPException(status_code=401, detail="real_family_session_required")
    meta = MutationMeta(x_correlation_id or "", idempotency_key or "", x_source or "")
    return await handler.submit(SubmitAssessmentCommand(family_id, context.tenant_id, context.person_id, session_id, meta))


@router.get("/{family_id}/ui/03/growth-hypothesis", responses={200: {"model": Ui03GrowthHypothesisProjectionResponse}})
async def get_ui03_projection(
    family_id: str,
    context: FamilyContext = Depends(get_family_context),
    handler: AssessmentQueryHandler = Depends(get_query_handler),
) -> dict:
    if context.family_id != family_id:
        raise HTTPException(status_code=401, detail="real_family_session_required")
    return await handler.get_ui03_projection(GetUi03ProjectionQuery(family_id, context.tenant_id, context.person_id))


@router.post(
    "/{family_id}/growth-hypotheses/decisions",
    responses={200: {"model": GrowthHypothesisDecisionReceiptResponse}},
)
async def decide_growth_hypothesis(
    family_id: str,
    body: DecideGrowthHypothesisRequestBody,
    context: FamilyContext = Depends(get_family_context),
    handler: GrowthHypothesisCommandHandler = Depends(get_growth_hypothesis_handler),
    x_correlation_id: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    if context.family_id != family_id:
        raise HTTPException(status_code=401, detail="real_family_session_required")
    return await handler.decide(
        DecideGrowthHypothesisCommand(
            family_id,
            context.tenant_id,
            context.person_id,
            body.assessment_session_id,
            body.hypothesis_ref,
            body.decision_type,
            x_correlation_id or "",
            idempotency_key or "",
        )
    )
