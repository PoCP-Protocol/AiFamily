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
        self._snapshot: dict[str, dict] | None = None
        self.fail_commit: Exception | None = None
        self.fail_append_ledger: Exception | None = None

    _STORE_NAMES = (
        "plans",
        "tier_definitions",
        "benefit_definitions",
        "subscriptions",
        "periods",
        "tier_transitions",
        "benefit_grants",
        "reservations",
        "benefit_ledger",
    )

    def _begin_write(self) -> None:
        if self._snapshot is None:
            self._snapshot = {name: dict(getattr(self, name)) for name in self._STORE_NAMES}

    async def commit(self) -> None:
        if self.fail_commit is not None:
            error = self.fail_commit
            self.fail_commit = None
            await self.rollback()
            raise error
        self._snapshot = None

    async def rollback(self) -> None:
        if self._snapshot is None:
            return
        for name, values in self._snapshot.items():
            setattr(self, name, values)
        self._snapshot = None

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

    @staticmethod
    def _load(
        store: dict,
        entity_id: str,
        code: str,
        *,
        tenant_id: str | None = None,
        family_id: str | None = None,
    ):
        entity = store.get(entity_id)
        if entity is None:
            raise MembershipNotFoundError(code)
        if tenant_id is not None and getattr(entity, "tenant_id", None) not in (None, tenant_id):
            raise MembershipNotFoundError(code)
        if family_id is not None and getattr(entity, "family_id", None) != family_id:
            raise MembershipNotFoundError(code)
        return entity

    # -- catalogue masters --
    async def save_plan(self, entity: MembershipPlan) -> None:
        self._begin_write()
        self.plans[entity.plan_id] = entity

    async def load_plan(self, plan_id: str, tenant_id: str | None = None) -> MembershipPlan:
        return self._load(self.plans, plan_id, "membership_plan_not_found", tenant_id=tenant_id)

    async def save_tier_definition(self, entity: MembershipTierDefinition) -> None:
        self._begin_write()
        self.tier_definitions[entity.tier_definition_id] = entity

    async def load_tier_definition(
        self, tier_definition_id: str, tenant_id: str | None = None
    ) -> MembershipTierDefinition:
        return self._load(
            self.tier_definitions,
            tier_definition_id,
            "tier_definition_not_found",
            tenant_id=tenant_id,
        )

    async def list_tier_definitions(self) -> list[MembershipTierDefinition]:
        return list(self.tier_definitions.values())

    async def save_benefit_definition(self, entity: BenefitDefinition) -> None:
        self._begin_write()
        self.benefit_definitions[entity.benefit_definition_id] = entity

    async def load_benefit_definition(
        self, benefit_definition_id: str, tenant_id: str | None = None
    ) -> BenefitDefinition:
        return self._load(
            self.benefit_definitions,
            benefit_definition_id,
            "benefit_definition_not_found",
            tenant_id=tenant_id,
        )

    # -- subscription --
    async def save_subscription(self, entity: MembershipSubscription) -> None:
        self._begin_write()
        self.subscriptions[entity.membership_subscription_id] = entity

    async def load_subscription(
        self,
        membership_subscription_id: str,
        tenant_id: str | None = None,
        family_id: str | None = None,
    ) -> MembershipSubscription:
        return self._load(
            self.subscriptions,
            membership_subscription_id,
            "subscription_not_found",
            tenant_id=tenant_id,
            family_id=family_id,
        )

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
        self._begin_write()
        self.periods[entity.membership_period_id] = entity

    async def load_period(
        self,
        membership_period_id: str,
        tenant_id: str | None = None,
        family_id: str | None = None,
    ) -> MembershipPeriod:
        return self._load(
            self.periods,
            membership_period_id,
            "period_not_found",
            tenant_id=tenant_id,
            family_id=family_id,
        )

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
        self._begin_write()
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
        self._begin_write()
        self.benefit_grants[entity.benefit_grant_id] = entity

    async def load_benefit_grant(
        self,
        benefit_grant_id: str,
        tenant_id: str | None = None,
        family_id: str | None = None,
        for_update: bool = False,
    ) -> BenefitGrant:
        del for_update
        return self._load(
            self.benefit_grants,
            benefit_grant_id,
            "benefit_grant_not_found",
            tenant_id=tenant_id,
            family_id=family_id,
        )

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
        self._begin_write()
        self.reservations[entity.benefit_reservation_id] = entity

    async def load_reservation(
        self,
        benefit_reservation_id: str,
        tenant_id: str | None = None,
        family_id: str | None = None,
    ) -> BenefitReservation:
        return self._load(
            self.reservations,
            benefit_reservation_id,
            "reservation_not_found",
            tenant_id=tenant_id,
            family_id=family_id,
        )

    async def list_reservations(self, tenant_id: str, family_id: str) -> list[BenefitReservation]:
        return self._scoped(self.reservations, tenant_id, family_id)

    async def find_reservation_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BenefitReservation | None:
        return self._by_key(self.reservations, tenant_id, family_id, idempotency_key)

    # -- benefit ledger (append-only) --
    async def append_benefit_ledger_entry(self, entity: BenefitLedgerEntry) -> None:
        self._begin_write()
        if self.fail_append_ledger is not None:
            error = self.fail_append_ledger
            self.fail_append_ledger = None
            raise error
        self.benefit_ledger[entity.membership_benefit_ledger_id] = entity

    async def find_benefit_ledger_entry_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BenefitLedgerEntry | None:
        return self._by_key(self.benefit_ledger, tenant_id, family_id, idempotency_key)

    async def list_benefit_ledger(self, tenant_id: str, family_id: str) -> list[BenefitLedgerEntry]:
        return self._scoped(self.benefit_ledger, tenant_id, family_id)
