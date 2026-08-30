"""P0 FGCN orchestration with no payment or external side effect."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceNotFoundError,
    ServiceValidationError,
)
from backend.intelligence.human_gate import ActorType, NamedActionRequest
from backend.platform.audit import AuditEvent, AuditRecorder

from .contracts import (
    AllocationBasisType,
    AllocationBucket,
    AllocationLine,
    AllocationReleaseState,
    AllocationStatement,
    BlueprintSnapshot,
    CaseStatus,
    ContributionQualityState,
    GateServiceScope,
    ServiceCase,
    ServiceContribution,
    ServiceDelivery,
    ServiceTask,
    TaskAssignment,
    TaskAssignmentStatus,
    TaskQualityReview,
    TaskQualityState,
    TaskStatus,
)

if TYPE_CHECKING:
    from backend.intelligence.human_gate.contracts import GateScope


FIXED_ALLOCATION_UNITS = {
    AllocationBucket.PLATFORM: Decimal("20"),
    AllocationBucket.CONTENT_RESOURCE: Decimal("15"),
    AllocationBucket.CASE_STEWARD: Decimal("15"),
    AllocationBucket.QUALITY_RESERVE: Decimal("10"),
}
DELIVERY_ALLOCATION_UNITS = Decimal("40")
ALLOWED_ASSIGNEE_KINDS = frozenset({"STEWARD", "AI", "COACH", "EXPERT", "CONTENT"})


def _now(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ServiceValidationError("fgcn_timestamp_must_be_timezone_aware")
    return result


def _human(actor_id: str) -> str:
    if not actor_id or not actor_id.strip():
        raise ServiceValidationError("fgcn_actor_required")
    normalized = actor_id.strip()
    if normalized.lower().startswith("ai:") or normalized.upper() in {"AI", "SYSTEM"}:
        raise ServiceForbiddenError("fgcn_requires_human_actor")
    return normalized


class FGCNEngine:
    """A deterministic, auditable in-memory FGCN P0 service.

    This is a domain/application seam, not a database replacement.  Every
    mutation is represented by an immutable value and produces an AuditEvent;
    the durable adapter can later replay the same commands in one transaction.
    """

    def __init__(self, audit_recorder: AuditRecorder | None = None) -> None:
        self.audit = audit_recorder or AuditRecorder()
        self.cases: dict[str, ServiceCase] = {}
        self.tasks: dict[str, ServiceTask] = {}
        self.assignments: dict[str, TaskAssignment] = {}
        self.deliveries: dict[str, ServiceDelivery] = {}
        self.reviews: dict[str, TaskQualityReview] = {}
        self.contributions: dict[str, ServiceContribution] = {}
        self.statements: dict[str, AllocationStatement] = {}
        self._case_keys: dict[tuple[str, str, str], str] = {}
        self._assignment_requests: dict[tuple[str, str], str] = {}
        self._assignment_request_values: dict[tuple[str, str], NamedActionRequest] = {}
        self._task_by_case_key: dict[tuple[str, str], str] = {}
        self._delivery_by_task: dict[str, str] = {}
        self._contribution_by_delivery: dict[str, str] = {}
        self._allocation_run_cases: dict[str, str] = {}

    def open_case(
        self,
        *,
        case_id: str,
        scope: GateServiceScope,
        intent_ref: str,
        plan_ref: str,
        owner_id: str,
        blueprint: BlueprintSnapshot,
        idempotency_key: str,
        opened_at: datetime | None = None,
    ) -> ServiceCase:
        actor = _human(owner_id)
        if not idempotency_key.strip():
            raise ServiceValidationError("fgcn_case_idempotency_key_required")
        existing_id = self._case_keys.get((scope.tenant_id, scope.family_id, idempotency_key))
        if existing_id is not None:
            existing = self.cases[existing_id]
            if (
                existing.case_id != case_id
                or existing.scope != scope
                or existing.intent_ref != intent_ref
                or existing.plan_ref != plan_ref
                or existing.owner_id != actor
                or existing.blueprint != blueprint
            ):
                raise ServiceConflictError("fgcn_case_idempotency_replay_mismatch")
            return existing
        if case_id in self.cases:
            raise ServiceConflictError("fgcn_case_id_already_exists")
        case = ServiceCase(
            case_id=case_id,
            scope=scope,
            intent_ref=intent_ref,
            plan_ref=plan_ref,
            owner_id=actor,
            blueprint=blueprint,
            opened_at=_now(opened_at),
        )
        self.cases[case_id] = case
        self._case_keys[(scope.tenant_id, scope.family_id, idempotency_key)] = case_id
        self._audit(
            actor_id=actor,
            scope=scope,
            action="OPEN_SERVICE_CASE",
            resource_type="ServiceCase",
            resource_id=case_id,
            reason="published blueprint snapshot accepted",
            before=None,
            after={"status": case.status.value, "blueprint_ref": blueprint.blueprint_ref},
        )
        return case

    def create_task(
        self,
        *,
        task_id: str,
        case_id: str,
        task_key: str,
        title: str,
        description: str,
        role_key: str,
        acceptance_criteria: tuple[str, ...],
        task_weight: Decimal | int | str = Decimal("1"),
        actor_id: str,
        created_at: datetime | None = None,
    ) -> ServiceTask:
        case = self._case(case_id)
        actor = _human(actor_id)
        if task_id in self.tasks:
            raise ServiceConflictError("fgcn_task_id_already_exists")
        if (case_id, task_key) in self._task_by_case_key:
            raise ServiceConflictError("fgcn_task_key_already_exists_in_case")
        if task_key not in case.blueprint.task_template_keys:
            raise ServiceValidationError("fgcn_task_key_not_in_published_blueprint")
        task = ServiceTask(
            task_id=task_id,
            case_id=case_id,
            blueprint_ref=case.blueprint.blueprint_ref,
            blueprint_version=case.blueprint.version,
            task_key=task_key,
            title=title,
            description=description,
            role_key=role_key,
            acceptance_criteria=acceptance_criteria,
            task_weight=task_weight,
            created_at=_now(created_at),
        )
        self.tasks[task_id] = task
        self._task_by_case_key[(case_id, task_key)] = task_id
        self._audit(
            actor_id=actor,
            scope=case.scope,
            action="CREATE_SERVICE_TASK",
            resource_type="ServiceTask",
            resource_id=task_id,
            reason="task created from frozen blueprint template",
            before=None,
            after={"status": task.status.value, "task_key": task.task_key},
        )
        return task

    def execute_named_action(self, request: NamedActionRequest) -> TaskAssignment:
        """Execute the owning service-domain Named Action after Human Gate."""

        if not isinstance(request, NamedActionRequest):
            raise ServiceValidationError("fgcn_named_action_request_invalid")
        if request.action_name != "CONFIRM_SERVICE_TASK_ASSIGNMENT":
            raise ServiceValidationError("fgcn_named_action_not_supported")
        try:
            actor_type = ActorType(request.actor_type)
        except ValueError as exc:
            raise ServiceForbiddenError("fgcn_requires_human_actor") from exc
        if actor_type in {ActorType.AI, ActorType.SYSTEM}:
            raise ServiceForbiddenError("fgcn_requires_human_actor")
        actor = _human(request.actor_id)
        args = request.action_arguments
        task_id = self._argument(args, "service_task_id")
        assignee_ref = self._argument(args, "provider_id")
        assignee_kind = self._argument(args, "assignee_kind", default="EXPERT")
        if assignee_kind not in ALLOWED_ASSIGNEE_KINDS:
            raise ServiceValidationError("fgcn_assignee_kind_invalid")
        task = self._task(task_id)
        case = self._case(task.case_id)
        self._assert_scope(case, request.scope)
        request_key = (request.scope.tenant_id, request.idempotency_key)
        previous_assignment_id = self._assignment_requests.get(request_key)
        if previous_assignment_id is not None:
            previous_request = self._assignment_request_values[request_key]
            if previous_request != request:
                raise ServiceConflictError("fgcn_assignment_idempotency_replay_mismatch")
            return self.assignments[previous_assignment_id]
        if task.status is not TaskStatus.PENDING:
            raise ServiceConflictError("fgcn_task_already_has_responsible_person")
        if any(
            assignment.task_id == task_id and assignment.status is TaskAssignmentStatus.ACCEPTED
            for assignment in self.assignments.values()
        ):
            raise ServiceConflictError("fgcn_one_accepted_assignment_per_task")
        assignment_id = str(args.get("assignment_id") or f"assignment:{task_id}:{assignee_ref}")
        if assignment_id in self.assignments:
            raise ServiceConflictError("fgcn_assignment_id_already_exists")
        accepted_at = _now(None)
        assignment = TaskAssignment(
            assignment_id=assignment_id,
            case_id=case.case_id,
            task_id=task.task_id,
            assignee_ref=assignee_ref,
            assignee_kind=assignee_kind,
            status=TaskAssignmentStatus.ACCEPTED,
            accepted_by_actor_id=actor,
            source_request_id=request.request_id,
            accepted_at=accepted_at,
        )
        updated_task = replace(
            task,
            status=TaskStatus.ACCEPTED,
            responsible_ref=assignee_ref,
        )
        self.assignments[assignment_id] = assignment
        self.tasks[task.task_id] = updated_task
        self._assignment_requests[request_key] = assignment_id
        self._assignment_request_values[request_key] = request
        self._audit(
            actor_id=actor,
            scope=case.scope,
            action="CONFIRM_SERVICE_TASK_ASSIGNMENT",
            resource_type="TaskAssignment",
            resource_id=assignment_id,
            reason="human-confirmed assignment request",
            before=None,
            after={"status": assignment.status.value, "task_id": task.task_id},
        )
        self._audit(
            actor_id=actor,
            scope=case.scope,
            action="ACCEPT_SERVICE_TASK",
            resource_type="ServiceTask",
            resource_id=task.task_id,
            reason="task received one accepted responsible person",
            before={"status": task.status.value},
            after={"status": updated_task.status.value, "responsible_ref": assignee_ref},
        )
        if case.status is CaseStatus.OPEN:
            self.cases[case.case_id] = replace(case, status=CaseStatus.ASSIGNED)
            self._audit(
                actor_id=actor,
                scope=case.scope,
                action="ASSIGN_SERVICE_CASE",
                resource_type="ServiceCase",
                resource_id=case.case_id,
                reason="first task assignment opened case collaboration",
                before={"status": case.status.value},
                after={"status": CaseStatus.ASSIGNED.value},
            )
        return assignment

    def submit_delivery(
        self,
        *,
        delivery_id: str,
        task_id: str,
        assignee_ref: str,
        evidence_ref: str,
        submitted_at: datetime | None = None,
    ) -> ServiceDelivery:
        task = self._task(task_id)
        case = self._case(task.case_id)
        if delivery_id in self.deliveries:
            existing = self.deliveries[delivery_id]
            if (
                existing.task_id == task_id
                and existing.assignee_ref == assignee_ref
                and existing.evidence_ref == evidence_ref
            ):
                return existing
            raise ServiceConflictError("fgcn_delivery_id_already_exists")
        # A previously persisted delivery may be replayed above, but a new
        # delivery cannot be appended after a case reaches a terminal state.
        # Keep this guard before task-level checks so a stale accepted task
        # cannot bypass the case boundary after rehydration/racing updates.
        if case.status in {CaseStatus.COMPLETED, CaseStatus.CANCELLED}:
            raise ServiceConflictError("fgcn_delivery_case_is_terminal")
        if task.status is not TaskStatus.ACCEPTED or task.responsible_ref != assignee_ref:
            raise ServiceConflictError("fgcn_delivery_requires_assigned_responsible_person")
        existing_delivery_id = self._delivery_by_task.get(task_id)
        if existing_delivery_id is not None:
            existing = self.deliveries[existing_delivery_id]
            if existing.delivery_id == delivery_id and existing.evidence_ref == evidence_ref:
                return existing
            raise ServiceConflictError("fgcn_one_delivery_per_task_in_p0")
        delivery = ServiceDelivery(
            delivery_id=delivery_id,
            case_id=case.case_id,
            task_id=task.task_id,
            assignee_ref=assignee_ref,
            evidence_ref=evidence_ref,
            delivered_at=_now(submitted_at),
        )
        self.deliveries[delivery_id] = delivery
        self._delivery_by_task[task_id] = delivery_id
        self.tasks[task_id] = replace(
            task,
            status=TaskStatus.DELIVERED,
            deliverable_ref=evidence_ref,
        )
        self.cases[case.case_id] = replace(case, status=CaseStatus.IN_PROGRESS)
        self._audit(
            actor_id=assignee_ref,
            scope=case.scope,
            action="SUBMIT_SERVICE_DELIVERY",
            resource_type="ServiceDelivery",
            resource_id=delivery_id,
            reason="assigned resource submitted a delivery evidence reference",
            before=None,
            after={"task_id": task_id, "status": TaskStatus.DELIVERED.value},
        )
        updated_task = self.tasks[task_id]
        self._audit(
            actor_id=assignee_ref,
            scope=case.scope,
            action="DELIVER_SERVICE_TASK",
            resource_type="ServiceTask",
            resource_id=task_id,
            reason="delivery evidence moved the task to delivered",
            before={"status": task.status.value},
            after={"status": updated_task.status.value},
        )
        self._audit(
            actor_id=assignee_ref,
            scope=case.scope,
            action="PROGRESS_SERVICE_CASE",
            resource_type="ServiceCase",
            resource_id=case.case_id,
            reason="a task delivery moved the case into progress",
            before={"status": case.status.value},
            after={"status": CaseStatus.IN_PROGRESS.value},
        )
        return delivery

    def verify_delivery(
        self,
        *,
        quality_review_id: str,
        task_id: str,
        reviewer_ref: str,
        review_note: str,
        quality_state: TaskQualityState = TaskQualityState.PASSED,
        reviewed_at: datetime | None = None,
    ) -> TaskQualityReview:
        task = self._task(task_id)
        case = self._case(task.case_id)
        reviewer = _human(reviewer_ref)
        if quality_review_id in self.reviews:
            existing = self.reviews[quality_review_id]
            if existing.task_id != task_id or existing.reviewer_ref != reviewer:
                raise ServiceConflictError("fgcn_quality_review_id_reuse_mismatch")
            return existing
        if task.status is not TaskStatus.DELIVERED:
            raise ServiceConflictError("fgcn_quality_review_requires_delivery")
        if task.responsible_ref == reviewer:
            raise ServiceForbiddenError("fgcn_quality_reviewer_must_differ_from_delivery_person")
        try:
            quality_state = TaskQualityState(quality_state)
        except ValueError as exc:
            raise ServiceValidationError("fgcn_quality_state_invalid") from exc
        if quality_state is not TaskQualityState.PASSED:
            raise ServiceConflictError("fgcn_non_pass_quality_requires_rework_flow")
        review = TaskQualityReview(
            quality_review_id=quality_review_id,
            case_id=case.case_id,
            task_id=task.task_id,
            reviewer_ref=reviewer,
            quality_state=quality_state,
            review_note=review_note,
            reviewed_at=_now(reviewed_at),
        )
        self.reviews[quality_review_id] = review
        self.tasks[task_id] = replace(
            task,
            status=TaskStatus.VERIFIED,
            verified_at=review.reviewed_at,
        )
        self._audit(
            actor_id=reviewer,
            scope=case.scope,
            action="VERIFY_SERVICE_DELIVERY",
            resource_type="TaskQualityReview",
            resource_id=quality_review_id,
            reason="quality reviewer passed delivery against frozen criteria",
            before={"task_status": task.status.value},
            after={"task_status": TaskStatus.VERIFIED.value},
        )
        updated_task = self.tasks[task_id]
        self._audit(
            actor_id=reviewer,
            scope=case.scope,
            action="VERIFY_SERVICE_TASK",
            resource_type="ServiceTask",
            resource_id=task_id,
            reason="quality review moved task to verified",
            before={"status": task.status.value},
            after={"status": updated_task.status.value},
        )
        return review

    def record_contribution(
        self,
        *,
        contribution_id: str,
        task_id: str,
        delivery_id: str,
        provider_ref: str,
        role_key: str,
        started_at: datetime,
        completed_at: datetime,
    ) -> ServiceContribution:
        task = self._task(task_id)
        case = self._case(task.case_id)
        if task.status is not TaskStatus.VERIFIED:
            raise ServiceConflictError("fgcn_contribution_requires_verified_task")
        delivery = self.deliveries.get(delivery_id)
        if delivery is None or delivery.task_id != task_id or delivery.assignee_ref != provider_ref:
            raise ServiceForbiddenError("fgcn_contribution_delivery_mismatch")
        if contribution_id in self.contributions:
            existing = self.contributions[contribution_id]
            if existing.delivery_id == delivery_id:
                return existing
            raise ServiceConflictError("fgcn_contribution_id_already_exists")
        previous_id = self._contribution_by_delivery.get(delivery_id)
        if previous_id is not None:
            previous = self.contributions[previous_id]
            if previous.contribution_id == contribution_id:
                return previous
            raise ServiceConflictError("fgcn_one_contribution_per_delivery")
        contribution = ServiceContribution(
            contribution_id=contribution_id,
            case_id=case.case_id,
            task_id=task_id,
            provider_ref=provider_ref,
            role_key=role_key,
            delivery_id=delivery_id,
            quality_state=ContributionQualityState.VERIFIED,
            started_at=_now(started_at),
            completed_at=_now(completed_at),
        )
        self.contributions[contribution_id] = contribution
        self._contribution_by_delivery[delivery_id] = contribution_id
        self._audit(
            actor_id=provider_ref,
            scope=case.scope,
            action="RECORD_SERVICE_CONTRIBUTION",
            resource_type="ServiceContribution",
            resource_id=contribution_id,
            reason="verified delivery became a service contribution fact",
            before=None,
            after={"quality_state": contribution.quality_state.value, "task_id": task_id},
        )
        return contribution

    def close_case(
        self, *, case_id: str, actor_id: str, closed_at: datetime | None = None
    ) -> ServiceCase:
        case = self._case(case_id)
        actor = _human(actor_id)
        tasks = [task for task in self.tasks.values() if task.case_id == case_id]
        if not tasks:
            raise ServiceConflictError("fgcn_case_requires_tasks_before_close")
        if any(task.status not in {TaskStatus.VERIFIED, TaskStatus.CANCELLED} for task in tasks):
            raise ServiceConflictError("fgcn_case_has_unfinished_tasks")
        if not any(task.status is TaskStatus.VERIFIED for task in tasks):
            raise ServiceConflictError("fgcn_case_requires_verified_service")
        if case.status is CaseStatus.COMPLETED:
            return case
        closed_at_value = _now(closed_at)
        closed = replace(case, status=CaseStatus.COMPLETED, closed_at=closed_at_value)
        self.cases[case_id] = closed
        self._audit(
            actor_id=actor,
            scope=case.scope,
            action="CLOSE_SERVICE_CASE",
            resource_type="ServiceCase",
            resource_id=case_id,
            reason="all required tasks reached a terminal verified state",
            before={"status": case.status.value},
            after={"status": closed.status.value, "closed_at": closed_at_value.isoformat()},
        )
        return closed

    def finalize_shadow_allocation(
        self,
        *,
        case_id: str,
        actor_id: str,
        allocation_run_id: str,
        finalized_at: datetime | None = None,
    ) -> AllocationStatement:
        case = self._case(case_id)
        actor = _human(actor_id)
        existing = self.statements.get(case_id)
        if existing is not None:
            if existing.allocation_run_id == allocation_run_id:
                return existing
            raise ServiceConflictError("fgcn_one_allocation_run_per_case")
        previous_case_id = self._allocation_run_cases.get(allocation_run_id)
        if previous_case_id is not None and previous_case_id != case_id:
            raise ServiceConflictError("fgcn_allocation_run_id_already_exists")
        if case.status is not CaseStatus.COMPLETED:
            raise ServiceConflictError("fgcn_allocation_requires_completed_case")
        contributions = [item for item in self.contributions.values() if item.case_id == case_id]
        if not contributions:
            raise ServiceConflictError("fgcn_allocation_requires_verified_contribution")
        policy = case.blueprint
        lines: list[AllocationLine] = []
        for bucket, units in FIXED_ALLOCATION_UNITS.items():
            beneficiary_ref, beneficiary_kind, role_key = self._fixed_beneficiary(case, bucket)
            lines.append(
                AllocationLine(
                    allocation_id=f"allocation:{allocation_run_id}:{bucket.value}",
                    allocation_run_id=allocation_run_id,
                    case_id=case_id,
                    allocation_bucket=bucket,
                    units=units,
                    beneficiary_ref=beneficiary_ref,
                    beneficiary_kind=beneficiary_kind,
                    role_key=role_key,
                    policy_ref=policy.policy_ref,
                    policy_version=policy.policy_version,
                    basis_type=AllocationBasisType.CASE,
                    basis_ref=case_id,
                    release_state=(
                        AllocationReleaseState.HELD
                        if bucket is AllocationBucket.QUALITY_RESERVE
                        else AllocationReleaseState.RELEASED
                    ),
                )
            )
        for contribution, units in self._delivery_units(contributions):
            lines.append(
                AllocationLine(
                    allocation_id=f"allocation:{allocation_run_id}:{contribution.contribution_id}",
                    allocation_run_id=allocation_run_id,
                    case_id=case_id,
                    allocation_bucket=AllocationBucket.DELIVERY_RESOURCE,
                    units=units,
                    beneficiary_ref=contribution.provider_ref,
                    beneficiary_kind="ADMITTED_PROVIDER",
                    role_key=contribution.role_key,
                    policy_ref=policy.policy_ref,
                    policy_version=policy.policy_version,
                    basis_type=AllocationBasisType.CONTRIBUTION_WEIGHT,
                    basis_ref=contribution.contribution_id,
                    release_state=AllocationReleaseState.RELEASED,
                )
            )
        statement = AllocationStatement(
            allocation_run_id=allocation_run_id,
            case_id=case_id,
            policy_ref=policy.policy_ref,
            policy_version=policy.policy_version,
            triggered_by_actor_id=actor,
            total_units=Decimal("100"),
            lines=tuple(lines),
            created_at=_now(finalized_at),
        )
        self.statements[case_id] = statement
        self._allocation_run_cases[allocation_run_id] = case_id
        self.cases[case_id] = replace(case, shadow_allocation_finalized_at=statement.created_at)
        self._audit(
            actor_id=actor,
            scope=case.scope,
            action="FINALIZE_SHADOW_ALLOCATION",
            resource_type="AllocationStatement",
            resource_id=allocation_run_id,
            reason="frozen policy finalized once for the completed case; shadow units only",
            before={"shadow_allocation_finalized": False},
            after={"shadow_allocation_finalized": True, "total_units": "100"},
        )
        self._audit(
            actor_id=actor,
            scope=case.scope,
            action="MARK_SERVICE_CASE_SHADOW_ALLOCATED",
            resource_type="ServiceCase",
            resource_id=case_id,
            reason="case carries one finalized shadow allocation marker",
            before={"shadow_allocation_finalized": False},
            after={"shadow_allocation_finalized": True},
        )
        return statement

    def _case(self, case_id: str) -> ServiceCase:
        try:
            return self.cases[case_id]
        except KeyError as exc:
            raise ServiceNotFoundError("fgcn_service_case_not_found") from exc

    def _task(self, task_id: str) -> ServiceTask:
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise ServiceNotFoundError("fgcn_service_task_not_found") from exc

    @staticmethod
    def _argument(arguments, name: str, default: str | None = None) -> str:
        value = arguments.get(name, default)
        if not isinstance(value, str) or not value.strip():
            raise ServiceValidationError(f"fgcn_named_action_argument_{name}_required")
        return value.strip()

    @staticmethod
    def _assert_scope(case: ServiceCase, request_scope: GateScope) -> None:
        if request_scope.tenant_id != case.scope.tenant_id:
            raise ServiceForbiddenError("fgcn_tenant_scope_violation")
        if request_scope.family_id != case.scope.family_id:
            raise ServiceForbiddenError("fgcn_family_scope_violation")
        if request_scope.purpose != case.scope.purpose:
            raise ServiceForbiddenError("fgcn_purpose_scope_violation")
        if request_scope.consent_version != case.scope.consent_version:
            raise ServiceForbiddenError("fgcn_consent_version_scope_violation")
        if case.scope.subject_person_id not in request_scope.subject_ids:
            raise ServiceForbiddenError("fgcn_subject_scope_violation")
        if request_scope.correlation_id != case.scope.correlation_id:
            raise ServiceForbiddenError("fgcn_correlation_scope_violation")

    @staticmethod
    def _fixed_beneficiary(case: ServiceCase, bucket: AllocationBucket) -> tuple[str, str, str]:
        if bucket is AllocationBucket.PLATFORM:
            return "platform", "PLATFORM", "PLATFORM"
        if bucket is AllocationBucket.CONTENT_RESOURCE:
            return "content-resource", "INTERNAL_ACTOR", "CONTENT_RESOURCE"
        if bucket is AllocationBucket.CASE_STEWARD:
            return case.owner_id, "INTERNAL_ACTOR", "CASE_STEWARD"
        return "quality-reserve", "PLATFORM", "QUALITY_RESERVE"

    def _delivery_units(
        self, contributions: list[ServiceContribution]
    ) -> list[tuple[ServiceContribution, Decimal]]:
        weights = {
            item.contribution_id: self.tasks[item.task_id].task_weight for item in contributions
        }
        total_weight = sum(weights.values(), Decimal("0"))
        if total_weight <= 0:
            raise ServiceConflictError("fgcn_delivery_weights_invalid")
        exact = {
            item.contribution_id: DELIVERY_ALLOCATION_UNITS
            * weights[item.contribution_id]
            / total_weight
            for item in contributions
        }
        rounded = {
            contribution_id: value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            for contribution_id, value in exact.items()
        }
        remainder = DELIVERY_ALLOCATION_UNITS - sum(rounded.values(), Decimal("0"))
        increments = int(remainder / Decimal("0.01"))
        ordered = sorted(
            contributions,
            key=lambda item: (
                exact[item.contribution_id] - rounded[item.contribution_id],
                item.contribution_id,
            ),
            reverse=True,
        )
        for item in ordered[:increments]:
            rounded[item.contribution_id] += Decimal("0.01")
        return [(item, rounded[item.contribution_id]) for item in contributions]

    def _audit(
        self,
        *,
        actor_id: str,
        scope: GateServiceScope,
        action: str,
        resource_type: str,
        resource_id: str,
        reason: str,
        before: dict | None,
        after: dict | None,
    ) -> None:
        self.audit.record(
            AuditEvent(
                actor_id=actor_id,
                tenant_id=scope.tenant_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                reason=reason,
                correlation_id=scope.correlation_id,
                before=before,
                after=after,
            )
        )


__all__ = ["FGCNEngine"]
