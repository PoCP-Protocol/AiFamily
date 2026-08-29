"""Real SQLAlchemy repository implementing `LoyaltyPointsRepositoryPort`.

`save_*` / `append_*` stage only; the caller commits once. That is what makes
"redemption + its debit entry" atomic — a redemption without its ledger row, or a
row without its redemption, is a ledger that cannot explain itself.

Tests run this same class against in-memory SQLite. Known gap, stated rather than
hidden: SQLite is not Postgres, so the DB-level CHECK constraints this schema will
carry in a real migration are not exercised here — only the domain-layer
equivalents are.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.entities import (
    PointsAccount,
    PointsEarnRule,
    PointsLedgerEntry,
    PointsRedemption,
    RedemptionCatalogItem,
)
from ..domain.errors import LoyaltyPointsNotFoundError
from . import sqlalchemy_models as m


def _row_to_dict(row: object) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


class SqlAlchemyLoyaltyPointsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    # -- catalogue masters --
    async def save_earn_rule(self, entity: PointsEarnRule) -> None:
        await self._session.merge(m.PointsEarnRuleRow(**entity.model_dump()))

    async def load_earn_rule(self, rule_id: str) -> PointsEarnRule:
        row = await self._session.get(m.PointsEarnRuleRow, rule_id)
        if row is None:
            raise LoyaltyPointsNotFoundError("earn_rule_not_found")
        return PointsEarnRule(**_row_to_dict(row))

    async def find_earn_rule_by_ref(self, rule_ref: str) -> PointsEarnRule | None:
        result = await self._session.execute(
            select(m.PointsEarnRuleRow)
            .where(m.PointsEarnRuleRow.rule_ref == rule_ref)
            .order_by(m.PointsEarnRuleRow.version_no.desc())
        )
        row = result.scalars().first()
        return None if row is None else PointsEarnRule(**_row_to_dict(row))

    async def list_earn_rules(self) -> list[PointsEarnRule]:
        result = await self._session.execute(select(m.PointsEarnRuleRow))
        return [PointsEarnRule(**_row_to_dict(r)) for r in result.scalars().all()]

    async def save_redemption_item(self, entity: RedemptionCatalogItem) -> None:
        await self._session.merge(m.RedemptionCatalogItemRow(**entity.model_dump()))

    async def find_redemption_item_by_ref(self, item_ref: str) -> RedemptionCatalogItem | None:
        result = await self._session.execute(
            select(m.RedemptionCatalogItemRow)
            .where(m.RedemptionCatalogItemRow.item_ref == item_ref)
            .order_by(m.RedemptionCatalogItemRow.version_no.desc())
        )
        row = result.scalars().first()
        return None if row is None else RedemptionCatalogItem(**_row_to_dict(row))

    async def list_redemption_items(self) -> list[RedemptionCatalogItem]:
        result = await self._session.execute(select(m.RedemptionCatalogItemRow))
        return [RedemptionCatalogItem(**_row_to_dict(r)) for r in result.scalars().all()]

    # -- account --
    async def save_account(self, entity: PointsAccount) -> None:
        await self._session.merge(m.PointsAccountRow(**entity.model_dump()))

    async def load_account(self, points_account_id: str) -> PointsAccount:
        row = await self._session.get(m.PointsAccountRow, points_account_id)
        if row is None:
            raise LoyaltyPointsNotFoundError("points_account_not_found")
        return PointsAccount(**_row_to_dict(row))

    async def find_account(self, tenant_id: str, family_id: str) -> PointsAccount | None:
        result = await self._session.execute(
            select(m.PointsAccountRow).where(
                m.PointsAccountRow.tenant_id == tenant_id,
                m.PointsAccountRow.family_id == family_id,
            )
        )
        row = result.scalars().first()
        return None if row is None else PointsAccount(**_row_to_dict(row))

    # -- ledger (append-only: no update/delete method exists) --
    async def append_ledger_entry(self, entity: PointsLedgerEntry) -> None:
        self._session.add(m.PointsLedgerEntryRow(**entity.model_dump()))

    async def list_ledger(self, tenant_id: str, family_id: str) -> list[PointsLedgerEntry]:
        result = await self._session.execute(
            select(m.PointsLedgerEntryRow).where(
                m.PointsLedgerEntryRow.tenant_id == tenant_id,
                m.PointsLedgerEntryRow.family_id == family_id,
            )
        )
        return [PointsLedgerEntry(**_row_to_dict(r)) for r in result.scalars().all()]

    async def find_ledger_entry_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PointsLedgerEntry | None:
        result = await self._session.execute(
            select(m.PointsLedgerEntryRow).where(
                m.PointsLedgerEntryRow.tenant_id == tenant_id,
                m.PointsLedgerEntryRow.family_id == family_id,
                m.PointsLedgerEntryRow.idempotency_key == idempotency_key,
            )
        )
        row = result.scalars().first()
        return None if row is None else PointsLedgerEntry(**_row_to_dict(row))

    # -- redemption --
    async def save_redemption(self, entity: PointsRedemption) -> None:
        await self._session.merge(m.PointsRedemptionRow(**entity.model_dump()))

    async def load_redemption(self, redemption_id: str) -> PointsRedemption:
        row = await self._session.get(m.PointsRedemptionRow, redemption_id)
        if row is None:
            raise LoyaltyPointsNotFoundError("redemption_not_found")
        return PointsRedemption(**_row_to_dict(row))

    async def list_redemptions(self, tenant_id: str, family_id: str) -> list[PointsRedemption]:
        result = await self._session.execute(
            select(m.PointsRedemptionRow).where(
                m.PointsRedemptionRow.tenant_id == tenant_id,
                m.PointsRedemptionRow.family_id == family_id,
            )
        )
        return [PointsRedemption(**_row_to_dict(r)) for r in result.scalars().all()]

    async def find_redemption_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PointsRedemption | None:
        result = await self._session.execute(
            select(m.PointsRedemptionRow).where(
                m.PointsRedemptionRow.tenant_id == tenant_id,
                m.PointsRedemptionRow.family_id == family_id,
                m.PointsRedemptionRow.idempotency_key == idempotency_key,
            )
        )
        row = result.scalars().first()
        return None if row is None else PointsRedemption(**_row_to_dict(row))
