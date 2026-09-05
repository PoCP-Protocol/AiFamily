"""Durable and in-memory adapters for PDM operator review tasks."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    GateStatus,
    HumanTask,
    HumanTaskRow,
    InMemoryHumanGate,
    SqlAlchemyHumanGate,
)
from backend.intelligence.human_gate.errors import HumanGateError
from backend.platform.audit import AuditRecorder

from ..application.product_definition_adoption import (
    ADOPT_PRODUCT_DEFINITION_ACTION,
    ADOPTION_PURPOSE,
)
from ..application.product_definition_review import (
    ProductDefinitionReviewConflictError,
    ProductDefinitionReviewDecision,
    ProductDefinitionReviewNotFoundError,
    ProductDefinitionReviewTask,
    ReviewOutcome,
    review_task_from_human_task,
)


def _decision_id(tenant_scope: str, actor_id: str, task_id: str, idempotency_key: str) -> str:
    value = json.dumps(
        [tenant_scope, actor_id, task_id, idempotency_key],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"decision:{uuid5(NAMESPACE_URL, value)}"


def _translate_gate_error(exc: HumanGateError) -> Exception:
    if exc.code == "TASK_NOT_FOUND":
        return ProductDefinitionReviewNotFoundError("product_definition_review_task_not_found")
    if exc.code in {"TASK_ALREADY_DECIDED", "TASK_EXPIRED"}:
        return ProductDefinitionReviewConflictError(f"product_definition_review_{exc.code.lower()}")
    return ProductDefinitionReviewConflictError(f"product_definition_review_{exc.code.lower()}")


def _ensure_tenant(task: HumanTask, tenant_scope: str) -> None:
    if task.proposal.scope.tenant_id != tenant_scope:
        raise ProductDefinitionReviewNotFoundError("product_definition_review_task_not_found")


class SqlAlchemyProductDefinitionReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = SqlAlchemyHumanGate(session)

    async def list_open(
        self, *, tenant_scope: str, limit: int
    ) -> Sequence[ProductDefinitionReviewTask]:
        task_ids = await self._session.scalars(
            sa.select(HumanTaskRow.task_id)
            .where(
                HumanTaskRow.tenant_id == tenant_scope,
                HumanTaskRow.family_id.is_(None),
                HumanTaskRow.action_name == ADOPT_PRODUCT_DEFINITION_ACTION,
                HumanTaskRow.purpose == ADOPTION_PURPOSE,
                HumanTaskRow.status == GateStatus.OPEN.value,
                HumanTaskRow.expires_at > datetime.now(UTC),
            )
            .order_by(HumanTaskRow.created_at, HumanTaskRow.task_id)
            .limit(limit)
        )
        tasks: list[ProductDefinitionReviewTask] = []
        for task_id in task_ids:
            tasks.append(review_task_from_human_task(await self._gate.get(task_id)))
        return tuple(tasks)

    async def get(self, *, task_id: str, tenant_scope: str) -> ProductDefinitionReviewTask:
        visible_task_id = await self._session.scalar(
            sa.select(HumanTaskRow.task_id).where(
                HumanTaskRow.task_id == task_id,
                HumanTaskRow.tenant_id == tenant_scope,
                HumanTaskRow.family_id.is_(None),
                HumanTaskRow.action_name == ADOPT_PRODUCT_DEFINITION_ACTION,
                HumanTaskRow.purpose == ADOPTION_PURPOSE,
            )
        )
        if visible_task_id is None:
            raise ProductDefinitionReviewNotFoundError("product_definition_review_task_not_found")
        try:
            task = await self._gate.get(visible_task_id)
        except HumanGateError as exc:
            raise _translate_gate_error(exc) from exc
        _ensure_tenant(task, tenant_scope)
        return review_task_from_human_task(task)

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
    ) -> ProductDefinitionReviewDecision:
        recorder = AuditRecorder()
        resolved_decision_id = _decision_id(tenant_scope, actor_id, task_id, idempotency_key)
        try:
            current = await self.get(task_id=task_id, tenant_scope=tenant_scope)
            if (
                current.decision_id == resolved_decision_id
                and current.decision_outcome == outcome
                and current.decision_reason == reason
            ):
                return ProductDefinitionReviewDecision(
                    task=current,
                    actor_id=actor_id,
                    execution_status=("PENDING" if outcome == "ACCEPT" else "NOT_APPLICABLE"),
                )
            if current.etag != if_match:
                raise ProductDefinitionReviewConflictError(
                    "product_definition_review_etag_mismatch"
                )
            task, _ = await self._gate.decide(
                task_id,
                actor_id=actor_id,
                actor_type=ActorType.OPERATOR,
                outcome=DecisionOutcome(outcome),
                reason=reason,
                decision_id=resolved_decision_id,
                recorder=recorder,
            )
            _ensure_tenant(task, tenant_scope)
            await self._gate.flush_audit(recorder)
            await self._gate.commit()
        except HumanGateError as exc:
            await self._gate.rollback()
            raise _translate_gate_error(exc) from exc
        except Exception:
            await self._gate.rollback()
            raise
        projection = review_task_from_human_task(task)
        return ProductDefinitionReviewDecision(
            task=projection,
            actor_id=actor_id,
            execution_status=("PENDING" if outcome == "ACCEPT" else "NOT_APPLICABLE"),
        )


class FakeProductDefinitionReviewRepository:
    def __init__(self, tasks: Sequence[HumanTask] = ()) -> None:
        self.gate = InMemoryHumanGate()
        for task in tasks:
            self.gate.submit(task.proposal, task_id=task.task_id)

    async def list_open(
        self, *, tenant_scope: str, limit: int
    ) -> Sequence[ProductDefinitionReviewTask]:
        tasks = (
            task
            for task in self.gate._tasks.values()
            if task.status is GateStatus.OPEN
            and task.proposal.scope.tenant_id == tenant_scope
            and task.proposal.action_name == ADOPT_PRODUCT_DEFINITION_ACTION
            and task.proposal.scope.purpose == ADOPTION_PURPOSE
            and task.proposal.expires_at > datetime.now(UTC)
        )
        return tuple(review_task_from_human_task(task) for task in tasks)[:limit]

    async def get(self, *, task_id: str, tenant_scope: str) -> ProductDefinitionReviewTask:
        try:
            task = self.gate.get(task_id)
        except HumanGateError as exc:
            raise _translate_gate_error(exc) from exc
        _ensure_tenant(task, tenant_scope)
        return review_task_from_human_task(task)

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
    ) -> ProductDefinitionReviewDecision:
        current = await self.get(task_id=task_id, tenant_scope=tenant_scope)
        resolved_decision_id = _decision_id(tenant_scope, actor_id, task_id, idempotency_key)
        if (
            current.decision_id == resolved_decision_id
            and current.decision_outcome == outcome
            and current.decision_reason == reason
        ):
            return ProductDefinitionReviewDecision(
                task=current,
                actor_id=actor_id,
                execution_status=("PENDING" if outcome == "ACCEPT" else "NOT_APPLICABLE"),
            )
        if current.etag != if_match:
            raise ProductDefinitionReviewConflictError("product_definition_review_etag_mismatch")
        try:
            task, _ = self.gate.decide(
                task_id,
                actor_id=actor_id,
                actor_type=ActorType.OPERATOR,
                outcome=DecisionOutcome(outcome),
                reason=reason,
                decision_id=resolved_decision_id,
            )
        except HumanGateError as exc:
            raise _translate_gate_error(exc) from exc
        return ProductDefinitionReviewDecision(
            task=review_task_from_human_task(task),
            actor_id=actor_id,
            execution_status=("PENDING" if outcome == "ACCEPT" else "NOT_APPLICABLE"),
        )


__all__ = [
    "FakeProductDefinitionReviewRepository",
    "SqlAlchemyProductDefinitionReviewRepository",
]
