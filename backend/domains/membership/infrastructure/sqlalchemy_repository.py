"""Real SQLAlchemy repository implementing `MembershipRepositoryPort`.

`save_*` / `append_*` stage only; the caller commits once via `commit()` — see
the unit-of-work note on the port. That is what makes "grant + its ledger row"
and "close old period + open new one + append transition" atomic instead of
three independent commits that can half-fail.

Tests run this same class against an in-memory SQLite engine
(`tests/conftest.py`). No real-Postgres integration test yet — the same known,
accepted gap as Batch 2 and `product_intelligence` (Override #4 item 4,
Override #6 item 4).
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from . import sqlalchemy_models as m


def _row_to_dict(row: object) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


class SqlAlchemyMembershipRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def _stage(self, row: object) -> None:
        await self._session.merge(row)

    async def _one(
        self,
        model,
        entity_id: str,
        code: str,
        *,
        tenant_id: str | None = None,
        family_id: str | None = None,
        for_update: bool = False,
    ):
        statement = select(model).where(model.__table__.primary_key.columns[0] == entity_id)
        if tenant_id is not None:
            statement = statement.where(
                or_(model.tenant_id.is_(None), model.tenant_id == tenant_id)
            )
        if family_id is not None:
            statement = statement.where(model.family_id == family_id)
        if for_update:
            statement = statement.with_for_update()
        row = (await self._session.execute(statement)).scalars().first()
        if row is None:
            raise MembershipNotFoundError(code)
        return row

    async def _all(self, model, tenant_id: str, family_id: str):
        result = await self._session.execute(
            select(model).where(model.tenant_id == tenant_id, model.family_id == family_id)
        )
        return result.scalars().all()

    async def _by_idempotency_key(self, model, tenant_id: str, family_id: str, key: str):
        result = await self._session.execute(
            select(model).where(
                model.tenant_id == tenant_id,
                model.family_id == family_id,
                model.idempotency_key == key,
            )
        )
        return result.scalars().first()

    # -- catalogue masters --
    async def save_plan(self, entity: MembershipPlan) -> None:
        await self._stage(m.MembershipPlanRow(**entity.model_dump()))

    async def load_plan(self, plan_id: str, tenant_id: str | None = None) -> MembershipPlan:
        row = await self._one(
            m.MembershipPlanRow,
            plan_id,
            "membership_plan_not_found",
            tenant_id=tenant_id,
        )
        return MembershipPlan(**_row_to_dict(row))

    async def save_tier_definition(self, entity: MembershipTierDefinition) -> None:
        await self._stage(m.MembershipTierDefinitionRow(**entity.model_dump()))

    async def load_tier_definition(
        self, tier_definition_id: str, tenant_id: str | None = None
    ) -> MembershipTierDefinition:
        row = await self._one(
            m.MembershipTierDefinitionRow,
            tier_definition_id,
            "tier_definition_not_found",
            tenant_id=tenant_id,
        )
        return MembershipTierDefinition(**_row_to_dict(row))

    async def list_tier_definitions(self) -> list[MembershipTierDefinition]:
        result = await self._session.execute(select(m.MembershipTierDefinitionRow))
        return [MembershipTierDefinition(**_row_to_dict(r)) for r in result.scalars().all()]

    async def save_benefit_definition(self, entity: BenefitDefinition) -> None:
        await self._stage(m.BenefitDefinitionRow(**entity.model_dump()))

    async def load_benefit_definition(
        self, benefit_definition_id: str, tenant_id: str | None = None
    ) -> BenefitDefinition:
        row = await self._one(
            m.BenefitDefinitionRow,
            benefit_definition_id,
            "benefit_definition_not_found",
            tenant_id=tenant_id,
        )
        return BenefitDefinition(**_row_to_dict(row))

    # -- subscription --
    async def save_subscription(self, entity: MembershipSubscription) -> None:
        await self._stage(m.MembershipSubscriptionRow(**entity.model_dump()))

    async def load_subscription(
        self,
        membership_subscription_id: str,
        tenant_id: str | None = None,
        family_id: str | None = None,
    ) -> MembershipSubscription:
        row = await self._one(
            m.MembershipSubscriptionRow,
            membership_subscription_id,
            "subscription_not_found",
            tenant_id=tenant_id,
            family_id=family_id,
        )
        return MembershipSubscription(**_row_to_dict(row))

    async def find_subscription_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipSubscription | None:
        row = await self._by_idempotency_key(
            m.MembershipSubscriptionRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else MembershipSubscription(**_row_to_dict(row))

    async def list_subscriptions(
        self, tenant_id: str, family_id: str
    ) -> list[MembershipSubscription]:
        rows = await self._all(m.MembershipSubscriptionRow, tenant_id, family_id)
        return [MembershipSubscription(**_row_to_dict(r)) for r in rows]

    # -- period --
    async def save_period(self, entity: MembershipPeriod) -> None:
        await self._stage(m.MembershipPeriodRow(**entity.model_dump()))

    async def load_period(
        self,
        membership_period_id: str,
        tenant_id: str | None = None,
        family_id: str | None = None,
    ) -> MembershipPeriod:
        row = await self._one(
            m.MembershipPeriodRow,
            membership_period_id,
            "period_not_found",
            tenant_id=tenant_id,
            family_id=family_id,
        )
        return MembershipPeriod(**_row_to_dict(row))

    async def load_active_period(self, tenant_id: str, family_id: str) -> MembershipPeriod | None:
        result = await self._session.execute(
            select(m.MembershipPeriodRow)
            .where(
                m.MembershipPeriodRow.tenant_id == tenant_id,
                m.MembershipPeriodRow.family_id == family_id,
                m.MembershipPeriodRow.status == "ACTIVE",
            )
            .order_by(m.MembershipPeriodRow.seq_no.desc())
        )
        row = result.scalars().first()
        return None if row is None else MembershipPeriod(**_row_to_dict(row))

    async def list_periods(self, tenant_id: str, family_id: str) -> list[MembershipPeriod]:
        rows = await self._all(m.MembershipPeriodRow, tenant_id, family_id)
        return [MembershipPeriod(**_row_to_dict(r)) for r in rows]

    async def find_period_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipPeriod | None:
        row = await self._by_idempotency_key(
            m.MembershipPeriodRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else MembershipPeriod(**_row_to_dict(row))

    # -- tier transition (append-only: no update/delete method exists) --
    async def append_tier_transition(self, entity: MembershipTierTransition) -> None:
        self._session.add(m.MembershipTierTransitionRow(**entity.model_dump()))

    async def find_tier_transition_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> MembershipTierTransition | None:
        row = await self._by_idempotency_key(
            m.MembershipTierTransitionRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else MembershipTierTransition(**_row_to_dict(row))

    async def list_tier_transitions(
        self, tenant_id: str, family_id: str
    ) -> list[MembershipTierTransition]:
        rows = await self._all(m.MembershipTierTransitionRow, tenant_id, family_id)
        return [MembershipTierTransition(**_row_to_dict(r)) for r in rows]

    # -- benefit grant --
    async def save_benefit_grant(self, entity: BenefitGrant) -> None:
        await self._stage(m.BenefitGrantRow(**entity.model_dump()))

    async def load_benefit_grant(
        self,
        benefit_grant_id: str,
        tenant_id: str | None = None,
        family_id: str | None = None,
        for_update: bool = False,
    ) -> BenefitGrant:
        row = await self._one(
            m.BenefitGrantRow,
            benefit_grant_id,
            "benefit_grant_not_found",
            tenant_id=tenant_id,
            family_id=family_id,
            for_update=for_update,
        )
        return BenefitGrant(**_row_to_dict(row))

    async def list_benefit_grants(self, tenant_id: str, family_id: str) -> list[BenefitGrant]:
        rows = await self._all(m.BenefitGrantRow, tenant_id, family_id)
        return [BenefitGrant(**_row_to_dict(r)) for r in rows]

    async def find_benefit_grant_by_ref(
        self, tenant_id: str, family_id: str, grant_ref: str
    ) -> BenefitGrant | None:
        result = await self._session.execute(
            select(m.BenefitGrantRow).where(
                m.BenefitGrantRow.tenant_id == tenant_id,
                m.BenefitGrantRow.family_id == family_id,
                m.BenefitGrantRow.grant_ref == grant_ref,
            )
        )
        row = result.scalars().first()
        return None if row is None else BenefitGrant(**_row_to_dict(row))

    # -- reservation --
    async def save_reservation(self, entity: BenefitReservation) -> None:
        await self._stage(m.BenefitReservationRow(**entity.model_dump()))

    async def load_reservation(
        self,
        benefit_reservation_id: str,
        tenant_id: str | None = None,
        family_id: str | None = None,
    ) -> BenefitReservation:
        row = await self._one(
            m.BenefitReservationRow,
            benefit_reservation_id,
            "reservation_not_found",
            tenant_id=tenant_id,
            family_id=family_id,
        )
        return BenefitReservation(**_row_to_dict(row))

    async def list_reservations(self, tenant_id: str, family_id: str) -> list[BenefitReservation]:
        rows = await self._all(m.BenefitReservationRow, tenant_id, family_id)
        return [BenefitReservation(**_row_to_dict(r)) for r in rows]

    async def find_reservation_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BenefitReservation | None:
        row = await self._by_idempotency_key(
            m.BenefitReservationRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else BenefitReservation(**_row_to_dict(row))

    # -- benefit ledger (append-only) --
    async def append_benefit_ledger_entry(self, entity: BenefitLedgerEntry) -> None:
        self._session.add(m.BenefitLedgerEntryRow(**entity.model_dump()))

    async def find_benefit_ledger_entry_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BenefitLedgerEntry | None:
        row = await self._by_idempotency_key(
            m.BenefitLedgerEntryRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else BenefitLedgerEntry(**_row_to_dict(row))

    async def list_benefit_ledger(self, tenant_id: str, family_id: str) -> list[BenefitLedgerEntry]:
        rows = await self._all(m.BenefitLedgerEntryRow, tenant_id, family_id)
        return [BenefitLedgerEntry(**_row_to_dict(r)) for r in rows]
