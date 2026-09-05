"""Internal operator-only API for Experience delivery operations."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from backend.apps.family_api.operator_request_context import bind_operator_request_context
from backend.intelligence.evaluation.operator_identity import OperatorIdentityError
from backend.intelligence.experience.operations_query import (
    AuthorizedExperienceOperationsQueryService,
    ExperienceOperationsCursorError,
    ExperienceOperationsQueryError,
    HmacExperienceOperationsCursorSigner,
)
from backend.intelligence.experience.persistence import ExperienceDeliveryAttemptStatus


class DeliveryAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    attempts: int = Field(ge=0)
    status: ExperienceDeliveryAttemptStatus
    last_error: str | None = None
    updated_at: datetime
    terminal_at: datetime | None = None
    lease_owner: str | None = None
    lease_until: datetime | None = None


class DeliveryAttemptPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[DeliveryAttemptResponse, ...]
    next_cursor: str | None = None


class DeliveryAttemptSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counts: dict[ExperienceDeliveryAttemptStatus, int]


def get_experience_operations_query_service() -> (
    AuthorizedExperienceOperationsQueryService | None
):
    """No operator identity/runtime is installed by default."""

    return None


def get_experience_operations_cursor_signer() -> HmacExperienceOperationsCursorSigner | None:
    """Cursor signing is explicit; no process environment fallback is allowed."""

    return None


router = APIRouter(prefix="/internal/ai/experience", tags=["ai-experience-operations"])


def _metadata_error(value: str | None) -> str | None:
    """Expose only presence, never arbitrary worker/provider error text."""

    return None if value is None else "DELIVERY_ERROR_REDACTED"


async def _require_service(
    service: AuthorizedExperienceOperationsQueryService | None,
) -> AuthorizedExperienceOperationsQueryService:
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_operations_query_runtime_not_configured",
        )
    return service


def _map_error(error: Exception) -> HTTPException:
    if isinstance(error, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="experience_operations_query_scope_denied",
        )
    if isinstance(error, ExperienceOperationsCursorError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="experience_operations_query_cursor_invalid",
        )
    if isinstance(error, (ExperienceOperationsQueryError, OperatorIdentityError)):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_operations_query_runtime_unavailable",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="experience_operations_query_unavailable",
    )


@router.get("/delivery-attempts", response_model=DeliveryAttemptPageResponse)
async def list_delivery_attempts(
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    attempt_status: Annotated[ExperienceDeliveryAttemptStatus | None, Query(alias="status")] = None,
    cursor: str | None = None,
    service: AuthorizedExperienceOperationsQueryService | None = Depends(
        get_experience_operations_query_service
    ),
    signer: HmacExperienceOperationsCursorSigner | None = Depends(
        get_experience_operations_cursor_signer
    ),
    _operator_context: Annotated[None, Depends(bind_operator_request_context)] = None,
) -> DeliveryAttemptPageResponse:
    runtime = await _require_service(service)
    if signer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_operations_cursor_signer_not_configured",
        )
    try:
        after = signer.decode(cursor, status=attempt_status) if cursor else None
        page = await runtime.list_attempts_page(
            limit=limit,
            status=attempt_status,
            after=after,
        )
    except (
        PermissionError,
        ExperienceOperationsCursorError,
        ExperienceOperationsQueryError,
        OperatorIdentityError,
    ) as error:
        raise _map_error(error) from error
    return DeliveryAttemptPageResponse(
        items=tuple(
            DeliveryAttemptResponse(
                message_id=item.message_id,
                attempts=item.attempts,
                status=item.status,
                last_error=_metadata_error(item.last_error),
                updated_at=item.updated_at,
                terminal_at=item.terminal_at,
                lease_owner=item.lease_owner,
                lease_until=item.lease_until,
            )
            for item in page.items
        ),
        next_cursor=(
            signer.encode(page.next_cursor, status=attempt_status)
            if page.next_cursor
            else None
        ),
    )


@router.get("/delivery-attempts/summary", response_model=DeliveryAttemptSummaryResponse)
async def delivery_attempt_summary(
    service: AuthorizedExperienceOperationsQueryService | None = Depends(
        get_experience_operations_query_service
    ),
    _operator_context: Annotated[None, Depends(bind_operator_request_context)] = None,
) -> DeliveryAttemptSummaryResponse:
    runtime = await _require_service(service)
    try:
        summary = await runtime.summary()
    except (PermissionError, ExperienceOperationsQueryError, OperatorIdentityError) as error:
        raise _map_error(error) from error
    return DeliveryAttemptSummaryResponse(counts=dict(summary.counts))


__all__ = [
    "DeliveryAttemptPageResponse",
    "DeliveryAttemptResponse",
    "DeliveryAttemptSummaryResponse",
    "get_experience_operations_cursor_signer",
    "get_experience_operations_query_service",
    "bind_operator_request_context",
    "router",
]
