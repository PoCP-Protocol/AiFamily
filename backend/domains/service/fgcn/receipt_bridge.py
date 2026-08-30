"""Read-only bridge from the canonical booking receipt into FGCN delivery.

The booking domain owns ``ServiceRecord`` and ``BookingRequest``.  FGCN must
consume those facts rather than create a second booking or service-record
writer.  This module is deliberately an anti-corruption seam: it only reads
the canonical records and returns an immutable ``ServiceDelivery`` candidate.

The candidate is still subject to the existing FGCN delivery command, human
quality review, and contribution gate.  In particular, ``ServiceRecord``'s
provider-session rating is not treated as ``FamilyFeedback`` or as a
``QualityDecision``.  A human must supply the S-01 outcome observation and the
existing FGCN quality reviewer must verify it later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from backend.domains.service.domain.entities import BookingRequest, ServiceRecord
from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)
from backend.platform.audit import AuditRecorder

from .contracts import (
    CaseStatus,
    GateServiceScope,
    ServiceCase,
    ServiceDelivery,
    ServiceTask,
    TaskStatus,
)
from .delivery_application import FGCNDeliveryRepository, submit_service_delivery


class CanonicalServiceRecordReader(Protocol):
    """The read-only portion of the canonical Service repository."""

    async def load_service_record(self, booking_service_record_id: str) -> ServiceRecord: ...

    async def load_booking(self, booking_request_id: str) -> BookingRequest: ...


def _human_actor(actor_id: object, code: str) -> str:
    if not isinstance(actor_id, str) or not actor_id.strip():
        raise ServiceValidationError(code)
    actor = actor_id.strip()
    if actor.upper() in {"AI", "SYSTEM"} or actor.lower().startswith(("ai:", "system:")):
        raise ServiceForbiddenError("fgcn_receipt_requires_human_completion")
    return actor


def _assert_scope(case: ServiceCase, scope: GateServiceScope) -> None:
    if not isinstance(scope, GateServiceScope):
        raise ServiceValidationError("fgcn_receipt_scope_invalid")
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


def _aware_utc(value: object) -> datetime:
    """Normalize the booking adapter's SQLite-naive timestamp at the seam."""

    if not isinstance(value, datetime):
        raise ServiceValidationError("fgcn_receipt_completed_at_required")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _snapshot_provider_ref(booking: BookingRequest) -> str:
    snapshot = booking.service_snapshot
    if not isinstance(snapshot, dict):
        raise ServiceValidationError("fgcn_receipt_booking_snapshot_invalid")
    provider_ref = snapshot.get("provider_ref")
    if not isinstance(provider_ref, str) or not provider_ref.strip():
        raise ServiceForbiddenError("fgcn_receipt_provider_binding_missing")
    return provider_ref.strip()


