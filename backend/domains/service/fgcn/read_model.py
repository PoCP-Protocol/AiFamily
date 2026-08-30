"""Read-only FGCN progress projections.

The projector deliberately accepts only the immutable facts owned by the FGCN
contracts.  It does not load data, mutate aggregates, call a model, calculate
family scores/ranks, or turn shadow units into money.  A caller must provide a
scope snapshot when a projection is requested on behalf of a family actor;
tenant, family, subject, purpose, and consent mismatches fail closed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)

from .admission import ProviderAdmissionSnapshot, assert_provider_admitted
from .contracts import (
    AllocationBasisType,
    AllocationBucket,
    AllocationReleaseState,
    AllocationStatement,
    CaseStatus,
    ContributionQualityState,
    GateServiceScope,
    ServiceCase,
    ServiceContribution,
    ServiceDelivery,
    ServiceTask,
    TaskAssignment,
    TaskQualityReview,
    TaskQualityState,
    TaskStatus,
)


@dataclass(frozen=True, slots=True)
class ServiceTaskProgressProjection:
    """A task's current status and its delivery/quality boundary."""

    task_id: str
    task_key: str
    status: TaskStatus
    responsible_ref: str | None
    delivery_id: str | None
    evidence_ref: str | None
    quality_review_id: str | None
    quality_state: TaskQualityState | None
    verified_at: datetime | None
    verified_contribution_ids: tuple[str, ...]

    @property
    def delivery_verified(self) -> bool:
        return (
            self.status is TaskStatus.VERIFIED
            and self.delivery_id is not None
            and self.quality_state is TaskQualityState.PASSED
        )


@dataclass(frozen=True, slots=True)
class VerifiedContributionProjection:
    """A contribution that can be traced to one verified delivery."""

    contribution_id: str
    task_id: str
    delivery_id: str
    provider_ref: str
    role_key: str
    quality_state: ContributionQualityState


@dataclass(frozen=True, slots=True)
class AllocationUnitsProjection:
    """One persisted shadow-allocation line, never a monetary settlement."""

    allocation_id: str
    bucket: AllocationBucket
    units: Decimal
    release_state: AllocationReleaseState
    basis_type: AllocationBasisType
    basis_ref: str


@dataclass(frozen=True, slots=True)
class ServiceCaseProgressProjection:
    """Family-scoped read model for one FGCN case."""

    case_id: str
    tenant_id: str
    family_id: str
    subject_person_id: str
    purpose: str
    consent_version: str
    correlation_id: str
    case_status: CaseStatus
    tasks: tuple[ServiceTaskProgressProjection, ...]
    verified_contributions: tuple[VerifiedContributionProjection, ...]
    allocation_lines: tuple[AllocationUnitsProjection, ...]

    @property
    def scope(self) -> GateServiceScope:
        """Return the scope carried by the projection without a new lookup."""

        return GateServiceScope(
            tenant_id=self.tenant_id,
            family_id=self.family_id,
            subject_person_id=self.subject_person_id,
            purpose=self.purpose,
            consent_version=self.consent_version,
            correlation_id=self.correlation_id,
        )

    @property
    def task_statuses(self) -> Mapping[str, TaskStatus]:
        return MappingProxyType({task.task_id: task.status for task in self.tasks})

    @property
    def delivery_count(self) -> int:
        return sum(task.delivery_id is not None for task in self.tasks)

    @property
    def verified_contribution_ids(self) -> tuple[str, ...]:
        return tuple(item.contribution_id for item in self.verified_contributions)

    @property
    def allocation_units(self) -> Mapping[AllocationBucket, Decimal]:
        totals: dict[AllocationBucket, Decimal] = defaultdict(lambda: Decimal("0"))
        for line in self.allocation_lines:
            totals[line.bucket] += line.units
        return MappingProxyType(dict(totals))

    @property
    def total_allocation_units(self) -> Decimal:
        return sum(self.allocation_units.values(), Decimal("0"))

    @property
    def allocation_units_by_bucket(self) -> Mapping[AllocationBucket, Decimal]:
        """Explicit name used by read-model consumers (shadow units only)."""

        return self.allocation_units

    @property
    def task_progress(self) -> tuple[ServiceTaskProgressProjection, ...]:
        return self.tasks

    @property
    def contributions(self) -> tuple[VerifiedContributionProjection, ...]:
        return self.verified_contributions


