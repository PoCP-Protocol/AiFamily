"""Internal read API for governed AI evaluation evidence.

This router is intentionally outside ``/families``.  Evaluation evidence is
an operator concern and must never be confused with a family's canonical
state or a family-facing analytics endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from backend.apps.family_api.operator_request_context import bind_operator_request_context
from backend.intelligence.evaluation.operator_identity import OperatorIdentityError
from backend.intelligence.evaluation.query import (
    AuthorizedEvaluationQueryService,
    EvaluationQueryError,
)


class EvaluationReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_ref: str
    case_version: str
    dataset_fingerprint: str
    total_cases: int = Field(ge=0)
    metadata: dict[str, object]
    archived_at: datetime


class EvaluationSliceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_ref: str
    dataset_fingerprint: str
    dimension: str
    value: str
    case_count: int = Field(ge=0)
    slice_report_ref: str
    metadata: dict[str, object]
    archived_at: datetime


def get_evaluation_query_service() -> AuthorizedEvaluationQueryService | None:
    """No operator identity/archive runtime is installed by default."""

    return None


router = APIRouter(prefix="/internal/ai/evaluations", tags=["ai-evaluation"])


async def _require_service(
    service: AuthorizedEvaluationQueryService | None,
) -> AuthorizedEvaluationQueryService:
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="evaluation_query_runtime_not_configured",
        )
    return service


def _map_query_error(error: Exception) -> HTTPException:
    if isinstance(error, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="evaluation_query_scope_denied",
        )
    if isinstance(error, (EvaluationQueryError, OperatorIdentityError)):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="evaluation_query_runtime_unavailable",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="evaluation_query_unavailable",
    )


@router.get("/reports", response_model=tuple[EvaluationReportResponse, ...])
async def list_evaluation_reports(
    case_version: str | None = None,
    dataset_fingerprint: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 50,
    service: AuthorizedEvaluationQueryService | None = Depends(get_evaluation_query_service),
    _operator_context: Annotated[None, Depends(bind_operator_request_context)] = None,
) -> tuple[EvaluationReportResponse, ...]:
    runtime = await _require_service(service)
    try:
        reports = await runtime.list_reports(
            case_version=case_version,
            dataset_fingerprint=dataset_fingerprint,
            limit=limit,
        )
    except (PermissionError, EvaluationQueryError, OperatorIdentityError) as error:
        raise _map_query_error(error) from error
    return tuple(
        EvaluationReportResponse(
            report_ref=item.report_ref,
            case_version=item.case_version,
            dataset_fingerprint=item.dataset_fingerprint,
            total_cases=item.total_cases,
            metadata=dict(item.report_payload),
            archived_at=item.archived_at,
        )
        for item in reports
    )


@router.get("/slices", response_model=tuple[EvaluationSliceResponse, ...])
async def list_evaluation_slices(
    report_ref: str | None = None,
    dimension: str | None = None,
    value: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    service: AuthorizedEvaluationQueryService | None = Depends(get_evaluation_query_service),
    _operator_context: Annotated[None, Depends(bind_operator_request_context)] = None,
) -> tuple[EvaluationSliceResponse, ...]:
    runtime = await _require_service(service)
    try:
        slices = await runtime.list_slices(
            report_ref=report_ref,
            dimension=dimension,
            value=value,
            limit=limit,
        )
    except (PermissionError, EvaluationQueryError, OperatorIdentityError) as error:
        raise _map_query_error(error) from error
    return tuple(
        EvaluationSliceResponse(
            report_ref=item.report_ref,
            dataset_fingerprint=item.dataset_fingerprint,
            dimension=item.dimension,
            value=item.value,
            case_count=item.case_count,
            slice_report_ref=item.slice_report_ref,
            metadata=dict(item.report_payload),
            archived_at=item.archived_at,
        )
        for item in slices
    )


__all__ = [
    "EvaluationReportResponse",
    "EvaluationSliceResponse",
    "get_evaluation_query_service",
    "router",
]
