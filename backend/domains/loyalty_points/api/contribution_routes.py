"""HTTP adapter for the adult contribution ledger.

The router has no process-global repository and no client-controlled identity.
The composition root must override ``get_contribution_repository`` and
``get_contribution_context`` with the Fake or SQLAlchemy adapter plus the
authenticated tenant/family context.  Leaving either dependency unconfigured
fails closed instead of turning a test fixture into a production route.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..application.contribution_commands import (
    appeal_contribution,
    confirm_family_use,
    hold_contribution,
    release_contribution,
    resolve_appeal,
    reverse_released_contribution,
    review_contribution,
    submit_contribution,
    verify_contribution,
    withdraw_contribution,
)
from ..application.contribution_ports import (
    ContributionActionContext,
    ContributionRepositoryPort,
)
from ..domain.contribution import (
    ContentType,
    ContributionConflictError,
    ContributionError,
    ContributionForbiddenError,
    ContributionNotFoundError,
    ContributionValidationError,
    ReviewDecision,
)

router = APIRouter(prefix="/families", tags=["adult-contributions"])


class SubmitContributionBody(BaseModel):
    consumer_family_id: str
    content_ref: str
    content_type: ContentType
    content_version: int = Field(default=1, ge=1)
    purpose: str
    copyright_attestation_ref: str
    privacy_redaction_ref: str


class ReviewContributionBody(BaseModel):
    review_ref: str
    reviewer_person_id: str
    content_approved: bool
    copyright_approved: bool
    safety_approved: bool
    reason_code: str


class VerifyContributionBody(BaseModel):
    verification_ref: str


class UseConfirmationBody(BaseModel):
    confirmation_ref: str


class HoldContributionBody(BaseModel):
    hold_reason: str


class ReleaseContributionBody(BaseModel):
    release_ref: str
    reward_basis: str = "VERIFIED_ADULT_CONTRIBUTION"


class WithdrawContributionBody(BaseModel):
    reason_code: str


class AppealContributionBody(BaseModel):
    appeal_ref: str
    reason: str


class ResolveAppealBody(BaseModel):
    approved: bool
    decision_code: str


class RefundReversalBody(BaseModel):
    refund_ref: str


async def get_contribution_context(
    family_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> ContributionActionContext:
    """Fail closed until the family API composition root supplies auth wiring."""

    raise HTTPException(status_code=503, detail="contribution_auth_not_configured")


def get_contribution_repository() -> ContributionRepositoryPort:
    """Fail closed until the composition root supplies Fake or SQL persistence."""

    raise HTTPException(status_code=503, detail="contribution_repository_not_configured")


def register_exception_handlers(app: FastAPI) -> None:
    statuses = {
        ContributionValidationError: 400,
        ContributionForbiddenError: 403,
        ContributionNotFoundError: 404,
        ContributionConflictError: 409,
    }

    @app.exception_handler(ContributionError)
    async def _handle_contribution_error(request, error: ContributionError) -> JSONResponse:
        return JSONResponse(
            status_code=statuses.get(type(error), 400), content={"detail": error.code}
        )


def _assert_path_scope(context: ContributionActionContext, family_id: str) -> None:
    if context.family_id != family_id:
        raise HTTPException(status_code=403, detail="family_access_denied")


def _request_context(
    context: ContributionActionContext,
    idempotency_key: str | None,
    correlation_id: str | None,
) -> ContributionActionContext:
    return replace(
        context,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id or context.correlation_id or str(uuid4()),
    )


@router.post("/{family_id}/contributions", status_code=201)
async def submit_contribution_route(
    family_id: str,
    body: SubmitContributionBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await submit_contribution(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        consumer_family_id=body.consumer_family_id,
        content_ref=body.content_ref,
        content_type=body.content_type,
        purpose=body.purpose,
        copyright_attestation_ref=body.copyright_attestation_ref,
        privacy_redaction_ref=body.privacy_redaction_ref,
        content_version=body.content_version,
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/review")
async def review_contribution_route(
    family_id: str,
    contribution_id: str,
    body: ReviewContributionBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await review_contribution(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        ReviewDecision(**body.model_dump()),
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/verify")
async def verify_contribution_route(
    family_id: str,
    contribution_id: str,
    body: VerifyContributionBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await verify_contribution(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        verification_ref=body.verification_ref,
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/use-confirmation")
async def confirm_family_use_route(
    family_id: str,
    contribution_id: str,
    body: UseConfirmationBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await confirm_family_use(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        confirmation_ref=body.confirmation_ref,
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/hold")
async def hold_contribution_route(
    family_id: str,
    contribution_id: str,
    body: HoldContributionBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await hold_contribution(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        hold_reason=body.hold_reason,
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/release")
async def release_contribution_route(
    family_id: str,
    contribution_id: str,
    body: ReleaseContributionBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await release_contribution(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        release_ref=body.release_ref,
        reward_basis=body.reward_basis,
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/withdraw")
async def withdraw_contribution_route(
    family_id: str,
    contribution_id: str,
    body: WithdrawContributionBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await withdraw_contribution(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        reason_code=body.reason_code,
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/appeal")
async def appeal_contribution_route(
    family_id: str,
    contribution_id: str,
    body: AppealContributionBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await appeal_contribution(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        appeal_ref=body.appeal_ref,
        reason=body.reason,
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/appeal/resolve")
async def resolve_appeal_route(
    family_id: str,
    contribution_id: str,
    body: ResolveAppealBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await resolve_appeal(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        approved=body.approved,
        decision_code=body.decision_code,
    )
    return record.model_dump(mode="json")


@router.post("/{family_id}/contributions/{contribution_id}/refund-reversal")
async def reverse_contribution_route(
    family_id: str,
    contribution_id: str,
    body: RefundReversalBody,
    context: Annotated[ContributionActionContext, Depends(get_contribution_context)],
    repo: Annotated[ContributionRepositoryPort, Depends(get_contribution_repository)],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    _assert_path_scope(context, family_id)
    record = await reverse_released_contribution(
        repo,
        _request_context(context, idempotency_key, x_correlation_id),
        contribution_id,
        refund_ref=body.refund_ref,
    )
    return record.model_dump(mode="json")


__all__ = [
    "get_contribution_context",
    "get_contribution_repository",
    "register_exception_handlers",
    "router",
]
