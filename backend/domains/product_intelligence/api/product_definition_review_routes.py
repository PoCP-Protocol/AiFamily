"""Trusted operator HTTP surface for ProductDefinition Human Gate review."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from ..application.context import ActorContext
from ..application.product_definition_review import (
    ProductDefinitionReviewConflictError,
    ProductDefinitionReviewDecision,
    ProductDefinitionReviewError,
    ProductDefinitionReviewForbiddenError,
    ProductDefinitionReviewNotFoundError,
    ProductDefinitionReviewRepository,
    ProductDefinitionReviewTask,
    ProductDefinitionReviewValidationError,
    decide_product_definition_review_task,
    get_product_definition_review_task,
    list_product_definition_review_tasks,
)
from .dependencies import get_actor_context
from .product_definition_review_dependencies import (
    get_product_definition_review_repository,
)

router = APIRouter(
    prefix="/product-intelligence/operator/product-definition-review-tasks",
    tags=["product-definition-review"],
)


class ProductDefinitionReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["ACCEPT", "REJECT", "ESCALATE"]
    reason: str = Field(min_length=1)


class ProductDefinitionReviewTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    status: Literal["OPEN", "DECIDED", "EXPIRED"]
    proposal_id: str
    draft_id: str
    action_name: str
    action_arguments: dict[str, Any]
    risk_level: str
    provenance_ref: str
    created_at: datetime
    expires_at: datetime
    etag: str
    decision_id: str | None = None
    decision_outcome: Literal["ACCEPT", "REJECT", "ESCALATE"] | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    request_id: str | None = None


class ProductDefinitionReviewTaskListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ProductDefinitionReviewTaskResponse, ...]


class ProductDefinitionReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task: ProductDefinitionReviewTaskResponse
    actor_id: str
    execution_status: Literal["PENDING", "NOT_APPLICABLE"]


def _task_response(task: ProductDefinitionReviewTask) -> ProductDefinitionReviewTaskResponse:
    return ProductDefinitionReviewTaskResponse(
        task_id=task.task_id,
        status=task.status,
        proposal_id=task.proposal_id,
        draft_id=task.draft_id,
        action_name=task.action_name,
        action_arguments=dict(task.action_arguments),
        risk_level=task.risk_level,
        provenance_ref=task.provenance_ref,
        created_at=task.created_at,
        expires_at=task.expires_at,
        etag=task.etag,
        decision_id=task.decision_id,
        decision_outcome=task.decision_outcome,
        decision_reason=task.decision_reason,
        decided_at=task.decided_at,
        request_id=task.request_id,
    )


def _decision_response(
    decision: ProductDefinitionReviewDecision,
) -> ProductDefinitionReviewDecisionResponse:
    return ProductDefinitionReviewDecisionResponse(
        task=_task_response(decision.task),
        actor_id=decision.actor_id,
        execution_status=decision.execution_status,
    )


def _raise_review_http(exc: ProductDefinitionReviewError) -> NoReturn:
    status = 400
    if isinstance(exc, ProductDefinitionReviewForbiddenError):
        status = 403
    elif isinstance(exc, ProductDefinitionReviewNotFoundError):
        status = 404
    elif isinstance(exc, ProductDefinitionReviewConflictError):
        status = 409
    elif isinstance(exc, ProductDefinitionReviewValidationError):
        status = 422
    raise HTTPException(status_code=status, detail=exc.code) from exc


@router.get("", response_model=ProductDefinitionReviewTaskListResponse)
async def list_review_tasks(
    limit: int = Query(default=50, ge=1, le=100),
    repo: ProductDefinitionReviewRepository = Depends(get_product_definition_review_repository),
    context: ActorContext = Depends(get_actor_context),
) -> ProductDefinitionReviewTaskListResponse:
    try:
        tasks = await list_product_definition_review_tasks(
            repo,
            context,
            limit=limit,
        )
    except ProductDefinitionReviewError as exc:
        _raise_review_http(exc)
    return ProductDefinitionReviewTaskListResponse(
        items=tuple(_task_response(task) for task in tasks)
    )


@router.get("/{task_id}", response_model=ProductDefinitionReviewTaskResponse)
async def get_review_task(
    task_id: str,
    response: Response,
    repo: ProductDefinitionReviewRepository = Depends(get_product_definition_review_repository),
    context: ActorContext = Depends(get_actor_context),
) -> ProductDefinitionReviewTaskResponse:
    try:
        task = await get_product_definition_review_task(
            repo,
            context,
            task_id=task_id,
        )
    except ProductDefinitionReviewError as exc:
        _raise_review_http(exc)
    response.headers["ETag"] = task.etag
    return _task_response(task)


@router.post(
    "/{task_id}/decision",
    response_model=ProductDefinitionReviewDecisionResponse,
)
async def decide_review_task(
    task_id: str,
    body: ProductDefinitionReviewDecisionRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1),
    if_match: str = Header(alias="If-Match", min_length=1),
    repo: ProductDefinitionReviewRepository = Depends(get_product_definition_review_repository),
    context: ActorContext = Depends(get_actor_context),
) -> ProductDefinitionReviewDecisionResponse:
    try:
        decision = await decide_product_definition_review_task(
            repo,
            context,
            task_id=task_id,
            outcome=body.outcome,
            reason=body.reason,
            idempotency_key=idempotency_key,
            if_match=if_match,
        )
    except ProductDefinitionReviewError as exc:
        _raise_review_http(exc)
    response.headers["ETag"] = decision.task.etag
    return _decision_response(decision)


__all__ = ["router"]