class PDCAPhase(StrEnum):
    """The first unmet phase in one FGCN service-improvement cycle."""

    PLAN = "PLAN"
    DO = "DO"
    CHECK = "CHECK"
    ACT = "ACT"


@dataclass(frozen=True, slots=True)
class FGCNPDCAProjection:
    """Read-only evidence that locates an FGCN case in the PDCA cycle.

    This is an evidence projection, not a second workflow or a command. A
    phase is ready only when its concrete FGCN facts exist; the projection
    never infers delivery, quality, contribution, or settlement from a draft
    or from a model output.
    """

    case_id: str
    family_id: str
    subject_person_id: str
    intent_ref: str
    plan_ref: str
    blueprint_ref: str
    scenario_key: str
    service_outcome: str
    plan_ready: bool
    do_ready: bool
    check_ready: bool
    act_ready: bool
    current_phase: PDCAPhase
    blockers: tuple[str, ...]
    resource_gap: str | None
    provider_ref: str | None
    capacity_available: int | None
    shadow_allocation_present: bool

    @property
    def cycle_complete(self) -> bool:
        return self.plan_ready and self.do_ready and self.check_ready and self.act_ready


def _assert_human_actor(actor_id: str, error_code: str) -> None:
    if (
        not isinstance(actor_id, str)
        or not actor_id.strip()
        or actor_id.strip().upper() in {"AI", "SYSTEM"}
        or actor_id.strip().lower().startswith(("ai:", "system:"))
    ):
        raise ServiceForbiddenError(error_code)


