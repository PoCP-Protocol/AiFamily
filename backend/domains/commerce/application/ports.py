"""Ports for the commerce catalogue read model."""

from __future__ import annotations

from typing import Protocol

from ..domain.entities import ProductOffering
from ..domain.facts import Entitlement, OrderIntent


class CommerceRepositoryPort(Protocol):
    async def commit(self) -> None: ...

    async def save_product(self, entity: ProductOffering) -> None: ...

    async def list_products(self, *, tenant_id: str) -> list[ProductOffering]: ...

    async def save_order_intent(self, entity: OrderIntent) -> None: ...

    async def find_order_intent_by_idempotency(
        self, *, tenant_id: str, family_id: str, idempotency_key: str
    ) -> OrderIntent | None: ...

    async def list_order_intents(self, *, tenant_id: str, family_id: str) -> list[OrderIntent]: ...

    async def save_entitlement(self, entity: Entitlement) -> None: ...

    async def list_entitlements(self, *, tenant_id: str, family_id: str) -> list[Entitlement]: ...
