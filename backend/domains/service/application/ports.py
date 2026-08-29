"""Ports for the service booking chain.

Two ports, not one, and the split is the point.

`ServiceRepositoryPort` is persistence. `ConsentQueryPort` is the seam through
which the *current* consent grants for a subject are read on every booking —
`backend/platform/consent/gate.py`'s docstring requires exactly this ("that
repository must call `ConsentGate.check` with the *current* grants it just read,
not a cached list from an earlier request"). Giving consent its own port rather
than a `list_consent_grants` method on the repository means an implementation of
the repository cannot accidentally satisfy the consent contract by returning a
stale list it happened to have.

Every family-scoped read is scoped by `(tenant_id, family_id)`. There is
deliberately **no** cross-family read shape — no `list_bookings_for_provider`,
no `count_bookings_by_family`, no `top_families`. R9's 不做家庭排名 is enforced
by the port not offering the shape, so a ranking UI cannot be built on it later.
Provider-side operational reads (an operator's "who booked my slots") are a
different capability with a different authorization story and are not in this
port.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from backend.platform.consent.models import ConsentGrant, ConsentPurpose

from ..domain.entities import (
    AvailabilitySlot,
    BookingRequest,
    PrivateCheckinDraft,
    ServiceOffering,
    ServiceProvider,
    ServiceRecord,
)


class ConsentQueryPort(Protocol):
    """Reads the consent grants currently in force for one subject."""

    async def list_grants(
        self, *, tenant_id: str, subject_person_id: str, purpose: ConsentPurpose
    ) -> Sequence[ConsentGrant]:
        """Grants for this subject/purpose **as of now**.

        Implementations must query live state on every call. Returning a cached
        list defeats the "withdrawal takes effect immediately" guarantee that is
        the reason `ConsentGate` holds no state of its own.
        """
        ...


class ServiceRepositoryPort(Protocol):
    # -- unit of work --
    async def commit(self) -> None:
        """Minimal unit of work. `save_*` / `append_*` only stage; a command
        commits once at the end, so "slot capacity taken" and "booking row
        written" cannot land half-applied — which is the only thing that makes
        the double-booking refusal meaningful."""
        ...

    # -- supply masters --
    async def save_provider(self, entity: ServiceProvider) -> None: ...
    async def load_provider(self, provider_id: str) -> ServiceProvider: ...
    async def save_offering(self, entity: ServiceOffering) -> None: ...
    async def load_offering(self, service_offering_id: str) -> ServiceOffering: ...
    async def list_offerings(self, tenant_id: str) -> list[ServiceOffering]: ...

    # -- availability --
    async def save_slot(self, entity: AvailabilitySlot) -> None: ...
    async def load_slot(self, availability_slot_id: str) -> AvailabilitySlot: ...
    async def list_slots(
        self, tenant_id: str, *, service_offering_id: str | None = None
    ) -> list[AvailabilitySlot]: ...

    # -- booking requests --
    async def save_booking(self, entity: BookingRequest) -> None: ...
    async def load_booking(self, booking_request_id: str) -> BookingRequest: ...
    async def list_bookings(self, tenant_id: str, family_id: str) -> list[BookingRequest]: ...
    async def find_booking_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BookingRequest | None: ...

    # -- service records --
    async def save_service_record(self, entity: ServiceRecord) -> None: ...
    async def load_service_record(self, booking_service_record_id: str) -> ServiceRecord: ...
    async def find_service_record_for_booking(
        self, tenant_id: str, family_id: str, booking_request_id: str
    ) -> ServiceRecord | None: ...
    async def list_service_records(self, tenant_id: str, family_id: str) -> list[ServiceRecord]: ...

    # -- private check-in drafts (append-only: no update_/delete_ by design) --
    async def append_checkin_draft(self, entity: PrivateCheckinDraft) -> None: ...
    async def find_checkin_draft_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PrivateCheckinDraft | None: ...
    async def list_checkin_drafts(
        self, tenant_id: str, family_id: str, *, onboarding_id: str | None = None
    ) -> list[PrivateCheckinDraft]: ...
