"""Named Actions for the service booking chain.

Every mutation here is idempotent on `ctx.idempotency_key`, records an
`AuditEvent` (R6), and commits once. Read them in chain order:

    register_service_provider → publish_service_offering → open_availability_slot
        → submit_booking_request → confirm_booking_request → fulfil_service_record

`submit_booking_request` is the one that carries the compliance weight, and it
does three things no other command does:

1. **ConsentGate.** The subject of a booking may be a minor, so booking is
   sensitive-information processing under
   `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §1. The command reads the
   *current* SERVICE-purpose grants for the subject through `ConsentQueryPort`
   and passes them to `ConsentGate.check`. No grant → `ServiceForbiddenError`,
   not a warning and not a soft default. This is the gap the assessment domain
   currently has (`governance/CAPABILITY_REGISTRY.yaml` →
   `assessment_session_to_hypothesis.known_gaps` line 1); it is closed here
   rather than repeated.
2. **Slot capacity.** The slot is reserved in the same unit of work as the
   booking row, so "the slot was already taken" is a refusal rather than an
   overbooking discovered later.
3. **Supply admission.** Provider *and* offering must both be bookable. A
   suspended provider whose offering is still ACTIVE cannot be booked, which is
   why `ServiceProvider.is_bookable` checks three statuses at once.

R6 audit: the recorder is a required argument on every mutation, not an optional
one. An optional recorder is an audit trail that is missing exactly where
somebody forgot, and R6 does not have a "unless inconvenient" clause. Callers
flush it into the same transaction as the domain write (see
`backend/platform/audit/recorder.py` — same-transaction, not an outbox).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.consent.gate import ConsentGate
from backend.platform.consent.models import ConsentPurpose

from ..domain.entities import (
    AvailabilitySlot,
    BookingRequest,
    FamilyFeedback,
    PrivateCheckinDraft,
    QualityDecision,
    ServiceAction,
    ServiceEvent,
    ServiceOffering,
    ServiceProvider,
    ServiceRecord,
    utcnow,
)
from ..domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)
from ..domain.policies import (
    assert_booking_source_page,
    assert_checkin_action_ref,
    assert_family_scope,
    assert_fixture_boundary,
    assert_human_actor,
)
from ..domain.value_objects import (
    FEEDBACK_ISSUE_CODES,
    SERVICE_ACTION_TYPES,
    AdmissionStatus,
    Channel,
    FamilyFeedbackOutcome,
    FeedbackAuthorRole,
    FeedbackIssueCode,
    ProviderKind,
    QualificationStatus,
    QualityDecisionStatus,
    ScopeType,
    ServiceActionType,
    ServiceQualityRating,
)
from .context import ActionContext
from .ports import ConsentQueryPort, ServiceRepositoryPort

#: The only consent purpose this domain may act under. A grant for ASSESSMENT
#: does not permit a booking — `ConsentPurpose` is deliberately one-purpose-per-
#: grant, and widening it here would undo that.
BOOKING_CONSENT_PURPOSE = ConsentPurpose.SERVICE

#: Resource types used in audit events, so the migration/report side and the
#: code name the same strings once.
PROVIDER_RESOURCE = "ServiceProvider"
OFFERING_RESOURCE = "ServiceOffering"
SLOT_RESOURCE = "AvailabilitySlot"
BOOKING_RESOURCE = "BookingRequest"
RECORD_RESOURCE = "ServiceRecord"
CHECKIN_RESOURCE = "PrivateCheckinDraft"
FEEDBACK_RESOURCE = "FamilyFeedback"
QUALITY_RESOURCE = "QualityDecision"
ACTION_RESOURCE = "ServiceAction"
EVENT_RESOURCE = "ServiceEvent"
FIRST_SCENARIO_REF = "S-01_21_DAY_EVENING_STUDY_START_CONFLICT_REDUCTION"
FIRST_SCENARIO_OUTCOME_REF = "stable_evening_start_and_reduced_parent_child_conflict"
CONFIRMED_BOOKING_STATUS = "CONFIRMED"


def _assert_service_context(ctx: ActionContext) -> None:
    """Keep replay paths inside the fixture-only production boundary.

    A replay must not become a loophole: returning an existing DEV/TEST fact
    still cannot be requested from a production-shaped context.
    """
    assert_fixture_boundary(
        environment=ctx.environment,
        source_system="TEST_FIXTURE",
        external_effect=False,
        allowed_source_system="TEST_FIXTURE",
    )


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _event_key(ctx: ActionContext, action: str, aggregate_id: str) -> str:
    return ctx.child_key(f"event:{action}:{aggregate_id}") or (
        f"{ctx.correlation_id}:event:{action}:{aggregate_id}"
    )


def _audit(
    recorder: AuditRecorder,
    ctx: ActionContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """R6 — no authoritative state change without an AuditEvent.

    `before`/`after` are both named in R6, so a status transition records both
    rather than only the destination: "it is CONFIRMED now" without "it was
    REQUESTED" cannot answer whether a step was skipped.
    """
    recorder.record(
        AuditEvent(
            actor_id=ctx.actor,
            tenant_id=ctx.tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=f"named action {action}",
            correlation_id=ctx.correlation_id,
            before=before,
            after=after,
        )
    )


async def _event(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    idempotency_key: str,
    payload: dict,
    occurred_at: datetime | None = None,
) -> None:
    """Stage one idempotent service outbox message in the same UoW."""
    now = occurred_at or utcnow()
    await repo.append_service_event(
        ServiceEvent(
            service_event_id=_new_id("svcevent"),
            tenant_id=ctx.tenant_id,
            family_id=ctx.family_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            payload=payload,
            occurred_at=now,
            environment=ctx.environment,
            created_at=now,
        )
    )


# --------------------------------------------------------------------------
# Supply side
# --------------------------------------------------------------------------


async def register_service_provider(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    provider_ref: str,
    display_name: str,
    provider_kind: ProviderKind,
    qualification_status: QualificationStatus,
    admission_status: AdmissionStatus,
    source_ref: str,
    qualification_ref: str | None = None,
    scope_type: ScopeType = "TENANT",
) -> ServiceProvider:
    """Register supply. Not a family fact — no `family_id` on the row at all."""
    now = utcnow()
    provider = ServiceProvider(
        provider_id=_new_id("svcprov"),
        scope_type=scope_type,
        tenant_id=ctx.tenant_id if scope_type == "TENANT" else None,
        provider_ref=provider_ref,
        display_name=display_name,
        provider_kind=provider_kind,
        qualification_ref=qualification_ref,
        qualification_status=qualification_status,
        admission_status=admission_status,
        source_ref=source_ref,
        effective_from=now,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    )
    await repo.save_provider(provider)
    _audit(
        recorder,
        ctx,
        action="register_service_provider",
        resource_type=PROVIDER_RESOURCE,
        resource_id=provider.provider_id,
        after={"provider_ref": provider_ref, "admission_status": admission_status},
    )
    await _event(
        repo,
        ctx,
        event_type="service.provider_registered.v1",
        aggregate_type=PROVIDER_RESOURCE,
        aggregate_id=provider.provider_id,
        idempotency_key=_event_key(ctx, "register_service_provider", provider.provider_id),
        payload={"provider_id": provider.provider_id, "provider_ref": provider.provider_ref},
    )
    await repo.commit()
    return provider


async def publish_service_offering(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    provider_id: str,
    service_offering_ref: str,
    title: str,
    admission_status: AdmissionStatus,
    source_ref: str,
    version_no: int = 1,
    scenario_ref: str = FIRST_SCENARIO_REF,
) -> ServiceOffering:
    """Bind an offering to one already-admitted provider.

    Refuses a provider that is not bookable at publish time, so a suspended
    teacher's catalogue entry never reaches a family's browse screen.
    """
    provider = await repo.load_provider(provider_id)
    if provider.scope_type == "TENANT":
        assert_family_scope(
            expected_family_id=ctx.tenant_id,
            actual_family_id=provider.tenant_id or "",
        )
    if not provider.is_bookable:
        raise ServiceConflictError(
            "provider_not_admitted:"
            f"{provider.status}/{provider.qualification_status}/{provider.admission_status}"
        )

    now = utcnow()
    offering = ServiceOffering(
        service_offering_id=_new_id("svcoffer"),
        tenant_id=ctx.tenant_id,
        provider_id=provider_id,
        service_offering_ref=service_offering_ref,
        version_no=version_no,
        title=title,
        admission_status=admission_status,
        source_ref=source_ref,
        attributes={
            "scenario_ref": scenario_ref,
            "outcome_ref": FIRST_SCENARIO_OUTCOME_REF,
        },
        effective_from=now,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    )
    await repo.save_offering(offering)
    _audit(
        recorder,
        ctx,
        action="publish_service_offering",
        resource_type=OFFERING_RESOURCE,
        resource_id=offering.service_offering_id,
        after={"service_offering_ref": service_offering_ref, "version_no": version_no},
    )
    await _event(
        repo,
        ctx,
        event_type="service.offering_published.v1",
        aggregate_type=OFFERING_RESOURCE,
        aggregate_id=offering.service_offering_id,
        idempotency_key=_event_key(ctx, "publish_service_offering", offering.service_offering_id),
        payload={"service_offering_id": offering.service_offering_id},
    )
    await repo.commit()
    return offering


async def open_availability_slot(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    service_offering_id: str,
    availability_slot_ref: str,
    starts_at: datetime,
    ends_at: datetime,
    channel: Channel,
    capacity: int = 1,
) -> AvailabilitySlot:
    """Open inventory against one offering.

    The 0035 table comment is explicit that this "does not send calendar
    notifications" — opening a slot changes this system's state and nothing
    else, which is what `fixture_only` encodes.
    """
    offering = await repo.load_offering(service_offering_id)
    assert_family_scope(expected_family_id=ctx.tenant_id, actual_family_id=offering.tenant_id)
    if not offering.is_bookable:
        raise ServiceConflictError(
            f"offering_not_admitted:{offering.status}/{offering.admission_status}"
        )

    now = utcnow()
    slot = AvailabilitySlot(
        availability_slot_id=_new_id("svcslot"),
        tenant_id=ctx.tenant_id,
        provider_id=offering.provider_id,
        service_offering_id=service_offering_id,
        availability_slot_ref=availability_slot_ref,
        starts_at=starts_at,
        ends_at=ends_at,
        channel=channel,
        capacity=capacity,
        created_at=now,
        updated_at=now,
    )
    await repo.save_slot(slot)
    _audit(
        recorder,
        ctx,
        action="open_availability_slot",
        resource_type=SLOT_RESOURCE,
        resource_id=slot.availability_slot_id,
        after={"availability_slot_ref": availability_slot_ref, "capacity": capacity},
    )
    await _event(
        repo,
        ctx,
        event_type="service.slot_opened.v1",
        aggregate_type=SLOT_RESOURCE,
        aggregate_id=slot.availability_slot_id,
        idempotency_key=_event_key(ctx, "open_availability_slot", slot.availability_slot_id),
        payload={"availability_slot_id": slot.availability_slot_id},
    )
    await repo.commit()
    return slot


# --------------------------------------------------------------------------
# Family side
# --------------------------------------------------------------------------


async def submit_booking_request(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    consent: ConsentQueryPort,
    *,
    service_offering_id: str,
    availability_slot_id: str,
    booking_ref: str,
    source_page_id: str,
    subject_person_id: str,
    consent_ref: str,
) -> BookingRequest:
    """The family's booking intent. DRAFT → REQUESTED in one step.

    `subject_person_id` is required and is *the person being served* — usually a
    child, sometimes the parent. It is required because the consent check needs
    a subject: "does this family have consent" is not a well-formed question,
    consent belongs to a person.

    Ordering is deliberate: consent is checked **before** any supply is read or
    any capacity is touched. A refused booking must leave no trace of having
    reserved anything, and checking last would mean the refusal happens after a
    `reserve()` that then has to be unwound.
    """
    assert_human_actor(ctx.actor, code="booking_submit")
    # Ahead of entity construction on purpose: `BookingRequest.source_page_id` is
    # a `Literal`, so pydantic would raise its own `ValidationError` first and
    # the caller would see a pydantic error instead of the domain's
    # `booking_source_page_forbidden` code the HTTP layer maps.
    assert_booking_source_page(source_page_id)
    # Same reason: R5's refusal must surface as `environment_not_allowed`, not as
    # a pydantic literal_error on `BookingRequest.environment`.
    assert_fixture_boundary(
        environment=ctx.environment,
        source_system="TEST_FIXTURE",
        external_effect=False,
        allowed_source_system="TEST_FIXTURE",
    )

    if not consent_ref.strip():
        raise ServiceValidationError("booking_consent_ref_required")

    grants = await consent.list_grants(
        tenant_id=ctx.tenant_id,
        subject_person_id=subject_person_id,
        purpose=BOOKING_CONSENT_PURPOSE,
    )
    matching_grant = next(
        (
            grant
            for grant in grants
            if grant.consent_id == consent_ref and grant.guardian_person_id == ctx.actor_person_id
        ),
        None,
    )
    if matching_grant is None or not ConsentGate.check(
        subject_person_id, BOOKING_CONSENT_PURPOSE, grants
    ):
        raise ServiceForbiddenError(
            f"consent_required:{BOOKING_CONSENT_PURPOSE.value}:{subject_person_id}"
        )

    # Consent is deliberately checked before an idempotent replay. A replay is
    # still a request carrying a minor subject, and returning an old result after
    # withdrawal would turn the idempotency fast path into a consent bypass.
    if ctx.idempotency_key:
        existing = await repo.find_booking_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            # Replay of the same key returns the same booking. A *different*
            # payload under the same key is a conflict rather than a silent
            # return of the first result, because a client that reused a key by
            # accident must find out.
            if (
                existing.availability_slot_id != availability_slot_id
                or existing.service_offering_id != service_offering_id
                or existing.booking_ref != booking_ref
                or existing.consent_ref != consent_ref
                or existing.service_snapshot.get("subject_person_id") != subject_person_id
            ):
                raise ServiceConflictError("idempotency_key_reused_with_different_payload")
            return existing

    offering = await repo.load_offering(service_offering_id)
    assert_family_scope(expected_family_id=ctx.tenant_id, actual_family_id=offering.tenant_id)
    now = utcnow()
    if not offering.is_bookable_at(now):
        raise ServiceConflictError(
            f"offering_not_bookable:{offering.status}/{offering.admission_status}"
        )
    provider = await repo.load_provider(offering.provider_id)
    if provider.scope_type == "TENANT":
        assert_family_scope(
            expected_family_id=ctx.tenant_id, actual_family_id=provider.tenant_id or ""
        )
    if not provider.is_bookable_at(now):
        raise ServiceConflictError(
            "provider_not_bookable:"
            f"{provider.status}/{provider.qualification_status}/{provider.admission_status}"
        )

    slot = await repo.load_slot_for_update(availability_slot_id)
    assert_family_scope(expected_family_id=ctx.tenant_id, actual_family_id=slot.tenant_id)
    if slot.service_offering_id != service_offering_id:
        raise ServiceValidationError("slot_offering_mismatch")
    if now >= slot.ends_at:
        raise ServiceConflictError("slot_outside_booking_window")
    # `reserve()` raises ServiceConflictError when the slot is full or blocked —
    # the "时段已占用" refusal path.
    reserved = slot.reserve()

    booking = BookingRequest(
        booking_request_id=_new_id("svcbook"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        actor_person_id=ctx.actor_person_id,
        booking_ref=booking_ref,
        service_offering_id=service_offering_id,
        availability_slot_id=availability_slot_id,
        source_page_id=source_page_id,
        consent_ref=consent_ref,
        status="DRAFT",
        # Snapshot so "what did the family actually book" survives the offering
        # being re-versioned or retired afterwards. The subject reference is
        # retained only to prevent feedback from being rebound to another
        # consented subject; it is not exposed by the customer projection.
        service_snapshot={
            "service_offering_ref": offering.service_offering_ref,
            "version_no": offering.version_no,
            "title": offering.title,
            "provider_ref": provider.provider_ref,
            "availability_slot_ref": slot.availability_slot_ref,
            "starts_at": slot.starts_at.isoformat(),
            "ends_at": slot.ends_at.isoformat(),
            "channel": slot.channel,
            "scenario_ref": offering.attributes.get("scenario_ref", FIRST_SCENARIO_REF),
            "outcome_ref": offering.attributes.get("outcome_ref"),
            "subject_person_id": subject_person_id,
        },
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    ).submit(actor=ctx.actor)

    await repo.save_slot(reserved)
    await repo.save_booking(booking)
    _audit(
        recorder,
        ctx,
        action="submit_booking_request",
        resource_type=BOOKING_RESOURCE,
        resource_id=booking.booking_request_id,
        before={"status": "DRAFT"},
        after={
            "status": booking.status,
            "booking_ref": booking_ref,
            "availability_slot_id": availability_slot_id,
            "consent_ref": consent_ref,
            "scenario_ref": booking.service_snapshot.get("scenario_ref"),
            "outcome_ref": booking.service_snapshot.get("outcome_ref"),
        },
    )
    _audit(
        recorder,
        ctx,
        action="reserve_availability_slot",
        resource_type=SLOT_RESOURCE,
        resource_id=reserved.availability_slot_id,
        before={"reserved_count": slot.reserved_count, "status": slot.status},
        after={"reserved_count": reserved.reserved_count, "status": reserved.status},
    )
    await _event(
        repo,
        ctx,
        event_type="service.booking_requested.v1",
        aggregate_type=BOOKING_RESOURCE,
        aggregate_id=booking.booking_request_id,
        idempotency_key=_event_key(ctx, "submit_booking_request", booking.booking_request_id),
        payload={
            "booking_request_id": booking.booking_request_id,
            "service_offering_id": service_offering_id,
            "availability_slot_id": availability_slot_id,
            "consent_ref": consent_ref,
            "scenario_ref": booking.service_snapshot.get("scenario_ref"),
            "outcome_ref": booking.service_snapshot.get("outcome_ref"),
        },
    )
    await repo.commit()
    return booking


async def confirm_booking_request(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    booking_request_id: str,
) -> tuple[BookingRequest, ServiceRecord]:
    """REQUESTED → CONFIRMED, and open the PENDING service record.

    The record is created here rather than at fulfilment because a confirmed
    booking already has a delivery obligation attached; creating the receipt
    only at completion would leave "confirmed but never delivered" unrepresented.
    """
    _assert_service_context(ctx)
    # Must run before the state-idempotency return below: an AI caller may not
    # learn or replay a human confirmation through a second command path.
    assert_human_actor(ctx.actor, code="booking_confirm")
    booking = await repo.load_booking(booking_request_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=booking.family_id)

    existing_record = await repo.find_service_record_for_booking(
        ctx.tenant_id, ctx.family_id, booking_request_id
    )
    if existing_record is not None:
        # Idempotent by state, not only by key: the DDL has
        # UNIQUE (tenant_id, family_id, source_booking_request_id), so a second
        # confirm cannot produce a second record anyway. Returning the existing
        # pair makes the replay a success rather than a 409 a client must
        # special-case.
        if booking.status != CONFIRMED_BOOKING_STATUS:
            raise ServiceConflictError("confirmed_booking_record_mismatch")
        return booking, existing_record

    now = utcnow()
    offering = await repo.load_offering(booking.service_offering_id)
    assert_family_scope(expected_family_id=ctx.tenant_id, actual_family_id=offering.tenant_id)
    provider = await repo.load_provider(offering.provider_id)
    if not offering.is_bookable_at(now) or not provider.is_bookable_at(now):
        raise ServiceConflictError("supply_not_bookable_at_confirmation")
    slot = await repo.load_slot_for_update(booking.availability_slot_id)
    assert_family_scope(expected_family_id=ctx.tenant_id, actual_family_id=slot.tenant_id)
    if now >= slot.ends_at or slot.status in ("BLOCKED", "EXPIRED") or slot.reserved_count < 1:
        raise ServiceConflictError("slot_not_available_at_confirmation")

    confirmed = booking.confirm(actor=ctx.actor)
    record = ServiceRecord(
        booking_service_record_id=_new_id("svcrec"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        source_booking_request_id=booking_request_id,
        status="PENDING",
        environment=ctx.environment,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    )
    await repo.save_booking(confirmed)
    await repo.save_service_record(record)
    _audit(
        recorder,
        ctx,
        action="confirm_booking_request",
        resource_type=BOOKING_RESOURCE,
        resource_id=booking_request_id,
        before={"status": booking.status},
        after={"status": confirmed.status},
    )
    _audit(
        recorder,
        ctx,
        action="open_service_record",
        resource_type=RECORD_RESOURCE,
        resource_id=record.booking_service_record_id,
        after={"status": record.status, "source_booking_request_id": booking_request_id},
    )
    await _event(
        repo,
        ctx,
        event_type="service.booking_confirmed.v1",
        aggregate_type=BOOKING_RESOURCE,
        aggregate_id=booking_request_id,
        idempotency_key=_event_key(ctx, "confirm_booking_request", booking_request_id),
        payload={
            "booking_request_id": booking_request_id,
            "delivery_record_id": record.booking_service_record_id,
        },
    )
    await repo.commit()
    return confirmed, record


async def cancel_booking_request(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    booking_request_id: str,
) -> BookingRequest:
    """Cancel and give the slot capacity back.

    Releasing the slot is not optional bookkeeping: a cancelled booking that
    keeps its reservation makes the inventory permanently wrong, and nothing in
    the chain would ever notice.
    """
    _assert_service_context(ctx)
    assert_human_actor(ctx.actor, code="booking_cancel")
    booking = await repo.load_booking(booking_request_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=booking.family_id)
    # A completed delivery is a terminal service fact. It can be reviewed,
    # remedied or sent to the refund Gate, but it cannot be rewritten as a
    # cancellation (and its slot must not be released after the fact).
    if booking.status == "CANCELLED":
        return booking
    record = await repo.find_service_record_for_booking(
        ctx.tenant_id, ctx.family_id, booking_request_id
    )
    if record is not None and record.status == "COMPLETED":
        raise ServiceConflictError("completed_delivery_cannot_be_cancelled")
    cancelled = booking.cancel(actor=ctx.actor)

    slot = await repo.load_slot_for_update(booking.availability_slot_id)
    released = slot.release()
    await repo.save_slot(released)
    await repo.save_booking(cancelled)

    cancelled_record = None
    if record is not None and record.status in ("PENDING", "SCHEDULED"):
        cancelled_record = record.cancel(actor=ctx.actor)
        await repo.save_service_record(cancelled_record)

    _audit(
        recorder,
        ctx,
        action="cancel_booking_request",
        resource_type=BOOKING_RESOURCE,
        resource_id=booking_request_id,
        before={"status": booking.status},
        after={"status": cancelled.status},
    )
    _audit(
        recorder,
        ctx,
        action="release_availability_slot",
        resource_type=SLOT_RESOURCE,
        resource_id=released.availability_slot_id,
        before={"reserved_count": slot.reserved_count, "status": slot.status},
        after={"reserved_count": released.reserved_count, "status": released.status},
    )
    if cancelled_record is not None:
        _audit(
            recorder,
            ctx,
            action="cancel_service_record",
            resource_type=RECORD_RESOURCE,
            resource_id=cancelled_record.booking_service_record_id,
            before={"status": record.status},
            after={"status": cancelled_record.status},
        )
    await _event(
        repo,
        ctx,
        event_type="service.booking_cancelled.v1",
        aggregate_type=BOOKING_RESOURCE,
        aggregate_id=booking_request_id,
        idempotency_key=_event_key(ctx, "cancel_booking_request", booking_request_id),
        payload={
            "booking_request_id": booking_request_id,
            "delivery_record_id": record.booking_service_record_id if record else None,
        },
    )
    await repo.commit()
    return cancelled


async def fulfil_service_record(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    booking_service_record_id: str,
    quality_rating: ServiceQualityRating | None = None,
) -> ServiceRecord:
    """Mark the session delivered. Terminal state of the chain.

    `quality_rating` evaluates the *provider's session*, never the family — see
    `ServiceRecord`'s docstring for why that distinction is structural rather
    than a naming convention.
    """
    _assert_service_context(ctx)
    assert_human_actor(ctx.actor, code="record_complete")
    record = await repo.load_service_record(booking_service_record_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=record.family_id)
    booking = await repo.load_booking(record.source_booking_request_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=booking.family_id)
    if booking.status != CONFIRMED_BOOKING_STATUS:
        raise ServiceConflictError("delivery_requires_confirmed_booking")
    if record.status == "COMPLETED":
        if record.service_quality_rating != quality_rating:
            raise ServiceConflictError("delivery_idempotency_replay_mismatch")
        return record
    completed = record.complete(actor=ctx.actor, quality_rating=quality_rating)
    await repo.save_service_record(completed)
    _audit(
        recorder,
        ctx,
        action="fulfil_service_record",
        resource_type=RECORD_RESOURCE,
        resource_id=booking_service_record_id,
        before={"status": record.status},
        after={"status": completed.status, "service_quality_rating": quality_rating},
    )
    await _event(
        repo,
        ctx,
        event_type="service.delivery_completed.v1",
        aggregate_type=RECORD_RESOURCE,
        aggregate_id=booking_service_record_id,
        idempotency_key=_event_key(ctx, "fulfil_service_record", booking_service_record_id),
        payload={
            "delivery_record_id": booking_service_record_id,
            "booking_request_id": record.source_booking_request_id,
            "scenario_ref": booking.service_snapshot.get("scenario_ref"),
            "outcome_ref": booking.service_snapshot.get("outcome_ref"),
        },
    )
    await repo.commit()
    return completed


async def create_private_checkin_draft(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    onboarding_id: str,
    action_ref: str,
) -> PrivateCheckinDraft:
    """UI-06 §4.1 私密复盘草稿. Allow-listed selection only, no free text.

    An unsupported `action_ref` is a 422 in the source contract
    (`unsupported_private_checkin_action_ref`), which `assert_checkin_action_ref`
    raises as `ServiceValidationError`.
    """
    assert_checkin_action_ref(action_ref)
    if ctx.idempotency_key:
        existing = await repo.find_checkin_draft_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            return existing

    now = utcnow()
    draft = PrivateCheckinDraft(
        private_checkin_draft_id=_new_id("svccheckin"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        actor_person_id=ctx.actor_person_id,
        onboarding_id=onboarding_id,
        action_ref=action_ref,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        occurred_at=now,
        created_at=now,
        created_by=ctx.actor,
    )
    await repo.append_checkin_draft(draft)
    _audit(
        recorder,
        ctx,
        action="create_private_checkin_draft",
        resource_type=CHECKIN_RESOURCE,
        resource_id=draft.private_checkin_draft_id,
        after={"onboarding_id": onboarding_id, "action_ref": action_ref},
    )
    await repo.commit()
    return draft


# --------------------------------------------------------------------------
# Feedback, quality gate and human service playbook
# --------------------------------------------------------------------------


async def record_family_feedback(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    consent: ConsentQueryPort,
    *,
    booking_request_id: str,
    delivery_record_id: str,
    subject_person_id: str,
    author_role: FeedbackAuthorRole,
    outcome: FamilyFeedbackOutcome,
    issue_codes: list[FeedbackIssueCode],
    consent_ref: str,
) -> FamilyFeedback:
    """Record an adult's bounded response after a completed delivery."""
    _assert_service_context(ctx)
    assert_human_actor(ctx.actor, code="family_feedback")
    if any(code not in FEEDBACK_ISSUE_CODES for code in issue_codes):
        raise ServiceValidationError("family_feedback_issue_code_not_allowed")
    record = await repo.load_service_record(delivery_record_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=record.family_id)
    if record.source_booking_request_id != booking_request_id:
        raise ServiceValidationError("feedback_delivery_booking_mismatch")
    if record.status != "COMPLETED":
        raise ServiceConflictError("feedback_requires_completed_delivery")
    booking = await repo.load_booking(booking_request_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=booking.family_id)
    if booking.service_snapshot.get("subject_person_id") != subject_person_id:
        raise ServiceForbiddenError("feedback_subject_mismatch")

    grants = await consent.list_grants(
        tenant_id=ctx.tenant_id,
        subject_person_id=subject_person_id,
        purpose=BOOKING_CONSENT_PURPOSE,
    )
    matching_grant = next(
        (
            grant
            for grant in grants
            if grant.consent_id == consent_ref and grant.guardian_person_id == ctx.actor_person_id
        ),
        None,
    )
    if matching_grant is None or not ConsentGate.check(
        subject_person_id, BOOKING_CONSENT_PURPOSE, grants
    ):
        raise ServiceForbiddenError(
            f"consent_required:{BOOKING_CONSENT_PURPOSE.value}:{subject_person_id}"
        )

    # The live Consent check must precede an idempotent replay; otherwise a
    # withdrawn grant could be bypassed by repeating the old feedback key.
    if ctx.idempotency_key:
        existing = await repo.find_feedback_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            if (
                existing.booking_request_id != booking_request_id
                or existing.delivery_record_id != delivery_record_id
                or existing.outcome != outcome
                or existing.author_person_id != ctx.actor_person_id
                or existing.author_role != author_role
                or existing.consent_ref != consent_ref
                or sorted(existing.issue_codes) != sorted(issue_codes)
            ):
                raise ServiceConflictError("family_feedback_idempotency_replay_mismatch")
            return existing

    now = utcnow()
    feedback = FamilyFeedback(
        family_feedback_id=_new_id("svcfeedback"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        booking_request_id=booking_request_id,
        delivery_record_id=delivery_record_id,
        author_person_id=ctx.actor_person_id,
        author_role=author_role,
        outcome=outcome,
        issue_codes=issue_codes,
        consent_ref=consent_ref,
        idempotency_key=ctx.idempotency_key,
        correlation_id=ctx.correlation_id,
        occurred_at=now,
        created_at=now,
        created_by=ctx.actor,
        environment=ctx.environment,
    )
    await repo.save_family_feedback(feedback)
    _audit(
        recorder,
        ctx,
        action="record_family_feedback",
        resource_type=FEEDBACK_RESOURCE,
        resource_id=feedback.family_feedback_id,
        after={"outcome": outcome, "issue_codes": issue_codes},
    )
    await _event(
        repo,
        ctx,
        event_type="service.family_feedback_recorded.v1",
        aggregate_type=FEEDBACK_RESOURCE,
        aggregate_id=feedback.family_feedback_id,
        idempotency_key=_event_key(ctx, "record_family_feedback", feedback.family_feedback_id),
        payload={
            "booking_request_id": booking_request_id,
            "delivery_record_id": delivery_record_id,
            "outcome": outcome,
            "issue_codes": issue_codes,
            "scenario_ref": booking.service_snapshot.get("scenario_ref"),
            "outcome_ref": booking.service_snapshot.get("outcome_ref"),
        },
        occurred_at=now,
    )
    await repo.commit()
    return feedback


async def decide_service_quality(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    booking_request_id: str,
    delivery_record_id: str,
    status: QualityDecisionStatus,
    family_feedback_id: str | None = None,
) -> QualityDecision:
    """Apply the human acceptance gate; never release contribution or cash."""
    _assert_service_context(ctx)
    assert_human_actor(ctx.actor, code="quality_decision")
    if ctx.idempotency_key:
        existing = await repo.find_quality_decision_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            if (
                existing.status != status
                or existing.booking_request_id != booking_request_id
                or existing.delivery_record_id != delivery_record_id
                or existing.family_feedback_id != family_feedback_id
            ):
                raise ServiceConflictError("quality_decision_idempotency_replay_mismatch")
            return existing

    record = await repo.load_service_record(delivery_record_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=record.family_id)
    if record.source_booking_request_id != booking_request_id:
        raise ServiceValidationError("quality_delivery_booking_mismatch")
    if record.status != "COMPLETED":
        raise ServiceConflictError("quality_decision_requires_completed_delivery")
    booking = await repo.load_booking(booking_request_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=booking.family_id)

    feedback = None
    if family_feedback_id is not None:
        feedback = await repo.load_family_feedback(family_feedback_id)
        assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=feedback.family_id)
        if feedback.delivery_record_id != delivery_record_id:
            raise ServiceValidationError("quality_feedback_delivery_mismatch")
        if feedback.booking_request_id != booking_request_id:
            raise ServiceValidationError("quality_feedback_booking_mismatch")
        if feedback.outcome == "NOT_HELPFUL_YET" and status == "ACCEPTED":
            raise ServiceConflictError("not_helpful_feedback_requires_remedy")

    now = utcnow()
    decision = QualityDecision(
        quality_decision_id=_new_id("svcquality"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        booking_request_id=booking_request_id,
        delivery_record_id=delivery_record_id,
        family_feedback_id=family_feedback_id,
        status=status,
        decided_by=ctx.actor,
        idempotency_key=ctx.idempotency_key,
        correlation_id=ctx.correlation_id,
        decided_at=now,
        created_at=now,
        created_by=ctx.actor,
        environment=ctx.environment,
    )
    await repo.save_quality_decision(decision)
    _audit(
        recorder,
        ctx,
        action="decide_service_quality",
        resource_type=QUALITY_RESOURCE,
        resource_id=decision.quality_decision_id,
        after={"status": status, "contribution_eligible": decision.contribution_eligible},
    )
    await _event(
        repo,
        ctx,
        event_type="service.quality_decided.v1",
        aggregate_type=QUALITY_RESOURCE,
        aggregate_id=decision.quality_decision_id,
        idempotency_key=_event_key(ctx, "decide_service_quality", decision.quality_decision_id),
        payload={
            "booking_request_id": booking_request_id,
            "delivery_record_id": delivery_record_id,
            "status": status,
            "contribution_eligible": decision.contribution_eligible,
            "scenario_ref": booking.service_snapshot.get("scenario_ref"),
            "outcome_ref": booking.service_snapshot.get("outcome_ref"),
        },
        occurred_at=now,
    )
    await repo.commit()
    return decision


async def record_service_action(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    *,
    booking_request_id: str,
    action_type: ServiceActionType,
    delivery_record_id: str | None = None,
    family_feedback_id: str | None = None,
    sla_due_at: datetime | None = None,
    occurred_at: datetime | None = None,
) -> ServiceAction:
    """Execute one human Named Action from the welcome/SLA/remedy playbook."""
    _assert_service_context(ctx)
    assert_human_actor(ctx.actor, code="service_action")
    if action_type not in SERVICE_ACTION_TYPES:
        raise ServiceValidationError("service_action_type_not_allowed")
    if ctx.idempotency_key:
        existing = await repo.find_service_action_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            if (
                existing.action_type != action_type
                or existing.booking_request_id != booking_request_id
                or existing.delivery_record_id != delivery_record_id
                or existing.family_feedback_id != family_feedback_id
                or existing.sla_due_at != sla_due_at
            ):
                raise ServiceConflictError("service_action_idempotency_replay_mismatch")
            return existing

    booking = await repo.load_booking(booking_request_id)
    assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=booking.family_id)
    if booking.status in ("CANCELLED", "EXPIRED"):
        raise ServiceConflictError("service_action_requires_live_booking")
    if delivery_record_id is not None:
        record = await repo.load_service_record(delivery_record_id)
        assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=record.family_id)
        if record.source_booking_request_id != booking_request_id:
            raise ServiceValidationError("service_action_delivery_booking_mismatch")
        if (
            action_type
            in (
                "FOLLOW_UP",
                "REMEDY_REWORK",
                "REMEDY_REASSIGN",
                "REFUND_REQUESTED",
            )
            and record.status != "COMPLETED"
        ):
            raise ServiceConflictError("service_action_requires_completed_delivery")
    if family_feedback_id is not None:
        feedback = await repo.load_family_feedback(family_feedback_id)
        assert_family_scope(expected_family_id=ctx.family_id, actual_family_id=feedback.family_id)
        if feedback.booking_request_id != booking_request_id:
            raise ServiceValidationError("service_action_feedback_booking_mismatch")
        if delivery_record_id is not None and feedback.delivery_record_id != delivery_record_id:
            raise ServiceValidationError("service_action_feedback_delivery_mismatch")

    now = occurred_at or utcnow()
    action = ServiceAction(
        service_action_id=_new_id("svcaction"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        booking_request_id=booking_request_id,
        delivery_record_id=delivery_record_id,
        family_feedback_id=family_feedback_id,
        action_type=action_type,
        sla_due_at=sla_due_at,
        occurred_at=now,
        actor_person_id=ctx.actor_person_id,
        idempotency_key=ctx.idempotency_key,
        correlation_id=ctx.correlation_id,
        created_at=now,
        created_by=ctx.actor,
        environment=ctx.environment,
    )
    await repo.save_service_action(action)
    _audit(
        recorder,
        ctx,
        action=f"service_action:{action_type.lower()}",
        resource_type=ACTION_RESOURCE,
        resource_id=action.service_action_id,
        after={"action_type": action_type, "sla_met": action.sla_met},
    )
    await _event(
        repo,
        ctx,
        event_type=f"service.action_{action_type.lower()}.v1",
        aggregate_type=ACTION_RESOURCE,
        aggregate_id=action.service_action_id,
        idempotency_key=_event_key(ctx, "record_service_action", action.service_action_id),
        payload={
            "booking_request_id": booking_request_id,
            "delivery_record_id": delivery_record_id,
            "family_feedback_id": family_feedback_id,
            "action_type": action_type,
            "sla_met": action.sla_met,
            "scenario_ref": booking.service_snapshot.get("scenario_ref"),
            "outcome_ref": booking.service_snapshot.get("outcome_ref"),
        },
        occurred_at=now,
    )
    await repo.commit()
    return action
