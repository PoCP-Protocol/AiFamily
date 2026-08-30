from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.domains.service.domain.errors import ServiceForbiddenError, ServiceValidationError
from backend.domains.service.fgcn.contracts import (
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
from backend.domains.service.fgcn.read_model import (
    ServiceCaseProgressProjection,
    build_case_progress_projection,
)

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)


def _scope() -> GateServiceScope:
    return GateServiceScope(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_person_id="child-1",
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-read-model-1",
    )


def _blueprint() -> BlueprintSnapshot:
    return BlueprintSnapshot(
        blueprint_ref="communication-service",
        version=1,
        status="PUBLISHED",
        policy_ref="shadow-policy.v1",
        policy_version=1,
        checksum="checksum-v1",
        task_template_keys=("HUMAN_HANDOFF",),
    )


def _case(*, status: CaseStatus = CaseStatus.OPEN) -> ServiceCase:
    return ServiceCase(
        case_id="case-1",
        scope=_scope(),
        intent_ref="intent-1",
        plan_ref="plan-1",
        owner_id="steward-1",
        blueprint=_blueprint(),
        status=status,
        opened_at=NOW,
        closed_at=NOW + timedelta(hours=3) if status is CaseStatus.COMPLETED else None,
    )


def _task(*, status: TaskStatus = TaskStatus.ACCEPTED) -> ServiceTask:
    verified = status is TaskStatus.VERIFIED
    return ServiceTask(
        task_id="task-1",
        case_id="case-1",
        blueprint_ref="communication-service",
        blueprint_version=1,
        task_key="HUMAN_HANDOFF",
        title="Family handoff",
        description="Deliver the family-confirmed activity.",
        role_key="DELIVERY_RESOURCE",
        acceptance_criteria=("Evidence reference is present",),
        status=status,
        responsible_ref="expert-1",
        deliverable_ref=(
            "evidence:delivery-1"
            if status in {TaskStatus.DELIVERED, TaskStatus.VERIFIED}
            else None
        ),
        verified_at=NOW + timedelta(hours=2) if verified else None,
        created_at=NOW,
    )


def _assignment() -> TaskAssignment:
    return TaskAssignment(
        assignment_id="assignment-1",
        case_id="case-1",
        task_id="task-1",
        assignee_ref="expert-1",
        assignee_kind="EXPERT",
        status=TaskAssignmentStatus.ACCEPTED,
        accepted_by_actor_id="guardian-1",
        source_request_id="request-1",
        accepted_at=NOW + timedelta(minutes=1),
    )


def _delivery() -> ServiceDelivery:
    return ServiceDelivery(
        delivery_id="delivery-1",
        case_id="case-1",
        task_id="task-1",
        assignee_ref="expert-1",
        evidence_ref="evidence:delivery-1",
        delivered_at=NOW + timedelta(hours=1),
    )


def _review(*, quality_state: TaskQualityState = TaskQualityState.PASSED) -> TaskQualityReview:
    return TaskQualityReview(
        quality_review_id="review-1",
        case_id="case-1",
        task_id="task-1",
        reviewer_ref="quality-1",
        quality_state=quality_state,
        review_note="criteria checked",
        reviewed_at=NOW + timedelta(hours=2),
    )


def _contribution() -> ServiceContribution:
    return ServiceContribution(
        contribution_id="contribution-1",
        case_id="case-1",
        task_id="task-1",
        provider_ref="expert-1",
        role_key="DELIVERY_RESOURCE",
        delivery_id="delivery-1",
        quality_state=ContributionQualityState.VERIFIED,
        started_at=NOW,
        completed_at=NOW + timedelta(hours=1),
    )


def _allocation() -> AllocationStatement:
    line = AllocationLine(
        allocation_id="allocation-line-1",
        allocation_run_id="allocation-run-1",
        case_id="case-1",
        allocation_bucket=AllocationBucket.PLATFORM,
        units=Decimal("100"),
        beneficiary_ref="platform",
        beneficiary_kind="PLATFORM",
        role_key="PLATFORM",
        policy_ref="shadow-policy.v1",
        policy_version=1,
        basis_type=AllocationBasisType.CASE,
        basis_ref="case-1",
        release_state=AllocationReleaseState.RELEASED,
    )
    return AllocationStatement(
        allocation_run_id="allocation-run-1",
        case_id="case-1",
        policy_ref="shadow-policy.v1",
        policy_version=1,
        triggered_by_actor_id="operator-1",
        total_units=Decimal("100"),
        lines=(line,),
        created_at=NOW + timedelta(hours=4),
    )


def test_projection_supports_empty_case_without_writes_or_business_totals() -> None:
    projection = build_case_progress_projection(_case(), viewer_scope=_scope())

    assert isinstance(projection, ServiceCaseProgressProjection)
    assert projection.case_status is CaseStatus.OPEN
    assert projection.tasks == ()
    assert projection.verified_contribution_ids == ()
    assert projection.allocation_units == {}
    assert projection.total_allocation_units == Decimal("0")
    fields = {name.lower() for name in projection.__dataclass_fields__}
    assert not fields.intersection({"score", "rank", "amount", "settlement"})


def test_projection_shows_unverified_delivery_without_contribution() -> None:
    projection = build_case_progress_projection(
        _case(),
        tasks=(_task(),),
        assignments=(_assignment(),),
        deliveries=(_delivery(),),
        viewer_scope=_scope(),
    )

    task = projection.tasks[0]
    assert task.status is TaskStatus.ACCEPTED
    assert task.delivery_id == "delivery-1"
    assert task.delivery_verified is False
    assert task.quality_state is None
    assert projection.verified_contributions == ()


def test_projection_includes_only_verified_delivery_contribution_and_shadow_units() -> None:
    projection = build_case_progress_projection(
        _case(status=CaseStatus.COMPLETED),
        tasks=(_task(status=TaskStatus.VERIFIED),),
        assignments=(_assignment(),),
        deliveries=(_delivery(),),
        quality_reviews=(_review(),),
        contributions=(_contribution(),),
        allocation=_allocation(),
        viewer_scope=_scope(),
    )

    assert projection.case_status is CaseStatus.COMPLETED
    assert projection.tasks[0].delivery_verified is True
    assert projection.verified_contribution_ids == ("contribution-1",)
    assert projection.allocation_units[AllocationBucket.PLATFORM] == Decimal("100")
    assert projection.total_allocation_units == Decimal("100")


def test_projection_rejects_cross_tenant_and_subject_scope() -> None:
    with pytest.raises(ServiceForbiddenError, match="tenant_scope_violation"):
        build_case_progress_projection(
            _case(), viewer_scope=GateServiceScope(
                tenant_id="tenant-other",
                family_id="family-1",
                subject_person_id="child-1",
                purpose="service_collaboration",
                consent_version="consent.v1",
                correlation_id="corr-other",
            )
        )
    with pytest.raises(ServiceForbiddenError, match="subject_scope_violation"):
        build_case_progress_projection(
            _case(), viewer_scope=GateServiceScope(
                tenant_id="tenant-1",
                family_id="family-1",
                subject_person_id="child-other",
                purpose="service_collaboration",
                consent_version="consent.v1",
                correlation_id="corr-other",
            )
        )


def test_projection_rejects_contribution_without_verified_delivery_fact() -> None:
    with pytest.raises(
        ServiceValidationError, match="contribution_delivery_required"
    ):
        build_case_progress_projection(
            _case(),
            tasks=(_task(status=TaskStatus.VERIFIED),),
            contributions=(_contribution(),),
            viewer_scope=_scope(),
        )
