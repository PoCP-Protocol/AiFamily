"""SQLAlchemy persistence for the FGCN P0 facts.

The historical baseline already owns the FGCN tables.  This module maps the
P0 contracts onto those tables without creating a second service store:

* ``ServiceCase`` uses ``service_cases`` and stores the immutable blueprint
  snapshot in ``collaboration_blueprint_snapshot``;
* ``ServiceTask`` uses ``service_tasks``; its acceptance criteria are stored by
  the post-baseline migration because the historical table did not retain them;
* delivery evidence is kept in the existing task ``deliverable`` JSON because
  a standalone ``service_deliveries`` table is still a target-state object;
* allocation runs and lines use the baseline tables and remain shadow units,
  never money or settlement records.

All methods stage changes only.  The caller must use the same
``AsyncSession`` for domain rows and ``AuditRecorder.flush(session)`` and then
commit once through ``SqlAlchemyUnitOfWork``.  This adapter is therefore a
durable repository seam, not a claim that the application/API wiring is
complete.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceNotFoundError,
    ServiceValidationError,
)
from backend.platform.audit import AuditRecorder

from .contracts import (
    HUMAN_SERVICE_PROVIDER_KINDS,
    AllocationBasisType,
    AllocationBucket,
    AllocationLine,
    AllocationReleaseState,
    AllocationStatement,
    BlueprintSnapshot,
    CaseOpeningIdempotencyRecord,
    CaseStatus,
    ContributionQualityState,
    GateServiceScope,
    MutationIdempotencyRecord,
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
from .scenario import S01OutcomeMarkers, ServiceScenario

_UUID = Uuid(as_uuid=False)
_TIMESTAMP = DateTime(timezone=True)


def _existing_enum(*values: str, name: str) -> postgresql.ENUM:
    """Refer to a baseline Postgres enum without trying to create it.

    The same type compiles to ``VARCHAR`` on SQLite, preserving the repository
    test fast path while production writes use the enum types already created by
    the historical baseline.
    """

    return postgresql.ENUM(*values, name=name, create_type=False, validate_strings=True)


_CASE_STATUS = _existing_enum(
    "OPEN",
    "ASSIGNED",
    "IN_PROGRESS",
    "WAITING_FAMILY",
    "ESCALATED",
    "COMPLETED",
    "CANCELLED",
    name="service_case_status",
)
_TASK_STATUS = _existing_enum(
    "PENDING",
    "OFFERED",
    "ACCEPTED",
    "IN_PROGRESS",
    "DELIVERED",
    "VERIFIED",
    "CLOSED",
    "CANCELLED",
    "REWORK_REQUESTED",
    name="service_task_status",
)
_ASSIGNMENT_STATUS = _existing_enum(
    "OFFERED",
    "ACCEPTED",
    "DECLINED",
    "REVOKED",
    "COMPLETED",
    name="task_assignment_status",
)
_QUALITY_STATE = _existing_enum(
    "PENDING", "PASSED", "REWORK_REQUIRED", "REJECTED", name="task_quality_state"
)

_ALLOWED_ASSIGNEE_KINDS = HUMAN_SERVICE_PROVIDER_KINDS
_FIXED_ALLOCATION_UNITS = {
    AllocationBucket.PLATFORM: Decimal("20"),
    AllocationBucket.CONTENT_RESOURCE: Decimal("15"),
    AllocationBucket.CASE_STEWARD: Decimal("15"),
    AllocationBucket.QUALITY_RESERVE: Decimal("10"),
}
_DELIVERY_ALLOCATION_UNITS = Decimal("40")


class FGCNBase(DeclarativeBase):
    """Metadata owned by the FGCN adapter, separate from booking metadata."""


class ServiceCaseRow(FGCNBase):
    __tablename__ = "service_cases"

    case_id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    family_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    subject_person_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    intent_ref: Mapped[str] = mapped_column(_UUID, nullable=False)
    plan_ref: Mapped[str] = mapped_column(_UUID, nullable=False)
    status: Mapped[str] = mapped_column(_CASE_STATUS, nullable=False)
    owner: Mapped[str] = mapped_column(String(96), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False)
    next_action_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    scope_purpose: Mapped[str | None] = mapped_column(String(96), nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    collaboration_blueprint_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    collaboration_blueprint_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collaboration_blueprint_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    shadow_allocation_finalized_at: Mapped[datetime | None] = mapped_column(
        _TIMESTAMP, nullable=True
    )
    shadow_allocation_policy_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    shadow_allocation_policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class IdempotencyKeyRow(FGCNBase):
    """Mapping for the existing platform idempotency table.

    FGCN does not add or alter the shared table.  It stores a hashed,
    tenant-scoped key in its existing primary-key column, so the legacy global
    physical key space cannot turn into a cross-tenant collision.
    """

    __tablename__ = "idempotency_keys"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    action_name: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        _TIMESTAMP, nullable=False, server_default=sa.func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)


class ServiceTaskRow(FGCNBase):
    __tablename__ = "service_tasks"
    __table_args__ = (UniqueConstraint("case_ref", "task_key", name="uq_service_tasks_case_key"),)

    task_id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    case_ref: Mapped[str] = mapped_column(
        _UUID, ForeignKey("service_cases.case_id"), nullable=False
    )
    blueprint_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    task_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(_TASK_STATUS, nullable=False)
    responsible_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    deliverable: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False)
    role_key: Mapped[str | None] = mapped_column(String(96), nullable=True)
    required_capability_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    task_weight: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    rework_of_task_id: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("service_tasks.task_id"), nullable=True
    )
    rework_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class TaskAssignmentRow(FGCNBase):
    __tablename__ = "task_assignments"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "assignee_ref", "created_at", name="uq_task_assignments_identity"
        ),
        Index(
            "uq_task_assignments_one_accepted",
            "task_id",
            unique=True,
            postgresql_where=sa.text("status = 'ACCEPTED'"),
            sqlite_where=sa.text("status = 'ACCEPTED'"),
        ),
        Index(
            "uq_task_assignments_source_request",
            "source_request_id",
            unique=True,
            postgresql_where=sa.text("source_request_id IS NOT NULL"),
            sqlite_where=sa.text("source_request_id IS NOT NULL"),
        ),
    )

    assignment_id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    task_id: Mapped[str] = mapped_column(_UUID, ForeignKey("service_tasks.task_id"), nullable=False)
    assignee_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    assignee_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(_ASSIGNMENT_STATUS, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False)
    accepted_by_actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class TaskQualityReviewRow(FGCNBase):
    __tablename__ = "task_quality_reviews"

    quality_review_id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    task_id: Mapped[str] = mapped_column(_UUID, ForeignKey("service_tasks.task_id"), nullable=False)
    reviewer_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    quality_state: Mapped[str] = mapped_column(_QUALITY_STATE, nullable=False)
    review_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False)


class ServiceContributionRow(FGCNBase):
    __tablename__ = "service_contributions"

    contribution_id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    case_ref: Mapped[str] = mapped_column(
        _UUID, ForeignKey("service_cases.case_id"), nullable=False
    )
    provider_ref: Mapped[str | None] = mapped_column(String(96), nullable=True)
    role: Mapped[str] = mapped_column(String(48), nullable=False)
    # The legacy baseline made this varchar and did not retain the delivery
    # reference.  Keep the historical type and add the P0 delivery provenance
    # column in 0004; pretending either was a UUID FK would make the ORM claim
    # a relationship the production schema does not have.
    task_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    delivery_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    started_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    quality_state: Mapped[str] = mapped_column(String(32), nullable=False)


class AllocationRunRow(FGCNBase):
    __tablename__ = "service_case_allocation_runs"

    allocation_run_id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    case_ref: Mapped[str] = mapped_column(
        _UUID, ForeignKey("service_cases.case_id"), nullable=False
    )
    policy_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by_actor_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    total_units: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False)
    __table_args__ = (UniqueConstraint("case_ref", name="uq_case_allocation_run"),)


class AllocationLineRow(FGCNBase):
    __tablename__ = "service_contribution_allocations"

    allocation_id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    contribution_ref: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("service_contributions.contribution_id"), nullable=True
    )
    case_ref: Mapped[str] = mapped_column(
        _UUID, ForeignKey("service_cases.case_id"), nullable=False
    )
    task_ref: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("service_tasks.task_id"), nullable=True
    )
    allocation_bucket: Mapped[str] = mapped_column(String(32), nullable=False)
    units: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    release_state: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(240), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_TIMESTAMP, nullable=False)
    beneficiary_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    beneficiary_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role_key: Mapped[str | None] = mapped_column(String(96), nullable=True)
    policy_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basis_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basis_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    allocation_run_ref: Mapped[str | None] = mapped_column(
        _UUID, ForeignKey("service_case_allocation_runs.allocation_run_id"), nullable=True
    )


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _required_utc(value: object, code: str) -> datetime:
    if not isinstance(value, datetime):
        raise ServiceValidationError(code)
    normalized = _utc(value)
    if normalized is None:
        raise ServiceValidationError(code)
    return normalized


def _snapshot(blueprint: BlueprintSnapshot) -> dict[str, Any]:
    return {
        "blueprint_ref": blueprint.blueprint_ref,
        "version": blueprint.version,
        "status": blueprint.status,
        "policy_ref": blueprint.policy_ref,
        "policy_version": blueprint.policy_version,
        "checksum": blueprint.checksum,
        "task_template_keys": list(blueprint.task_template_keys),
        "scenario": {
            "scenario_key": blueprint.scenario.scenario_key,
            "scenario_version": blueprint.scenario.scenario_version,
            "outcome_key": blueprint.scenario.outcome_key,
            "policy_ref": blueprint.scenario.policy_ref,
            "policy_version": blueprint.scenario.policy_version,
            "locale": blueprint.scenario.locale,
            "family_problem": blueprint.scenario.family_problem,
            "provider_deliverable": blueprint.scenario.provider_deliverable,
            "service_outcome": blueprint.scenario.service_outcome,
        },
        "total_units": str(blueprint.total_units),
    }


def _blueprint_from_row(row: ServiceCaseRow) -> BlueprintSnapshot:
    raw = row.collaboration_blueprint_snapshot
    if not isinstance(raw, dict):
        raise ServiceValidationError("fgcn_blueprint_snapshot_missing")
    values = dict(raw)
    try:
        values["task_template_keys"] = tuple(values["task_template_keys"])
        values["scenario"] = ServiceScenario(**values["scenario"])
        return BlueprintSnapshot(**values)
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceValidationError("fgcn_blueprint_snapshot_invalid") from exc


def _required_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError(code)
    return value.strip()


def _text_tuple(value: object, code: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ServiceValidationError(code)
    result = tuple(_required_text(item, code) for item in value)
    return result


def _optional_text_tuple(value: object, code: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ServiceValidationError(code)
    return tuple(_required_text(item, code) for item in value)


def _human_actor(value: object, code: str = "fgcn_requires_human_actor") -> str:
    actor = _required_text(value, "fgcn_actor_required")
    if actor.lower().startswith("ai:") or actor.upper() in {"AI", "SYSTEM"}:
        raise ServiceForbiddenError(code)
    return actor


def _delivery_from_payload(task: ServiceTaskRow) -> ServiceDelivery | None:
    raw = task.deliverable
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ServiceValidationError("fgcn_task_deliverable_invalid")
    required = {
        "delivery_id": "fgcn_delivery_id_required",
        "evidence_ref": "fgcn_delivery_evidence_required",
        "outcome_observation": "fgcn_s01_delivery_outcome_required",
        "assignee_ref": "fgcn_delivery_assignee_required",
        "delivered_at": "fgcn_delivery_time_required",
    }
    try:
        delivered_at = datetime.fromisoformat(
            _required_text(raw["delivered_at"], required["delivered_at"])
        )
        raw_markers = raw.get("outcome_markers")
        markers = None
        if raw_markers is not None:
            if not isinstance(raw_markers, dict):
                raise ServiceValidationError("fgcn_delivery_markers_persisted_shape_invalid")
            markers = S01OutcomeMarkers(**raw_markers)
        delivery = ServiceDelivery(
            delivery_id=_required_text(raw["delivery_id"], required["delivery_id"]),
            case_id=task.case_ref,
            task_id=task.task_id,
            assignee_ref=_required_text(raw["assignee_ref"], required["assignee_ref"]),
            evidence_ref=_required_text(raw["evidence_ref"], required["evidence_ref"]),
            outcome_observation=_required_text(
                raw["outcome_observation"], required["outcome_observation"]
            ),
            delivered_at=_utc(delivered_at),
            locale=raw.get("locale", "en"),
            outcome_markers=markers,
        )
    except (KeyError, TypeError, ValueError, ServiceValidationError) as exc:
        raise ServiceValidationError("fgcn_delivery_persisted_shape_invalid") from exc
    return delivery


def _case_snapshot_matches(row: ServiceCaseRow, case: ServiceCase) -> bool:
    return (
        row.tenant_id == case.scope.tenant_id
        and row.family_id == case.scope.family_id
        and row.subject_person_id == case.scope.subject_person_id
        and row.intent_ref == case.intent_ref
        and row.plan_ref == case.plan_ref
        and row.owner == case.owner_id
        and row.scope_purpose == case.scope.purpose
        and row.consent_version == case.scope.consent_version
        and row.correlation_id == case.scope.correlation_id
        and row.collaboration_blueprint_ref == case.blueprint.blueprint_ref
        and row.collaboration_blueprint_version == case.blueprint.version
        and _blueprint_from_row(row) == case.blueprint
    )


def _fixed_allocation_identity(
    bucket: AllocationBucket, case_owner: str
) -> tuple[str, str, str] | None:
    return {
        AllocationBucket.PLATFORM: ("platform", "PLATFORM", "PLATFORM"),
        AllocationBucket.CONTENT_RESOURCE: (
            "content-resource",
            "INTERNAL_ACTOR",
            "CONTENT_RESOURCE",
        ),
        AllocationBucket.CASE_STEWARD: (case_owner, "INTERNAL_ACTOR", "CASE_STEWARD"),
        AllocationBucket.QUALITY_RESERVE: (
            "quality-reserve",
            "PLATFORM",
            "QUALITY_RESERVE",
        ),
    }.get(bucket)


def _task_status_transition_is_valid(existing: str, incoming: TaskStatus) -> bool:
    if existing == incoming.value:
        return True
    if existing in {TaskStatus.VERIFIED.value, TaskStatus.CLOSED.value, TaskStatus.CANCELLED.value}:
        return False
    if incoming is TaskStatus.CANCELLED:
        return True
    if incoming is TaskStatus.REWORK_REQUESTED:
        return existing == TaskStatus.DELIVERED.value
    if existing == TaskStatus.REWORK_REQUESTED.value:
        return False
    order = {
        TaskStatus.PENDING.value: 0,
        TaskStatus.ACCEPTED.value: 1,
        TaskStatus.IN_PROGRESS.value: 2,
        TaskStatus.DELIVERED.value: 3,
        TaskStatus.VERIFIED.value: 4,
        TaskStatus.CLOSED.value: 5,
    }
    return order.get(incoming.value, -1) >= order.get(existing, -1)


def _allocation_line_shape_is_valid(statement: AllocationStatement) -> None:
    if len({line.allocation_id for line in statement.lines}) != len(statement.lines):
        raise ServiceValidationError("fgcn_duplicate_allocation_line_id")
    if any(line.allocation_run_id != statement.allocation_run_id for line in statement.lines):
        raise ServiceValidationError("fgcn_allocation_line_run_mismatch")
    if any(
        line.policy_ref != statement.policy_ref or line.policy_version != statement.policy_version
        for line in statement.lines
    ):
        raise ServiceValidationError("fgcn_allocation_line_policy_mismatch")

    case_lines = [line for line in statement.lines if line.basis_type is AllocationBasisType.CASE]
    delivery_lines = [
        line
        for line in statement.lines
        if line.basis_type is AllocationBasisType.CONTRIBUTION_WEIGHT
    ]
    if len(case_lines) != len(_FIXED_ALLOCATION_UNITS):
        raise ServiceValidationError("fgcn_fixed_allocation_buckets_invalid")
    if {line.allocation_bucket for line in case_lines} != set(_FIXED_ALLOCATION_UNITS):
        raise ServiceValidationError("fgcn_fixed_allocation_buckets_invalid")
    for line in case_lines:
        expected_units = _FIXED_ALLOCATION_UNITS.get(line.allocation_bucket)
        if (
            expected_units is None
            or line.units != expected_units
            or line.basis_ref != statement.case_id
            or line.allocation_bucket is AllocationBucket.DELIVERY_RESOURCE
            or line.release_state
            != (
                AllocationReleaseState.HELD
                if line.allocation_bucket is AllocationBucket.QUALITY_RESERVE
                else AllocationReleaseState.RELEASED
            )
        ):
            raise ServiceValidationError("fgcn_fixed_allocation_line_invalid")
    if (
        not delivery_lines
        or sum((line.units for line in delivery_lines), Decimal("0")) != _DELIVERY_ALLOCATION_UNITS
    ):
        raise ServiceValidationError("fgcn_delivery_allocation_pool_invalid")
    if len({line.basis_ref for line in delivery_lines}) != len(delivery_lines):
        raise ServiceValidationError("fgcn_duplicate_delivery_allocation_basis")
    if any(
        line.allocation_bucket is not AllocationBucket.DELIVERY_RESOURCE
        or line.release_state is not AllocationReleaseState.RELEASED
        or not line.beneficiary_ref
        or not line.role_key
        for line in delivery_lines
    ):
        raise ServiceValidationError("fgcn_delivery_allocation_line_invalid")


def _allocation_row_matches(
    row: AllocationLineRow,
    line: AllocationLine,
    *,
    contribution_ref: str | None,
    task_ref: str | None,
    allocation_run_id: str,
) -> bool:
    return (
        row.allocation_id == line.allocation_id
        and row.contribution_ref == contribution_ref
        and row.case_ref == line.case_id
        and row.task_ref == task_ref
        and row.allocation_bucket == line.allocation_bucket.value
        and row.units == line.units
        and row.release_state == line.release_state.value
        and row.beneficiary_ref == line.beneficiary_ref
        and row.beneficiary_kind == line.beneficiary_kind
        and row.role_key == line.role_key
        and row.policy_ref == line.policy_ref
        and row.policy_version == line.policy_version
        and row.basis_type == line.basis_type.value
        and row.basis_ref == line.basis_ref
        and row.allocation_run_ref == allocation_run_id
        and row.reason == "shadow allocation basis"
        and row.released_at is None
    )


class SqlAlchemyFGCNRepository:
    """Durable repository for FGCN facts; commit remains the caller's job."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _stage(self, row: object) -> None:
        await self._session.merge(row)

    async def _get(self, model: type, entity_id: str, code: str):
        row = await self._session.get(model, entity_id)
        if row is None:
            raise ServiceNotFoundError(code)
        return row

    @staticmethod
    def _case_opening_storage_key(scope: GateServiceScope, idempotency_key: str) -> str:
        """Return a bounded, opaque key derived from tenant and client key."""

        material = (
            f"fgcn:open-service-case:{len(scope.tenant_id)}:{scope.tenant_id}:{idempotency_key}"
        )
        return f"fgcn:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"

    async def claim_case_opening(
        self,
        *,
        scope: GateServiceScope,
        idempotency_key: str,
        request_hash: str,
    ) -> CaseOpeningIdempotencyRecord:
        """Atomically reserve or replay a case-opening request.

        The insert, row lock/read, case write, audit flush, and response update
        all use the caller's transaction.  ``ON CONFLICT DO NOTHING`` is
        supported by both production PostgreSQL and the SQLite parity adapter;
        PostgreSQL waits for a concurrent winner before the locked read.
        """

        storage_key = self._case_opening_storage_key(scope, idempotency_key)
        insert_result = await self._session.execute(
            sa.text(
                """
                INSERT INTO idempotency_keys(
                    idempotency_key, action_name, request_hash
                ) VALUES (:key, :action, :request_hash)
                ON CONFLICT (idempotency_key) DO NOTHING
                """
            ),
            {
                "key": storage_key,
                "action": "OPEN_SERVICE_CASE",
                "request_hash": request_hash,
            },
        )
        row = await self._session.get(IdempotencyKeyRow, storage_key, with_for_update=True)
        if row is None:
            raise ServiceConflictError("fgcn_case_opening_idempotency_unavailable")
        if row.action_name != "OPEN_SERVICE_CASE" or row.request_hash != request_hash:
            raise ServiceConflictError("fgcn_case_opening_idempotency_replay_mismatch")
        inserted = insert_result.rowcount == 1
        case_id: str | None = None
        if row.response_body is not None:
            if not isinstance(row.response_body, dict):
                raise ServiceConflictError("fgcn_case_opening_idempotency_response_invalid")
            value = row.response_body.get("case_id")
            if not isinstance(value, str) or not value.strip():
                raise ServiceConflictError("fgcn_case_opening_idempotency_response_invalid")
            case_id = value
        if not inserted and case_id is None:
            raise ServiceConflictError("fgcn_case_opening_idempotency_incomplete")
        return CaseOpeningIdempotencyRecord(
            request_hash=request_hash, case_id=case_id, is_new=inserted
        )

    async def complete_case_opening(
        self,
        *,
        scope: GateServiceScope,
        idempotency_key: str,
        request_hash: str,
        case_id: str,
    ) -> None:
        """Bind the claimed key to its case before the transaction commits."""

        storage_key = self._case_opening_storage_key(scope, idempotency_key)
        result = await self._session.execute(
            sa.update(IdempotencyKeyRow)
            .where(
                IdempotencyKeyRow.idempotency_key == storage_key,
                IdempotencyKeyRow.action_name == "OPEN_SERVICE_CASE",
                IdempotencyKeyRow.request_hash == request_hash,
            )
            .values(response_code=200, response_body={"case_id": case_id})
        )
        if result.rowcount != 1:
            raise ServiceConflictError("fgcn_case_opening_idempotency_claim_missing")

    @staticmethod
    def _mutation_storage_key(
        scope: GateServiceScope,
        action_name: str,
        idempotency_key: str,
    ) -> str:
        """Hash tenant, action, and client key into the shared key column."""

        material = (
            f"fgcn:{action_name.strip()}:{len(scope.tenant_id)}:{scope.tenant_id}:"
            f"{idempotency_key.strip()}"
        )
        return f"fgcn:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"

    async def claim_mutation(
        self,
        *,
        scope: GateServiceScope,
        action_name: str,
        idempotency_key: str,
        request_hash: str,
    ) -> MutationIdempotencyRecord:
        """Claim an FGCN mutation in the same transaction as its fact.

        The physical table is pre-existing platform infrastructure.  The
        storage key remains opaque and tenant-scoped; the request hash binds
        the key to one immutable command payload.
        """

        if not action_name.strip() or not idempotency_key.strip():
            raise ServiceValidationError("fgcn_mutation_idempotency_key_required")
        storage_key = self._mutation_storage_key(scope, action_name, idempotency_key)
        insert_result = await self._session.execute(
            sa.text(
                """
                INSERT INTO idempotency_keys(
                    idempotency_key, action_name, request_hash
                ) VALUES (:key, :action, :request_hash)
                ON CONFLICT (idempotency_key) DO NOTHING
                """
            ),
            {
                "key": storage_key,
                "action": action_name.strip(),
                "request_hash": request_hash,
            },
        )
        row = await self._session.get(IdempotencyKeyRow, storage_key, with_for_update=True)
        if row is None:
            raise ServiceConflictError("fgcn_mutation_idempotency_unavailable")
        if row.action_name != action_name.strip() or row.request_hash != request_hash:
            raise ServiceConflictError("fgcn_mutation_idempotency_replay_mismatch")
        inserted = insert_result.rowcount == 1
        resource_id: str | None = None
        if row.response_body is not None:
            if not isinstance(row.response_body, dict):
                raise ServiceConflictError("fgcn_mutation_idempotency_response_invalid")
            value = row.response_body.get("resource_id")
            if not isinstance(value, str) or not value.strip():
                raise ServiceConflictError("fgcn_mutation_idempotency_response_invalid")
            resource_id = value
        if not inserted and resource_id is None:
            raise ServiceConflictError("fgcn_mutation_idempotency_incomplete")
        return MutationIdempotencyRecord(
            action_name=action_name.strip(),
            request_hash=request_hash,
            resource_id=resource_id,
            is_new=inserted,
        )

    async def complete_mutation(
        self,
        *,
        scope: GateServiceScope,
        action_name: str,
        idempotency_key: str,
        request_hash: str,
        resource_id: str,
    ) -> None:
        """Bind the durable response identity before the transaction commits."""

        storage_key = self._mutation_storage_key(scope, action_name, idempotency_key)
        result = await self._session.execute(
            sa.update(IdempotencyKeyRow)
            .where(
                IdempotencyKeyRow.idempotency_key == storage_key,
                IdempotencyKeyRow.action_name == action_name.strip(),
                IdempotencyKeyRow.request_hash == request_hash,
            )
            .values(response_code=200, response_body={"resource_id": resource_id})
        )
        if result.rowcount != 1:
            raise ServiceConflictError("fgcn_mutation_idempotency_claim_missing")

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        """Flush audit events through this repository's transaction.

        The application command uses this explicit seam before ``commit()`` so
        a Human Gate decision and its TaskAssignment cannot commit separately.
        Keeping the session hidden also prevents the command layer from
        reaching around the repository and opening a second transaction.
        """

        return await recorder.flush(self._session)

    async def commit(self) -> None:
        """Compatibility seam for the existing service repository protocol."""

        await self._session.commit()

    async def save_case(self, case: ServiceCase) -> None:
        existing = await self._session.get(ServiceCaseRow, case.case_id)
        if case.status is CaseStatus.COMPLETED and case.closed_at is None:
            raise ServiceValidationError("fgcn_completed_case_time_required")
        if existing is not None:
            try:
                immutable_matches = _case_snapshot_matches(existing, case)
            except ServiceValidationError:
                immutable_matches = False
            if not immutable_matches:
                raise ServiceConflictError("fgcn_case_id_reuse_mismatch")
            if (
                existing.status == CaseStatus.COMPLETED.value
                and case.status is not CaseStatus.COMPLETED
            ):
                raise ServiceConflictError("fgcn_completed_case_is_immutable")
            if (
                existing.status == CaseStatus.CANCELLED.value
                and case.status is not CaseStatus.CANCELLED
            ):
                raise ServiceConflictError("fgcn_cancelled_case_is_immutable")
            if existing.closed_at is not None and _utc(existing.closed_at) != case.closed_at:
                raise ServiceConflictError("fgcn_case_close_time_is_immutable")
            if existing.shadow_allocation_finalized_at is not None and (
                case.shadow_allocation_finalized_at is None
                or _utc(existing.shadow_allocation_finalized_at)
                != case.shadow_allocation_finalized_at
            ):
                raise ServiceConflictError("fgcn_shadow_allocation_marker_mismatch")
        await self._stage(
            ServiceCaseRow(
                case_id=case.case_id,
                tenant_id=case.scope.tenant_id,
                family_id=case.scope.family_id,
                subject_person_id=case.scope.subject_person_id,
                intent_ref=case.intent_ref,
                plan_ref=case.plan_ref,
                status=case.status.value,
                owner=case.owner_id,
                opened_at=case.opened_at,
                next_action_at=None,
                closed_at=case.closed_at,
                scope_purpose=case.scope.purpose,
                consent_version=case.scope.consent_version,
                correlation_id=case.scope.correlation_id,
                collaboration_blueprint_ref=case.blueprint.blueprint_ref,
                collaboration_blueprint_version=case.blueprint.version,
                collaboration_blueprint_snapshot=_snapshot(case.blueprint),
                shadow_allocation_finalized_at=case.shadow_allocation_finalized_at,
                shadow_allocation_policy_ref=(
                    case.blueprint.policy_ref if case.shadow_allocation_finalized_at else None
                ),
                shadow_allocation_policy_version=(
                    case.blueprint.policy_version if case.shadow_allocation_finalized_at else None
                ),
            )
        )

    async def load_case(self, case_id: str) -> ServiceCase:
        row = await self._get(ServiceCaseRow, case_id, "fgcn_service_case_not_found")
        try:
            status = CaseStatus(row.status)
        except ValueError as exc:
            raise ServiceValidationError("fgcn_case_status_invalid") from exc
        tenant_id = _required_text(row.tenant_id, "fgcn_case_tenant_required")
        family_id = _required_text(row.family_id, "fgcn_case_family_required")
        subject_person_id = _required_text(row.subject_person_id, "fgcn_case_subject_required")
        purpose = _required_text(row.scope_purpose, "fgcn_case_purpose_required")
        consent_version = _required_text(row.consent_version, "fgcn_case_consent_version_required")
        correlation_id = _required_text(row.correlation_id, "fgcn_case_correlation_required")
        blueprint = _blueprint_from_row(row)
        if (
            row.collaboration_blueprint_ref != blueprint.blueprint_ref
            or row.collaboration_blueprint_version != blueprint.version
        ):
            raise ServiceValidationError("fgcn_case_blueprint_columns_mismatch")
        return ServiceCase(
            case_id=row.case_id,
            scope=GateServiceScope(
                tenant_id=tenant_id,
                family_id=family_id,
                subject_person_id=subject_person_id,
                purpose=purpose,
                consent_version=consent_version,
                correlation_id=correlation_id,
            ),
            intent_ref=row.intent_ref,
            plan_ref=row.plan_ref,
            owner_id=row.owner,
            blueprint=blueprint,
            status=status,
            opened_at=_required_utc(row.opened_at, "fgcn_case_opened_at_required"),
            closed_at=_utc(row.closed_at),
            shadow_allocation_finalized_at=_utc(row.shadow_allocation_finalized_at),
        )

    async def save_task(self, task: ServiceTask) -> None:
        case = await self._get(ServiceCaseRow, task.case_id, "fgcn_service_case_not_found")
        if (
            case.collaboration_blueprint_ref != task.blueprint_ref
            or case.collaboration_blueprint_version != task.blueprint_version
        ):
            raise ServiceConflictError("fgcn_task_blueprint_snapshot_mismatch")
        existing = await self._session.get(ServiceTaskRow, task.task_id)
        try:
            task_status = TaskStatus(task.status)
        except ValueError as exc:
            raise ServiceValidationError("fgcn_task_status_invalid") from exc
        try:
            case_status = CaseStatus(case.status)
        except (TypeError, ValueError) as exc:
            raise ServiceValidationError("fgcn_case_status_invalid") from exc
        if task.rework_of_task_id is not None:
            parent = await self._get(
                ServiceTaskRow,
                task.rework_of_task_id,
                "fgcn_rework_source_task_not_found",
            )
            if parent.case_ref != task.case_id:
                raise ServiceForbiddenError("fgcn_rework_source_case_mismatch")
            if task.rework_attempt < 1:
                raise ServiceValidationError("fgcn_rework_attempt_invalid")
        elif task.rework_attempt != 0:
            raise ServiceValidationError("fgcn_rework_attempt_without_parent")
        if (
            case_status in {CaseStatus.COMPLETED, CaseStatus.CANCELLED}
            and task_status
            in {
                TaskStatus.DELIVERED,
                TaskStatus.VERIFIED,
            }
            and (existing is None or existing.status != task_status.value)
        ):
            # A stale worker must not append a delivery/verification after the
            # case reached its terminal state.  An exact persisted replay is
            # still allowed so rehydration remains idempotent.
            raise ServiceConflictError("fgcn_delivery_case_is_terminal")
        if task_status is TaskStatus.VERIFIED and task.verified_at is None:
            raise ServiceValidationError("fgcn_verified_task_time_required")
        if task_status in {TaskStatus.DELIVERED, TaskStatus.VERIFIED} and not task.deliverable_ref:
            raise ServiceValidationError("fgcn_delivered_task_evidence_required")
        if task.deliverable_ref is not None:
            task_evidence_ref = _required_text(
                task.deliverable_ref, "fgcn_delivery_evidence_required"
            )
        else:
            task_evidence_ref = None
        created_at = _utc(existing.created_at) if existing is not None else task.created_at
        deliverable = existing.deliverable if existing is not None else None
        if existing is not None:
            if (
                existing.case_ref != task.case_id
                or existing.blueprint_ref != task.blueprint_ref
                or existing.task_key != task.task_key
                or existing.title != task.title
                or existing.description != task.description
                or existing.role_key != task.role_key
                or tuple(existing.acceptance_criteria or ()) != task.acceptance_criteria
                or existing.task_weight != task.task_weight
                or existing.rework_of_task_id != task.rework_of_task_id
                or existing.rework_attempt != task.rework_attempt
            ):
                raise ServiceConflictError("fgcn_task_id_reuse_mismatch")
            if not _task_status_transition_is_valid(existing.status, task_status):
                raise ServiceConflictError("fgcn_task_status_regression")
            existing_delivery = None
            if isinstance(existing.deliverable, dict) and "delivery_id" in existing.deliverable:
                existing_delivery = _delivery_from_payload(existing)
            if existing_delivery is not None and task_evidence_ref not in {
                None,
                existing_delivery.evidence_ref,
            }:
                raise ServiceConflictError("fgcn_task_delivery_replay_mismatch")
            if existing.verified_at is not None and task.verified_at not in {
                None,
                _utc(existing.verified_at),
            }:
                raise ServiceConflictError("fgcn_task_verification_replay_mismatch")
        if task_evidence_ref is not None:
            deliverable = dict(deliverable or {})
            deliverable["evidence_ref"] = task_evidence_ref
        await self._stage(
            ServiceTaskRow(
                task_id=task.task_id,
                case_ref=task.case_id,
                blueprint_ref=task.blueprint_ref,
                task_key=task.task_key,
                title=task.title,
                description=task.description,
                status=task_status.value,
                responsible_ref=task.responsible_ref,
                due_at=None,
                deliverable=deliverable,
                verified_at=task.verified_at,
                created_at=created_at,
                updated_at=datetime.now(UTC),
                role_key=task.role_key,
                required_capability_keys=list(task.required_capability_keys),
                task_weight=task.task_weight,
                rework_of_task_id=task.rework_of_task_id,
                rework_attempt=task.rework_attempt,
                acceptance_criteria=list(task.acceptance_criteria),
            )
        )

    async def load_task(self, task_id: str) -> ServiceTask:
        row = await self._get(ServiceTaskRow, task_id, "fgcn_service_task_not_found")
        try:
            status = TaskStatus(row.status)
        except (TypeError, ValueError) as exc:
            raise ServiceValidationError("fgcn_task_persisted_shape_invalid") from exc
        criteria = _text_tuple(row.acceptance_criteria, "fgcn_task_acceptance_criteria_missing")
        required_capability_keys = _optional_text_tuple(
            row.required_capability_keys,
            "fgcn_task_required_capability_keys_invalid",
        )
        deliverable_ref = None
        if row.deliverable is not None:
            if not isinstance(row.deliverable, dict):
                raise ServiceValidationError("fgcn_task_deliverable_invalid")
            raw_evidence_ref = row.deliverable.get("evidence_ref")
            if raw_evidence_ref is not None:
                deliverable_ref = _required_text(
                    raw_evidence_ref, "fgcn_delivery_evidence_required"
                )
        case = await self._get(ServiceCaseRow, row.case_ref, "fgcn_service_case_not_found")
        if case.collaboration_blueprint_version is None:
            raise ServiceValidationError("fgcn_case_blueprint_version_missing")
        if case.collaboration_blueprint_ref != row.blueprint_ref:
            raise ServiceConflictError("fgcn_task_blueprint_snapshot_mismatch")
        if status is TaskStatus.VERIFIED and row.verified_at is None:
            raise ServiceValidationError("fgcn_verified_task_time_required")
        if (
            status
            in {
                TaskStatus.DELIVERED,
                TaskStatus.REWORK_REQUESTED,
                TaskStatus.VERIFIED,
            }
            and deliverable_ref is None
        ):
            raise ServiceValidationError("fgcn_delivered_task_evidence_required")
        rework_of_task_id = row.rework_of_task_id
        if rework_of_task_id is not None:
            parent = await self._get(
                ServiceTaskRow,
                rework_of_task_id,
                "fgcn_rework_source_task_not_found",
            )
            if parent.case_ref != row.case_ref:
                raise ServiceValidationError("fgcn_rework_source_case_mismatch")
            if row.rework_attempt < 1:
                raise ServiceValidationError("fgcn_rework_attempt_invalid")
        elif row.rework_attempt != 0:
            raise ServiceValidationError("fgcn_rework_attempt_without_parent")
        return ServiceTask(
            task_id=row.task_id,
            case_id=row.case_ref,
            blueprint_ref=row.blueprint_ref,
            blueprint_version=case.collaboration_blueprint_version,
            task_key=row.task_key,
            title=row.title,
            description=row.description,
            role_key=_required_text(row.role_key, "fgcn_task_role_required"),
            acceptance_criteria=criteria,
            required_capability_keys=required_capability_keys,
            task_weight=row.task_weight,
            status=status,
            responsible_ref=row.responsible_ref,
            deliverable_ref=deliverable_ref,
            verified_at=_utc(row.verified_at),
            created_at=_required_utc(row.created_at, "fgcn_task_created_at_required"),
            locale=_blueprint_from_row(case).scenario.locale,
            rework_of_task_id=rework_of_task_id,
            rework_attempt=row.rework_attempt,
        )

    async def save_assignment(self, assignment: TaskAssignment) -> None:
        _human_actor(assignment.accepted_by_actor_id)
        if assignment.assignee_kind not in _ALLOWED_ASSIGNEE_KINDS:
            raise ServiceValidationError("fgcn_assignee_kind_invalid")
        task = await self._get(ServiceTaskRow, assignment.task_id, "fgcn_service_task_not_found")
        if (
            task.status != TaskStatus.ACCEPTED.value
            or task.responsible_ref != assignment.assignee_ref
        ):
            raise ServiceConflictError("fgcn_assignment_task_state_mismatch")
        await self._get(ServiceCaseRow, task.case_ref, "fgcn_service_case_not_found")
        existing = await self._session.get(TaskAssignmentRow, assignment.assignment_id)
        if existing is not None:
            if (
                existing.task_id != assignment.task_id
                or existing.assignee_ref != assignment.assignee_ref
                or existing.assignee_kind != assignment.assignee_kind
                or existing.status != assignment.status.value
                or existing.accepted_by_actor_id != assignment.accepted_by_actor_id
                or existing.source_request_id != assignment.source_request_id
                or _utc(existing.accepted_at) != assignment.accepted_at
            ):
                raise ServiceConflictError("fgcn_assignment_id_reuse_mismatch")
            return
        accepted = await self._session.scalar(
            sa.select(TaskAssignmentRow).where(
                TaskAssignmentRow.task_id == assignment.task_id,
                TaskAssignmentRow.status == TaskAssignmentStatus.ACCEPTED.value,
            )
        )
        if accepted is not None:
            raise ServiceConflictError("fgcn_one_accepted_assignment_per_task")
        await self._stage(
            TaskAssignmentRow(
                assignment_id=assignment.assignment_id,
                task_id=assignment.task_id,
                assignee_ref=assignment.assignee_ref,
                assignee_kind=assignment.assignee_kind,
                status=assignment.status.value,
                accepted_at=assignment.accepted_at,
                declined_at=None,
                revoked_at=None,
                created_at=assignment.accepted_at,
                accepted_by_actor_id=assignment.accepted_by_actor_id,
                source_request_id=assignment.source_request_id,
            )
        )

    async def save_delivery(self, delivery: ServiceDelivery) -> None:
        task = await self._get(ServiceTaskRow, delivery.task_id, "fgcn_service_task_not_found")
        if task.case_ref != delivery.case_id:
            raise ServiceForbiddenError("fgcn_delivery_case_mismatch")
        case = await self._get(ServiceCaseRow, task.case_ref, "fgcn_service_case_not_found")
        try:
            case_status = CaseStatus(case.status)
        except ValueError as exc:
            raise ServiceValidationError("fgcn_case_status_invalid") from exc
        existing_delivery = None
        if isinstance(task.deliverable, dict) and "delivery_id" in task.deliverable:
            existing_delivery = _delivery_from_payload(task)
        if existing_delivery is not None:
            if existing_delivery != delivery:
                raise ServiceConflictError("fgcn_delivery_id_reuse_mismatch")
            return
        if task.responsible_ref != delivery.assignee_ref:
            raise ServiceForbiddenError("fgcn_delivery_requires_assigned_responsible_person")
        if task.status != TaskStatus.ACCEPTED.value:
            raise ServiceConflictError("fgcn_delivery_state_invalid")
        if case_status in {CaseStatus.COMPLETED, CaseStatus.CANCELLED}:
            raise ServiceConflictError("fgcn_delivery_case_is_terminal")
        current = dict(task.deliverable or {})
        current.update(
            {
                "delivery_id": delivery.delivery_id,
                "evidence_ref": delivery.evidence_ref,
                "outcome_observation": delivery.outcome_observation,
                "assignee_ref": delivery.assignee_ref,
                "delivered_at": delivery.delivered_at.isoformat(),
                "locale": delivery.locale,
                "outcome_markers": asdict(delivery.outcome_markers),
            }
        )
        task.deliverable = current
        task.status = TaskStatus.DELIVERED.value
        task.updated_at = datetime.now(UTC)
        if case_status in {CaseStatus.OPEN, CaseStatus.ASSIGNED}:
            case.status = CaseStatus.IN_PROGRESS.value

    async def load_delivery(self, task_id: str) -> ServiceDelivery:
        task = await self._get(ServiceTaskRow, task_id, "fgcn_service_task_not_found")
        if task.status not in {
            TaskStatus.DELIVERED.value,
            TaskStatus.REWORK_REQUESTED.value,
            TaskStatus.VERIFIED.value,
            TaskStatus.CLOSED.value,
        }:
            raise ServiceValidationError("fgcn_delivery_task_state_invalid")
        delivery = _delivery_from_payload(task)
        if delivery is None:
            raise ServiceNotFoundError("fgcn_service_delivery_not_found")
        if task.responsible_ref != delivery.assignee_ref:
            raise ServiceValidationError("fgcn_delivery_assignee_mismatch")
        return delivery

    async def load_assignment(self, assignment_id: str) -> TaskAssignment:
        row = await self._get(TaskAssignmentRow, assignment_id, "fgcn_task_assignment_not_found")
        try:
            status = TaskAssignmentStatus(row.status)
        except (TypeError, ValueError) as exc:
            raise ServiceValidationError("fgcn_assignment_persisted_shape_invalid") from exc
        if status not in {
            TaskAssignmentStatus.ACCEPTED,
            TaskAssignmentStatus.REVOKED,
            TaskAssignmentStatus.COMPLETED,
        }:
            raise ServiceValidationError("fgcn_assignment_status_not_replayable")
        if row.assignee_kind not in _ALLOWED_ASSIGNEE_KINDS:
            raise ServiceValidationError("fgcn_assignee_kind_invalid")
        _human_actor(row.accepted_by_actor_id)
        task = await self._get(ServiceTaskRow, row.task_id, "fgcn_service_task_not_found")
        await self._get(ServiceCaseRow, task.case_ref, "fgcn_service_case_not_found")
        if (
            task.status
            not in {
                TaskStatus.ACCEPTED.value,
                TaskStatus.IN_PROGRESS.value,
                TaskStatus.DELIVERED.value,
                TaskStatus.VERIFIED.value,
                TaskStatus.CLOSED.value,
                TaskStatus.REWORK_REQUESTED.value,
            }
            or task.responsible_ref != row.assignee_ref
        ):
            raise ServiceValidationError("fgcn_assignment_task_state_mismatch")
        return TaskAssignment(
            assignment_id=row.assignment_id,
            case_id=task.case_ref,
            task_id=row.task_id,
            assignee_ref=_required_text(row.assignee_ref, "fgcn_assignment_assignee_required"),
            assignee_kind=_required_text(row.assignee_kind, "fgcn_assignee_kind_required"),
            status=status,
            accepted_by_actor_id=_required_text(
                row.accepted_by_actor_id, "fgcn_assignment_actor_required"
            ),
            source_request_id=_required_text(
                row.source_request_id, "fgcn_assignment_source_request_required"
            ),
            accepted_at=_required_utc(row.accepted_at, "fgcn_assignment_accepted_at_required"),
        )

    async def find_assignment_by_source_request_id(
        self, *, source_request_id: str
    ) -> TaskAssignment | None:
        """Find the durable result of one Named Action request.

        ``source_request_id`` is the durable replay key for the P0 bridge and
        is globally unique when non-null. Querying globally lets a request id
        accidentally reused for another task fail as a domain conflict instead
        of surfacing a raw database uniqueness error; the application command
        checks the loaded assignment against its task and case.
        The partial unique index is the database-side concurrency guard for
        non-null request ids.
        """

        rows = (
            await self._session.scalars(
                sa.select(TaskAssignmentRow).where(
                    TaskAssignmentRow.source_request_id == source_request_id,
                )
            )
        ).all()
        if not rows:
            return None
        if len(rows) != 1:
            raise ServiceConflictError("fgcn_assignment_source_request_ambiguous")
        return await self.load_assignment(rows[0].assignment_id)

    async def load_quality_review(self, quality_review_id: str) -> TaskQualityReview:
        row = await self._get(
            TaskQualityReviewRow, quality_review_id, "fgcn_quality_review_not_found"
        )
        try:
            quality_state = TaskQualityState(row.quality_state)
        except (TypeError, ValueError) as exc:
            raise ServiceValidationError("fgcn_quality_persisted_shape_invalid") from exc
        if quality_state not in {
            TaskQualityState.PASSED,
            TaskQualityState.REWORK_REQUIRED,
        }:
            raise ServiceValidationError("fgcn_non_pass_quality_requires_rework_flow")
        task = await self._get(ServiceTaskRow, row.task_id, "fgcn_service_task_not_found")
        if task.case_ref is None:
            raise ServiceValidationError("fgcn_quality_review_case_required")
        expected_task_status = (
            TaskStatus.VERIFIED.value
            if quality_state is TaskQualityState.PASSED
            else TaskStatus.REWORK_REQUESTED.value
        )
        if task.status != expected_task_status:
            raise ServiceValidationError("fgcn_quality_review_task_state_invalid")
        delivery = _delivery_from_payload(task)
        if delivery is None:
            raise ServiceValidationError("fgcn_quality_review_delivery_required")
        await self._get(ServiceCaseRow, task.case_ref, "fgcn_service_case_not_found")
        return TaskQualityReview(
            quality_review_id=row.quality_review_id,
            case_id=task.case_ref,
            task_id=row.task_id,
            reviewer_ref=_required_text(row.reviewer_ref, "fgcn_quality_reviewer_ref_required"),
            quality_state=quality_state,
            review_note=_required_text(row.review_note, "fgcn_quality_review_note_required"),
            reviewed_at=_required_utc(row.reviewed_at, "fgcn_quality_reviewed_at_required"),
            locale=delivery.locale,
        )

    async def load_contribution(self, contribution_id: str) -> ServiceContribution:
        row = await self._get(
            ServiceContributionRow, contribution_id, "fgcn_contribution_not_found"
        )
        try:
            quality_state = ContributionQualityState(row.quality_state)
        except (TypeError, ValueError) as exc:
            raise ServiceValidationError("fgcn_contribution_persisted_shape_invalid") from exc
        task = await self._get(ServiceTaskRow, row.task_ref, "fgcn_service_task_not_found")
        if task.status != TaskStatus.VERIFIED.value:
            raise ServiceValidationError("fgcn_contribution_task_state_invalid")
        delivery = _delivery_from_payload(task)
        delivery_ref = _required_text(row.delivery_ref, "fgcn_contribution_delivery_required")
        if delivery is None or delivery.delivery_id != delivery_ref:
            raise ServiceValidationError("fgcn_contribution_delivery_mismatch")
        if task.responsible_ref != row.provider_ref:
            raise ServiceValidationError("fgcn_contribution_provider_mismatch")
        await self._get(ServiceCaseRow, row.case_ref, "fgcn_service_case_not_found")
        return ServiceContribution(
            contribution_id=row.contribution_id,
            case_id=row.case_ref,
            task_id=row.task_ref,
            provider_ref=_required_text(row.provider_ref, "fgcn_contribution_provider_required"),
            role_key=_required_text(row.role, "fgcn_contribution_role_required"),
            delivery_id=delivery_ref,
            quality_state=quality_state,
            started_at=_required_utc(row.started_at, "fgcn_contribution_started_at_required"),
            completed_at=_required_utc(row.completed_at, "fgcn_contribution_completed_at_required"),
        )

    async def save_quality_review(self, review: TaskQualityReview) -> None:
        task = await self._get(ServiceTaskRow, review.task_id, "fgcn_service_task_not_found")
        if task.case_ref != review.case_id:
            raise ServiceForbiddenError("fgcn_quality_review_case_mismatch")
        case = await self._get(ServiceCaseRow, task.case_ref, "fgcn_service_case_not_found")
        reviewer = _human_actor(review.reviewer_ref, "fgcn_quality_reviewer_must_be_human")
        if task.responsible_ref == reviewer:
            raise ServiceForbiddenError("fgcn_quality_reviewer_must_differ_from_delivery_person")
        try:
            quality_state = TaskQualityState(review.quality_state)
        except ValueError as exc:
            raise ServiceValidationError("fgcn_quality_state_invalid") from exc
        if quality_state not in {
            TaskQualityState.PASSED,
            TaskQualityState.REWORK_REQUIRED,
        }:
            raise ServiceConflictError("fgcn_non_pass_quality_requires_rework_flow")
        delivery = _delivery_from_payload(task)
        if delivery is None:
            raise ServiceConflictError("fgcn_quality_review_requires_delivery")
        if review.locale != delivery.locale:
            raise ServiceConflictError("fgcn_quality_review_locale_mismatch")
        existing = await self._session.get(TaskQualityReviewRow, review.quality_review_id)
        if existing is not None:
            if (
                existing.task_id != review.task_id
                or existing.reviewer_ref != reviewer
                or existing.quality_state != quality_state.value
                or existing.review_note != review.review_note
                or _utc(existing.reviewed_at) != review.reviewed_at
            ):
                raise ServiceConflictError("fgcn_quality_review_id_reuse_mismatch")
            return
        previous = await self._session.scalar(
            sa.select(TaskQualityReviewRow).where(TaskQualityReviewRow.task_id == review.task_id)
        )
        if previous is not None:
            raise ServiceConflictError("fgcn_one_quality_review_per_task")
        if task.status != TaskStatus.DELIVERED.value:
            raise ServiceConflictError("fgcn_quality_review_requires_delivery")
        await self._stage(
            TaskQualityReviewRow(
                quality_review_id=review.quality_review_id,
                task_id=review.task_id,
                reviewer_ref=reviewer,
                quality_state=quality_state.value,
                review_note=review.review_note,
                reviewed_at=review.reviewed_at,
                created_at=review.reviewed_at,
            )
        )
        if quality_state is TaskQualityState.PASSED:
            task.status = TaskStatus.VERIFIED.value
            task.verified_at = review.reviewed_at
        else:
            task.status = TaskStatus.REWORK_REQUESTED.value
            task.verified_at = None
        task.updated_at = datetime.now(UTC)
        # `case` is intentionally loaded above even though no case mutation is
        # needed: a quality fact must never be accepted for a dangling task.
        _ = case

    async def save_contribution(self, contribution: ServiceContribution) -> None:
        task = await self._get(ServiceTaskRow, contribution.task_id, "fgcn_service_task_not_found")
        case = await self._get(ServiceCaseRow, task.case_ref, "fgcn_service_case_not_found")
        if contribution.case_id != case.case_id or contribution.task_id != task.task_id:
            raise ServiceForbiddenError("fgcn_contribution_scope_mismatch")
        if task.status != TaskStatus.VERIFIED.value:
            raise ServiceConflictError("fgcn_contribution_requires_verified_task")
        if task.responsible_ref != contribution.provider_ref:
            raise ServiceForbiddenError("fgcn_contribution_provider_mismatch")
        if task.role_key != contribution.role_key:
            raise ServiceForbiddenError("fgcn_contribution_role_mismatch")
        delivery = _delivery_from_payload(task)
        if delivery is None or delivery.delivery_id != contribution.delivery_id:
            raise ServiceForbiddenError("fgcn_contribution_delivery_mismatch")
        if delivery.assignee_ref != contribution.provider_ref:
            raise ServiceForbiddenError("fgcn_contribution_delivery_mismatch")
        if contribution.quality_state.value != ContributionQualityState.VERIFIED.value:
            raise ServiceValidationError("fgcn_contribution_requires_verified_quality")
        existing = await self._session.get(ServiceContributionRow, contribution.contribution_id)
        if existing is not None:
            if (
                existing.case_ref != contribution.case_id
                or existing.task_ref != contribution.task_id
                or existing.provider_ref != contribution.provider_ref
                or existing.role != contribution.role_key
                or existing.delivery_ref != contribution.delivery_id
                or _utc(existing.started_at) != contribution.started_at
                or _utc(existing.completed_at) != contribution.completed_at
                or existing.quality_state != contribution.quality_state.value
            ):
                raise ServiceConflictError("fgcn_contribution_id_reuse_mismatch")
            return
        previous = await self._session.scalar(
            sa.select(ServiceContributionRow).where(
                ServiceContributionRow.delivery_ref == contribution.delivery_id
            )
        )
        if previous is not None:
            raise ServiceConflictError("fgcn_one_contribution_per_delivery")
        await self._stage(
            ServiceContributionRow(
                contribution_id=contribution.contribution_id,
                case_ref=contribution.case_id,
                provider_ref=contribution.provider_ref,
                role=contribution.role_key,
                task_ref=contribution.task_id,
                delivery_ref=contribution.delivery_id,
                started_at=contribution.started_at,
                completed_at=contribution.completed_at,
                quality_state=contribution.quality_state.value,
            )
        )

    async def save_allocation_statement(self, statement: AllocationStatement) -> None:
        _human_actor(statement.triggered_by_actor_id)
        _allocation_line_shape_is_valid(statement)
        case = await self._get(ServiceCaseRow, statement.case_id, "fgcn_service_case_not_found")
        try:
            case_status = CaseStatus(case.status)
        except ValueError as exc:
            raise ServiceValidationError("fgcn_case_status_invalid") from exc
        if case_status is not CaseStatus.COMPLETED:
            raise ServiceConflictError("fgcn_allocation_requires_completed_case")
        blueprint = _blueprint_from_row(case)
        if (
            blueprint.policy_ref != statement.policy_ref
            or blueprint.policy_version != statement.policy_version
        ):
            raise ServiceConflictError("fgcn_allocation_policy_snapshot_mismatch")

        resolved_basis: dict[str, tuple[str | None, str | None]] = {}
        for line in statement.lines:
            if line.basis_type is AllocationBasisType.CASE:
                expected_identity = _fixed_allocation_identity(line.allocation_bucket, case.owner)
                if (
                    expected_identity is None
                    or (
                        line.beneficiary_ref,
                        line.beneficiary_kind,
                        line.role_key,
                    )
                    != expected_identity
                ):
                    raise ServiceValidationError("fgcn_fixed_allocation_beneficiary_invalid")
                resolved_basis[line.allocation_id] = (None, None)
                continue
            contribution = await self._get(
                ServiceContributionRow,
                line.basis_ref,
                "fgcn_allocation_contribution_not_found",
            )
            if (
                contribution.case_ref != statement.case_id
                or contribution.delivery_ref is None
                or contribution.quality_state != ContributionQualityState.VERIFIED.value
                or contribution.provider_ref != line.beneficiary_ref
                or contribution.role != line.role_key
            ):
                raise ServiceForbiddenError("fgcn_allocation_contribution_mismatch")
            task = await self._get(
                ServiceTaskRow, contribution.task_ref, "fgcn_allocation_task_not_found"
            )
            if task.status != TaskStatus.VERIFIED.value:
                raise ServiceConflictError("fgcn_allocation_requires_verified_task")
            delivery = _delivery_from_payload(task)
            if delivery is None or delivery.delivery_id != contribution.delivery_ref:
                raise ServiceValidationError("fgcn_allocation_delivery_mismatch")
            resolved_basis[line.allocation_id] = (contribution.contribution_id, task.task_id)

        existing = await self._session.scalar(
            sa.select(AllocationRunRow).where(AllocationRunRow.case_ref == statement.case_id)
        )
        if existing is not None and (
            existing.allocation_run_id != statement.allocation_run_id
            or existing.policy_ref != statement.policy_ref
            or existing.policy_version != statement.policy_version
            or existing.triggered_by_actor_ref != statement.triggered_by_actor_id
            or existing.total_units != statement.total_units
            or _utc(existing.created_at) != statement.created_at
        ):
            raise ServiceConflictError("fgcn_allocation_run_replay_mismatch")
        if existing is not None:
            existing_result = await self._session.execute(
                sa.select(AllocationLineRow).where(
                    AllocationLineRow.allocation_run_ref == statement.allocation_run_id
                )
            )
            existing_rows = {row.allocation_id: row for row in existing_result.scalars().all()}
            if set(existing_rows) != {line.allocation_id for line in statement.lines}:
                raise ServiceConflictError("fgcn_allocation_line_replay_mismatch")
            for line in statement.lines:
                contribution_ref, task_ref = resolved_basis[line.allocation_id]
                if not _allocation_row_matches(
                    existing_rows[line.allocation_id],
                    line,
                    contribution_ref=contribution_ref,
                    task_ref=task_ref,
                    allocation_run_id=statement.allocation_run_id,
                ):
                    raise ServiceConflictError("fgcn_allocation_line_replay_mismatch")
            if (
                case.shadow_allocation_finalized_at is None
                or _utc(case.shadow_allocation_finalized_at) != statement.created_at
                or case.shadow_allocation_policy_ref != statement.policy_ref
                or case.shadow_allocation_policy_version != statement.policy_version
            ):
                raise ServiceConflictError("fgcn_shadow_allocation_marker_mismatch")
            return

        run_with_same_id = await self._session.get(AllocationRunRow, statement.allocation_run_id)
        if run_with_same_id is not None:
            raise ServiceConflictError("fgcn_allocation_run_id_already_exists")
        if case.shadow_allocation_finalized_at is not None:
            raise ServiceConflictError("fgcn_shadow_allocation_already_finalized")
        await self._stage(
            AllocationRunRow(
                allocation_run_id=statement.allocation_run_id,
                case_ref=statement.case_id,
                policy_ref=statement.policy_ref,
                policy_version=statement.policy_version,
                triggered_by_actor_ref=statement.triggered_by_actor_id,
                total_units=statement.total_units,
                created_at=statement.created_at,
            )
        )
        case.shadow_allocation_finalized_at = statement.created_at
        case.shadow_allocation_policy_ref = statement.policy_ref
        case.shadow_allocation_policy_version = statement.policy_version
        await self._session.flush()

        for line in statement.lines:
            contribution_ref, task_ref = resolved_basis[line.allocation_id]
            existing_line = await self._session.get(AllocationLineRow, line.allocation_id)
            if existing_line is not None:
                raise ServiceConflictError("fgcn_allocation_line_id_already_exists")
            await self._stage(
                AllocationLineRow(
                    allocation_id=line.allocation_id,
                    contribution_ref=contribution_ref,
                    case_ref=line.case_id,
                    task_ref=task_ref,
                    allocation_bucket=line.allocation_bucket.value,
                    units=line.units,
                    release_state=line.release_state.value,
                    reason="shadow allocation basis",
                    released_at=None,
                    created_at=statement.created_at,
                    beneficiary_ref=line.beneficiary_ref,
                    beneficiary_kind=line.beneficiary_kind,
                    role_key=line.role_key,
                    policy_ref=line.policy_ref,
                    policy_version=line.policy_version,
                    basis_type=line.basis_type.value,
                    basis_ref=line.basis_ref,
                    allocation_run_ref=statement.allocation_run_id,
                )
            )

    async def load_allocation_statement(self, case_id: str) -> AllocationStatement:
        run = await self._session.scalar(
            sa.select(AllocationRunRow).where(AllocationRunRow.case_ref == case_id)
        )
        if run is None:
            raise ServiceNotFoundError("fgcn_allocation_statement_not_found")
        case = await self._get(ServiceCaseRow, case_id, "fgcn_service_case_not_found")
        try:
            case_status = CaseStatus(case.status)
        except ValueError as exc:
            raise ServiceValidationError("fgcn_case_status_invalid") from exc
        if case_status is not CaseStatus.COMPLETED:
            raise ServiceValidationError("fgcn_allocation_case_not_completed")
        if (
            case.shadow_allocation_finalized_at is None
            or _utc(case.shadow_allocation_finalized_at) != _utc(run.created_at)
            or case.shadow_allocation_policy_ref != run.policy_ref
            or case.shadow_allocation_policy_version != run.policy_version
        ):
            raise ServiceValidationError("fgcn_shadow_allocation_marker_mismatch")
        result = await self._session.execute(
            sa.select(AllocationLineRow)
            .where(AllocationLineRow.allocation_run_ref == run.allocation_run_id)
            .order_by(AllocationLineRow.allocation_id)
        )
        persisted_rows = result.scalars().all()
        lines: list[AllocationLine] = []
        try:
            for row in persisted_rows:
                lines.append(
                    AllocationLine(
                        allocation_id=row.allocation_id,
                        allocation_run_id=run.allocation_run_id,
                        case_id=row.case_ref,
                        allocation_bucket=AllocationBucket(row.allocation_bucket),
                        units=row.units,
                        beneficiary_ref=_required_text(
                            row.beneficiary_ref, "fgcn_allocation_beneficiary_required"
                        ),
                        beneficiary_kind=_required_text(
                            row.beneficiary_kind, "fgcn_allocation_beneficiary_kind_required"
                        ),
                        role_key=_required_text(row.role_key, "fgcn_allocation_role_required"),
                        policy_ref=_required_text(
                            row.policy_ref, "fgcn_allocation_policy_required"
                        ),
                        policy_version=row.policy_version,
                        basis_type=AllocationBasisType(row.basis_type),
                        basis_ref=_required_text(row.basis_ref, "fgcn_allocation_basis_required"),
                        release_state=AllocationReleaseState(row.release_state),
                    )
                )
        except (TypeError, ValueError) as exc:
            raise ServiceValidationError("fgcn_allocation_persisted_shape_invalid") from exc
        statement = AllocationStatement(
            allocation_run_id=run.allocation_run_id,
            case_id=run.case_ref,
            policy_ref=run.policy_ref,
            policy_version=run.policy_version,
            triggered_by_actor_id=run.triggered_by_actor_ref,
            total_units=run.total_units,
            lines=tuple(lines),
            created_at=_required_utc(run.created_at, "fgcn_allocation_created_at_required"),
        )
        try:
            _allocation_line_shape_is_valid(statement)
        except ServiceValidationError:
            raise
        for row, line in zip(persisted_rows, statement.lines, strict=True):
            contribution_ref = None
            task_ref = None
            if line.basis_type is not AllocationBasisType.CASE:
                contribution = await self._get(
                    ServiceContributionRow,
                    line.basis_ref,
                    "fgcn_allocation_contribution_not_found",
                )
                contribution_ref = contribution.contribution_id
                task_ref = contribution.task_ref
            if not _allocation_row_matches(
                row,
                line,
                contribution_ref=contribution_ref,
                task_ref=task_ref,
                allocation_run_id=run.allocation_run_id,
            ):
                raise ServiceValidationError("fgcn_allocation_persisted_row_mismatch")
        return statement


__all__ = [
    "AllocationLineRow",
    "AllocationRunRow",
    "FGCNBase",
    "IdempotencyKeyRow",
    "ServiceCaseRow",
    "ServiceContributionRow",
    "ServiceTaskRow",
    "SqlAlchemyFGCNRepository",
    "TaskAssignmentRow",
    "TaskQualityReviewRow",
]
