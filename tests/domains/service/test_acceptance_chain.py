"""Acceptance chain for the service booking sub-chain.

The happy path is the one the migration plan called "已验证的付费主力闭环":

    供给登记 → 时段开放 → 家长预约 → 确认 → 履约

Every test runs against all three repositories via the `repo` fixture, so a
result that only holds for the in-memory dict is not reported as green.

The refusal tests matter more than the happy path. Each one is a rule somebody
could remove without breaking the chain, and each names the constitution or
compliance clause it protects.
"""

from __future__ import annotations

import pytest

from backend.domains.service.application import commands
from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)

from .helpers import (
    CHILD,
    CONSENT_REF,
    FAMILY,
    OTHER_FAMILY,
    granted,
    make_ctx,
    seed_supply,
)

pytestmark = pytest.mark.asyncio


async def _book(repo, consent, recorder, *, offering, slot, ctx=None, **overrides):
    kwargs = {
        "service_offering_id": offering.service_offering_id,
        "availability_slot_id": slot.availability_slot_id,
        "booking_ref": "BOOK-001",
        "source_page_id": "UI-21",
        "subject_person_id": CHILD,
        "consent_ref": CONSENT_REF,
    }
    kwargs.update(overrides)
    return await commands.submit_booking_request(
        repo, ctx or make_ctx(), recorder, consent, **kwargs
    )


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


async def test_full_chain_supply_to_fulfilment(repo, consent, recorder) -> None:
    """供给登记 → 时段开放 → 家长预约 → 确认 → 履约."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)

    booking = await _book(repo, consent, recorder, offering=offering, slot=slot)
    assert booking.status == "REQUESTED"
    # The intent is DEV/TEST-only supply and reaches nothing outside this system.
    assert booking.external_effect is False
    assert booking.source_system == "TEST_FIXTURE"
    # The snapshot preserves what was booked even if the offering is re-versioned.
    assert booking.service_snapshot["service_offering_ref"] == "PARENT_COACHING_60"

    # Capacity-1 slot is now fully reserved.
    reserved = await repo.load_slot(slot.availability_slot_id)
    assert (reserved.reserved_count, reserved.status) == (1, "RESERVED")

    confirmed, record = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    assert confirmed.status == "CONFIRMED"
    assert record.status == "PENDING"
    assert record.source_booking_request_id == booking.booking_request_id
    assert record.source_system == "TEST_NOOP_ADAPTER"

    completed = await commands.fulfil_service_record(
        repo,
        make_ctx(),
        recorder,
        booking_service_record_id=record.booking_service_record_id,
        quality_rating="POSITIVE",
    )
    assert completed.status == "COMPLETED"
    # Rates the provider's session, never the family — see ServiceRecord docstring.
    assert completed.service_quality_rating == "POSITIVE"


async def test_every_state_change_records_an_audit_event(repo, consent, recorder) -> None:
    """R6 — 任何对权威业务状态的写入必须产生 AuditEvent.

    Asserts the specific action names rather than only a count: a count passes
    if one command records twice and another records nothing.
    """
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _book(repo, consent, recorder, offering=offering, slot=slot)
    _confirmed, record = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    await commands.fulfil_service_record(
        repo,
        make_ctx(),
        recorder,
        booking_service_record_id=record.booking_service_record_id,
    )

    actions = [e.action for e in recorder.all_events()]
    for expected in (
        "register_service_provider",
        "publish_service_offering",
        "open_availability_slot",
        "submit_booking_request",
        "reserve_availability_slot",
        "confirm_booking_request",
        "open_service_record",
        "fulfil_service_record",
    ):
        assert expected in actions, f"no AuditEvent for {expected}"

    # R6 names before *and* after. A transition that records only the
    # destination cannot answer whether a step was skipped.
    confirm_event = next(e for e in recorder.all_events() if e.action == "confirm_booking_request")
    assert confirm_event.before == {"status": "REQUESTED"}
    assert confirm_event.after == {"status": "CONFIRMED"}


async def test_cancellation_returns_the_slot_capacity(repo, consent, recorder) -> None:
    """A cancelled booking that keeps its reservation makes inventory
    permanently wrong and nothing in the chain would notice."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _book(repo, consent, recorder, offering=offering, slot=slot)
    await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )

    cancelled = await commands.cancel_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    assert cancelled.status == "CANCELLED"
    assert cancelled.cancelled_at is not None

    freed = await repo.load_slot(slot.availability_slot_id)
    assert (freed.reserved_count, freed.status) == (0, "AVAILABLE")

    # The delivery receipt is cancelled with it — a CONFIRMED-then-cancelled
    # booking must not leave a PENDING obligation behind.
    record = await repo.find_service_record_for_booking(
        cancelled.tenant_id, cancelled.family_id, booking.booking_request_id
    )
    assert record is not None
    assert record.status == "CANCELLED"

    # And the freed capacity is genuinely re-bookable.
    again = await _book(
        repo, consent, recorder, offering=offering, slot=slot, booking_ref="BOOK-002"
    )
    assert again.status == "REQUESTED"


