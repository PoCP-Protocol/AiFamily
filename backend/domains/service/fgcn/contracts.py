"""Immutable FGCN facts and the P0 allocation policy types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from backend.domains.service.domain.errors import ServiceValidationError


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError(f"fgcn_{name}_required")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ServiceValidationError(f"fgcn_{name}_must_be_timezone_aware")


def _decimal(value: Decimal | int | str, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (ArithmeticError, ValueError) as exc:
        raise ServiceValidationError(f"fgcn_{name}_invalid") from exc
    if not result.is_finite():
        raise ServiceValidationError(f"fgcn_{name}_invalid")
    return result


class CaseStatus(StrEnum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    DELIVERED = "DELIVERED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TaskAssignmentStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    REVOKED = "REVOKED"
    COMPLETED = "COMPLETED"


class TaskQualityState(StrEnum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    REJECTED = "REJECTED"


class ContributionQualityState(StrEnum):
    VERIFIED = "VERIFIED"


class AllocationBucket(StrEnum):
    PLATFORM = "PLATFORM"
    CONTENT_RESOURCE = "CONTENT_RESOURCE"
    CASE_STEWARD = "CASE_STEWARD"
    DELIVERY_RESOURCE = "DELIVERY_RESOURCE"
    QUALITY_RESERVE = "QUALITY_RESERVE"


class AllocationReleaseState(StrEnum):
    HELD = "HELD"
    RELEASED = "RELEASED"


class AllocationBasisType(StrEnum):
    CASE = "CASE"
    CONTRIBUTION_WEIGHT = "CONTRIBUTION_WEIGHT"


@dataclass(frozen=True, slots=True)
class GateServiceScope:
    """The minimum family scope needed by an FGCN business fact."""

    tenant_id: str
    family_id: str
    subject_person_id: str
    purpose: str
    consent_version: str
    correlation_id: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.tenant_id, "tenant_id"),
            (self.family_id, "family_id"),
            (self.subject_person_id, "subject_person_id"),
            (self.purpose, "purpose"),
            (self.consent_version, "consent_version"),
            (self.correlation_id, "correlation_id"),
        ):
            _text(value, name)


@dataclass(frozen=True, slots=True)
class BlueprintSnapshot:
    """The published service configuration frozen into a case."""

    blueprint_ref: str
    version: int
    status: str
    policy_ref: str
    policy_version: int
    checksum: str
    task_template_keys: tuple[str, ...]
    total_units: Decimal = Decimal("100")

    def __post_init__(self) -> None:
        for value, name in (
            (self.blueprint_ref, "blueprint_ref"),
            (self.status, "blueprint_status"),
            (self.policy_ref, "policy_ref"),
            (self.checksum, "blueprint_checksum"),
        ):
            _text(value, name)
        if self.status != "PUBLISHED":
            raise ServiceValidationError("fgcn_blueprint_must_be_published")
        if self.version < 1 or self.policy_version < 1:
            raise ServiceValidationError("fgcn_blueprint_version_invalid")
        if not self.task_template_keys or any(
            not isinstance(key, str) or not key.strip() for key in self.task_template_keys
        ):
            raise ServiceValidationError("fgcn_task_templates_required")
        total_units = _decimal(self.total_units, "total_units")
        if total_units != Decimal("100"):
            raise ServiceValidationError("fgcn_shadow_pool_must_be_100_units")
        object.__setattr__(self, "total_units", total_units)


@dataclass(frozen=True, slots=True)
class ServiceCase:
    case_id: str
    scope: GateServiceScope
    intent_ref: str
    plan_ref: str
    owner_id: str
    blueprint: BlueprintSnapshot
    status: CaseStatus = CaseStatus.OPEN
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None
    shadow_allocation_finalized_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.case_id, "case_id"),
            (self.intent_ref, "intent_ref"),
            (self.plan_ref, "plan_ref"),
            (self.owner_id, "owner_id"),
        ):
            _text(value, name)
        _aware(self.opened_at, "opened_at")
        if self.closed_at is not None:
            _aware(self.closed_at, "closed_at")
        if self.status is CaseStatus.COMPLETED and self.closed_at is None:
            raise ServiceValidationError("fgcn_completed_case_time_required")
        if self.status is not CaseStatus.COMPLETED and self.closed_at is not None:
            raise ServiceValidationError("fgcn_non_completed_case_close_time_invalid")
        if self.shadow_allocation_finalized_at is not None:
            _aware(self.shadow_allocation_finalized_at, "shadow_allocation_finalized_at")


@dataclass(frozen=True, slots=True)
class ServiceTask:
    task_id: str
    case_id: str
    blueprint_ref: str
    blueprint_version: int
    task_key: str
    title: str
    description: str
    role_key: str
    acceptance_criteria: tuple[str, ...]
    task_weight: Decimal = Decimal("1")
    status: TaskStatus = TaskStatus.PENDING
    responsible_ref: str | None = None
    deliverable_ref: str | None = None
    verified_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for value, name in (
            (self.task_id, "task_id"),
            (self.case_id, "case_id"),
            (self.blueprint_ref, "blueprint_ref"),
            (self.task_key, "task_key"),
            (self.title, "task_title"),
            (self.description, "task_description"),
            (self.role_key, "role_key"),
        ):
            _text(value, name)
        if self.blueprint_version < 1 or not self.acceptance_criteria:
            raise ServiceValidationError("fgcn_task_configuration_invalid")
        if any(not criterion.strip() for criterion in self.acceptance_criteria):
            raise ServiceValidationError("fgcn_acceptance_criteria_invalid")
        weight = _decimal(self.task_weight, "task_weight")
        if weight <= 0:
            raise ServiceValidationError("fgcn_task_weight_must_be_positive")
        object.__setattr__(self, "task_weight", weight)
        _aware(self.created_at, "task_created_at")
        if self.verified_at is not None:
            _aware(self.verified_at, "task_verified_at")


@dataclass(frozen=True, slots=True)
class TaskAssignment:
    assignment_id: str
    case_id: str
    task_id: str
    assignee_ref: str
    assignee_kind: str
    status: TaskAssignmentStatus
    accepted_by_actor_id: str
    source_request_id: str
    accepted_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.assignment_id, "assignment_id"),
            (self.case_id, "case_id"),
            (self.task_id, "task_id"),
            (self.assignee_ref, "assignee_ref"),
            (self.assignee_kind, "assignee_kind"),
            (self.accepted_by_actor_id, "accepted_by_actor_id"),
            (self.source_request_id, "source_request_id"),
        ):
            _text(value, name)
        if self.status is not TaskAssignmentStatus.ACCEPTED:
            raise ServiceValidationError("fgcn_only_accepted_assignment_is_supported")
        _aware(self.accepted_at, "assignment_accepted_at")


@dataclass(frozen=True, slots=True)
class ServiceDelivery:
    delivery_id: str
    case_id: str
    task_id: str
    assignee_ref: str
    evidence_ref: str
    delivered_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.delivery_id, "delivery_id"),
            (self.case_id, "case_id"),
            (self.task_id, "task_id"),
            (self.assignee_ref, "assignee_ref"),
            (self.evidence_ref, "delivery_evidence_ref"),
        ):
            _text(value, name)
        _aware(self.delivered_at, "delivery_delivered_at")


@dataclass(frozen=True, slots=True)
class TaskQualityReview:
    quality_review_id: str
    case_id: str
    task_id: str
    reviewer_ref: str
    quality_state: TaskQualityState
    review_note: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.quality_review_id, "quality_review_id"),
            (self.case_id, "case_id"),
            (self.task_id, "task_id"),
            (self.reviewer_ref, "quality_reviewer_ref"),
            (self.review_note, "quality_review_note"),
        ):
            _text(value, name)
        _aware(self.reviewed_at, "quality_reviewed_at")


@dataclass(frozen=True, slots=True)
class ServiceContribution:
    contribution_id: str
    case_id: str
    task_id: str
    provider_ref: str
    role_key: str
    delivery_id: str
    quality_state: ContributionQualityState
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.contribution_id, "contribution_id"),
            (self.case_id, "case_id"),
            (self.task_id, "task_id"),
            (self.provider_ref, "contribution_provider_ref"),
            (self.role_key, "contribution_role_key"),
            (self.delivery_id, "contribution_delivery_id"),
        ):
            _text(value, name)
        if self.quality_state is not ContributionQualityState.VERIFIED:
            raise ServiceValidationError("fgcn_contribution_requires_verified_quality")
        _aware(self.started_at, "contribution_started_at")
        _aware(self.completed_at, "contribution_completed_at")
        if self.completed_at < self.started_at:
            raise ServiceValidationError("fgcn_contribution_time_window_invalid")


@dataclass(frozen=True, slots=True)
class AllocationLine:
    allocation_id: str
    allocation_run_id: str
    case_id: str
    allocation_bucket: AllocationBucket
    units: Decimal
    beneficiary_ref: str
    beneficiary_kind: str
    role_key: str
    policy_ref: str
    policy_version: int
    basis_type: AllocationBasisType
    basis_ref: str
    release_state: AllocationReleaseState

    def __post_init__(self) -> None:
        try:
            allocation_bucket = AllocationBucket(self.allocation_bucket)
            basis_type = AllocationBasisType(self.basis_type)
            release_state = AllocationReleaseState(self.release_state)
        except ValueError as exc:
            raise ServiceValidationError("fgcn_allocation_enum_invalid") from exc
        object.__setattr__(self, "allocation_bucket", allocation_bucket)
        object.__setattr__(self, "basis_type", basis_type)
        object.__setattr__(self, "release_state", release_state)
        for value, name in (
            (self.allocation_id, "allocation_id"),
            (self.allocation_run_id, "allocation_run_id"),
            (self.case_id, "case_id"),
            (self.beneficiary_ref, "allocation_beneficiary_ref"),
            (self.beneficiary_kind, "allocation_beneficiary_kind"),
            (self.role_key, "allocation_role_key"),
            (self.policy_ref, "allocation_policy_ref"),
            (self.basis_ref, "allocation_basis_ref"),
        ):
            _text(value, name)
        if self.policy_version < 1:
            raise ServiceValidationError("fgcn_allocation_policy_version_invalid")
        units = _decimal(self.units, "allocation_units")
        if units < 0:
            raise ServiceValidationError("fgcn_allocation_units_negative")
        object.__setattr__(self, "units", units)


@dataclass(frozen=True, slots=True)
class AllocationStatement:
    allocation_run_id: str
    case_id: str
    policy_ref: str
    policy_version: int
    triggered_by_actor_id: str
    total_units: Decimal
    lines: tuple[AllocationLine, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for value, name in (
            (self.allocation_run_id, "allocation_run_id"),
            (self.case_id, "allocation_case_id"),
            (self.policy_ref, "allocation_policy_ref"),
            (self.triggered_by_actor_id, "allocation_actor_id"),
        ):
            _text(value, name)
        if self.policy_version < 1 or not self.lines:
            raise ServiceValidationError("fgcn_allocation_statement_invalid")
        total_units = _decimal(self.total_units, "allocation_total_units")
        if total_units != Decimal("100"):
            raise ServiceValidationError("fgcn_allocation_total_must_be_100_units")
        if sum((line.units for line in self.lines), Decimal("0")) != total_units:
            raise ServiceValidationError("fgcn_allocation_lines_must_sum_to_100_units")
        if any(line.case_id != self.case_id for line in self.lines):
            raise ServiceValidationError("fgcn_allocation_line_case_mismatch")
        object.__setattr__(self, "total_units", total_units)
        _aware(self.created_at, "allocation_created_at")


__all__ = [
    "AllocationBasisType",
    "AllocationBucket",
    "AllocationLine",
    "AllocationReleaseState",
    "AllocationStatement",
    "BlueprintSnapshot",
    "CaseStatus",
    "ContributionQualityState",
    "GateServiceScope",
    "ServiceCase",
    "ServiceContribution",
    "ServiceDelivery",
    "ServiceTask",
    "TaskAssignment",
    "TaskAssignmentStatus",
    "TaskQualityReview",
    "TaskQualityState",
    "TaskStatus",
]
