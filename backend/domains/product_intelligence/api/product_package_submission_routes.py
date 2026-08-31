"""Strict create/read HTTP adapter for ProductPackage review submissions."""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from ..application.context import ActorContext
from ..application.product_package_source_resolution import (
    ProductPackageSourceNotFoundError,
    ProductPackageSourceResolutionError,
    ProductPackageSourceUnavailableError,
    product_package_intent_hash,
    resolve_product_package_source,
)
from ..application.product_package_submission import (
    ProductPackageSubmissionConflictError,
    ProductPackageSubmissionError,
    ProductPackageSubmissionForbiddenError,
    ProductPackageSubmissionRepository,
    ProductPackageSubmissionResult,
    find_product_package_intent_replay,
    get_product_package_submission,
    submit_product_package_draft,
)
from ..domain.errors import ProductIntelligenceNotFoundError
from .product_package_submission_contracts import (
    ProductPackageReviewSubmissionRequest,
    ProductPackageReviewSubmissionResponse,
    ProductPackageReviewTaskReceipt,
)
from .product_package_submission_dependencies import (
    ProductPackageSubmissionServices,
    get_authorized_product_package_reader,
    get_authorized_product_package_submitter,
    get_product_package_submission_clock,
    get_product_package_submission_repository,
    get_product_package_submission_services,
)

router = APIRouter(
    prefix="/product-intelligence/product-package-review-submissions",
    tags=["product-package-review-submission"],
)


def _etag(content_hash: str) -> str:
    return f'"{content_hash}"'


def _response(result: ProductPackageSubmissionResult) -> ProductPackageReviewSubmissionResponse:
    task = result.task
    proposal = task.proposal
    return ProductPackageReviewSubmissionResponse(
        draft=result.draft,
        review_task=ProductPackageReviewTaskReceipt(
            task_id=task.task_id,
            status=task.status.value,
            proposal_id=proposal.proposal_id,
            action_name=proposal.action_name,
            risk_level=proposal.risk_level,
            provenance_ref=proposal.provenance_ref,
            created_at=proposal.created_at,
            expires_at=proposal.expires_at,
        ),
        etag=_etag(result.draft.content_hash),
        replayed=result.replayed,
    )


def _raise_http(exc: Exception) -> NoReturn:
    if isinstance(exc, ProductPackageSubmissionForbiddenError):
        status_code = 403
        detail = exc.code
    elif isinstance(exc, (ProductPackageSourceNotFoundError, ProductIntelligenceNotFoundError)):
        status_code = 404
        detail = getattr(exc, "code", "PRODUCT_PACKAGE_SOURCE_NOT_FOUND")
    elif isinstance(exc, ProductPackageSubmissionConflictError):
        status_code = 409
        detail = exc.code
    elif isinstance(exc, ProductPackageSourceUnavailableError):
        status_code = 503
        detail = exc.code
    elif isinstance(exc, (ProductPackageSourceResolutionError, ProductPackageSubmissionError)):
        status_code = 422
        detail = exc.code
    else:  # pragma: no cover - callers only pass the closed error union above
        raise exc
    raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("", response_model=ProductPackageReviewSubmissionResponse, status_code=201)
async def submit_product_package_review(
    body: ProductPackageReviewSubmissionRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=256),
    context: ActorContext = Depends(get_authorized_product_package_submitter),
    services: ProductPackageSubmissionServices = Depends(
        get_product_package_submission_services
    ),
    now: datetime = Depends(get_product_package_submission_clock),
) -> ProductPackageReviewSubmissionResponse:
    try:
        intent = body.to_intent()
        intent_hash = product_package_intent_hash(intent)
        result = await find_product_package_intent_replay(
            services.repository,
            context,
            idempotency_key=idempotency_key,
            intent_hash=intent_hash,
        )
        if result is not None:
            response.status_code = 200
            response.headers["Location"] = (
                "/product-intelligence/product-package-review-submissions/"
                f"{quote(result.draft.draft_id, safe='')}"
            )
            response.headers["ETag"] = _etag(result.draft.content_hash)
            return _response(result)
        if services.source_resolver is None:
            raise ProductPackageSourceUnavailableError(
                "PRODUCT_PACKAGE_TRUSTED_SOURCE_RESOLVER_NOT_CONFIGURED"
            )
        source = await resolve_product_package_source(
            services.source_resolver,
            context,
            intent,
            now=now,
        )
        result = await submit_product_package_draft(
            services.repository,
            context,
            source,
            idempotency_key=idempotency_key,
            intent_hash=intent_hash,
            source_draft_locator=intent.source_draft_locator,
            now=now,
        )
    except (
        ProductPackageSourceResolutionError,
        ProductPackageSubmissionError,
        ProductIntelligenceNotFoundError,
    ) as exc:
        _raise_http(exc)
    response.status_code = 200 if result.replayed else 201
    response.headers["Location"] = (
        "/product-intelligence/product-package-review-submissions/"
        f"{quote(result.draft.draft_id, safe='')}"
    )
    response.headers["ETag"] = _etag(result.draft.content_hash)
    return _response(result)


@router.get("/{draft_id}", response_model=ProductPackageReviewSubmissionResponse)
async def get_product_package_review(
    draft_id: str,
    response: Response,
    context: ActorContext = Depends(get_authorized_product_package_reader),
    repository: ProductPackageSubmissionRepository = Depends(
        get_product_package_submission_repository
    ),
) -> ProductPackageReviewSubmissionResponse:
    try:
        result = await get_product_package_submission(
            repository,
            context,
            draft_id=draft_id,
        )
    except (ProductPackageSubmissionError, ProductIntelligenceNotFoundError) as exc:
        _raise_http(exc)
    response.headers["ETag"] = _etag(result.draft.content_hash)
    return _response(result)


__all__ = ["router"]
