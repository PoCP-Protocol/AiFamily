"""Read-side functions behind the SERVICE GET endpoints.

Every family-scoped query takes `(tenant_id, family_id)` as keyword arguments
derived from the authenticated context — never from a path or query parameter.
That is what makes cross-family reads unreachable rather than merely
unauthorised.

The offerings/slots queries are tenant-scoped and carry no family facts: supply
is what a tenant sells, and returning it does not disclose anything about any
family.
"""

from __future__ import annotations

from .ports import ServiceRepositoryPort
from .read_models import (
    BookingProjectionRow,
    CheckinDraftView,
    CustomerProjection,
    OfferingView,
    ServiceJourneyView,
    SlotView,
)


async def list_activity_catalog(repo: ServiceRepositoryPort) -> list[dict]:
    """UI-22/UI-23 catalog projection; browsing does not create attendance."""
    return [
        {
            "activity_ref": item.activity_ref,
            "title": item.title,
            "summary": item.attributes.get("summary", ""),
            "age_hint": item.attributes.get("age_hint", ""),
            "detail_route": item.attributes.get("detail_route", "activity-detail"),
            "starts_at": item.starts_at,
            "activity_kind": item.activity_kind,
            "location": item.attributes.get("location", ""),
        }
        for item in sorted(
            (item for item in await repo.list_activities() if item.is_admitted),
            key=lambda item: item.starts_at,
        )
    ]


async def list_service_offerings(
    repo: ServiceRepositoryPort, *, tenant_id: str
) -> list[OfferingView]:
    """UI-19 browse. Only bookable supply is returned.

    Filtering here rather than in the client is the point: a RETIRED offering
    that reaches the browse screen is a family being invited to book something
    that cannot be delivered.
    """
    offerings = [o for o in await repo.list_offerings(tenant_id) if o.is_bookable]
    slots = await repo.list_slots(tenant_id)
    views: list[OfferingView] = []
    for offering in offerings:
        provider = await repo.load_provider(offering.provider_id)
        if not provider.is_bookable:
            continue
        own_slots = [s for s in slots if s.service_offering_id == offering.service_offering_id]
        views.append(
            OfferingView(
                service_offering_id=offering.service_offering_id,
                service_offering_ref=offering.service_offering_ref,
                version_no=offering.version_no,
                title=offering.title,
                provider_id=provider.provider_id,
                provider_display_name=provider.display_name,
                provider_kind=provider.provider_kind,
                channel_options=sorted({s.channel for s in own_slots}),
                open_slot_count=sum(1 for s in own_slots if s.is_open),
            )
        )
    return views


async def list_availability_slots(
    repo: ServiceRepositoryPort, *, tenant_id: str, service_offering_id: str | None = None
) -> list[SlotView]:
    """UI-20/21 slot picker. Every slot in scope, open or not.

    Closed slots are returned rather than filtered out so the picker can grey
    them out; a picker that only receives open slots cannot show a family that
    the 10:00 they wanted is gone, and silently omitting it looks like the slot
    never existed.
    """
    slots = await repo.list_slots(tenant_id, service_offering_id=service_offering_id)
    return [
        SlotView(
            availability_slot_id=s.availability_slot_id,
            availability_slot_ref=s.availability_slot_ref,
            service_offering_id=s.service_offering_id,
            starts_at=s.starts_at,
            ends_at=s.ends_at,
            channel=s.channel,
            status=s.status,
            capacity=s.capacity,
            remaining_capacity=max(s.capacity - s.reserved_count, 0),
        )
        for s in slots
    ]


async def _projection_rows(
    repo: ServiceRepositoryPort, *, tenant_id: str, family_id: str
) -> list[BookingProjectionRow]:
    """Assembles what `family_customer_service_booking_projection_v` selects.

    Done in Python rather than by querying the view: the view is Postgres-only
    (0035 defines it with `CREATE OR REPLACE VIEW`) and the SQLite fast test path
    has no such object, so a repository method reading the view would be
    untestable on the default path. The column list is kept in step with the view
    deliberately — see `read_models.BookingProjectionRow`.
    """
    bookings = await repo.list_bookings(tenant_id, family_id)
    records = {
        r.source_booking_request_id: r
        for r in await repo.list_service_records(tenant_id, family_id)
    }
    rows: list[BookingProjectionRow] = []
    for booking in sorted(bookings, key=lambda b: b.created_at, reverse=True):
        record = records.get(booking.booking_request_id)
        snapshot = booking.service_snapshot
        slot = await repo.load_slot(booking.availability_slot_id)
        rows.append(
            BookingProjectionRow(
                booking_request_id=booking.booking_request_id,
                booking_ref=booking.booking_ref,
                booking_status=booking.status,
                # From the snapshot, not from a live re-read of the offering:
                # the family booked a specific version, and showing today's title
                # for yesterday's booking rewrites history in the UI.
                service_offering_ref=snapshot.get("service_offering_ref", ""),
                availability_slot_ref=slot.availability_slot_ref,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                channel=slot.channel,
                booking_service_record_id=(
                    None if record is None else record.booking_service_record_id
                ),
                service_record_status=None if record is None else record.status,
                service_quality_rating=None if record is None else record.service_quality_rating,
                environment=booking.environment,
                source_system=booking.source_system,
                external_effect=booking.external_effect,
            )
        )
    return rows


async def get_customer_projection(
    repo: ServiceRepositoryPort, *, tenant_id: str, family_id: str
) -> CustomerProjection:
    """UI-24 我的预约."""
    return CustomerProjection(
        family_id=family_id,
        bookings=await _projection_rows(repo, tenant_id=tenant_id, family_id=family_id),
    )


async def get_service_journey(
    repo: ServiceRepositoryPort, *, tenant_id: str, family_id: str, onboarding_id: str
) -> ServiceJourneyView:
    """UI-06 服务旅程 — bookings plus the family's own private check-in drafts."""
    drafts = await repo.list_checkin_drafts(tenant_id, family_id, onboarding_id=onboarding_id)
    return ServiceJourneyView(
        family_id=family_id,
        onboarding_id=onboarding_id,
        bookings=await _projection_rows(repo, tenant_id=tenant_id, family_id=family_id),
        checkin_drafts=[
            CheckinDraftView(
                private_checkin_draft_id=d.private_checkin_draft_id,
                onboarding_id=d.onboarding_id,
                action_ref=d.action_ref,
                occurred_at=d.occurred_at,
            )
            for d in sorted(drafts, key=lambda d: d.occurred_at)
        ],
    )
