"""SQLAlchemy ORM models for the service booking chain.

Column names and nullability mirror the SQL SSOT exactly:

* `database/baseline/0035_family_service_booking_objects.sql` — providers,
  offerings, availability_slots, booking_requests, booking_service_records. This
  Python side maps onto the **existing** tables rather than creating a parallel
  set, so there is one schema per concept.
* `database/migrations/versions/0003_service_private_checkin_drafts.py` — the
  one genuinely new table (`family_service_private_checkin_drafts`), plus the
  one column 0035 lacks that this domain needs
  (`family_booking_service_records.service_quality_rating`).

There is deliberately **no** `subject_person_id` column on
`family_booking_requests`. The subject is supplied to
`submit_booking_request` for the consent check and is not persisted on the
booking row: 0035 does not have the column, and storing "which child this
booking is about" is a data-minimisation decision (PIPL 第6条) that needs its own
retention scoping, not a column added in passing. The consent reference that
permitted the booking *is* stored (`consent_ref`), which is what makes the
booking auditable without holding the child's identity on every commercial row.

**The T-03 lesson is the rule here**: `product_intelligence` kept a private SQL
copy inside the domain, so ORM columns existed that the Alembic baseline never
created, and its tests never caught it because they built their own schema.
Every column below therefore either exists in baselined `0035` or is added by
that new revision. There is no third source. Adding a column to this module
without adding it to a migration reintroduces exactly that failure.

Types are widened — `uuid` → `String`, `jsonb` → `JSON`, `timestamptz` →
`DateTime` — so the same models run against both real Postgres and the
in-memory SQLite engine the fast test path uses. Same approach and same accepted
gap as `membership` and `product_intelligence`: the widening means the SQLite
pass proves the mapping, and `tests/domains/service/conftest.py::postgres_repo`
is what proves it on the database production uses.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON

Base = declarative_base()


class ServiceProviderRow(Base):
    __tablename__ = "family_service_providers"
    provider_id = Column(String, primary_key=True)
    scope_type = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)
    provider_ref = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    provider_kind = Column(String, nullable=False)
    qualification_ref = Column(String, nullable=True)
    qualification_status = Column(String, nullable=False)
    admission_status = Column(String, nullable=False)
    source_ref = Column(String, nullable=False)
    fixture_only = Column(Boolean, nullable=False, default=True)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    status = Column(String, nullable=False)
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=True)


class ServiceOfferingRow(Base):
    __tablename__ = "family_service_offerings"
    service_offering_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    provider_id = Column(String, nullable=False)
    service_offering_ref = Column(String, nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=False)
    admission_status = Column(String, nullable=False)
    source_ref = Column(String, nullable=False)
    fixture_only = Column(Boolean, nullable=False, default=True)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    status = Column(String, nullable=False)
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=True)


class AvailabilitySlotRow(Base):
    """Note the absence of `created_by` / `updated_by`: 0035 does not give this
    table actor columns, and inventing them would be the drift this module
    exists to prevent."""

    __tablename__ = "family_service_availability_slots"
    availability_slot_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    provider_id = Column(String, nullable=False)
    service_offering_id = Column(String, nullable=False)
    availability_slot_ref = Column(String, nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    channel = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False, default=1)
    reserved_count = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False)
    fixture_only = Column(Boolean, nullable=False, default=True)
    attributes = Column(JSON, nullable=False, default=dict)
    # `attributes_schema_version` is added by the new revision. 0035 gave this
    # one table `attributes` without a schema version while giving it to all
    # four others — an inconsistency in the legacy DDL, not a design. It is
    # added rather than dropped from the entity so the whole chain versions its
    # extensibility the same way.
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class BookingRequestRow(Base):
    __tablename__ = "family_booking_requests"
    booking_request_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    booking_ref = Column(String, nullable=False)
    service_offering_id = Column(String, nullable=False)
    availability_slot_id = Column(String, nullable=False)
    source_page_id = Column(String, nullable=False)
    consent_ref = Column(String, nullable=False)
    status = Column(String, nullable=False)
    service_snapshot = Column(JSON, nullable=False, default=dict)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    correlation_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    retention_class = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)
    cancelled_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)


class ServiceRecordRow(Base):
    """`service_quality_rating` is added by the new revision, not present in
    0035. It rates the provider's delivered session — see
    `domain/entities.py::ServiceRecord` for why that is not an R9 violation."""

    __tablename__ = "family_booking_service_records"
    booking_service_record_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    source_booking_request_id = Column(String, nullable=False)
    status = Column(String, nullable=False)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    service_quality_rating = Column(String, nullable=True)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)


class PrivateCheckinDraftRow(Base):
    """Append-only. No `updated_at` / `updated_by` columns exist on purpose —
    the row cannot be edited, so there is nothing to record about an edit.

    No free-text column either: `action_ref` is allow-listed. See
    `domain/entities.py::PrivateCheckinDraft` for why widening this needs an ADR
    rather than a migration.
    """

    __tablename__ = "family_service_private_checkin_drafts"
    private_checkin_draft_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    onboarding_id = Column(String, nullable=False)
    action_ref = Column(String, nullable=False)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    correlation_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    occurred_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