async def test_multi_capacity_slot_stays_available_until_full(repo, consent, recorder) -> None:
    """`RESERVED` means "no capacity left", not "somebody booked it".

    A salon host takes several families in one window, so a capacity-2 slot with
    one booking must still be offered to the second family.
    """
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, capacity=2, recorder=recorder)

    await _book(repo, consent, recorder, offering=offering, slot=slot, booking_ref="BOOK-A")
    after_first = await repo.load_slot(slot.availability_slot_id)
    assert (after_first.reserved_count, after_first.status) == (1, "AVAILABLE")

    await _book(repo, consent, recorder, offering=offering, slot=slot, booking_ref="BOOK-B")
    after_second = await repo.load_slot(slot.availability_slot_id)
    assert (after_second.reserved_count, after_second.status) == (2, "RESERVED")


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


async def test_booking_without_consent_is_refused(repo, consent, recorder) -> None:
    """ConsentGate — the gap `assessment` still has, closed here.

    The subject of a booking may be a minor, so booking is sensitive-information
    processing (COMPLIANCE_HARD_CONSTRAINTS §1). No active SERVICE grant is a
    refusal, not a warning.
    """
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    # `consent` fixture is intentionally empty.
    with pytest.raises(ServiceForbiddenError) as exc:
        await _book(repo, consent, recorder, offering=offering, slot=slot)
    assert exc.value.code.startswith("consent_required:service:")

    # And the refusal left no trace: no booking row, and the slot capacity was
    # never touched. A refusal that half-applies is worse than no gate.
    untouched = await repo.load_slot(slot.availability_slot_id)
    assert (untouched.reserved_count, untouched.status) == (0, "AVAILABLE")
    assert await repo.list_bookings(untouched.tenant_id, FAMILY) == []


async def test_withdrawn_consent_takes_effect_immediately(repo, consent, recorder) -> None:
    """`ConsentGate` holds no cache by construction; this proves the port does
    not reintroduce one. A booking allowed a moment ago must be refused the
    instant the grant is withdrawn."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, capacity=2, recorder=recorder)
    await _book(repo, consent, recorder, offering=offering, slot=slot, booking_ref="BOOK-A")

    consent.withdraw(CONSENT_REF)
    with pytest.raises(ServiceForbiddenError):
        await _book(repo, consent, recorder, offering=offering, slot=slot, booking_ref="BOOK-B")


async def test_consent_for_another_purpose_does_not_permit_booking(repo, consent, recorder) -> None:
    """A grant is scoped to exactly one purpose — ASSESSMENT consent is not
    SERVICE consent. Widening scope is intentionally not representable."""
    from backend.domains.service.domain.entities import utcnow
    from backend.platform.consent.models import (
        ConsentGrant,
        ConsentPurpose,
        ConsentStatus,
        GuardianRelation,
        SubjectAge,
    )

    from .helpers import GUARDIAN

    consent.add(
        ConsentGrant(
            consent_id="consent-assessment-001",
            subject_person_id=CHILD,
            guardian_person_id=GUARDIAN,
            purpose=ConsentPurpose.ASSESSMENT,
            status=ConsentStatus.GRANTED,
            granted_at=utcnow(),
            subject_age=SubjectAge(years=9),
            guardian_relation=GuardianRelation.GUARDIAN,
        )
    )
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    with pytest.raises(ServiceForbiddenError):
        await _book(repo, consent, recorder, offering=offering, slot=slot)


async def test_consent_for_another_subject_does_not_permit_booking(repo, consent, recorder) -> None:
    """Consent belongs to a person, not to a family. A grant for one sibling
    does not cover the other."""
    consent.add(granted(subject_person_id="person-child-002"))
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    with pytest.raises(ServiceForbiddenError):
        await _book(repo, consent, recorder, offering=offering, slot=slot)


async def test_cross_family_booking_access_is_refused(repo, consent, recorder) -> None:
    """Scope always comes from the authenticated context. Reaching a booking
    that belongs to another family is a refusal, not a 404 — the caller is
    authenticated, it is just not theirs."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _book(repo, consent, recorder, offering=offering, slot=slot)

    intruder = make_ctx(family_id=OTHER_FAMILY)
    with pytest.raises(ServiceForbiddenError) as exc:
        await commands.confirm_booking_request(
            repo, intruder, recorder, booking_request_id=booking.booking_request_id
        )
    assert exc.value.code == "family_scope_violation"


