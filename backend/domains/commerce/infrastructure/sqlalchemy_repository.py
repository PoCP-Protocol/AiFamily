"""SQLAlchemy implementation of the commerce catalogue port."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.entities import ProductOffering
from ..domain.facts import Entitlement, OrderIntent
from . import sqlalchemy_models as m


def _row_to_entity(row: object) -> ProductOffering | OrderIntent | Entitlement:
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    if isinstance(row, m.OrderIntentRow):
        snapshot = data.get("catalog_snapshot") or {}
        data["product_ref"] = snapshot.get("product_ref", "")
        data["product_version"] = snapshot.get("product_version", 1)
        return OrderIntent(**data)
    if isinstance(row, m.EntitlementRow):
        return Entitlement(**data)
    return ProductOffering(**data)


class SqlAlchemyCommerceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def save_product(self, entity: ProductOffering) -> None:
        await self._session.merge(m.ProductOfferingRow(**entity.model_dump()))

    async def list_products(self, *, tenant_id: str) -> list[ProductOffering]:
        result = await self._session.execute(
            select(m.ProductOfferingRow).where(
                (m.ProductOfferingRow.scope_type == "PLATFORM")
                | (m.ProductOfferingRow.tenant_id == tenant_id)
            )
        )
        return [_row_to_entity(row) for row in result.scalars().all()]

    async def save_order_intent(self, entity: OrderIntent) -> None:
        data = entity.model_dump()
        snapshot = dict(data.pop("catalog_snapshot", {}))
        snapshot.update(
            {
                "product_ref": data.pop("product_ref"),
                "product_version": data.pop("product_version"),
            }
        )
        data["catalog_snapshot"] = snapshot
        await self._session.merge(m.OrderIntentRow(**data))

    async def find_order_intent_by_idempotency(
        self, *, tenant_id: str, family_id: str, idempotency_key: str
    ) -> OrderIntent | None:
        result = await self._session.execute(
            select(m.OrderIntentRow).where(
                m.OrderIntentRow.tenant_id == tenant_id,
                m.OrderIntentRow.family_id == family_id,
                m.OrderIntentRow.idempotency_key == idempotency_key,
            )
        )
        row = result.scalars().first()
        return None if row is None else _row_to_entity(row)

    async def list_order_intents(self, *, tenant_id: str, family_id: str) -> list[OrderIntent]:
        result = await self._session.execute(
            select(m.OrderIntentRow).where(
                m.OrderIntentRow.tenant_id == tenant_id,
                m.OrderIntentRow.family_id == family_id,
            )
        )
        return [_row_to_entity(row) for row in result.scalars().all()]

    async def save_entitlement(self, entity: Entitlement) -> None:
        await self._session.merge(m.EntitlementRow(**entity.model_dump()))

    async def list_entitlements(self, *, tenant_id: str, family_id: str) -> list[Entitlement]:
        result = await self._session.execute(
            select(m.EntitlementRow).where(
                m.EntitlementRow.tenant_id == tenant_id,
                m.EntitlementRow.family_id == family_id,
            )
        )
        return [_row_to_entity(row) for row in result.scalars().all()]
