"""Read models for the four SERVICE read surfaces.

These are shapes the mobile client consumes, so they are declared once here
rather than assembled ad-hoc inside route bodies — a route that builds its own
dict is a contract nobody can diff.

What is absent is as deliberate as what is present:

* No aggregate over families. Not `bookings_by_family`, not
  `most_active_families`, not a completion percentage for a household. R9's
  不做家庭排名 is enforced by the read model not having a field for it, so a
  ranking screen cannot be assembled from this response.
* No `subject_person_id`. The customer projection tells a parent what they
  booked; it does not restate which child each row is about, because the
  booking row does not hold that (see `infrastructure/sqlalchemy_models.py`).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ..domain.value_objects import (
    BookingStatus,
    Channel,
    ServiceQualityRating,
    ServiceRecordStatus,
    SlotStatus,
)


class OfferingView(BaseModel):
    """One admitted offering, as shown on the browse surface (UI-19)."""

    service_offering_id: str
    service_offering_ref: str
    version_no: int
    title: str
    provider_id: str
    provider_display_name: str
    provider_kind: str
    channel_options: list[Channel] = []
    open_slot_count: int = 0


class SlotView(BaseModel):
    availability_slot_id: str
    availability_slot_ref: str
    service_offering_id: str
    starts_at: datetime
    ends_at: datetime
    channel: Channel
    status: SlotStatus
    capacity: int
    remaining_capacity: int


class BookingProjectionRow(BaseModel):
    """One row of `family_customer_service_booking_projection_v` (0035).

    Mirrors that view's column list rather than inventing a shape, so the
    read-through-a-view path and the read-through-the-repository path answer the
    same question the same way. `external_effect` and `source_system` are
    included deliberately: a client showing "your booking is confirmed" should be
    able to see that this is DEV/TEST supply, and hiding those two fields is how
    a fixture starts looking like a real appointment.
    """

    booking_request_id: str
    booking_ref: str
    booking_status: BookingStatus
    service_offering_ref: str
    availability_slot_ref: str
    starts_at: datetime
    ends_at: datetime
    channel: Channel
    booking_service_record_id: str | None = None
    service_record_status: ServiceRecordStatus | None = None
    service_quality_rating: ServiceQualityRating | None = None
    environment: str
    source_system: str
    external_effect: bool


class CustomerProjection(BaseModel):
    """UI-24 我的预约. Family-scoped, and there is no shape for another family."""

    family_id: str
    bookings: list[BookingProjectionRow] = []


class CheckinDraftView(BaseModel):
    private_checkin_draft_id: str
    onboarding_id: str
    action_ref: str
    occurred_at: datetime


class ServiceJourneyView(BaseModel):
    """UI-06 服务旅程.

    `checkin_drafts` are the family's own private selections. They are returned
    to the family that wrote them and to nobody else — the query is scoped by
    `(tenant_id, family_id)` and the port offers no other shape.
    """

    family_id: str
    onboarding_id: str
    bookings: list[BookingProjectionRow] = []
    checkin_drafts: list[CheckinDraftView] = []
