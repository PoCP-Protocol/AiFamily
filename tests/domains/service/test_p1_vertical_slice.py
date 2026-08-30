"""P1 service production-shape slice and fail-closed reversals.

The test parameter is the same ``Fake``/``SQLite``/gated ``PostgreSQL``
repository contract used by the existing acceptance chain.  Nothing here
claims commercial validity: the fixture boundary remains DEV/TEST and the
service outbox is inspected as a pending integration fact only.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.domains.service.application import commands
from backend.domains.service.domain.entities import utcnow
from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)

from .helpers import CHILD, CONSENT_REF, granted, make_ctx, seed_supply

pytestmark = pytest.mark.asyncio


async def _book(repo, consent, recorder, offering, slot, *, ctx=None, **overrides):
    values = {
        "service_offering_id": offering.service_offering_id,
        "availability_slot_id": slot.availability_slot_id,
        "booking_ref": "P1-BOOK-001",
        "source_page_id": "UI-21",
        "subject_person_id": CHILD,
        "consent_ref": CONSENT_REF,
    }
    values.update(overrides)
    return await commands.submit_booking_request(
        repo, ctx or make_ctx(), recorder, consent, **values
    )


async def _completed(repo, consent, recorder):
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _book(repo, consent, recorder, offering, slot)
    _confirmed, record = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    completed = await commands.fulfil_service_record(
        repo,
        make_ctx(),
        recorder,
        booking_service_record_id=record.booking_service_record_id,
    )
    return booking, completed


async def test_feedback_quality_and_service_playbook(repo, consent, recorder) -> None:
    booking, record = await _completed(repo, consent, recorder)

    feedback = await commands.record_family_feedback(
        repo,
        make_ctx(idempotency_key="feedback-1"),
        recorder,
        consent,
        booking_request_id=booking.booking_request_id,
        delivery_record_id=record.booking_service_record_id,
        subject_person_id=CHILD,
        author_role="GUARDIAN",
        outcome="HELPFUL",
        issue_codes=[],
        consent_ref=CONSENT_REF,
    )
    replay = await commands.record_family_feedback(
        repo,
        make_ctx(idempotency_key="feedback-1"),
        recorder,
        consent,
        booking_request_id=booking.booking_request_id,
        delivery_record_id=record.booking_service_record_id,
        subject_person_id=CHILD,
        author_role="GUARDIAN",
        outcome="HELPFUL",
        issue_codes=[],
        consent_ref=CONSENT_REF,
    )
    assert replay.family_feedback_id == feedback.family_feedback_id
    booking_event = next(
        event
        for event in await repo.list_pending_service_events(booking.tenant_id)
        if event.event_type == "service.booking_requested.v1"
    )
    assert booking_event.payload["scenario_ref"] == (
        "S-01_21_DAY_EVENING_STUDY_START_CONFLICT_REDUCTION"
    )

    quality = await commands.decide_service_quality(
        repo,
        make_ctx(idempotency_key="quality-1"),
        recorder,
        booking_request_id=booking.booking_request_id,
        delivery_record_id=record.booking_service_record_id,
        family_feedback_id=feedback.family_feedback_id,
        status="ACCEPTED",
    )
    assert quality.contribution_eligible is True
    assert not hasattr(quality, "cash_amount")

    welcome = await commands.record_service_action(
        repo,
        make_ctx(idempotency_key="action-welcome"),
        recorder,
        booking_request_id=booking.booking_request_id,
        action_type="WELCOME",
    )
    needs = await commands.record_service_action(
        repo,
        make_ctx(idempotency_key="action-needs"),
        recorder,
        booking_request_id=booking.booking_request_id,
        action_type="NEEDS_IDENTIFIED",
    )
    first_response = await commands.record_service_action(
        repo,
        make_ctx(idempotency_key="action-first-response"),
        recorder,
        booking_request_id=booking.booking_request_id,
        action_type="FIRST_RESPONSE",
        sla_due_at=utcnow() + timedelta(minutes=5),
    )
    follow_up = await commands.record_service_action(
        repo,
        make_ctx(idempotency_key="action-follow-up"),
        recorder,
        booking_request_id=booking.booking_request_id,
        action_type="FOLLOW_UP",
        delivery_record_id=record.booking_service_record_id,
    )
    assert welcome.action_type == "WELCOME"
    assert needs.action_type == "NEEDS_IDENTIFIED"
    assert first_response.sla_met is True
    assert follow_up.action_type == "FOLLOW_UP"

    events = await repo.list_pending_service_events(booking.tenant_id)
    event_types = {event.event_type for event in events}
    assert "service.booking_requested.v1" in event_types
    assert "service.delivery_completed.v1" in event_types
    assert "service.family_feedback_recorded.v1" in event_types
    assert "service.quality_decided.v1" in event_types
    assert not any("contribution" in event.event_type for event in events)
    assert not any("cash" in key for event in events for key in event.payload)


async def test_not_helpful_feedback_requires_human_remedy(repo, consent, recorder) -> None:
    booking, record = await _completed(repo, consent, recorder)
    feedback = await commands.record_family_feedback(
        repo,
        make_ctx(idempotency_key="feedback-remedy"),
        recorder,
        consent,
        booking_request_id=booking.booking_request_id,
        delivery_record_id=record.booking_service_record_id,
        subject_person_id=CHILD,
        author_role="GUARDIAN",
        outcome="NOT_HELPFUL_YET",
        issue_codes=["NEED_MISSED"],
        consent_ref=CONSENT_REF,
    )
    with pytest.raises(ServiceConflictError, match="not_helpful_feedback_requires_remedy"):
        await commands.decide_service_quality(
            repo,
            make_ctx(idempotency_key="quality-remedy-accept"),
            recorder,
            booking_request_id=booking.booking_request_id,
            delivery_record_id=record.booking_service_record_id,
            family_feedback_id=feedback.family_feedback_id,
            status="ACCEPTED",
        )

    rework = await commands.record_service_action(
        repo,
        make_ctx(idempotency_key="action-rework"),
        recorder,
        booking_request_id=booking.booking_request_id,
        delivery_record_id=record.booking_service_record_id,
        family_feedback_id=feedback.family_feedback_id,
        action_type="REMEDY_REWORK",
    )
    refund = await commands.record_service_action(
        repo,
        make_ctx(idempotency_key="action-refund"),
        recorder,
        booking_request_id=booking.booking_request_id,
        delivery_record_id=record.booking_service_record_id,
        family_feedback_id=feedback.family_feedback_id,
        action_type="REFUND_REQUESTED",
    )
    assert (rework.action_type, refund.action_type) == ("REMEDY_REWORK", "REFUND_REQUESTED")
    assert not hasattr(refund, "cash_amount")

    decision = await commands.decide_service_quality(
        repo,
        make_ctx(idempotency_key="quality-remedy-refund"),
        recorder,
        booking_request_id=booking.booking_request_id,
        delivery_record_id=record.booking_service_record_id,
        family_feedback_id=feedback.family_feedback_id,
        status="REFUND_REQUIRED",
    )
    assert decision.contribution_eligible is False


async def test_feedback_fail_closed_for_consent_scope_and_uncompleted_delivery(
    repo, consent, recorder
) -> None:
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _book(repo, consent, recorder, offering, slot)
    _confirmed, record = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )
    with pytest.raises(ServiceConflictError, match="feedback_requires_completed_delivery"):
        await commands.record_family_feedback(
            repo,
            make_ctx(idempotency_key="feedback-pending"),
            recorder,
            consent,
            booking_request_id=booking.booking_request_id,
            delivery_record_id=record.booking_service_record_id,
            subject_person_id=CHILD,
            author_role="GUARDIAN",
            outcome="HELPFUL",
            issue_codes=[],
            consent_ref=CONSENT_REF,
        )

    await commands.fulfil_service_record(
        repo,
        make_ctx(),
        recorder,
        booking_service_record_id=record.booking_service_record_id,
    )
    replay_key = "feedback-withdrawal-replay"
    await commands.record_family_feedback(
        repo,
        make_ctx(idempotency_key=replay_key),
        recorder,
        consent,
        booking_request_id=booking.booking_request_id,
        delivery_record_id=record.booking_service_record_id,
        subject_person_id=CHILD,
        author_role="GUARDIAN",
        outcome="HELPFUL",
        issue_codes=[],
        consent_ref=CONSENT_REF,
    )
    consent.withdraw(CONSENT_REF)
    with pytest.raises(ServiceForbiddenError, match="consent_required:service:"):
        await commands.record_family_feedback(
            repo,
            make_ctx(idempotency_key=replay_key),
            recorder,
            consent,
            booking_request_id=booking.booking_request_id,
            delivery_record_id=record.booking_service_record_id,
            subject_person_id=CHILD,
            author_role="GUARDIAN",
            outcome="HELPFUL",
            issue_codes=[],
            consent_ref=CONSENT_REF,
        )


async def test_feedback_cannot_rebind_a_booking_to_another_consented_subject(
    repo, consent, recorder
) -> None:
    consent.add(granted())
    booking, record = await _completed(repo, consent, recorder)
    other_subject = "person-other-child"
    other_consent = "consent-service-other-child"
    consent.add(granted(subject_person_id=other_subject, consent_id=other_consent))

    with pytest.raises(ServiceForbiddenError, match="feedback_subject_mismatch"):
        await commands.record_family_feedback(
            repo,
            make_ctx(idempotency_key="feedback-subject-mismatch"),
            recorder,
            consent,
            booking_request_id=booking.booking_request_id,
            delivery_record_id=record.booking_service_record_id,
            subject_person_id=other_subject,
            author_role="GUARDIAN",
            outcome="HELPFUL",
            issue_codes=[],
            consent_ref=other_consent,
        )


async def test_remedy_action_cannot_mix_feedback_from_another_delivery(
    repo, consent, recorder
) -> None:
    consent.add(granted())
    booking_a, record_a = await _completed(repo, consent, recorder)
    feedback_a = await commands.record_family_feedback(
        repo,
        make_ctx(idempotency_key="feedback-delivery-a"),
        recorder,
        consent,
        booking_request_id=booking_a.booking_request_id,
        delivery_record_id=record_a.booking_service_record_id,
        subject_person_id=CHILD,
        author_role="GUARDIAN",
        outcome="NOT_HELPFUL_YET",
        issue_codes=["NEED_MISSED"],
        consent_ref=CONSENT_REF,
    )
    # Simulate a stale/corrupt relational reference without bypassing the
    # command under test. The service action must reject it before writing a
    # remedy fact.
    mixed_feedback = feedback_a.model_copy(update={"delivery_record_id": "foreign-delivery"})
    await repo.save_family_feedback(mixed_feedback)
    await repo.commit()

    with pytest.raises(ServiceValidationError, match="service_action_feedback_delivery_mismatch"):
        await commands.record_service_action(
            repo,
            make_ctx(idempotency_key="action-mixed-delivery"),
            recorder,
            booking_request_id=booking_a.booking_request_id,
            delivery_record_id=record_a.booking_service_record_id,
            family_feedback_id=mixed_feedback.family_feedback_id,
            action_type="REMEDY_REWORK",
        )


async def test_expired_supply_and_ai_named_action_are_denied(repo, consent, recorder) -> None:
    consent.add(granted())
    provider, offering, slot = await seed_supply(repo, recorder=recorder)
    expired_from = utcnow() - timedelta(days=2)
    await repo.save_provider(
        provider.model_copy(
            update={
                "effective_from": expired_from,
                "effective_to": utcnow() - timedelta(seconds=1),
            }
        )
    )
    await repo.commit()
    with pytest.raises(ServiceConflictError, match="provider_not_bookable"):
        await _book(repo, consent, recorder, offering, slot)

    # A separately completed chain proves the human gate applies to high-impact
    # welcome/remedy actions too, not only booking confirmation.
    booking, record = await _completed(repo, consent, recorder)
    with pytest.raises(ServiceForbiddenError, match="service_action_requires_human_actor"):
        await commands.record_service_action(
            repo,
            make_ctx(actor="ai:planner", idempotency_key="ai-action"),
            recorder,
            booking_request_id=booking.booking_request_id,
            delivery_record_id=record.booking_service_record_id,
            action_type="FOLLOW_UP",
        )


async def test_duplicate_delivery_callback_is_idempotent_and_payload_bound(
    repo, consent, recorder
) -> None:
    """A retried provider callback cannot create a second delivery event."""
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _book(repo, consent, recorder, offering, slot)
    _confirmed, record = await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )

    callback_ctx = make_ctx(idempotency_key="delivery-callback-1")
    first = await commands.fulfil_service_record(
        repo,
        callback_ctx,
        recorder,
        booking_service_record_id=record.booking_service_record_id,
        quality_rating="POSITIVE",
    )
    replay = await commands.fulfil_service_record(
        repo,
        callback_ctx,
        recorder,
        booking_service_record_id=record.booking_service_record_id,
        quality_rating="POSITIVE",
    )
    assert replay == first

    events = await repo.list_pending_service_events(booking.tenant_id)
    assert sum(event.event_type == "service.delivery_completed.v1" for event in events) == 1
    with pytest.raises(ServiceConflictError, match="delivery_idempotency_replay_mismatch"):
        await commands.fulfil_service_record(
            repo,
            callback_ctx,
            recorder,
            booking_service_record_id=record.booking_service_record_id,
            quality_rating="NEUTRAL",
        )


async def test_completed_delivery_cannot_be_cancelled_or_release_capacity(
    repo, consent, recorder
) -> None:
    booking, record = await _completed(repo, consent, recorder)
    with pytest.raises(ServiceConflictError, match="completed_delivery_cannot_be_cancelled"):
        await commands.cancel_booking_request(
            repo,
            make_ctx(idempotency_key="cancel-after-delivery"),
            recorder,
            booking_request_id=booking.booking_request_id,
        )

    current_booking = await repo.load_booking(booking.booking_request_id)
    current_record = await repo.load_service_record(record.booking_service_record_id)
    slot = await repo.load_slot(booking.availability_slot_id)
    assert current_booking.status == "CONFIRMED"
    assert current_record.status == "COMPLETED"
    assert slot.reserved_count == 1
    assert not any(
        event.event_type == "service.booking_cancelled.v1"
        for event in await repo.list_pending_service_events(booking.tenant_id)
    )


async def test_duplicate_cancellation_is_state_idempotent(repo, consent, recorder) -> None:
    consent.add(granted())
    _provider, offering, slot = await seed_supply(repo, recorder=recorder)
    booking = await _book(repo, consent, recorder, offering, slot)
    await commands.confirm_booking_request(
        repo, make_ctx(), recorder, booking_request_id=booking.booking_request_id
    )

    cancel_ctx = make_ctx(idempotency_key="cancel-replay-1")
    first = await commands.cancel_booking_request(
        repo, cancel_ctx, recorder, booking_request_id=booking.booking_request_id
    )
    replay = await commands.cancel_booking_request(
        repo, cancel_ctx, recorder, booking_request_id=booking.booking_request_id
    )
    assert replay == first
    slot_after = await repo.load_slot(slot.availability_slot_id)
    assert (slot_after.reserved_count, slot_after.status) == (0, "AVAILABLE")
    events = await repo.list_pending_service_events(booking.tenant_id)
    assert sum(event.event_type == "service.booking_cancelled.v1" for event in events) == 1
    assert any(
        event.payload["delivery_record_id"] is not None
        for event in events
        if event.event_type == "service.booking_cancelled.v1"
    )
