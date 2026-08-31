"""Application boundary for operator review of PDM adoption proposals."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal, Protocol

from backend.intelligence.human_gate.contracts import HumanTask

from .context import ActorContext
from .product_definition_adoption import (
    ADOPT_PRODUCT_DEFINITION_ACTION,
    ADOPTION_PURPOSE,
)

PRODUCT_DEFINITION_REVIEW_PERMISSION = "product_intelligence.product_definition.review"
ReviewOutcome = Literal["ACCEPT", "REJECT", "ESCALATE"]


class ProductDefinitionReviewError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ProductDefinitionReviewForbiddenError(ProductDefinitionReviewError):
    pass


class ProductDefinitionReviewNotFoundError(ProductDefinitionReviewError):
    pass


class ProductDefinitionReviewConflictError(ProductDefinitionReviewError):
    pass


class ProductDefinitionReviewValidationError(ProductDefinitionReviewError):
    pass


@dataclass(frozen=True, slots=True)
class ProductDefinitionReviewTask:
    task_id: str
    status: Literal["OPEN", "DECIDED", "EXPIRED"]
    proposal_id: str
    draft_id: str
    action_name: str
    action_arguments: Mapping[str, Any]
    risk_level: str
    provenance_ref: str
    created_at: datetime
    expires_at: datetime
    etag: str
    decision_id: str | None = None
    decision_outcome: ReviewOutcome | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProductDefinitionReviewDecision:
    task: ProductDefinitionReviewTask
    actor_id: str
    execution_status: Literal["PENDING", "NOT_APPLICABLE"]


class ProductDefinitionReviewRepository(Protocol):
    async def list_open(
        self, *, tenant_scope: str, limit: int
    ) -> Sequence[ProductDefinitionReviewTask]: ...

    async def get(self, *, task_id: str, tenant_scope: str) -> ProductDefinitionReviewTask: ...

    async def decide(
        self,
        *,
        task_id: str,
        tenant_scope: str,
        actor_id: str,
        outcome: ReviewOutcome,
        reason: str,
        idempotency_key: str,
        if_match: str,
    ) -> ProductDefinitionReviewDecision: ...


def review_task_from_human_task(task: HumanTask) -> ProductDefinitionReviewTask:
    """Project only the immutable fields safe for an operator review surface."""

    proposal = task.proposal
    if (
        proposal.action_name != ADOPT_PRODUCT_DEFINITION_ACTION
        or proposal.scope.family_id is not None
        or proposal.scope.purpose != ADOPTION_PURPOSE
    ):
        raise ProductDefinitionReviewNotFoundError("product_definition_review_task_not_found")
    decision = task.decision
    request = task.action_request
    payload = {
        "task_id": task.task_id,
        "proposal_id": proposal.proposal_id,
        "draft_id": proposal.draft_id,
        "action_name": proposal.action_name,
        "action_arguments": dict(proposal.action_arguments),
        "risk_level": proposal.risk_level,
        "provenance_ref": proposal.provenance_ref,
        "created_at": proposal.created_at.isoformat(),
        "expires_at": proposal.expires_at.isoformat(),
        "status": task.status.value,
        "decision_id": decision.decision_id if decision is not None else None,
        "decision_outcome": decision.outcome.value if decision is not None else None,
        "decision_reason": decision.reason if decision is not None else None,
        "decided_at": decision.decided_at.isoformat() if decision is not None else None,
        "request_id": request.request_id if request is not None else None,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    etag = '"' + sha256(canonical.encode()).hexdigest() + '"'
    outcome = decision.outcome.value if decision is not None else None
    return ProductDefinitionReviewTask(
        task_id=task.task_id,
        status=task.status.value,
        proposal_id=proposal.proposal_id,
        draft_id=proposal.draft_id,
        action_name=proposal.action_name,
        action_arguments=proposal.action_arguments,
        risk_level=proposal.risk_level,
        provenance_ref=proposal.provenance_ref,
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
        etag=etag,
        decision_id=decision.decision_id if decision is not None else None,
        decision_outcome=outcome,
        decision_reason=decision.reason if decision is not None else None,
        decided_at=decision.decided_at if decision is not None else None,
        request_id=request.request_id if request is not None else None,
    )


def _authorize(context: ActorContext) -> None:
    if (
        context.actor_type != "HUMAN"
        or PRODUCT_DEFINITION_REVIEW_PERMISSION not in context.permissions
    ):
        raise ProductDefinitionReviewForbiddenError("product_definition_review_permission_required")


async def list_product_definition_review_tasks(
    repo: ProductDefinitionReviewRepository,
    context: ActorContext,
    *,
    limit: int = 50,
) -> Sequence[ProductDefinitionReviewTask]:
    _authorize(context)
    if limit < 1 or limit > 100:
        raise ProductDefinitionReviewValidationError("product_definition_review_limit_invalid")
    return await repo.list_open(tenant_scope=context.tenant_scope, limit=limit)


async def get_product_definition_review_task(
    repo: ProductDefinitionReviewRepository,
    context: ActorContext,
    *,
    task_id: str,
) -> ProductDefinitionReviewTask:
    _authorize(context)
    if not task_id.strip():
        raise ProductDefinitionReviewValidationError("product_definition_review_task_id_required")
    return await repo.get(task_id=task_id, tenant_scope=context.tenant_scope)


async def decide_product_definition_review_task(
    repo: ProductDefinitionReviewRepository,
    context: ActorContext,
    *,
    task_id: str,
    outcome: ReviewOutcome,
    reason: str,
    idempotency_key: str,
    if_match: str,
) -> ProductDefinitionReviewDecision:
    _authorize(context)
    if not task_id.strip():
        raise ProductDefinitionReviewValidationError("product_definition_review_task_id_required")
    if outcome not in {"ACCEPT", "REJECT", "ESCALATE"}:
        raise ProductDefinitionReviewValidationError("product_definition_review_outcome_invalid")
    if not reason.strip():
        raise ProductDefinitionReviewValidationError("product_definition_review_reason_required")
    if not idempotency_key.strip():
        raise ProductDefinitionReviewValidationError(
            "product_definition_review_idempotency_key_required"
        )
    if not if_match.strip():
        raise ProductDefinitionReviewValidationError("product_definition_review_etag_required")
    return await repo.decide(
        task_id=task_id,
        tenant_scope=context.tenant_scope,
        actor_id=context.actor_id,
        outcome=outcome,
        reason=reason.strip(),
        idempotency_key=idempotency_key.strip(),
        if_match=if_match.strip(),
    )


__all__ = [
    "PRODUCT_DEFINITION_REVIEW_PERMISSION",
    "ProductDefinitionReviewConflictError",
    "ProductDefinitionReviewDecision",
    "ProductDefinitionReviewError",
    "ProductDefinitionReviewForbiddenError",
    "ProductDefinitionReviewNotFoundError",
    "ProductDefinitionReviewRepository",
    "ProductDefinitionReviewTask",
    "ProductDefinitionReviewValidationError",
    "ReviewOutcome",
    "decide_product_definition_review_task",
    "get_product_definition_review_task",
    "list_product_definition_review_tasks",
    "review_task_from_human_task",
]