async def test_occupied_slot_is_refused(repo, consent, recorder) -> None:
    """时段已占用 — a capacity-1 slot takes exactly one booking."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    await _book(repo, consent, recorder, offering=offering, slot=slot, booking_ref="BOOK-A")

    with pytest.raises(ServiceConflictError) as exc:
        await _book(repo, consent, recorder, offering=offering, slot=slot, booking_ref="BOOK-B")
    assert exc.value.code == "slot_not_available:RESERVED"


async def test_replayed_idempotency_key_returns_the_same_booking(repo, consent, recorder) -> None:
    """Idempotency — a retried request must not consume a second slot unit."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, capacity=2, recorder=recorder)
    ctx = make_ctx(idempotency_key="idem-booking-001")

    first = await _book(repo, consent, recorder, offering=offering, slot=slot, ctx=ctx)
    second = await _book(repo, consent, recorder, offering=offering, slot=slot, ctx=ctx)
    assert first.booking_request_id == second.booking_request_id

    slot_after = await repo.load_slot(slot.availability_slot_id)
    assert slot_after.reserved_count == 1


async def test_idempotency_key_reused_with_a_different_payload_is_a_conflict(
    repo, consent, recorder
) -> None:
    """Silently returning the first result would hide a client bug: the caller
    asked for a different slot and got somebody else's booking back."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, capacity=2, recorder=recorder)
    other_slot = await commands.open_availability_slot(
        repo,
        make_ctx(),
        recorder,
        service_offering_id=offering.service_offering_id,
        availability_slot_ref="SLOT-2026-09-02-1000",
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        channel="VIDEO",
    )
    ctx = make_ctx(idempotency_key="idem-booking-002")
    await _book(repo, consent, recorder, offering=offering, slot=slot, ctx=ctx)

    with pytest.raises(ServiceConflictError) as exc:
        await _book(repo, consent, recorder, offering=offering, slot=other_slot, ctx=ctx)
    assert exc.value.code == "idempotency_key_reused_with_different_payload"


async def test_ai_actor_cannot_book_or_confirm(repo, consent, recorder) -> None:
    """R9 — AI may surface a recommendation, never commit a family to a service.

    Refused at the domain boundary, so the refusal holds for a call path that
    never passes through a route or a policy engine.
    """
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    ai_ctx = make_ctx(actor="ai:recommender-v1")

    with pytest.raises(ServiceForbiddenError) as exc:
        await _book(repo, consent, recorder, offering=offering, slot=slot, ctx=ai_ctx)
    assert exc.value.code == "booking_submit_requires_human_actor"

    booking = await _book(repo, consent, recorder, offering=offering, slot=slot)
    with pytest.raises(ServiceForbiddenError) as exc:
        await commands.confirm_booking_request(
            repo, ai_ctx, recorder, booking_request_id=booking.booking_request_id
        )
    assert exc.value.code == "booking_confirm_requires_human_actor"


async def test_suspended_provider_cannot_be_booked(repo, consent, recorder) -> None:
    """Provider *and* offering must both be bookable. A suspended teacher whose
    offering row is still ACTIVE is the case a single "active?" flag would miss.
    """
    consent.add(granted())
    provider, offering, slot = await seed_supply(repo, recorder=recorder)
    await repo.save_provider(provider.model_copy(update={"admission_status": "SUSPENDED"}))
    await repo.commit()

    with pytest.raises(ServiceConflictError) as exc:
        await _book(repo, consent, recorder, offering=offering, slot=slot)
    assert exc.value.code.startswith("provider_not_bookable:")


async def test_slot_from_another_offering_is_refused(repo, consent, recorder) -> None:
    """Booking offering A against offering B's slot would put a family in a
    session nobody published."""
    consent.add(granted())
    provider, offering, slot = await seed_supply(repo, recorder=recorder)
    other_offering = await commands.publish_service_offering(
        repo,
        make_ctx(),
        recorder,
        provider_id=provider.provider_id,
        service_offering_ref="GROUP_SALON_90",
        title="家长沙龙 90 分钟",
        admission_status="ADMITTED",
        source_ref="supply:seed",
    )
    with pytest.raises(ServiceValidationError) as exc:
        await _book(repo, consent, recorder, offering=other_offering, slot=slot)
    assert exc.value.code == "slot_offering_mismatch"


async def test_booking_from_an_unlisted_surface_is_refused(repo, consent, recorder) -> None:
    """`family_booking_requests.source_page_id` CHECK — a booking may only
    originate from one of the four verified surfaces."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    with pytest.raises(ServiceForbiddenError) as exc:
        await _book(repo, consent, recorder, offering=offering, slot=slot, source_page_id="UI-99")
    assert exc.value.code == "booking_source_page_forbidden:UI-99"