async def build_service_delivery_from_record(
    reader: CanonicalServiceRecordReader,
    *,
    case: ServiceCase,
    task: ServiceTask,
    service_record_id: str,
    scope: GateServiceScope,
    outcome_observation: str,
) -> ServiceDelivery:
    """Build a delivery candidate from one canonical completed ServiceRecord.

    This function performs no mutation.  The returned object can be passed to
    the existing FGCN delivery application command, which remains responsible
    for the durable idempotency claim, Audit/Outbox transaction, and task/case
    transition.  The record's stable identifier becomes both the delivery
    identity and evidence reference, preventing a second FGCN receipt for the
    same canonical session.
    """

    _assert_scope(case, scope)
    if task.case_id != case.case_id:
        raise ServiceForbiddenError("fgcn_receipt_task_case_mismatch")
    if task.responsible_ref is None:
        raise ServiceValidationError("fgcn_receipt_provider_binding_missing")

    record = await reader.load_service_record(service_record_id)
    if not isinstance(record, ServiceRecord):
        raise ServiceValidationError("fgcn_receipt_service_record_invalid")
    if record.booking_service_record_id != service_record_id:
        raise ServiceConflictError("fgcn_receipt_service_record_identity_mismatch")
    if record.status != "COMPLETED":
        raise ServiceConflictError("fgcn_receipt_service_record_not_completed")
    _human_actor(record.updated_by, "fgcn_receipt_completion_actor_required")
    if record.external_effect:
        raise ServiceForbiddenError("fgcn_receipt_external_effect_not_allowed")
    if record.tenant_id != scope.tenant_id or record.family_id != scope.family_id:
        raise ServiceForbiddenError("fgcn_receipt_booking_scope_mismatch")

    booking = await reader.load_booking(record.source_booking_request_id)
    if not isinstance(booking, BookingRequest):
        raise ServiceValidationError("fgcn_receipt_booking_invalid")
    if booking.booking_request_id != record.source_booking_request_id:
        raise ServiceConflictError("fgcn_receipt_booking_identity_mismatch")
    if booking.status != "CONFIRMED":
        raise ServiceConflictError("fgcn_receipt_booking_not_confirmed")
    if booking.tenant_id != scope.tenant_id or booking.family_id != scope.family_id:
        raise ServiceForbiddenError("fgcn_receipt_booking_scope_mismatch")
    if booking.external_effect:
        raise ServiceForbiddenError("fgcn_receipt_external_effect_not_allowed")
    if booking.environment != record.environment:
        raise ServiceConflictError("fgcn_receipt_environment_mismatch")
    if not booking.consent_ref.strip():
        raise ServiceForbiddenError("fgcn_receipt_consent_provenance_missing")

    provider_ref = _snapshot_provider_ref(booking)
    if provider_ref != task.responsible_ref:
        raise ServiceForbiddenError("fgcn_receipt_provider_task_mismatch")

    # The ServiceRecord is the canonical session receipt.  It is intentionally
    # not treated as FamilyFeedback/QualityDecision; the human S-01 outcome
    # evidence and the separate FGCN reviewer gate remain mandatory.
    receipt_ref = f"service-record:{record.booking_service_record_id}"
    exact_replay = (
        task.status in {TaskStatus.DELIVERED, TaskStatus.VERIFIED, TaskStatus.CLOSED}
        and task.deliverable_ref == receipt_ref
    )
    if case.status in {CaseStatus.COMPLETED, CaseStatus.CANCELLED} and not exact_replay:
        raise ServiceConflictError("fgcn_receipt_case_is_terminal")
    if task.status is not TaskStatus.ACCEPTED and not exact_replay:
        raise ServiceConflictError("fgcn_receipt_requires_accepted_task")
    return ServiceDelivery(
        delivery_id=receipt_ref,
        case_id=case.case_id,
        task_id=task.task_id,
        assignee_ref=task.responsible_ref,
        evidence_ref=receipt_ref,
        outcome_observation=outcome_observation,
        delivered_at=_aware_utc(record.updated_at),
        locale=task.locale,
    )


async def submit_service_delivery_from_record(
    reader: CanonicalServiceRecordReader,
    repository: FGCNDeliveryRepository,
    *,
    case: ServiceCase,
    task: ServiceTask,
    service_record_id: str,
    scope: GateServiceScope,
    outcome_observation: str,
    actor_id: str,
    recorder: AuditRecorder,
    idempotency_key: str | None = None,
) -> ServiceDelivery:
    """Submit one canonical service receipt through the existing FGCN writer.

    The canonical service repository remains read-only to this seam.  The
    actual FGCN mutation is delegated to ``submit_service_delivery``, which
    owns the durable idempotency claim, task transition, Audit/Outbox
    transaction, and commit.  The authenticated actor must be the admitted
    task provider; an operator or AI cannot silently impersonate delivery.
    """

    candidate = await build_service_delivery_from_record(
        reader,
        case=case,
        task=task,
        service_record_id=service_record_id,
        scope=scope,
        outcome_observation=outcome_observation,
    )
    if not isinstance(actor_id, str) or actor_id.strip() != candidate.assignee_ref:
        raise ServiceForbiddenError("fgcn_receipt_delivery_actor_mismatch")
    return await submit_service_delivery(
        repository,
        task_id=candidate.task_id,
        delivery_id=candidate.delivery_id,
        evidence_ref=candidate.evidence_ref,
        outcome_observation=candidate.outcome_observation,
        actor_id=actor_id,
        scope=scope,
        recorder=recorder,
        delivered_at=candidate.delivered_at,
        idempotency_key=idempotency_key,
    )


__all__ = [
    "CanonicalServiceRecordReader",
    "build_service_delivery_from_record",
    "submit_service_delivery_from_record",
]
