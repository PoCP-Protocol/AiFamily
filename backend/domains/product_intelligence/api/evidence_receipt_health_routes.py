"""Unmounted HTTP adapter for read-only evidence receipt health snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Response

from ..application.context import ActorContext
from ..application.evidence_receipt_health import (
    EvidenceReceiptHealthConflictError,
    EvidenceReceiptHealthUnavailableError,
    get_evidence_receipt_health,
)
from ..application.product_package_evidence_admission import ProductPackageEvidenceReader
from ..application.product_package_submission import (
    ProductPackageSubmissionError,
    ProductPackageSubmissionForbiddenError,
)
from ..domain.errors import ProductIntelligenceNotFoundError
from .evidence_receipt_health_contracts import EvidenceReceiptHealthResponse
from .evidence_receipt_health_dependencies import (
    get_authorized_evidence_receipt_health_context,
    get_evidence_receipt_health_clock,
    get_evidence_receipt_health_reader,
)

router = APIRouter(
    prefix="/product-intelligence/evidence-verification-receipts",
    tags=["evidence-receipt-health"],
)
_NO_STORE = {"Cache-Control": "no-store"}


def _raise_http(exc: Exception) -> NoReturn:
    if isinstance(exc, ProductPackageSubmissionForbiddenError):
        status_code = 403
    elif isinstance(exc, ProductIntelligenceNotFoundError):
        status_code = 404
    elif isinstance(exc, EvidenceReceiptHealthConflictError):
        status_code = 409
    elif isinstance(exc, EvidenceReceiptHealthUnavailableError):
        status_code = 503
    elif isinstance(exc, ProductPackageSubmissionError):
        status_code = 422
    else:  # pragma: no cover - closed error union
        raise exc
    raise HTTPException(
        status_code=status_code,
        detail=exc.code,
        headers=_NO_STORE,
    ) from exc


@router.get("/{receipt_id}/health", response_model=EvidenceReceiptHealthResponse)
async def get_receipt_health(
    receipt_id: str,
    response: Response,
    context: ActorContext = Depends(get_authorized_evidence_receipt_health_context),
    reader: ProductPackageEvidenceReader = Depends(get_evidence_receipt_health_reader),
    now: datetime = Depends(get_evidence_receipt_health_clock),
) -> EvidenceReceiptHealthResponse:
    try:
        projection = await get_evidence_receipt_health(
            reader,
            context,
            receipt_id=receipt_id,
            now=now,
        )
    except (
        ProductPackageSubmissionError,
        ProductIntelligenceNotFoundError,
    ) as exc:
        _raise_http(exc)
    response.headers["Cache-Control"] = "no-store"
    return EvidenceReceiptHealthResponse.model_validate(projection)


__all__ = ["router"]
