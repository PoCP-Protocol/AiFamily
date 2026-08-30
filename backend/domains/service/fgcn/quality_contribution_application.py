"""Durable FGCN quality and contribution application commands.

The commands in this module continue the provider-neutral FGCN fact chain
after delivery evidence.  Quality approval is a separate human action from
delivery, and only a passed review can produce a contribution fact.  Neither
command calls AI, calculates family value, or creates a money/settlement row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceNotFoundError,
    ServiceValidationError,
)
from backend.platform.audit import AuditEvent, AuditRecorder

from .contracts import (
    CaseStatus,
    ContributionQualityState,
    GateServiceScope,
    ServiceCase,
    ServiceContribution,
    ServiceDelivery,
    ServiceTask,
    TaskQualityReview,
    TaskQualityState,
    TaskStatus,
)


class FGCNQualityContributionRepository(Protocol):
    """Narrow durable port shared by the quality and contribution commands."""

    async def load_case(self, case_id: str) -> ServiceCase: ...

    async def load_task(self, task_id: str) -> ServiceTask: ...

    async def load_delivery(self, task_id: str) -> ServiceDelivery: ...

    async def load_quality_review(self, quality_review_id: str) -> TaskQualityReview: ...

    async def load_contribution(self, contribution_id: str) -> ServiceContribution: ...

    async def save_quality_review(self, review: TaskQualityReview) -> None: ...

    async def save_contribution(self, contribution: ServiceContribution) -> None: ...

    async def flush_audit(self, recorder: AuditRecorder) -> int: ...

    async def commit(self) -> None: ...


def _human_actor(actor_id: str, *, error_code: str) -> str:
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ServiceValidationError(error_code)
    actor = actor_id.strip()
    if actor.upper() in {"AI", "SYSTEM"} or actor.lower().startswith(("ai:", "system:")):
        raise ServiceForbiddenError("fgcn_requires_human_actor")
    return actor


def _assert_scope(case: ServiceCase, scope: GateServiceScope) -> None:
    if not isinstance(scope, GateServiceScope):
        raise ServiceValidationError("fgcn_scope_invalid")
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


def _quality_replay_matches(
    existing: TaskQualityReview,
    *,
    quality_review_id: str,
    task_id: str,
    reviewer_ref: str,
    quality_state: TaskQualityState,
    review_note: str,
) -> bool:
    """Compare review intent while ignoring its server-assigned timestamp."""

    return (
        existing.quality_review_id == quality_review_id
        and existing.task_id == task_id
        and existing.reviewer_ref == reviewer_ref
        and existing.quality_state is quality_state
        and existing.review_note == review_note
    )


async def verify_service_delivery(
    repo: FGCNQualityContributionRepository,
    *,
    task_id: str,
    quality_review_id: str,
    reviewer_ref: str,
    review_note: str,
    scope: GateServiceScope,
    recorder: AuditRecorder,
    quality_state: TaskQualityState | str = TaskQualityState.PASSED,
    reviewed_at: datetime | None = None,
) -> TaskQualityReview:
    """Pass one delivered task through an independent human quality review."""

    task = await repo.load_task(task_id)
    case = await repo.load_case(task.case_id)
    _assert_scope(case, scope)
    reviewer = _human_actor(
        reviewer_ref,
        error_code="fgcn_quality_reviewer_required",
    )
    if task.responsible_ref == reviewer:
        raise ServiceForbiddenError("fgcn_quality_reviewer_must_differ_from_delivery_person")
    try:
        quality_state = TaskQualityState(quality_state)
    except ValueError as exc:
        raise ServiceValidationError("fgcn_quality_state_invalid") from exc
    if quality_state is not TaskQualityState.PASSED:
        raise ServiceConflictError("fgcn_non_pass_quality_requires_rework_flow")

    if task.status is TaskStatus.VERIFIED:
        try:
            existing = await repo.load_quality_review(quality_review_id)
        except ServiceNotFoundError as exc:
            raise ServiceConflictError("fgcn_quality_review_already_recorded") from exc
        if _quality_replay_matches(
            existing,
            quality_review_id=quality_review_id,
            task_id=task_id,
            reviewer_ref=reviewer,
            quality_state=quality_state,
            review_note=review_note.strip(),
        ):
            return existing
        raise ServiceConflictError("fgcn_quality_review_idempotency_replay_mismatch")

    if case.status in {CaseStatus.COMPLETED, CaseStatus.CANCELLED}:
        raise ServiceConflictError("fgcn_quality_case_is_terminal")
    if task.status is not TaskStatus.DELIVERED:
        raise ServiceConflictError("fgcn_quality_review_requires_delivery")

    review = TaskQualityReview(
        quality_review_id=quality_review_id,
        case_id=case.case_id,
        task_id=task.task_id,
        reviewer_ref=reviewer,
        quality_state=quality_state,
        review_note=review_note,
        reviewed_at=reviewed_at or datetime.now(UTC),
    )
    await repo.save_quality_review(review)
    recorder.record(
        AuditEvent(
            actor_id=reviewer,
            tenant_id=case.scope.tenant_id,
            action="VERIFY_SERVICE_DELIVERY",
            resource_type="TaskQualityReview",
            resource_id=review.quality_review_id,
            reason="quality reviewer passed delivery against frozen criteria",
            correlation_id=case.scope.correlation_id,
            before={"task_status": TaskStatus.DELIVERED.value},
            after={"task_status": TaskStatus.VERIFIED.value},
        )
    )
    recorder.record(
        AuditEvent(
            actor_id=reviewer,
            tenant_id=case.scope.tenant_id,
            action="VERIFY_SERVICE_TASK",
            resource_type="ServiceTask",
            resource_id=task.task_id,
            reason="quality review moved task to verified",
            correlation_id=case.scope.correlation_id,
            before={"status": TaskStatus.DELIVERED.value},
            after={"status": TaskStatus.VERIFIED.value},
        )
    )
    await repo.flush_audit(recorder)
    await repo.commit()
    return review


def _contribution_replay_matches(
    existing: ServiceContribution,
    expected: ServiceContribution,
) -> bool:
    return existing == expected


async def record_service_contribution(
    repo: FGCNQualityContributionRepository,
    *,
    task_id: str,
    contribution_id: str,
    delivery_id: str,
    provider_ref: str,
    role_key: str,
    started_at: datetime,
    completed_at: datetime,
    scope: GateServiceScope,
    recorder: AuditRecorder,
) -> ServiceContribution:
    """Turn one verified delivery into one auditable contribution fact."""

    task = await repo.load_task(task_id)
    case = await repo.load_case(task.case_id)
    _assert_scope(case, scope)
    provider = _human_actor(
        provider_ref,
        error_code="fgcn_contribution_provider_required",
    )
    if task.responsible_ref != provider:
        raise ServiceForbiddenError("fgcn_contribution_provider_mismatch")
    if task.status is not TaskStatus.VERIFIED:
        raise ServiceConflictError("fgcn_contribution_requires_verified_task")
    delivery = await repo.load_delivery(task_id)
    if delivery.delivery_id != delivery_id or delivery.assignee_ref != provider:
        raise ServiceForbiddenError("fgcn_contribution_delivery_mismatch")

    contribution = ServiceContribution(
        contribution_id=contribution_id,
        case_id=case.case_id,
        task_id=task.task_id,
        provider_ref=provider,
        role_key=role_key,
        delivery_id=delivery.delivery_id,
        quality_state=ContributionQualityState.VERIFIED,
        started_at=started_at,
        completed_at=completed_at,
    )
    try:
        existing = await repo.load_contribution(contribution_id)
    except ServiceNotFoundError:
        existing = None
    if existing is not None:
        if _contribution_replay_matches(existing, contribution):
            return existing
        raise ServiceConflictError("fgcn_contribution_idempotency_replay_mismatch")

    await repo.save_contribution(contribution)
    recorder.record(
        AuditEvent(
            actor_id=provider,
            tenant_id=case.scope.tenant_id,
            action="RECORD_SERVICE_CONTRIBUTION",
            resource_type="ServiceContribution",
            resource_id=contribution.contribution_id,
            reason="verified delivery became a service contribution fact",
            correlation_id=case.scope.correlation_id,
            after={
                "quality_state": contribution.quality_state.value,
                "task_id": task.task_id,
                "delivery_id": delivery.delivery_id,
            },
        )
    )
    await repo.flush_audit(recorder)
    await repo.commit()
    return contribution


__all__ = [
    "FGCNQualityContributionRepository",
    "record_service_contribution",
    "verify_service_delivery",
]
