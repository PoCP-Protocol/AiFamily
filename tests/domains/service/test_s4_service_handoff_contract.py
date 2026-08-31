"""S4 contract skeleton: confirmed family need -> controlled human service.

This file deliberately does not create a second ServiceCase implementation.
The small adapter below describes the input receipt that Team 1 must eventually
publish and delegates every service mutation to the existing canonical Service
commands.  It can be deleted when the accepted cross-domain receipt contract is
available.

Feedback and Remedy are intentionally outside this first skeleton: the current
``ServiceRecord.service_quality_rating`` rates a delivered provider session; it
is not a family feedback aggregate or a remedy decision.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.domains.service.application import commands
from backend.domains.service.domain.errors import ServiceConflictError, ServiceForbiddenError

from .helpers import CHILD, CONSENT_REF, FAMILY, granted, make_ctx, seed_supply

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class ConfirmedNeedReceipt:
    """Temporary consumer-side shape; not a new canonical business object."""

    receipt_ref: str
    tenant_id: str
    family_id: str
    decision: str


async def _request_human_help(
    repo,
    consent,
    recorder,
    *,
    receipt: ConfirmedNeedReceipt,
    offering_id: str,
    slot_id: str,
):
    """Fail closed before delegating to the canonical booking command."""

    ctx = make_ctx(idempotency_key=f"s4:{receipt.receipt_ref}")
    if receipt.tenant_id != ctx.tenant_id or receipt.family_id != ctx.family_id:
        raise ServiceForbiddenError("confirmed_need_scope_mismatch")
    if receipt.decision != "HUMAN_HELP_CONFIRMED":
        raise ServiceForbiddenError("human_help_not_confirmed")

    return await commands.submit_booking_request(
        repo,
        ctx,
        recorder,
        consent,
        service_offering_id=offering_id,
        availability_slot_id=slot_id,
        booking_ref=receipt.receipt_ref,
        source_page_id="UI-21",
        subject_person_id=CHILD,
        consent_ref=CONSENT_REF,
    )


def _confirmed_receipt(**overrides) -> ConfirmedNeedReceipt:
    values = {
        "receipt_ref": "need-confirmation-001",
        "tenant_id": "tenant-001",
        "family_id": FAMILY,
        "decision": "HUMAN_HELP_CONFIRMED",
    }
    values.update(overrides)
    return ConfirmedNeedReceipt(**values)


async def test_confirmed_need_enters_canonical_booking_and_delivery(repo, consent, recorder):
    """A guardian-confirmed need can produce one controlled delivery receipt."""

    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)

    booking = await _request_human_help(
        repo,
        consent,
        recorder,
        receipt=_confirmed_receipt(),
        offering_id=offering.service_offering_id,
        slot_id=slot.availability_slot_id,
    )
    assert booking.status == "REQUESTED"
    assert booking.external_effect is False

    confirmed, record = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    assert confirmed.status == "CONFIRMED"
    assert record.status == "PENDING"

    delivered = await commands.fulfil_service_record(
        repo,
        make_ctx(),
        recorder,
        booking_service_record_id=record.booking_service_record_id,
    )
    assert delivered.status == "COMPLETED"
    assert delivered.service_quality_rating is None


@pytest.mark.parametrize(
    ("receipt", "error_code"),
    [
        (_confirmed_receipt(decision="SELF_HELP_CONTINUES"), "human_help_not_confirmed"),
        (_confirmed_receipt(family_id="family-other"), "confirmed_need_scope_mismatch"),
        (_confirmed_receipt(tenant_id="tenant-other"), "confirmed_need_scope_mismatch"),
    ],
)
async def test_unconfirmed_or_out_of_scope_need_creates_no_booking(
    repo, consent, recorder, receipt, error_code
):
    """No implicit upsell and no cross-family/tenant handoff."""

    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)

    with pytest.raises(ServiceForbiddenError, match=error_code):
        await _request_human_help(
            repo,
            consent,
            recorder,
            receipt=receipt,
            offering_id=offering.service_offering_id,
            slot_id=slot.availability_slot_id,
        )

    assert await repo.list_bookings("tenant-001", FAMILY) == []
    unchanged = await repo.load_slot(slot.availability_slot_id)
    assert (unchanged.reserved_count, unchanged.status) == (0, "AVAILABLE")


async def test_cancelled_handoff_releases_capacity_and_cannot_be_delivered(
    repo, consent, recorder
):
    """Cancellation is recovery, not delivery, feedback, contribution or cash."""

    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _request_human_help(
        repo,
        consent,
        recorder,
        receipt=_confirmed_receipt(),
        offering_id=offering.service_offering_id,
        slot_id=slot.availability_slot_id,
    )
    _confirmed, record = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )

    cancelled = await commands.cancel_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    assert cancelled.status == "CANCELLED"
    assert (await repo.load_slot(slot.availability_slot_id)).status == "AVAILABLE"

    cancelled_record = await repo.load_service_record(record.booking_service_record_id)
    assert cancelled_record.status == "CANCELLED"
    with pytest.raises(ServiceConflictError, match="record_not_completable:CANCELLED"):
        await commands.fulfil_service_record(
            repo,
            make_ctx(),
            recorder,
            booking_service_record_id=record.booking_service_record_id,
        )
