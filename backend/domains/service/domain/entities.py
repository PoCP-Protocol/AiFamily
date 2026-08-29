"""Service booking entities.

Field names mirror `database/baseline/0035_family_service_booking_objects.sql`
column-for-column, so the Python side and the SQL SSOT cannot drift. Direction
of authority is SQL → Python: `0035` is a baselined historical artefact and is
not editable, so where the two disagree the SQL wins and this module is wrong.

No FastAPI / SQLAlchemy import here (four-layer rule,
`docs/10_engineering/ENGINEERING_ARCHITECTURE.md`).

Two structural notes, both load-bearing rather than stylistic:

* **No field anywhere scores a family or a child.** `ServiceRecord` carries
  `service_quality_rating`, which rates the *provider's delivered session* —
  the customer evaluating the vendor. See `value_objects.ServiceQualityRating`
  for the argument, and `policies.assert_no_family_scoring_semantics` for the
  guard on the untyped `attributes` escape hatch.
* **State transitions are methods, not setters.** Every one returns a new copy
  with `row_version` bumped, refuses an illegal source state, and refuses an
  `ai:` actor for the transitions that commit a human being's time. A caller
  cannot reach a status by assignment.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, model_validator

from .errors import ServiceConflictError, ServiceValidationError
from .policies import (
    assert_booking_source_page,
    assert_fixture_boundary,
    assert_human_actor,
    assert_no_family_scoring_semantics,
)
from .value_objects import (
    AdmissionStatus,
    BookingSourcePageId,
    BookingSourceSystem,
    BookingStatus,
    Channel,
    Environment,
    OfferingStatus,
    ProviderKind,
    ProviderStatus,
    QualificationStatus,
    ScopeType,
    ServiceQualityRating,
    ServiceRecordSourceSystem,
    ServiceRecordStatus,
    SlotStatus,
)


def utcnow() -> datetime:
    """Naive UTC, matching membership's `entities.utcnow`.

    The SQL columns are `timestamptz`, but the SQLite engine the fast test path
    uses drops tzinfo silently, so an aware value would compare unequal to its
    own round-trip.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class _Extensible(BaseModel):
    """`attributes_schema_version` + `attributes jsonb`, as in the 0035 DDL."""

    attributes_schema_version: int = 1
    attributes: dict = {}

    @model_validator(mode="after")
    def _check_attributes(self):
        assert_no_family_scoring_semantics(self.attributes)
        return self


class _Audited(BaseModel):
    row_version: int = 1
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class _SupplyMaster(BaseModel):
    """`fixture_only boolean NOT NULL CHECK (fixture_only = true)`.

    Supply masters have no `environment` column in 0035 — the DDL pins them with
    `fixture_only` instead. Re-asserted here so the invariant survives the
    SQLite path and the in-memory fake, neither of which enforces a CHECK the
    way Postgres does.
    """

    fixture_only: bool = True

    @model_validator(mode="after")
    def _check_fixture_only(self):
        if not self.fixture_only:
            raise ServiceValidationError("supply_must_be_fixture_only")
        return self


class _FixtureBoundary(BaseModel):
    """R5 production boundary as a domain invariant, not only a DB CHECK.

    `_allowed_source_system` is a class-level constant rather than a field:
    a booking request is a `TEST_FIXTURE` and a service record comes from the
    `TEST_NOOP_ADAPTER`, and letting one claim the other's provenance is exactly
    what a single shared vocabulary would permit.
    """

    _allowed_source_system: str = "TEST_FIXTURE"

    environment: Environment
    external_effect: bool = False

    @model_validator(mode="after")
    def _check_boundary(self):
        assert_fixture_boundary(
            environment=self.environment,
            source_system=self.source_system,  # type: ignore[attr-defined]
            external_effect=self.external_effect,
            allowed_source_system=self._allowed_source_system,
        )
        return self


# --------------------------------------------------------------------------
# Supply masters (PLATFORM / TENANT scope — never hold Family facts)
# --------------------------------------------------------------------------


