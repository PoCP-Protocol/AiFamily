"""In-memory `ServiceRepositoryPort` / `ConsentQueryPort` implementations.

Exists so the application layer can be exercised without SQLAlchemy, and so the
acceptance chain runs against two independent persistence shapes — proving the
commands depend on the port rather than on a particular ORM quirk (the
dual-repository convention `product_intelligence` established and `membership`
followed).

`commit()` is a no-op here: there is no transaction to close. That is a real
difference from the SQLAlchemy repository and is precisely why the SQLite pass
exists as well.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.platform.consent.models import ConsentGrant, ConsentPurpose

from ..domain.entities import (
    AvailabilitySlot,
    BookingRequest,
    PrivateCheckinDraft,
    ServiceOffering,
    ServiceProvider,
    ServiceRecord,
)
from ..domain.errors import ServiceNotFoundError


class FakeConsentQuery:
    """Consent grants held in a dict, keyed by nothing — filtered on every call.

    Filtering rather than caching a per-subject answer is deliberate: `withdraw`
    mutates the stored grant and the very next `list_grants` reflects it, which
    is the behaviour `ConsentGate` exists to preserve. A fake that memoised the
    allow decision would make the "withdrawal takes effect immediately" test
    pass for the wrong reason.
    """

    def __init__(self) -> None:
        self.grants: list[ConsentGrant] = []

    def add(self, grant: ConsentGrant) -> None:
        self.grants.append(grant)

    def withdraw(self, consent_id: str) -> None:
        from backend.platform.consent.models import ConsentStatus

        self.grants = [
            (
                g
                if g.consent_id != consent_id
                else ConsentGrant(
                    consent_id=g.consent_id,
                    subject_person_id=g.subject_person_id,
                    guardian_person_id=g.guardian_person_id,
                    purpose=g.purpose,
                    status=ConsentStatus.WITHDRAWN,
                    granted_at=g.granted_at,
                )
            )
            for g in self.grants
        ]

    async def list_grants(
        self, *, tenant_id: str, subject_person_id: str, purpose: ConsentPurpose
    ) -> Sequence[ConsentGrant]:
        return [
            g
            for g in self.grants
            if g.subject_person_id == subject_person_id and g.purpose is purpose
        ]


class FakeServiceRepository:
    def __init__(self) -> None:
        self.providers: dict[str, ServiceProvider] = {}
        self.offerings: dict[str, ServiceOffering] = {}
        self.slots: dict[str, AvailabilitySlot] = {}
        self.bookings: dict[str, BookingRequest] = {}
        self.service_records: dict[str, ServiceRecord] = {}
        self.checkin_drafts: dict[str, PrivateCheckinDraft] = {}

    async def commit(self) -> None:
        return None

    @staticmethod
    def _scoped(store: dict, tenant_id: str, family_id: str) -> list:
        return [e for e in store.values() if e.tenant_id == tenant_id and e.family_id == family_id]

    @staticmethod
    def _by_key(store: dict, tenant_id: str, family_id: str, key: str):
        for entity in store.values():
            if (
                entity.tenant_id == tenant_id
                and entity.family_id == family_id
                and entity.idempotency_key == key
            ):
                return entity
        return None

    # -- supply masters --
    async def save_provider(self, entity: ServiceProvider) -> None:
        self.providers[entity.provider_id] = entity

    async def load_provider(self, provider_id: str) -> ServiceProvider:
        if provider_id not in self.providers:
            raise ServiceNotFoundError("service_provider_not_found")
        return self.providers[provider_id]

    async def save_offering(self, entity: ServiceOffering) -> None:
        self.offerings[entity.service_offering_id] = entity

    async def load_offering(self, service_offering_id: str) -> ServiceOffering:
        if service_offering_id not in self.offerings:
            raise ServiceNotFoundError("service_offering_not_found")
        return self.offerings[service_offering_id]

    async def list_offerings(self, tenant_id: str) -> list[ServiceOffering]:
        return [o for o in self.offerings.values() if o.tenant_id == tenant_id]

    # -- availability --
    async def save_slot(self, entity: AvailabilitySlot) -> None:
        self.slots[entity.availability_slot_id] = entity

    async def load_slot(self, availability_slot_id: str) -> AvailabilitySlot:
        if availability_slot_id not in self.slots:
            raise ServiceNotFoundError("availability_slot_not_found")
        return self.slots[availability_slot_id]

    async def list_slots(
        self, tenant_id: str, *, service_offering_id: str | None = None
    ) -> list[AvailabilitySlot]:
        return [
            s
            for s in self.slots.values()
            if s.tenant_id == tenant_id
            and (service_offering_id is None or s.service_offering_id == service_offering_id)
        ]

    # -- booking requests --
    async def save_booking(self, entity: BookingRequest) -> None:
        self.bookings[entity.booking_request_id] = entity

    async def load_booking(self, booking_request_id: str) -> BookingRequest:
        if booking_request_id not in self.bookings:
            raise ServiceNotFoundError("booking_request_not_found")
        return self.bookings[booking_request_id]

    async def list_bookings(self, tenant_id: str, family_id: str) -> list[BookingRequest]:
        return self._scoped(self.bookings, tenant_id, family_id)

    async def find_booking_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BookingRequest | None:
        return self._by_key(self.bookings, tenant_id, family_id, idempotency_key)

    # -- service records --
    async def save_service_record(self, entity: ServiceRecord) -> None:
        self.service_records[entity.booking_service_record_id] = entity

    async def load_service_record(self, booking_service_record_id: str) -> ServiceRecord:
        if booking_service_record_id not in self.service_records:
            raise ServiceNotFoundError("service_record_not_found")
        return self.service_records[booking_service_record_id]

    async def find_service_record_for_booking(
        self, tenant_id: str, family_id: str, booking_request_id: str
    ) -> ServiceRecord | None:
        for record in self._scoped(self.service_records, tenant_id, family_id):
            if record.source_booking_request_id == booking_request_id:
                return record
        return None

    async def list_service_records(self, tenant_id: str, family_id: str) -> list[ServiceRecord]:
        return self._scoped(self.service_records, tenant_id, family_id)

    # -- private check-in drafts --
    async def append_checkin_draft(self, entity: PrivateCheckinDraft) -> None:
        self.checkin_drafts[entity.private_checkin_draft_id] = entity

    async def find_checkin_draft_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PrivateCheckinDraft | None:
        return self._by_key(self.checkin_drafts, tenant_id, family_id, idempotency_key)

    async def list_checkin_drafts(
        self, tenant_id: str, family_id: str, *, onboarding_id: str | None = None
    ) -> list[PrivateCheckinDraft]:
        return [
            d
            for d in self._scoped(self.checkin_drafts, tenant_id, family_id)
            if onboarding_id is None or d.onboarding_id == onboarding_id
        ]