def build_fgcn_pdca_projection(
    case: ServiceCase,
    tasks: Iterable[ServiceTask] = (),
    assignments: Iterable[TaskAssignment] = (),
    deliveries: Iterable[ServiceDelivery] = (),
    quality_reviews: Iterable[TaskQualityReview] = (),
    contributions: Iterable[ServiceContribution] = (),
    allocation: AllocationStatement | None = None,
    viewer_scope: GateServiceScope | None = None,
    *,
    provider_admission: ProviderAdmissionSnapshot | None = None,
) -> FGCNPDCAProjection:
    """Evaluate FGCN facts as one deterministic PLAN→ACT PDCA cycle.

    ``provider_admission`` is an explicit upstream snapshot, not a local
    provider registry or a capacity reservation. A zero-capacity snapshot is
    surfaced as ``RESOURCE_GAP``; this function never creates state.
    """

    task_facts = tuple(tasks)
    assignment_facts = tuple(assignments)
    delivery_facts = tuple(deliveries)
    review_facts = tuple(quality_reviews)
    contribution_facts = tuple(contributions)
    progress = build_case_progress_projection(
        case,
        tasks=task_facts,
        assignments=assignment_facts,
        deliveries=delivery_facts,
        quality_reviews=review_facts,
        contributions=contribution_facts,
        allocation=allocation,
        viewer_scope=viewer_scope,
    )

    blockers: list[str] = []
    resource_gap: str | None = None
    required_capabilities = tuple(
        sorted({key for task in task_facts for key in task.required_capability_keys})
    )
    plan_ready = bool(task_facts)
    if not plan_ready:
        blockers.append("fgcn_plan_tasks_required")
    if provider_admission is None:
        blockers.append("fgcn_provider_admission_unavailable")
        plan_ready = False
    else:
        admission_provider_ref = ""
        admission_assignee_kind = ""
        if isinstance(provider_admission, ProviderAdmissionSnapshot):
            admission_provider_ref = provider_admission.provider_ref
            admission_assignee_kind = provider_admission.assignee_kind
        try:
            assert_provider_admitted(
                provider_admission,
                provider_ref=admission_provider_ref,
                assignee_kind=admission_assignee_kind,
                required_capability_keys=required_capabilities,
                scope=case.scope,
            )
        except (ServiceConflictError, ServiceForbiddenError, ServiceValidationError) as exc:
            blockers.append(exc.code)
            plan_ready = False
            if exc.code == "RESOURCE_GAP":
                resource_gap = exc.code

    task_ids = {task.task_id for task in task_facts}
    assigned_task_ids = {assignment.task_id for assignment in assignment_facts}
    delivered_task_ids = {delivery.task_id for delivery in delivery_facts}
    reviewed_task_ids = {
        review.task_id for review in review_facts if review.quality_state is TaskQualityState.PASSED
    }
    contributed_task_ids = {item.task_id for item in contribution_facts}
    assigned_provider_refs = {assignment.assignee_ref for assignment in assignment_facts}
    provider_assignment_matches = not assigned_provider_refs or (
        isinstance(provider_admission, ProviderAdmissionSnapshot)
        and assigned_provider_refs == {provider_admission.provider_ref}
    )
    if not provider_assignment_matches:
        blockers.append("fgcn_provider_assignment_mismatch")
    do_ready = (
        bool(task_ids)
        and task_ids.issubset(assigned_task_ids)
        and task_ids.issubset(delivered_task_ids)
        and provider_assignment_matches
        and all(
            task.status in {TaskStatus.DELIVERED, TaskStatus.VERIFIED, TaskStatus.CLOSED}
            and task.deliverable_ref is not None
            for task in task_facts
        )
    )
    if not do_ready:
        blockers.append("fgcn_delivery_evidence_incomplete")

    check_ready = (
        do_ready
        and task_ids.issubset(reviewed_task_ids)
        and all(task.status in {TaskStatus.VERIFIED, TaskStatus.CLOSED} for task in task_facts)
    )
    if not check_ready:
        blockers.append("fgcn_quality_decision_incomplete")

    allocation_marker_matches = (
        allocation is not None
        and case.shadow_allocation_finalized_at is not None
        and allocation.created_at == case.shadow_allocation_finalized_at
        and allocation.policy_ref == case.blueprint.policy_ref
        and allocation.policy_version == case.blueprint.policy_version
    )
    if allocation is not None and not allocation_marker_matches:
        blockers.append("fgcn_shadow_allocation_marker_missing")

    act_ready = (
        check_ready
        and task_ids.issubset(contributed_task_ids)
        and case.status is CaseStatus.COMPLETED
        and allocation_marker_matches
    )
    if not act_ready:
        if not task_ids.issubset(contributed_task_ids):
            blockers.append("fgcn_contribution_not_released")
        if case.status is not CaseStatus.COMPLETED:
            blockers.append("fgcn_case_not_completed")
        if not allocation_marker_matches:
            blockers.append("fgcn_shadow_allocation_not_finalized")

    if not plan_ready:
        current_phase = PDCAPhase.PLAN
    elif not do_ready:
        current_phase = PDCAPhase.DO
    elif not check_ready:
        current_phase = PDCAPhase.CHECK
    else:
        current_phase = PDCAPhase.ACT

    return FGCNPDCAProjection(
        case_id=progress.case_id,
        family_id=case.scope.family_id,
        subject_person_id=case.scope.subject_person_id,
        intent_ref=case.intent_ref,
        plan_ref=case.plan_ref,
        blueprint_ref=case.blueprint.blueprint_ref,
        scenario_key=case.blueprint.scenario.scenario_key,
        service_outcome=case.blueprint.scenario.service_outcome,
        plan_ready=plan_ready,
        do_ready=do_ready,
        check_ready=check_ready,
        act_ready=act_ready,
        current_phase=current_phase,
        blockers=tuple(dict.fromkeys(blockers)),
        resource_gap=resource_gap,
        provider_ref=(
            provider_admission.provider_ref
            if isinstance(provider_admission, ProviderAdmissionSnapshot)
            else None
        ),
        capacity_available=(
            provider_admission.capacity_available
            if isinstance(provider_admission, ProviderAdmissionSnapshot)
            else None
        ),
        shadow_allocation_present=allocation is not None,
    )


