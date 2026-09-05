"""Ports for family core.

Three ports, and the split is the point.

`FamilyRepositoryPort` is persistence for the five aggregate tables.
`IdempotencyPort` is separate because **none of the five tables has an
`idempotency_key` column** — `database/baseline/0001_family_identity.sql` predates
that convention, and `0002_platform_foundation.sql` provides a shared
`idempotency_keys` table instead. So this domain cannot do what `service` does
(`find_booking_by_idempotency_key` on the row itself); it has to reserve a key and
remember which resource that key produced. Giving that its own port rather than
five more repository methods keeps the "which table" question out of it: an
idempotency record is `(tenant, key, action) → resource_id + request fingerprint`,
and that shape is the same for all six commands.

`OutboxPort` is separate for the same kind of reason: `outbox_events` is a platform
table shared by every domain, and the acceptance spec asserts on its contents
(`FamilyCreated / FamilyMemberAdded / FamilyRelationshipCreated /
LifeStageAssigned / ConsentGranted`). Making it a port means the fake and the real
implementation are the same interface, and a command cannot "publish" by writing a
row directly.

Every family-scoped read is scoped by `family_id`. There is deliberately **no**
cross-family read shape — no `list_all_families`, no `count_children_by_family`,
no `top_families`. R9's 不做家庭排名 is enforced by the port not offering the
shape, so a ranking UI cannot be built on it later. `list_families_for_actor`
exists because a parent with two accounts still needs to find their own family,
and it is scoped to the actor, not to the tenant.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.entities import (
    Consent,
    Family,
    FamilyMember,
    FamilyRelationship,
    LifeStageAssignment,
)


class IdempotencyReservation(Protocol):
    """What a previous run of the same key produced."""

    @property
    def resource_id(self) -> str: ...
    @property
    def request_fingerprint(self) -> str: ...


class IdempotencyPort(Protocol):
    """Records `(tenant, key, action) → resource_id` so a replay is a lookup.

    `find` returns the earlier reservation or ``None``. `reserve` writes one. The
    caller compares fingerprints itself and raises `FamilyConflictError` on a
    mismatch, rather than this port deciding — the port cannot know which fields
    of a request are supposed to be stable.
    """

    async def find(
        self, *, tenant_id: str, key: str, action: str
    ) -> IdempotencyReservation | None: ...

    async def reserve(
        self,
        *,
        tenant_id: str,
        key: str,
        action: str,
        resource_id: str,
        request_fingerprint: str,
    ) -> None: ...


class OutboxPort(Protocol):
    """Appends a domain event to `outbox_events` in the current unit of work.

    Same transaction as the domain write, deliberately: an event published after a
    separate commit can be published for a write that then rolled back, and an
    event published before it can be published for a write that never happened.
    """

    async def append(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_name: str,
        payload: dict,
        correlation_id: str,
        event_version: int = 1,
    ) -> None: ...


class FamilyRepositoryPort(Protocol):
    # -- unit of work --
    async def commit(self) -> None:
        """Minimal unit of work. `save_*` only stage; a command commits once at the
        end, so "person row written" and "family primary contact updated" cannot
        land half-applied."""
        ...

    # -- families --
    async def save_family(self, entity: Family) -> None: ...
    async def load_family(self, family_id: str) -> Family: ...
    async def find_family(self, family_id: str) -> Family | None: ...

    # -- members --
    async def save_member(self, entity: FamilyMember) -> None: ...
    async def load_member(self, person_id: str) -> FamilyMember: ...
    async def list_members(self, family_id: str) -> list[FamilyMember]: ...

    # -- relationships --
    async def save_relationship(self, entity: FamilyRelationship) -> None: ...
    async def list_relationships(self, family_id: str) -> list[FamilyRelationship]: ...

    # -- life stages --
    async def save_life_stage(self, entity: LifeStageAssignment) -> None: ...
    async def list_life_stages(
        self, family_id: str, *, active_only: bool = False
    ) -> list[LifeStageAssignment]: ...
    async def list_active_life_stages_for_child(
        self, child_id: str
    ) -> list[LifeStageAssignment]: ...

    # -- consents --
    async def save_consent(self, entity: Consent) -> None: ...
    async def list_consents(
        self, family_id: str, *, active_only: bool = False
    ) -> list[Consent]: ...
    async def list_consents_for_subject(
        self, subject_person_id: str, *, purpose: str | None = None
    ) -> list[Consent]:
        """Grants for one subject **as of now**, read live on every call.

        This is what `backend/platform/consent/gate.py` requires of whoever first
        gives it a data source: "that repository must call `ConsentGate.check` with
        the *current* grants it just read, not a cached list from an earlier
        request." Implementations must query, not memoise.
        """
        ...