class ServiceProvider(_Extensible, _Audited, _SupplyMaster):
    """`family_service_providers` (0035).

    Qualification and admission are two separate statuses on purpose: a teacher
    whose certificate expired (`qualification_status = EXPIRED`) and a teacher
    who was suspended from the platform (`admission_status = SUSPENDED`) are
    different facts with different remedies, and collapsing them into one
    "active?" flag loses which one to fix.
    """

    provider_id: str
    scope_type: ScopeType = "TENANT"
    tenant_id: str | None = None
    provider_ref: str
    display_name: str
    provider_kind: ProviderKind
    qualification_ref: str | None = None
    qualification_status: QualificationStatus
    admission_status: AdmissionStatus
    source_ref: str
    status: ProviderStatus = "ACTIVE"
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def _check_scope(self):
        # `family_service_provider_scope_ck`
        if self.scope_type == "PLATFORM" and self.tenant_id is not None:
            raise ServiceValidationError("platform_provider_must_not_have_tenant")
        if self.scope_type == "TENANT" and self.tenant_id is None:
            raise ServiceValidationError("tenant_provider_requires_tenant")
        # `family_service_provider_effective_ck`
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ServiceValidationError("provider_effective_window_invalid")
        return self

    @property
    def is_bookable(self) -> bool:
        """A provider may only back a booking while all three hold at once.

        Expressed as a property rather than three checks at the call site so a
        second call site cannot enforce two of the three.
        """
        return (
            self.status == "ACTIVE"
            and self.qualification_status == "ACTIVE"
            and self.admission_status == "ADMITTED"
        )


class ServiceOffering(_Extensible, _Audited, _SupplyMaster):
    """`family_service_offerings` (0035). Versioned, bound to one provider.

    `tenant_id` is NOT NULL here even though a provider may be PLATFORM-scope:
    an offering is always something a tenant sells, so a PLATFORM provider can
    back offerings in several tenants without the offering itself being global.
    """

    service_offering_id: str
    tenant_id: str
    provider_id: str
    service_offering_ref: str
    version_no: int = 1
    title: str
    admission_status: AdmissionStatus
    source_ref: str
    status: OfferingStatus = "ACTIVE"
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self):
        if self.version_no < 1:
            raise ServiceValidationError("offering_version_no_must_be_positive")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ServiceValidationError("offering_effective_window_invalid")
        return self

    @property
    def is_bookable(self) -> bool:
        return self.status == "ACTIVE" and self.admission_status == "ADMITTED"


class AvailabilitySlot(_Extensible, _SupplyMaster):
    """`family_service_availability_slots` (0035).

    Capacity is a counter, not a boolean, because the DDL says so
    (`reserved_count <= capacity`) — a salon host takes several families in one
    window. `reserve()` is the only way the counter moves, so "the slot is full"
    is decided in one place instead of at every caller.

    No `created_by` / `updated_by` here: 0035 gives this table `created_at` /
    `updated_at` only. Slot inventory is opened by an operator process, and
    inventing actor columns the SQL does not have is the drift this module
    exists to prevent.
    """

    availability_slot_id: str
    tenant_id: str
    provider_id: str
    service_offering_id: str
    availability_slot_ref: str
    starts_at: datetime
    ends_at: datetime
    channel: Channel
    capacity: int = 1
    reserved_count: int = 0
    status: SlotStatus = "AVAILABLE"
    row_version: int = 1
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _check_window_and_capacity(self):
        # `family_service_slot_window_ck`
        if self.ends_at <= self.starts_at:
            raise ServiceValidationError("slot_window_invalid")
        if self.capacity < 1:
            raise ServiceValidationError("slot_capacity_must_be_positive")
        if not 0 <= self.reserved_count <= self.capacity:
            raise ServiceValidationError("slot_reserved_count_out_of_range")
        return self

    @property
    def is_open(self) -> bool:
        return self.status == "AVAILABLE" and self.reserved_count < self.capacity

    def reserve(self) -> AvailabilitySlot:
        """Take one unit of capacity. Refuses a full or non-AVAILABLE slot.

        Raises `ServiceConflictError` rather than returning a flag: "the slot
        was taken" is a 409, and a boolean return is a thing a caller can
        forget to check.
        """
        if self.status != "AVAILABLE":
            raise ServiceConflictError(f"slot_not_available:{self.status}")
        if self.reserved_count >= self.capacity:
            raise ServiceConflictError("slot_capacity_exhausted")
        taken = self.reserved_count + 1
        return self.model_copy(
            update={
                "reserved_count": taken,
                # RESERVED means "no more capacity", not "somebody booked it" —
                # a capacity-3 slot with one booking is still AVAILABLE.
                "status": "RESERVED" if taken == self.capacity else "AVAILABLE",
                "updated_at": utcnow(),
                "row_version": self.row_version + 1,
            }
        )

    def release(self) -> AvailabilitySlot:
        """Give one unit of capacity back (booking cancelled)."""
        if self.reserved_count <= 0:
            raise ServiceConflictError("slot_has_no_reservation_to_release")
        if self.status in ("BLOCKED", "EXPIRED"):
            raise ServiceConflictError(f"slot_not_releasable:{self.status}")
        return self.model_copy(
            update={
                "reserved_count": self.reserved_count - 1,
                "status": "AVAILABLE",
                "updated_at": utcnow(),
                "row_version": self.row_version + 1,
            }
        )