def _immutable_facts[FactT](
    value: Iterable[FactT], expected_type: type[FactT], name: str
) -> tuple[FactT, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        raise TypeError(f"fgcn_projection_{name}_facts_required")
    try:
        facts = tuple(value)
    except TypeError as exc:
        raise TypeError(f"fgcn_projection_{name}_facts_required") from exc
    for fact in facts:
        if not isinstance(fact, expected_type):
            raise TypeError(f"fgcn_projection_{name}_fact_type_invalid")
        params = getattr(type(fact), "__dataclass_params__", None)
        if params is None or not params.frozen:
            raise TypeError(f"fgcn_projection_{name}_fact_must_be_immutable")
    return facts


def _assert_scope(case: ServiceCase, viewer_scope: GateServiceScope | None) -> None:
    if viewer_scope is None:
        return
    if not isinstance(viewer_scope, GateServiceScope):
        raise TypeError("fgcn_projection_scope_type_invalid")
    if viewer_scope.tenant_id != case.scope.tenant_id:
        raise ServiceForbiddenError("fgcn_projection_tenant_scope_violation")
    if viewer_scope.family_id != case.scope.family_id:
        raise ServiceForbiddenError("fgcn_projection_family_scope_violation")
    if viewer_scope.subject_person_id != case.scope.subject_person_id:
        raise ServiceForbiddenError("fgcn_projection_subject_scope_violation")
    if viewer_scope.purpose != case.scope.purpose:
        raise ServiceForbiddenError("fgcn_projection_purpose_scope_violation")
    if viewer_scope.consent_version != case.scope.consent_version:
        raise ServiceForbiddenError("fgcn_projection_consent_scope_violation")
    if viewer_scope.correlation_id != case.scope.correlation_id:
        raise ServiceForbiddenError("fgcn_projection_correlation_scope_violation")


def _index_tasks(case: ServiceCase, tasks: tuple[ServiceTask, ...]) -> dict[str, ServiceTask]:
    indexed: dict[str, ServiceTask] = {}
    for task in tasks:
        if task.case_id != case.case_id:
            raise ServiceForbiddenError("fgcn_projection_task_case_mismatch")
        if (
            task.blueprint_ref != case.blueprint.blueprint_ref
            or task.blueprint_version != case.blueprint.version
        ):
            raise ServiceValidationError("fgcn_projection_task_blueprint_mismatch")
        if task.task_id in indexed and indexed[task.task_id] != task:
            raise ServiceValidationError("fgcn_projection_duplicate_task")
        indexed[task.task_id] = task
    return indexed


def _index_deliveries(
    case: ServiceCase, tasks: dict[str, ServiceTask], deliveries: tuple[ServiceDelivery, ...]
) -> dict[str, ServiceDelivery]:
    by_task: dict[str, ServiceDelivery] = {}
    by_id: dict[str, ServiceDelivery] = {}
    for delivery in deliveries:
        if delivery.case_id != case.case_id:
            raise ServiceForbiddenError("fgcn_projection_delivery_case_mismatch")
        task = tasks.get(delivery.task_id)
        if task is None:
            raise ServiceValidationError("fgcn_projection_delivery_task_missing")
        if task.responsible_ref != delivery.assignee_ref:
            raise ServiceForbiddenError("fgcn_projection_delivery_assignee_mismatch")
        if delivery.delivery_id in by_id and by_id[delivery.delivery_id] != delivery:
            raise ServiceValidationError("fgcn_projection_duplicate_delivery")
        if delivery.task_id in by_task and by_task[delivery.task_id] != delivery:
            raise ServiceValidationError("fgcn_projection_one_delivery_per_task")
        by_id[delivery.delivery_id] = delivery
        by_task[delivery.task_id] = delivery
    return by_task


def _index_reviews(
    case: ServiceCase, tasks: dict[str, ServiceTask], reviews: tuple[TaskQualityReview, ...]
) -> dict[str, TaskQualityReview]:
    by_task: dict[str, TaskQualityReview] = {}
    for review in reviews:
        if review.case_id != case.case_id:
            raise ServiceForbiddenError("fgcn_projection_quality_case_mismatch")
        if review.task_id not in tasks:
            raise ServiceValidationError("fgcn_projection_quality_task_missing")
        _assert_human_actor(
            review.reviewer_ref,
            "fgcn_projection_quality_reviewer_must_be_human",
        )
        if tasks[review.task_id].responsible_ref == review.reviewer_ref:
            raise ServiceForbiddenError(
                "fgcn_projection_quality_reviewer_must_differ_from_delivery_person"
            )
        if review.task_id in by_task and by_task[review.task_id] != review:
            raise ServiceValidationError("fgcn_projection_one_quality_review_per_task")
        by_task[review.task_id] = review
    return by_task


def _index_contributions(
    case: ServiceCase,
    tasks: dict[str, ServiceTask],
    deliveries: dict[str, ServiceDelivery],
    reviews: dict[str, TaskQualityReview],
    contributions: tuple[ServiceContribution, ...],
) -> dict[str, VerifiedContributionProjection]:
    indexed: dict[str, VerifiedContributionProjection] = {}
    contribution_by_delivery: dict[str, str] = {}
    for contribution in contributions:
        if contribution.case_id != case.case_id:
            raise ServiceForbiddenError("fgcn_projection_contribution_case_mismatch")
        task = tasks.get(contribution.task_id)
        if task is None:
            raise ServiceValidationError("fgcn_projection_contribution_task_missing")
        delivery = deliveries.get(contribution.task_id)
        if delivery is None or delivery.delivery_id != contribution.delivery_id:
            raise ServiceValidationError("fgcn_projection_contribution_delivery_required")
        if delivery.assignee_ref != contribution.provider_ref:
            raise ServiceForbiddenError("fgcn_projection_contribution_provider_mismatch")
        review = reviews.get(contribution.task_id)
        if (
            task.status is not TaskStatus.VERIFIED
            or review is None
            or review.quality_state is not TaskQualityState.PASSED
        ):
            raise ServiceValidationError("fgcn_projection_contribution_requires_verified_delivery")
        projected = VerifiedContributionProjection(
            contribution_id=contribution.contribution_id,
            task_id=contribution.task_id,
            delivery_id=contribution.delivery_id,
            provider_ref=contribution.provider_ref,
            role_key=contribution.role_key,
            quality_state=contribution.quality_state,
        )
        previous = indexed.get(contribution.contribution_id)
        if previous is not None and previous != projected:
            raise ServiceValidationError("fgcn_projection_duplicate_contribution")
        previous_contribution_id = contribution_by_delivery.get(contribution.delivery_id)
        if (
            previous_contribution_id is not None
            and previous_contribution_id != contribution.contribution_id
        ):
            raise ServiceValidationError("fgcn_projection_one_contribution_per_delivery")
        indexed[contribution.contribution_id] = projected
        contribution_by_delivery[contribution.delivery_id] = contribution.contribution_id
    return indexed


def _project_allocations(
    case: ServiceCase,
    contributions: dict[str, VerifiedContributionProjection],
    allocation: AllocationStatement | None,
) -> tuple[AllocationUnitsProjection, ...]:
    if allocation is None:
        return ()
    if not isinstance(allocation, AllocationStatement):
        raise TypeError("fgcn_projection_allocation_fact_type_invalid")
    params = getattr(type(allocation), "__dataclass_params__", None)
    if params is None or not params.frozen:
        raise TypeError("fgcn_projection_allocation_fact_must_be_immutable")
    if allocation.case_id != case.case_id:
        raise ServiceForbiddenError("fgcn_projection_allocation_case_mismatch")
    if case.status is not CaseStatus.COMPLETED:
        raise ServiceValidationError("fgcn_projection_allocation_case_not_completed")
    _assert_human_actor(
        allocation.triggered_by_actor_id,
        "fgcn_projection_allocation_requires_human_actor",
    )
    if (
        allocation.policy_ref != case.blueprint.policy_ref
        or allocation.policy_version != case.blueprint.policy_version
    ):
        raise ServiceValidationError("fgcn_projection_allocation_policy_mismatch")
    projected: list[AllocationUnitsProjection] = []
    seen_ids: set[str] = set()
    for line in allocation.lines:
        if line.case_id != case.case_id:
            raise ServiceForbiddenError("fgcn_projection_allocation_line_case_mismatch")
        if line.allocation_id in seen_ids:
            raise ServiceValidationError("fgcn_projection_duplicate_allocation_line")
        seen_ids.add(line.allocation_id)
        if (
            line.policy_ref != allocation.policy_ref
            or line.policy_version != allocation.policy_version
        ):
            raise ServiceValidationError("fgcn_projection_allocation_policy_mismatch")
        if line.basis_type is AllocationBasisType.CASE and line.basis_ref != case.case_id:
            raise ServiceValidationError("fgcn_projection_allocation_case_basis_mismatch")
        if line.basis_type.value == "CONTRIBUTION_WEIGHT" and line.basis_ref not in contributions:
            raise ServiceValidationError("fgcn_projection_allocation_contribution_required")
        projected.append(
            AllocationUnitsProjection(
                allocation_id=line.allocation_id,
                bucket=line.allocation_bucket,
                units=line.units,
                release_state=line.release_state,
                basis_type=line.basis_type,
                basis_ref=line.basis_ref,
            )
        )
    return tuple(projected)


def build_case_progress_projection(
    case: ServiceCase,
    tasks: Iterable[ServiceTask] = (),
    assignments: Iterable[TaskAssignment] = (),
    deliveries: Iterable[ServiceDelivery] = (),
    quality_reviews: Iterable[TaskQualityReview] = (),
    contributions: Iterable[ServiceContribution] = (),
    allocation: AllocationStatement | None = None,
    viewer_scope: GateServiceScope | None = None,
    *,
    task_facts: Iterable[ServiceTask] | None = None,
    assignment_facts: Iterable[TaskAssignment] | None = None,
    delivery_facts: Iterable[ServiceDelivery] | None = None,
    quality_facts: Iterable[TaskQualityReview] | None = None,
    contribution_facts: Iterable[ServiceContribution] | None = None,
    allocation_statement: AllocationStatement | None = None,
    scope: GateServiceScope | None = None,
) -> ServiceCaseProgressProjection:
    """Build one deterministic, family-scoped FGCN read projection.

    All inputs are already-persisted facts.  The projector never infers a
    delivery from a task's evidence text: only a concrete ``ServiceDelivery``
    plus a passed ``TaskQualityReview`` can make a contribution visible.
    """

    if task_facts is not None:
        if tasks:
            raise TypeError("fgcn_projection_tasks_alias_conflict")
        tasks = task_facts
    if assignment_facts is not None:
        if assignments:
            raise TypeError("fgcn_projection_assignments_alias_conflict")
        assignments = assignment_facts
    if delivery_facts is not None:
        if deliveries:
            raise TypeError("fgcn_projection_deliveries_alias_conflict")
        deliveries = delivery_facts
    if quality_facts is not None:
        if quality_reviews:
            raise TypeError("fgcn_projection_quality_alias_conflict")
        quality_reviews = quality_facts
    if contribution_facts is not None:
        if contributions:
            raise TypeError("fgcn_projection_contributions_alias_conflict")
        contributions = contribution_facts
    if allocation_statement is not None:
        if allocation is not None:
            raise TypeError("fgcn_projection_allocation_alias_conflict")
        allocation = allocation_statement
    if scope is not None:
        if viewer_scope is not None:
            raise TypeError("fgcn_projection_scope_alias_conflict")
        viewer_scope = scope

    if not isinstance(case, ServiceCase):
        raise TypeError("fgcn_projection_case_fact_type_invalid")
    case_params = getattr(type(case), "__dataclass_params__", None)
    if case_params is None or not case_params.frozen:
        raise TypeError("fgcn_projection_case_fact_must_be_immutable")
    _assert_scope(case, viewer_scope)
    task_facts = _immutable_facts(tasks, ServiceTask, "task")
    assignment_facts = _immutable_facts(assignments, TaskAssignment, "assignment")
    delivery_facts = _immutable_facts(deliveries, ServiceDelivery, "delivery")
    review_facts = _immutable_facts(quality_reviews, TaskQualityReview, "quality")
    contribution_facts = _immutable_facts(contributions, ServiceContribution, "contribution")
    task_by_id = _index_tasks(case, task_facts)

    assignment_by_task: dict[str, TaskAssignment] = {}
    for assignment in assignment_facts:
        task = task_by_id.get(assignment.task_id)
        if task is None:
            raise ServiceValidationError("fgcn_projection_assignment_task_missing")
        if assignment.case_id != case.case_id:
            raise ServiceForbiddenError("fgcn_projection_assignment_case_mismatch")
        if task.responsible_ref != assignment.assignee_ref:
            raise ServiceForbiddenError("fgcn_projection_assignment_assignee_mismatch")
        previous = assignment_by_task.get(assignment.task_id)
        if previous is not None and previous != assignment:
            raise ServiceValidationError("fgcn_projection_one_assignment_per_task")
        assignment_by_task[assignment.task_id] = assignment

    delivery_by_task = _index_deliveries(case, task_by_id, delivery_facts)
    review_by_task = _index_reviews(case, task_by_id, review_facts)
    contribution_by_id = _index_contributions(
        case, task_by_id, delivery_by_task, review_by_task, contribution_facts
    )
    contribution_ids_by_task: dict[str, list[str]] = defaultdict(list)
    for contribution in contribution_by_id.values():
        contribution_ids_by_task[contribution.task_id].append(contribution.contribution_id)

    task_projections: list[ServiceTaskProgressProjection] = []
    for task in sorted(task_by_id.values(), key=lambda item: item.task_id):
        delivery = delivery_by_task.get(task.task_id)
        review = review_by_task.get(task.task_id)
        verified_delivery = (
            delivery is not None
            and task.status is TaskStatus.VERIFIED
            and review is not None
            and review.quality_state is TaskQualityState.PASSED
        )
        task_projections.append(
            ServiceTaskProgressProjection(
                task_id=task.task_id,
                task_key=task.task_key,
                status=task.status,
                responsible_ref=task.responsible_ref,
                delivery_id=delivery.delivery_id if delivery is not None else None,
                # An unverified delivery is progress metadata only.  Its
                # evidence cannot be exposed as accepted proof or reused as a
                # contribution basis until the immutable PASSED review exists.
                evidence_ref=delivery.evidence_ref if verified_delivery else None,
                quality_review_id=review.quality_review_id if review is not None else None,
                quality_state=review.quality_state if review is not None else None,
                verified_at=task.verified_at,
                verified_contribution_ids=tuple(
                    sorted(contribution_ids_by_task.get(task.task_id, ()))
                ),
            )
        )

    allocation_lines = _project_allocations(case, contribution_by_id, allocation)
    return ServiceCaseProgressProjection(
        case_id=case.case_id,
        tenant_id=case.scope.tenant_id,
        family_id=case.scope.family_id,
        subject_person_id=case.scope.subject_person_id,
        purpose=case.scope.purpose,
        consent_version=case.scope.consent_version,
        correlation_id=case.scope.correlation_id,
        case_status=case.status,
        tasks=tuple(task_projections),
        verified_contributions=tuple(
            contribution_by_id[contribution_id] for contribution_id in sorted(contribution_by_id)
        ),
        allocation_lines=allocation_lines,
    )


class ServiceCaseProgressProjector:
    """Named adapter for callers that prefer an object seam."""

    @staticmethod
    def project(
        case: ServiceCase,
        tasks: Iterable[ServiceTask] = (),
        assignments: Iterable[TaskAssignment] = (),
        deliveries: Iterable[ServiceDelivery] = (),
        quality_reviews: Iterable[TaskQualityReview] = (),
        contributions: Iterable[ServiceContribution] = (),
        allocation: AllocationStatement | None = None,
        viewer_scope: GateServiceScope | None = None,
        **aliases,
    ) -> ServiceCaseProgressProjection:
        return build_case_progress_projection(
            case,
            tasks,
            assignments,
            deliveries,
            quality_reviews,
            contributions,
            allocation,
            viewer_scope,
            **aliases,
        )


# Concise alias for read-model consumers while preserving one implementation.
project_case_progress = build_case_progress_projection


__all__ = [
    "AllocationUnitsProjection",
    "FGCNPDCAProjection",
    "PDCAPhase",
    "ServiceCaseProgressProjection",
    "ServiceCaseProgressProjector",
    "ServiceTaskProgressProjection",
    "VerifiedContributionProjection",
    "build_case_progress_projection",
    "build_fgcn_pdca_projection",
    "project_case_progress",
]
