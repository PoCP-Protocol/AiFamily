"""Durable application command for the FGCN delivery boundary.

The assignment command is the first business fact after Human Gate.  This
module advances one accepted task to a delivery-evidence fact without calling
AI or writing a contribution/settlement record.  The repository owns the
task/case state transition; this command owns scope, actor, audit, and commit
coordination.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)
from backend.platform.audit import AuditEvent, AuditRecorder

from .contracts import (
    CaseStatus,
    GateServiceScope,
    ServiceCase,
    ServiceDelivery,
    ServiceTask,
    TaskStatus,
)


class FGCNDeliveryRepository(Protocol):
    """The narrow repository port needed by the delivery command."""

    async def load_case(self, case_id: str) -> ServiceCase: ...

    async def load_task(self, task_id: str) -> ServiceTask: ...

    async def load_delivery(self, task_id: str) -> ServiceDelivery: ...

    async def save_delivery(self, delivery: ServiceDelivery) -> None: ...

    async def flush_audit(self, recorder: AuditRecorder) -> int: ...

    async def commit(self) -> None: ...


def _human_actor(actor_id: str) -> str:
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ServiceValidationError("fgcn_delivery_actor_required")
    actor = actor_id.strip()
    if actor.upper() in {"AI", "SYSTEM"} or actor.lower().startswith(("ai:", "system:")):
        raise ServiceForbiddenError("fgcn_delivery_requires_human_actor")
    return actor


def _assert_scope(case: ServiceCase, scope: GateServiceScope) -> None:
    if not isinstance(scope, GateServiceScope):
        raise ServiceValidationError("fgcn_delivery_scope_invalid")
    for field_name, error_code in (
        ("tenant_id", "fgcn_tenant_scope_violation"),
        ("family_id", "fgcn_family_scope_violation"),
        ("subject_person_id", "fgcn_subject_scope_violation"),
        ("purpose", "fgcn_purpose_scope_violation"),
        ("consent_version", "fgcn_consent_version_scope_violation"),
        ("correlation_id", "fgcn_correlation_scope_violation"),
    ):
        if getattr(scope, field_name) != getattr(case.scope, field_name):
            raise ServiceForbiddenError(error_code)


def _replay_matches(
    existing: ServiceDelivery,
    *,
    delivery_id: str,
    task_id: str,
    assignee_ref: str,
    evidence_ref: str,
    outcome_observation: str,
) -> bool:
    """Compare business input while ignoring server-generated delivery time."""

    return (
        existing.delivery_id == delivery_id
        and existing.task_id == task_id
        and existing.assignee_ref == assignee_ref
        and existing.evidence_ref == evidence_ref
        and existing.outcome_observation == outcome_observation.strip()
    )


async def submit_service_delivery(
    repo: FGCNDeliveryRepository,
    *,
    task_id: str,
    delivery_id: str,
    evidence_ref: str,
    outcome_observation: str,
    actor_id: str,
    scope: GateServiceScope,
    recorder: AuditRecorder,
    delivered_at: datetime | None = None,
) -> ServiceDelivery:
    """Record one delivery evidence reference for an accepted FGCN task.

    A retry of the same delivery returns the durable delivery and emits no new
    audit rows.  A different payload for the same task is rejected.  The
    caller's session owns the transaction: domain state and audit rows are
    flushed together and committed exactly once here.
    """

    task = await repo.load_task(task_id)
    case = await repo.load_case(task.case_id)
    _assert_scope(case, scope)

    if task.status in {
        TaskStatus.DELIVERED,
        TaskStatus.VERIFIED,
        TaskStatus.CLOSED,
    }:
        replay_actor = _human_actor(actor_id)
        existing = await repo.load_delivery(task_id)
        if _replay_matches(
            existing,
            delivery_id=delivery_id,
            task_id=task_id,
            assignee_ref=replay_actor,
            evidence_ref=evidence_ref,
            outcome_observation=outcome_observation,
        ):
            return existing
        raise ServiceConflictError("fgcn_delivery_idempotency_replay_mismatch")

    if case.status in {CaseStatus.COMPLETED, CaseStatus.CANCELLED}:
        raise ServiceConflictError("fgcn_delivery_case_is_terminal")
    if task.status is not TaskStatus.ACCEPTED:
        raise ServiceConflictError("fgcn_delivery_requires_assigned_responsible_person")
    actor = _human_actor(actor_id)
    if task.responsible_ref != actor:
        raise ServiceForbiddenError("fgcn_delivery_actor_mismatch")

    delivery = ServiceDelivery(
        delivery_id=delivery_id,
        case_id=case.case_id,
        task_id=task.task_id,
        assignee_ref=actor,
        evidence_ref=evidence_ref,
        outcome_observation=outcome_observation,
        delivered_at=delivered_at or datetime.now(UTC),
        locale=task.locale,
    )
    await repo.save_delivery(delivery)

    recorder.record(
        AuditEvent(
            actor_id=actor,
            tenant_id=case.scope.tenant_id,
            action="SUBMIT_SERVICE_DELIVERY",
            resource_type="ServiceDelivery",
            resource_id=delivery.delivery_id,
            reason="assigned resource submitted a delivery evidence reference",
            correlation_id=case.scope.correlation_id,
            after={"task_id": task_id, "status": TaskStatus.DELIVERED.value},
        )
    )
    recorder.record(
        AuditEvent(
            actor_id=actor,
            tenant_id=case.scope.tenant_id,
            action="DELIVER_SERVICE_TASK",
            resource_type="ServiceTask",
            resource_id=task_id,
            reason="delivery evidence moved the task to delivered",
            correlation_id=case.scope.correlation_id,
            before={"status": task.status.value},
            after={"status": TaskStatus.DELIVERED.value},
        )
    )
    recorder.record(
        AuditEvent(
            actor_id=actor,
            tenant_id=case.scope.tenant_id,
            action="PROGRESS_SERVICE_CASE",
            resource_type="ServiceCase",
            resource_id=case.case_id,
            reason="a task delivery moved the case into progress",
            correlation_id=case.scope.correlation_id,
            before={"status": case.status.value},
            after={"status": CaseStatus.IN_PROGRESS.value},
        )
    )
    await repo.flush_audit(recorder)
    await repo.commit()
    return delivery


__all__ = ["FGCNDeliveryRepository", "submit_service_delivery"]
