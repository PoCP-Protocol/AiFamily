"""Repository port for the membership domain.

Every read is scoped by `(tenant_id, family_id)`. There is deliberately **no**
`list_families_by_tier`, `count_by_tier`, `top_families`, `compare_families`
or any other cross-family read: 不做家庭 Ranking is enforced by the port not
offering the shape, so a UI cannot be built on top of it later.

The append-only facts (`MembershipTierTransition`, `BenefitLedgerEntry`) get
`append_*` methods and no `update_*` / `delete_*` — baseline invariants 2 and
8. A guardrail test asserts this Protocol never grows one.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.entities import (
    BenefitDefinition,
    BenefitGrant,
    BenefitLedgerEntry,
    BenefitReservation,
    MembershipPeriod,
    MembershipPlan,
    MembershipSubscription,
    MembershipTierDefinition,
    MembershipTierTransition,
)


class MembershipRepositoryPort(Protocol):
    # -- unit of work --
    async def commit(self) -> None:
        """Minimal unit of work. `save_*` / `append_*` only stage; a command
        commits once at the end so a grant and its ledger entry — or a closed
        period and the transition that closed it — cannot land half-written.
        The repo has no shared `packages/persistence` UoW yet, so the boundary
        lives on the port rather than in a separate object.
        """
        ...

    # -- catalogue masters --
    async def save_plan(self, entity: MembershipPlan) -> None: ...
    async def load_plan(self, plan_id: str) -> MembershipPlan: ...
    async def save_tier_definition(self, entity: MembershipTierDefinition) -> None: ...
    async def load_tier_definition(self, tier_definition_id: str) -> MembershipTierDefinition: ...
    async def list_tier_definitions(self) -> list[MembershipTierDefinition]: ...
    async def save_benefit_definition(self, entity: BenefitDefinition) -> None: ...
    async def load_benefit_definition(self, benefit_definition_id: str) -> BenefitDefinition: ...

    # -- subscription --
    async def save_subscription(self, entity: MembershipSubscription) -> None: ...
    async def load_subscription(
        self, membership_subscription_id: str
    ) -> MembershipSubscription: ...
    async def find_subscription_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipSubscription | None: ...
    async def list_subscriptions(
        self, tenant_id: str, family_id: str
    ) -> list[MembershipSubscription]: ...

    # -- period --
    async def save_period(self, entity: MembershipPeriod) -> None: ...
    async def load_period(self, membership_period_id: str) -> MembershipPeriod: ...
    async def load_active_period(
        self, tenant_id: str, family_id: str
    ) -> MembershipPeriod | None: ...
    async def list_periods(self, tenant_id: str, family_id: str) -> list[MembershipPeriod]: ...
    async def find_period_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipPeriod | None: ...

    # -- tier transition (append-only) --
    async def append_tier_transition(self, entity: MembershipTierTransition) -> None: ...
    async def find_tier_transition_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipTierTransition | None: ...
    async def list_tier_transitions(
        self, tenant_id: str, family_id: str
    ) -> list[MembershipTierTransition]: ...

    # -- benefit grant --
    async def save_benefit_grant(self, entity: BenefitGrant) -> None: ...
    async def load_benefit_grant(self, benefit_grant_id: str) -> BenefitGrant: ...
    async def list_benefit_grants(self, tenant_id: str, family_id: str) -> list[BenefitGrant]: ...
    async def find_benefit_grant_by_ref(
        self, tenant_id: str, family_id: str, grant_ref: str
    ) -> BenefitGrant | None: ...

    # -- reservation --
    async def save_reservation(self, entity: BenefitReservation) -> None: ...
    async def load_reservation(self, benefit_reservation_id: str) -> BenefitReservation: ...
    async def list_reservations(
        self, tenant_id: str, family_id: str
    ) -> list[BenefitReservation]: ...
    async def find_reservation_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BenefitReservation | None: ...

    # -- benefit ledger (append-only) --
    async def append_benefit_ledger_entry(self, entity: BenefitLedgerEntry) -> None: ...
    async def find_benefit_ledger_entry_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BenefitLedgerEntry | None: ...
    async def list_benefit_ledger(
        self, tenant_id: str, family_id: str
    ) -> list[BenefitLedgerEntry]: ...
