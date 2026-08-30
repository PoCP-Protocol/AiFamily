"""Durable application boundary for the FGCN Human Gate bridge.

The AI path ends at ``NamedActionRequest``. This module is the only P0
application command that turns the accepted request into a durable assignment:
it re-checks the frozen case scope, writes the task/assignment/case changes,
flushes the audit events through the same repository transaction, and commits
once. It deliberately does not call a model provider, send a notification, or
create a payment/settlement record.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)
from backend.intelligence.human_gate import (
    ActorType,
    GateScope,
    NamedActionRequest,
)
from backend.intelligence.human_gate.contracts import HUMAN_ACTOR_TYPES
from backend.platform.audit import AuditEvent, AuditRecorder

from .contracts import (
    CaseStatus,
    ServiceCase,
    ServiceTask,
    TaskAssignment,
    TaskAssignmentStatus,
    TaskStatus,
)


class FGCNAssignmentRepository(Protocol):
    """The narrow durable port used by the assignment command."""

    async def load_case(self, case_id: str) -> ServiceCase: ...

    async def load_task(self, task_id: str) -> ServiceTask: ...

    async def find_assignment_by_source_request_id(
        self, *, source_request_id: str
    ) -> TaskAssignment | None: ...

    async def save_case(self, case: ServiceCase) -> None: ...

    async def save_task(self, task: ServiceTask) -> None: ...

    async def save_assignment(self, assignment: TaskAssignment) -> None: ...

    async def flush_audit(self, recorder: AuditRecorder) -> int: ...

    async def commit(self) -> None: ...


def _now(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ServiceValidationError("fgcn_assignment_timestamp_must_be_timezone_aware")
    return result


def _argument(arguments: Mapping[str, object], name: str, default: str | None = None) -> str:
    value = arguments.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError(f"fgcn_named_action_argument_{name}_required")
    return value.strip()


def _assert_human_request(request: NamedActionRequest) -> str:
    try:
        actor_type = ActorType(request.actor_type)
    except ValueError as exc:
        raise ServiceForbiddenError("fgcn_requires_human_actor") from exc
    if actor_type not in HUMAN_ACTOR_TYPES:
        raise ServiceForbiddenError("fgcn_requires_human_actor")
    actor_id = request.actor_id.strip()
    if not actor_id:
        raise ServiceValidationError("fgcn_actor_required")
    if actor_id.lower().startswith("ai:") or actor_id.upper() in {"AI", "SYSTEM"}:
        raise ServiceForbiddenError("fgcn_requires_human_actor")
    return actor_id


def _assert_scope(case: ServiceCase, scope: GateScope) -> None:
    if scope.tenant_id != case.scope.tenant_id:
        raise ServiceForbiddenError("fgcn_tenant_scope_violation")
    if scope.family_id != case.scope.family_id:
        raise ServiceForbiddenError("fgcn_family_scope_violation")
    if case.scope.subject_person_id not in scope.subject_ids:
        raise ServiceForbiddenError("fgcn_subject_scope_violation")
    if scope.purpose != case.scope.purpose:
        raise ServiceForbiddenError("fgcn_purpose_scope_violation")
    if scope.consent_version != case.scope.consent_version:
        raise ServiceForbiddenError("fgcn_consent_version_scope_violation")
    if scope.correlation_id != case.scope.correlation_id:
        raise ServiceForbiddenError("fgcn_correlation_scope_violation")


def _assignment_matches(
    existing: TaskAssignment,
    *,
    case: ServiceCase,
    task: ServiceTask,
    request: NamedActionRequest,
    actor_id: str,
    assignee_ref: str,
    assignee_kind: str,
    assignment_id: str,
) -> bool:
    return (
        existing.case_id == case.case_id
        and existing.task_id == task.task_id
        and existing.assignment_id == assignment_id
        and existing.assignee_ref == assignee_ref
        and existing.assignee_kind == assignee_kind
        and existing.status is TaskAssignmentStatus.ACCEPTED
        and existing.accepted_by_actor_id == actor_id
        and existing.source_request_id == request.request_id
    )


async def execute_task_assignment_named_action(
    repo: FGCNAssignmentRepository,
    request: NamedActionRequest,
    *,
    recorder: AuditRecorder,
    accepted_at: datetime | None = None,
) -> TaskAssignment:
    """Execute ``CONFIRM_SERVICE_TASK_ASSIGNMENT`` after Human Gate approval.

    The command is intentionally idempotent by the durable request id. A
    replay of the same request returns the persisted assignment without adding
    audit rows; a request id reused with different content is rejected. All
    new writes and their audit events are committed through one repository
    transaction.
    """

    if not isinstance(request, NamedActionRequest):
        raise ServiceValidationError("fgcn_named_action_request_invalid")
    if request.action_name != "CONFIRM_SERVICE_TASK_ASSIGNMENT":
        raise ServiceValidationError("fgcn_named_action_not_supported")
    actor_id = _assert_human_request(request)
    args = request.action_arguments
    task_id = _argument(args, "service_task_id")
    assignee_ref = _argument(args, "provider_id")
    assignee_kind = _argument(args, "assignee_kind", default="EXPERT")
    if "assignment_id" in args:
        assignment_id = _argument(args, "assignment_id")
    else:
        assignment_id = str(uuid5(NAMESPACE_URL, f"fgcn-assignment:{request.request_id}"))
    if assignee_kind not in {"STEWARD", "AI", "COACH", "EXPERT", "CONTENT"}:
        raise ServiceValidationError("fgcn_assignee_kind_invalid")

    task = await repo.load_task(task_id)
    case = await repo.load_case(task.case_id)
    _assert_scope(case, request.scope)

    existing = await repo.find_assignment_by_source_request_id(source_request_id=request.request_id)
    if existing is not None:
        if not _assignment_matches(
            existing,
            case=case,
            task=task,
            request=request,
            actor_id=actor_id,
            assignee_ref=assignee_ref,
            assignee_kind=assignee_kind,
            assignment_id=assignment_id,
        ):
            raise ServiceConflictError("fgcn_assignment_idempotency_replay_mismatch")
        return existing

    if case.status in {CaseStatus.COMPLETED, CaseStatus.CANCELLED}:
        raise ServiceConflictError("fgcn_case_is_terminal")
    if task.status is not TaskStatus.PENDING:
        raise ServiceConflictError("fgcn_task_already_has_responsible_person")

    accepted_at = _now(accepted_at)
    assignment = TaskAssignment(
        assignment_id=assignment_id,
        case_id=case.case_id,
        task_id=task.task_id,
        assignee_ref=assignee_ref,
        assignee_kind=assignee_kind,
        status=TaskAssignmentStatus.ACCEPTED,
        accepted_by_actor_id=actor_id,
        source_request_id=request.request_id,
        accepted_at=accepted_at,
    )
    updated_task = replace(
        task,
        status=TaskStatus.ACCEPTED,
        responsible_ref=assignee_ref,
    )
    # The repository validates that an assignment can only follow an accepted
    # task. Save the state transition first, then the assignment row.
    await repo.save_task(updated_task)
    await repo.save_assignment(assignment)

    recorder.record(
        AuditEvent(
            actor_id=actor_id,
            tenant_id=case.scope.tenant_id,
            action="CONFIRM_SERVICE_TASK_ASSIGNMENT",
            resource_type="TaskAssignment",
            resource_id=assignment.assignment_id,
            reason="human-confirmed assignment request",
            correlation_id=case.scope.correlation_id,
            after={"status": assignment.status.value, "task_id": task.task_id},
        )
    )
    recorder.record(
        AuditEvent(
            actor_id=actor_id,
            tenant_id=case.scope.tenant_id,
            action="ACCEPT_SERVICE_TASK",
            resource_type="ServiceTask",
            resource_id=task.task_id,
            reason="task received one accepted responsible person",
            correlation_id=case.scope.correlation_id,
            before={"status": task.status.value},
            after={"status": updated_task.status.value, "responsible_ref": assignee_ref},
        )
    )

    if case.status is CaseStatus.OPEN:
        updated_case = replace(case, status=CaseStatus.ASSIGNED)
        await repo.save_case(updated_case)
        recorder.record(
            AuditEvent(
                actor_id=actor_id,
                tenant_id=case.scope.tenant_id,
                action="ASSIGN_SERVICE_CASE",
                resource_type="ServiceCase",
                resource_id=case.case_id,
                reason="first task assignment opened case collaboration",
                correlation_id=case.scope.correlation_id,
                before={"status": case.status.value},
                after={"status": updated_case.status.value},
            )
        )

    await repo.flush_audit(recorder)
    await repo.commit()
    return assignment


__all__ = ["FGCNAssignmentRepository", "execute_task_assignment_named_action"]