# --------------------------------------------------------------------------
# Family transaction facts
# --------------------------------------------------------------------------


class BookingRequest(_Extensible, _Audited, _FixtureBoundary):
    """`family_booking_requests` (0035).

    Named "request", and the 0035 table comment says why: *"Family-scoped
    booking intent; it is not a confirmed real-world appointment."* Nothing in
    this chain notifies the provider, writes a calendar, or takes money. A
    `CONFIRMED` status means an operator acknowledged the intent inside this
    system, and the fixture boundary (`external_effect = false`) makes that
    claim structurally honest.

    `consent_ref` is NOT NULL in the DDL and non-empty here: the person being
    served may be a minor, so booking is sensitive-information processing under
    `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §1. The reference to the
    consent that permitted it is part of the fact, not metadata beside it.
    """

    _allowed_source_system: str = "TEST_FIXTURE"

    booking_request_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    booking_ref: str
    service_offering_id: str
    availability_slot_id: str
    source_page_id: BookingSourcePageId
    consent_ref: str
    status: BookingStatus = "DRAFT"
    service_snapshot: dict = {}
    source_system: BookingSourceSystem = "TEST_FIXTURE"
    correlation_id: str
    idempotency_key: str | None = None
    retention_class: str = "SERVICE_BOOKING_TEST"
    cancelled_at: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _check_invariants(self):
        assert_booking_source_page(self.source_page_id)
        if not self.consent_ref.strip():
            raise ServiceValidationError("booking_consent_ref_required")
        # `family_booking_cancelled_ck`
        if self.status == "CANCELLED" and self.cancelled_at is None:
            raise ServiceValidationError("cancelled_booking_requires_cancelled_at")
        assert_no_family_scoring_semantics(self.service_snapshot)
        return self

    def submit(self, *, actor: str) -> BookingRequest:
        """DRAFT → REQUESTED. The family's own act, so a human actor only."""
        assert_human_actor(actor, code="booking_submit")
        if self.status != "DRAFT":
            raise ServiceConflictError(f"booking_not_submittable:{self.status}")
        return self._advance("REQUESTED", actor)

    def confirm(self, *, actor: str) -> BookingRequest:
        """REQUESTED → CONFIRMED.

        Human-only: confirming commits a named provider's time, which is R8's
        high-impact class. An `ai:` actor is refused here, in the domain, so the
        refusal holds even for a call path that never passes through a route.
        """
        assert_human_actor(actor, code="booking_confirm")
        if self.status != "REQUESTED":
            raise ServiceConflictError(f"booking_not_confirmable:{self.status}")
        return self._advance("CONFIRMED", actor)

    def cancel(self, *, actor: str) -> BookingRequest:
        assert_human_actor(actor, code="booking_cancel")
        if self.status in ("CANCELLED", "EXPIRED"):
            raise ServiceConflictError(f"booking_not_cancellable:{self.status}")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "CANCELLED",
                "cancelled_at": now,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def _advance(self, status: BookingStatus, actor: str) -> BookingRequest:
        return self.model_copy(
            update={
                "status": status,
                "updated_at": utcnow(),
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )


class ServiceRecord(_Extensible, _Audited, _FixtureBoundary):
    """`family_booking_service_records` (0035). The delivery receipt.

    Produced by a no-op adapter (`source_system = TEST_NOOP_ADAPTER`), which is
    what makes "the service happened" a claim about this system's state rather
    than about the world.

    `service_quality_rating` is the one evaluative field in the whole domain and
    it points at the *provider's session*. It is not a family score: the subject
    is the vendor, the author is the customer, and the direction of power is the
    opposite of the one R9 exists to protect. The repo-wide checker
    (`tests/architecture/test_compliance_constraints.py`) stays green because
    the field name pairs no family/child subject with a scoring verb — the shape
    is right, not exempted.
    """

    _allowed_source_system: str = "TEST_NOOP_ADAPTER"

    booking_service_record_id: str
    tenant_id: str
    family_id: str
    source_booking_request_id: str
    status: ServiceRecordStatus = "PENDING"
    source_system: ServiceRecordSourceSystem = "TEST_NOOP_ADAPTER"
    service_quality_rating: ServiceQualityRating | None = None

    def schedule(self, *, actor: str) -> ServiceRecord:
        if self.status != "PENDING":
            raise ServiceConflictError(f"record_not_schedulable:{self.status}")
        return self._advance("SCHEDULED", actor)

    def complete(
        self, *, actor: str, quality_rating: ServiceQualityRating | None = None
    ) -> ServiceRecord:
        """Fulfilment. Human-only, and the terminal state of the chain.

        `quality_rating` is optional: a family that does not want to evaluate
        the session must still be able to close it, and a required rating would
        make "say nothing" impossible.
        """
        assert_human_actor(actor, code="record_complete")
        if self.status not in ("PENDING", "SCHEDULED"):
            raise ServiceConflictError(f"record_not_completable:{self.status}")
        return self._advance("COMPLETED", actor, quality_rating=quality_rating)

    def cancel(self, *, actor: str) -> ServiceRecord:
        if self.status in ("CANCELLED", "COMPLETED"):
            raise ServiceConflictError(f"record_not_cancellable:{self.status}")
        return self._advance("CANCELLED", actor)

    def _advance(
        self,
        status: ServiceRecordStatus,
        actor: str,
        *,
        quality_rating: ServiceQualityRating | None = None,
    ) -> ServiceRecord:
        update: dict = {
            "status": status,
            "updated_at": utcnow(),
            "updated_by": actor,
            "row_version": self.row_version + 1,
        }
        if quality_rating is not None:
            update["service_quality_rating"] = quality_rating
        return self.model_copy(update=update)


class PrivateCheckinDraft(_Extensible, _FixtureBoundary):
    """UI-06 §4.1 私密复盘草稿 — the `createPrivateCheckinDraft` endpoint's object.

    Append-only and deliberately **not** persisted to `0035`: 0035 has no table
    for it, and inventing one inside this domain is the `product_intelligence`
    mistake T-03 recorded (a private SQL copy whose columns the baseline never
    had). Its own revision creates `family_service_private_checkin_drafts`; see
    `database/migrations/versions/0003_service_booking_additions.py`.

    "Private" is the whole point: the draft carries an allow-listed
    `action_ref` and **no free-text field**. An allow-list cannot carry a child
    fact; a free-text box can, and would put unreviewed minor data into a
    record whose retention nobody scoped. Widening this to free text needs a
    consent-purpose and retention decision first, which is an ADR, not a field.
    """

    _allowed_source_system: str = "TEST_FIXTURE"

    private_checkin_draft_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    onboarding_id: str
    action_ref: str
    source_system: BookingSourceSystem = "TEST_FIXTURE"
    correlation_id: str
    idempotency_key: str | None = None
    occurred_at: datetime
    created_at: datetime
    created_by: str
