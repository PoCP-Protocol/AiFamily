"""Durable application boundary for the FGCN Human Gate bridge.

The AI path ends at ``NamedActionRequest``. This module is the only P0
application command that turns the accepted request into a durable assignment:
it re-checks the frozen case scope, writes the task/assignment/case changes,
flushes the audit events through the same repository transaction, and commits
once. It deliberately does not call a model provider, send a notification, or
create a payment/settlement record.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceNotFoundError,
    ServiceValidationError,
)
from backend.intelligence.human_gate import (
    ActorType,
    GateScope,
    NamedActionRequest,
)
from backend.intelligence.human_gate.contracts import HUMAN_ACTOR_TYPES
from backend.platform.audit import AuditEvent, AuditRecorder

from .admission import (
    DEFAULT_ASYNC_PROVIDER_ADMISSION,
    AsyncProviderAdmissionQuery,
    require_provider_admitted_async,
)
from .contracts import (
    BlueprintSnapshot,
    CaseOpeningIdempotencyRecord,
    CaseStatus,
    GateServiceScope,
    ServiceCase,
    ServiceTask,
    TaskAssignment,
    TaskAssignmentStatus,
    TaskStatus,
)
from .entry import (
    DEFAULT_ASYNC_CASE_ENTRY_DEPENDENCIES,
    AsyncCaseEntryDependencyQuery,
    require_case_entry_dependencies_async,
)


class FGCNCaseRepository(Protocol):
    """The narrow durable port used by the protected case-opening command."""

    async def load_case(self, case_id: str) -> ServiceCase: ...

    async def save_case(self, case: ServiceCase) -> None: ...

    async def flush_audit(self, recorder: AuditRecorder) -> int: ...

    async def commit(self) -> None: ...

    async def claim_case_opening(
        self, *, scope: GateServiceScope, idempotency_key: str, request_hash: str
    ) -> CaseOpeningIdempotencyRecord: ...

    async def complete_case_opening(
        self,
        *,
        scope: GateServiceScope,
        idempotency_key: str,
        request_hash: str,
        case_id: str,
    ) -> None: ...


class FGCNAssignmentRepository(FGCNCaseRepository, Protocol):
    """The narrow durable port used by the assignment command."""

    async def load_task(self, task_id: str) -> ServiceTask: ...

    async def find_assignment_by_source_request_id(
        self, *, source_request_id: str
    ) -> TaskAssignment | None: ...

    async def save_task(self, task: ServiceTask) -> None: ...

    async def save_assignment(self, assignment: TaskAssignment) -> None: ...


def _assert_case_owner(owner_id: str) -> str:
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ServiceValidationError("fgcn_actor_required")
    normalized = owner_id.strip()
    if normalized.lower().startswith("ai:") or normalized.upper() in {"AI", "SYSTEM"}:
        raise ServiceForbiddenError("fgcn_requires_human_actor")
    return normalized


def _case_open_request_matches(
    existing: ServiceCase,
    *,
    scope: GateServiceScope,
    intent_ref: str,
    plan_ref: str,
    owner_id: str,
    blueprint: BlueprintSnapshot,
) -> bool:
    return (
        existing.scope == scope
        and existing.intent_ref == intent_ref
        and existing.plan_ref == plan_ref
        and existing.owner_id == owner_id
        and existing.blueprint == blueprint
    )


def _case_open_request_hash(
    *,
    case_id: str,
    scope: GateServiceScope,
    intent_ref: str,
    plan_ref: str,
    owner_id: str,
    blueprint: BlueprintSnapshot,
) -> str:
    canonical = json.dumps(
        {
            "action": "OPEN_SERVICE_CASE",
            "case_id": case_id,
            "scope": {
                "tenant_id": scope.tenant_id,
                "family_id": scope.family_id,
                "subject_person_id": scope.subject_person_id,
                "purpose": scope.purpose,
                "consent_version": scope.consent_version,
                "correlation_id": scope.correlation_id,
            },
            "intent_ref": intent_ref,
            "plan_ref": plan_ref,
            "owner_id": owner_id,
            "blueprint": {
                "blueprint_ref": blueprint.blueprint_ref,
                "version": blueprint.version,
                "status": blueprint.status,
                "policy_ref": blueprint.policy_ref,
                "policy_version": blueprint.policy_version,
                "checksum": blueprint.checksum,
                "task_template_keys": blueprint.task_template_keys,
                "scenario": {
                    "scenario_key": blueprint.scenario.scenario_key,
                    "family_problem": blueprint.scenario.family_problem,
                    "provider_deliverable": blueprint.scenario.provider_deliverable,
                    "service_outcome": blueprint.scenario.service_outcome,
                },
                "total_units": str(blueprint.total_units),
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def open_service_case(
    repo: FGCNCaseRepository,
    *,
    case_id: str,
    scope: GateServiceScope,
    intent_ref: str,
    plan_ref: str,
    owner_id: str,
    blueprint: BlueprintSnapshot,
    idempotency_key: str,
    recorder: AuditRecorder,
    entry_dependencies: AsyncCaseEntryDependencyQuery = DEFAULT_ASYNC_CASE_ENTRY_DEPENDENCIES,
    opened_at: datetime | None = None,
) -> ServiceCase:
    """Open a durable case only after all external entry dependencies pass.

    The existing platform idempotency table stores a tenant-scoped opaque key
    and request hash in the same transaction as the case and audit event. A
    replay with the same immutable case payload returns the stored case;
    changed scope, intent, plan, owner, blueprint, or case id is rejected.
    """

    owner = _assert_case_owner(owner_id)
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ServiceValidationError("fgcn_case_idempotency_key_required")
    request_hash = _case_open_request_hash(
        case_id=case_id,
        scope=scope,
        intent_ref=intent_ref,
        plan_ref=plan_ref,
        owner_id=owner,
        blueprint=blueprint,
    )
    opening_time = _now(opened_at)
    candidate = ServiceCase(
        case_id=case_id,
        scope=scope,
        intent_ref=intent_ref,
        plan_ref=plan_ref,
        owner_id=owner,
        blueprint=blueprint,
        opened_at=opening_time,
    )

    try:
        existing = await repo.load_case(case_id)
    except ServiceNotFoundError:
        existing = None
    if existing is not None:
        if not _case_open_request_matches(
            existing,
            scope=scope,
            intent_ref=intent_ref,
            plan_ref=plan_ref,
            owner_id=owner,
            blueprint=blueprint,
        ):
            raise ServiceConflictError("fgcn_case_idempotency_replay_mismatch")
        reservation = await repo.claim_case_opening(
            scope=scope, idempotency_key=idempotency_key.strip(), request_hash=request_hash
        )
        if reservation.case_id is not None and reservation.case_id != existing.case_id:
            raise ServiceConflictError("fgcn_case_opening_idempotency_case_mismatch")
        if reservation.case_id is None and reservation.is_new:
            await repo.complete_case_opening(
                scope=scope,
                idempotency_key=idempotency_key.strip(),
                request_hash=request_hash,
                case_id=existing.case_id,
            )
            await repo.commit()
        return existing

    entry_snapshot = await require_case_entry_dependencies_async(
        entry_dependencies,
        scope=scope,
        intent_ref=intent_ref,
        as_of=opening_time,
    )
    reservation = await repo.claim_case_opening(
        scope=scope, idempotency_key=idempotency_key.strip(), request_hash=request_hash
    )
    if reservation.case_id is not None:
        try:
            replay = await repo.load_case(reservation.case_id)
        except ServiceNotFoundError as exc:
            raise ServiceConflictError("fgcn_case_opening_idempotency_case_missing") from exc
        if not _case_open_request_matches(
            replay,
            scope=scope,
            intent_ref=intent_ref,
            plan_ref=plan_ref,
            owner_id=owner,
            blueprint=blueprint,
        ):
            raise ServiceConflictError("fgcn_case_opening_idempotency_replay_mismatch")
        return replay
    if not reservation.is_new:
        raise ServiceConflictError("fgcn_case_opening_idempotency_incomplete")
    await repo.save_case(candidate)
    recorder.record(
        AuditEvent(
            actor_id=owner,
            tenant_id=scope.tenant_id,
            action="OPEN_SERVICE_CASE",
            resource_type="ServiceCase",
            resource_id=candidate.case_id,
            reason="confirmed intent, active consent, and tenant-family binding accepted",
            correlation_id=scope.correlation_id,
            after={
                "status": candidate.status.value,
                "blueprint_ref": candidate.blueprint.blueprint_ref,
                "scenario_key": candidate.blueprint.scenario.scenario_key,
                "family_request_ref": entry_snapshot.family_request.ref,
                "family_request_status": entry_snapshot.family_request.status,
                "family_request_version": entry_snapshot.family_request.version,
                "family_request_locale": entry_snapshot.family_request.locale,
                "self_help_action_refs": tuple(
                    action.ref for action in entry_snapshot.self_help_actions
                ),
                "self_help_observation_refs": tuple(
                    observation.ref for observation in entry_snapshot.self_help_observations
                ),
            },
        )
    )
    await repo.complete_case_opening(
        scope=scope,
        idempotency_key=idempotency_key.strip(),
        request_hash=request_hash,
        case_id=candidate.case_id,
    )
    await repo.flush_audit(recorder)
    await repo.commit()
    return candidate


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


def _assignment_request_hash(
    *,
    case_id: str,
    task_id: str,
    assignment_id: str,
    assignee_ref: str,
    assignee_kind: str,
    accepted_by_actor_id: str,
    source_request_id: str,
) -> str:
    """Hash the immutable assignment identity, excluding lifecycle state.

    ``TaskAssignment.status`` is a delivery lifecycle fact. It can move from
    ``ACCEPTED`` to ``COMPLETED`` or ``REVOKED`` after the Named Action has
    committed, so it must never participate in the request replay identity.
    The fields below are the canonical, durable projection of the accepted
    request that the assignment row retains.
    """

    canonical = json.dumps(
        {
            "action": "CONFIRM_SERVICE_TASK_ASSIGNMENT",
            "case_id": case_id,
            "task_id": task_id,
            "assignment_id": assignment_id,
            "assignee_ref": assignee_ref,
            "assignee_kind": assignee_kind,
            "accepted_by_actor_id": accepted_by_actor_id,
            "source_request_id": source_request_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    expected_hash = _assignment_request_hash(
        case_id=case.case_id,
        task_id=task.task_id,
        assignment_id=assignment_id,
        assignee_ref=assignee_ref,
        assignee_kind=assignee_kind,
        accepted_by_actor_id=actor_id,
        source_request_id=request.request_id,
    )
    existing_hash = _assignment_request_hash(
        case_id=existing.case_id,
        task_id=existing.task_id,
        assignment_id=existing.assignment_id,
        assignee_ref=existing.assignee_ref,
        assignee_kind=existing.assignee_kind,
        accepted_by_actor_id=existing.accepted_by_actor_id,
        source_request_id=existing.source_request_id,
    )
    return expected_hash == existing_hash


async def execute_task_assignment_named_action(
    repo: FGCNAssignmentRepository,
    request: NamedActionRequest,
    *,
    recorder: AuditRecorder,
    provider_admission: AsyncProviderAdmissionQuery = DEFAULT_ASYNC_PROVIDER_ADMISSION,
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
    await require_provider_admitted_async(
        provider_admission,
        provider_ref=assignee_ref,
        assignee_kind=assignee_kind,
        required_capability_keys=task.required_capability_keys,
        scope=case.scope,
    )

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


__all__ = [
    "FGCNAssignmentRepository",
    "FGCNCaseRepository",
    "execute_task_assignment_named_action",
    "open_service_case",
]
