"""In-memory `MembershipRepositoryPort` implementation.

Exists so the application layer can be tested without SQLAlchemy, and so the
acceptance chain runs twice — once here, once against real ORM models — proving
the commands depend on the port and not on a particular persistence quirk (the
dual-repository convention `product_intelligence` established).

`commit()` is a no-op: there is no transaction to close. That is a real
difference from the SQLAlchemy repo and is the reason the SQLite pass exists.
"""

from __future__ import annotations

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
from ..domain.errors import MembershipNotFoundError


class FakeMembershipRepository:
    def __init__(self) -> None:
        self.plans: dict[str, MembershipPlan] = {}
        self.tier_definitions: dict[str, MembershipTierDefinition] = {}
        self.benefit_definitions: dict[str, BenefitDefinition] = {}
        self.subscriptions: dict[str, MembershipSubscription] = {}
        self.periods: dict[str, MembershipPeriod] = {}
        self.tier_transitions: dict[str, MembershipTierTransition] = {}
        self.benefit_grants: dict[str, BenefitGrant] = {}
        self.reservations: dict[str, BenefitReservation] = {}
        self.benefit_ledger: dict[str, BenefitLedgerEntry] = {}

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

    # -- catalogue masters --
    async def save_plan(self, entity: MembershipPlan) -> None:
        self.plans[entity.plan_id] = entity

    async def load_plan(self, plan_id: str) -> MembershipPlan:
        if plan_id not in self.plans:
            raise MembershipNotFoundError("membership_plan_not_found")
        return self.plans[plan_id]

    async def save_tier_definition(self, entity: MembershipTierDefinition) -> None:
        self.tier_definitions[entity.tier_definition_id] = entity

    async def load_tier_definition(self, tier_definition_id: str) -> MembershipTierDefinition:
        if tier_definition_id not in self.tier_definitions:
            raise MembershipNotFoundError("tier_definition_not_found")
        return self.tier_definitions[tier_definition_id]

    async def list_tier_definitions(self) -> list[MembershipTierDefinition]:
        return list(self.tier_definitions.values())

    async def save_benefit_definition(self, entity: BenefitDefinition) -> None:
        self.benefit_definitions[entity.benefit_definition_id] = entity

    async def load_benefit_definition(self, benefit_definition_id: str) -> BenefitDefinition:
        if benefit_definition_id not in self.benefit_definitions:
            raise MembershipNotFoundError("benefit_definition_not_found")
        return self.benefit_definitions[benefit_definition_id]

    # -- subscription --
    async def save_subscription(self, entity: MembershipSubscription) -> None:
        self.subscriptions[entity.membership_subscription_id] = entity

    async def load_subscription(self, membership_subscription_id: str) -> MembershipSubscription:
        if membership_subscription_id not in self.subscriptions:
            raise MembershipNotFoundError("subscription_not_found")
        return self.subscriptions[membership_subscription_id]

    async def find_subscription_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipSubscription | None:
        return self._by_key(self.subscriptions, tenant_id, family_id, idempotency_key)

    async def list_subscriptions(
        self, tenant_id: str, family_id: str
    ) -> list[MembershipSubscription]:
        return self._scoped(self.subscriptions, tenant_id, family_id)

    # -- period --
    async def save_period(self, entity: MembershipPeriod) -> None:
        self.periods[entity.membership_period_id] = entity

    async def load_period(self, membership_period_id: str) -> MembershipPeriod:
        if membership_period_id not in self.periods:
            raise MembershipNotFoundError("period_not_found")
        return self.periods[membership_period_id]

    async def load_active_period(self, tenant_id: str, family_id: str) -> MembershipPeriod | None:
        active = [
            p for p in self._scoped(self.periods, tenant_id, family_id) if p.status == "ACTIVE"
        ]
        return max(active, key=lambda p: p.seq_no) if active else None

    async def list_periods(self, tenant_id: str, family_id: str) -> list[MembershipPeriod]:
        return self._scoped(self.periods, tenant_id, family_id)

    async def find_period_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipPeriod | None:
        return self._by_key(self.periods, tenant_id, family_id, idempotency_key)

    # -- tier transition (append-only) --
    async def append_tier_transition(self, entity: MembershipTierTransition) -> None:
        self.tier_transitions[entity.tier_transition_id] = entity

    async def find_tier_transition_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipTierTransition | None:
        return self._by_key(self.tier_transitions, tenant_id, family_id, idempotency_key)

    async def list_tier_transitions(
        self, tenant_id: str, family_id: str
    ) -> list[MembershipTierTransition]:
        return self._scoped(self.tier_transitions, tenant_id, family_id)

    # -- benefit grant --
    async def save_benefit_grant(self, entity: BenefitGrant) -> None:
        self.benefit_grants[entity.benefit_grant_id] = entity

    async def load_benefit_grant(self, benefit_grant_id: str) -> BenefitGrant:
        if benefit_grant_id not in self.benefit_grants:
            raise MembershipNotFoundError("benefit_grant_not_found")
        return self.benefit_grants[benefit_grant_id]

    async def list_benefit_grants(self, tenant_id: str, family_id: str) -> list[BenefitGrant]:
        return self._scoped(self.benefit_grants, tenant_id, family_id)

    async def find_benefit_grant_by_ref(
        self, tenant_id: str, family_id: str, grant_ref: str
    ) -> BenefitGrant | None:
        for grant in self._scoped(self.benefit_grants, tenant_id, family_id):
            if grant.grant_ref == grant_ref:
                return grant
        return None

    # -- reservation --
    async def save_reservation(self, entity: BenefitReservation) -> None:
        self.reservations[entity.benefit_reservation_id] = entity

    async def load_reservation(self, benefit_reservation_id: str) -> BenefitReservation:
        if benefit_reservation_id not in self.reservations:
            raise MembershipNotFoundError("reservation_not_found")
        return self.reservations[benefit_reservation_id]

    async def list_reservations(self, tenant_id: str, family_id: str) -> list[BenefitReservation]:
        return self._scoped(self.reservations, tenant_id, family_id)

    async def find_reservation_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BenefitReservation | None:
        return self._by_key(self.reservations, tenant_id, family_id, idempotency_key)

    # -- benefit ledger (append-only) --
    async def append_benefit_ledger_entry(self, entity: BenefitLedgerEntry) -> None:
        self.benefit_ledger[entity.membership_benefit_ledger_id] = entity

    async def find_benefit_ledger_entry_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BenefitLedgerEntry | None:
        return self._by_key(self.benefit_ledger, tenant_id, family_id, idempotency_key)

    async def list_benefit_ledger(self, tenant_id: str, family_id: str) -> list[BenefitLedgerEntry]:
        return self._scoped(self.benefit_ledger, tenant_id, family_id)
