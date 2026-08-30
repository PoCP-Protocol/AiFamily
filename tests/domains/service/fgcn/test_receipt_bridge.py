"""Positive and adversarial tests for the read-only ServiceRecord bridge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.domains.service.domain.entities import BookingRequest, ServiceRecord
from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
)
from backend.domains.service.fgcn.contracts import (
    BlueprintSnapshot,
    CaseStatus,
    GateServiceScope,
    ServiceCase,
    ServiceTask,
    TaskStatus,
)
from backend.domains.service.fgcn.receipt_bridge import (
    build_service_delivery_from_record,
)
from backend.domains.service.fgcn.scenario import (
    S01_OUTCOME_OBSERVATION,
    S01_SCENARIO,
    S01_TASK_ACCEPTANCE_CRITERION,
)

NOW = datetime(2026, 8, 30, 18, tzinfo=UTC)
TENANT = "tenant-receipt"
FAMILY = "family-receipt"
CHILD = "child-receipt"
CASE = "case-receipt"
TASK = "task-receipt"
BOOKING = "booking-receipt"
RECORD = "record-receipt"
PROVIDER = "provider-receipt"


def _scope(*, family_id: str = FAMILY) -> GateServiceScope:
    return GateServiceScope(
        tenant_id=TENANT,
        family_id=family_id,
        subject_person_id=CHILD,
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-receipt-bridge",
    )


def _case(*, status: CaseStatus = CaseStatus.OPEN) -> ServiceCase:
    return ServiceCase(
        case_id=CASE,
        scope=_scope(),
        intent_ref="intent-receipt",
        plan_ref="plan-receipt",
        owner_id="steward-receipt",
        blueprint=BlueprintSnapshot(
            blueprint_ref="blueprint-receipt",
            version=1,
            status="PUBLISHED",
            policy_ref="shadow-policy.v1",
            policy_version=1,
            checksum="checksum-receipt",
            task_template_keys=("GUIDANCE_DELIVERY",),
            scenario=S01_SCENARIO,
        ),
        status=status,
        opened_at=NOW,
        closed_at=NOW + timedelta(hours=4) if status is CaseStatus.COMPLETED else None,
    )


def _task(*, status: TaskStatus = TaskStatus.ACCEPTED) -> ServiceTask:
    return ServiceTask(
        task_id=TASK,
        case_id=CASE,
        blueprint_ref="blueprint-receipt",
        blueprint_version=1,
        task_key="GUIDANCE_DELIVERY",
        title="S-01 guidance delivery",
        description="Deliver the approved calm-start support.",
        role_key="DELIVERY_RESOURCE",
        acceptance_criteria=(S01_TASK_ACCEPTANCE_CRITERION,),
        task_weight=Decimal("1"),
        status=status,
        responsible_ref=PROVIDER if status is not TaskStatus.PENDING else None,
        created_at=NOW,
    )


def _booking(
    *,
    status: str = "CONFIRMED",
    family_id: str = FAMILY,
    provider_ref: str | None = PROVIDER,
    environment: str = "TEST",
) -> BookingRequest:
    snapshot = {} if provider_ref is None else {"provider_ref": provider_ref}
    return BookingRequest(
        booking_request_id=BOOKING,
        tenant_id=TENANT,
        family_id=family_id,
        actor_person_id="guardian-receipt",
        booking_ref="BOOK-RECEIPT",
        service_offering_id="offering-receipt",
        availability_slot_id="slot-receipt",
        source_page_id="UI-21",
        consent_ref="consent-ref-1",
        status=status,
        service_snapshot=snapshot,
        environment=environment,
        correlation_id="corr-receipt-bridge",
        idempotency_key="booking-key-receipt",
        created_at=NOW.replace(tzinfo=None),
        created_by="guardian-receipt",
        updated_at=NOW.replace(tzinfo=None),
        updated_by="guardian-receipt",
    )


def _record(
    *,
    status: str = "COMPLETED",
    family_id: str = FAMILY,
    updated_by: str = PROVIDER,
    environment: str = "TEST",
) -> ServiceRecord:
    completed_at = (NOW + timedelta(hours=2)).replace(tzinfo=None)
    return ServiceRecord(
        booking_service_record_id=RECORD,
        tenant_id=TENANT,
        family_id=family_id,
        source_booking_request_id=BOOKING,
        status=status,
        environment=environment,
        created_at=NOW.replace(tzinfo=None),
        created_by="guardian-receipt",
        updated_at=completed_at,
        updated_by=updated_by,
    )


class _Reader:
    def __init__(self, record: ServiceRecord, booking: BookingRequest) -> None:
        self.record = record
        self.booking = booking
        self.writes = 0

    async def load_service_record(self, booking_service_record_id: str) -> ServiceRecord:
        assert booking_service_record_id == RECORD
        return self.record

    async def load_booking(self, booking_request_id: str) -> BookingRequest:
        assert booking_request_id == BOOKING
        return self.booking


@pytest.mark.asyncio
async def test_completed_canonical_record_builds_stable_delivery_candidate() -> None:
    candidate = await build_service_delivery_from_record(
        _Reader(_record(), _booking()),
        case=_case(),
        task=_task(),
        service_record_id=RECORD,
        scope=_scope(),
        outcome_observation=S01_OUTCOME_OBSERVATION,
    )

    assert candidate.delivery_id == "service-record:record-receipt"
    assert candidate.evidence_ref == candidate.delivery_id
    assert candidate.assignee_ref == PROVIDER
    assert candidate.delivered_at == NOW + timedelta(hours=2)


@pytest.mark.asyncio
async def test_bridge_is_read_only_and_does_not_turn_provider_rating_into_quality() -> None:
    record = _record()
    record = record.model_copy(update={"service_quality_rating": "POSITIVE"})
    reader = _Reader(record, _booking())

    candidate = await build_service_delivery_from_record(
        reader,
        case=_case(),
        task=_task(),
        service_record_id=RECORD,
        scope=_scope(),
        outcome_observation=S01_OUTCOME_OBSERVATION,
    )

    assert candidate.outcome_markers is not None
    assert not hasattr(candidate, "service_quality_rating")
    assert reader.writes == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record_kwargs", "booking_kwargs", "error_type", "error_code"),
    (
        (
            {"status": "PENDING"},
            {},
            ServiceConflictError,
            "fgcn_receipt_service_record_not_completed",
        ),
        (
            {"family_id": "foreign-family"},
            {},
            ServiceForbiddenError,
            "fgcn_receipt_booking_scope_mismatch",
        ),
        ({}, {"status": "REQUESTED"}, ServiceConflictError, "fgcn_receipt_booking_not_confirmed"),
        (
            {},
            {"provider_ref": "other-provider"},
            ServiceForbiddenError,
            "fgcn_receipt_provider_task_mismatch",
        ),
        (
            {},
            {"provider_ref": None},
            ServiceForbiddenError,
            "fgcn_receipt_provider_binding_missing",
        ),
        ({}, {"environment": "DEV"}, ServiceConflictError, "fgcn_receipt_environment_mismatch"),
        (
            {"updated_by": "ai:provider"},
            {},
            ServiceForbiddenError,
            "fgcn_receipt_requires_human_completion",
        ),
    ),
)
async def test_bridge_rejects_unproven_or_mismatched_receipts(
    record_kwargs: dict,
    booking_kwargs: dict,
    error_type: type[Exception],
    error_code: str,
) -> None:
    with pytest.raises(error_type, match=error_code):
        await build_service_delivery_from_record(
            _Reader(_record(**record_kwargs), _booking(**booking_kwargs)),
            case=_case(),
            task=_task(),
            service_record_id=RECORD,
            scope=_scope(),
            outcome_observation=S01_OUTCOME_OBSERVATION,
        )


@pytest.mark.asyncio
async def test_bridge_rejects_foreign_fgcn_scope_and_terminal_task() -> None:
    with pytest.raises(ServiceForbiddenError, match="fgcn_family_scope_violation"):
        await build_service_delivery_from_record(
            _Reader(_record(), _booking()),
            case=_case(),
            task=_task(),
            service_record_id=RECORD,
            scope=_scope(family_id="foreign-family"),
            outcome_observation=S01_OUTCOME_OBSERVATION,
        )

    with pytest.raises(ServiceConflictError, match="fgcn_receipt_case_is_terminal"):
        await build_service_delivery_from_record(
            _Reader(_record(), _booking()),
            case=_case(status=CaseStatus.COMPLETED),
            task=_task(),
            service_record_id=RECORD,
            scope=_scope(),
            outcome_observation=S01_OUTCOME_OBSERVATION,
        )