async def test_missing_consent_ref_is_a_validation_error(repo, consent, recorder) -> None:
    """`consent_ref` is NOT NULL in 0035 and non-empty here: the reference to
    the consent that permitted the booking is part of the fact."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    with pytest.raises(ServiceValidationError) as exc:
        await _book(repo, consent, recorder, offering=offering, slot=slot, consent_ref="  ")
    assert exc.value.code == "booking_consent_ref_required"


async def test_double_confirm_is_idempotent_by_state(repo, consent, recorder) -> None:
    """0035 has UNIQUE (tenant_id, family_id, source_booking_request_id), so a
    second confirm cannot produce a second record. Returning the existing pair
    makes the replay a success rather than a 409 clients must special-case."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _book(repo, consent, recorder, offering=offering, slot=slot)

    _first, record_a = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    _second, record_b = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    assert record_a.booking_service_record_id == record_b.booking_service_record_id
    assert len(await repo.list_service_records(booking.tenant_id, booking.family_id)) == 1


async def test_production_environment_is_not_reachable(repo, consent, recorder) -> None:
    """R5 — the whole chain is fixture-only supply. `Environment` is a Literal
    of DEV/TEST, and the domain policy refuses anything else even if a caller
    bypasses the type."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    prod_ctx = make_ctx()
    object.__setattr__(prod_ctx, "environment", "PRODUCTION")
    with pytest.raises(ServiceForbiddenError) as exc:
        await _book(repo, consent, recorder, offering=offering, slot=slot, ctx=prod_ctx)
    assert exc.value.code == "environment_not_allowed:PRODUCTION"


# --------------------------------------------------------------------------
# Private check-in draft (UI-06 §4.1)
# --------------------------------------------------------------------------


async def test_private_checkin_draft_allow_list(repo, recorder) -> None:
    """Allow-listed selections only, no free text: an allow-list cannot carry a
    child fact, a free-text field can."""
    ctx = make_ctx(idempotency_key="idem-checkin-001")
    draft = await commands.create_private_checkin_draft(
        repo, ctx, recorder, onboarding_id="onb-001", action_ref="WEEKLY_ACTION_SEE"
    )
    assert draft.action_ref == "WEEKLY_ACTION_SEE"

    replay = await commands.create_private_checkin_draft(
        repo, ctx, recorder, onboarding_id="onb-001", action_ref="WEEKLY_ACTION_SEE"
    )
    assert replay.private_checkin_draft_id == draft.private_checkin_draft_id

    with pytest.raises(ServiceValidationError) as exc:
        await commands.create_private_checkin_draft(
            repo, make_ctx(), recorder, onboarding_id="onb-001", action_ref="FREE_TEXT_NOTE"
        )
    assert exc.value.code == "unsupported_private_checkin_action_ref:FREE_TEXT_NOTE"
