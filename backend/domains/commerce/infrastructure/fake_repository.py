"""In-memory commerce catalogue repository for DEV/TEST."""

from ..domain.entities import ProductOffering
from ..domain.facts import Entitlement, OrderIntent


class FakeCommerceRepository:
    def __init__(self) -> None:
        self.products: dict[str, ProductOffering] = {}
        self.order_intents: dict[str, OrderIntent] = {}
        self.entitlements: dict[str, Entitlement] = {}

    async def commit(self) -> None:
        return None

    async def save_product(self, entity: ProductOffering) -> None:
        self.products[entity.product_id] = entity

    async def list_products(self, *, tenant_id: str) -> list[ProductOffering]:
        return [
            product
            for product in self.products.values()
            if product.scope_type == "PLATFORM"
            or product.tenant_id == tenant_id
        ]

    async def save_order_intent(self, entity: OrderIntent) -> None:
        self.order_intents[entity.order_intent_id] = entity

    async def find_order_intent_by_idempotency(
        self, *, tenant_id: str, family_id: str, idempotency_key: str
    ) -> OrderIntent | None:
        return next(
            (
                intent
                for intent in self.order_intents.values()
                if intent.tenant_id == tenant_id
                and intent.family_id == family_id
                and intent.idempotency_key == idempotency_key
            ),
            None,
        )

    async def list_order_intents(self, *, tenant_id: str, family_id: str) -> list[OrderIntent]:
        return [
            intent
            for intent in self.order_intents.values()
            if intent.tenant_id == tenant_id and intent.family_id == family_id
        ]

    async def save_entitlement(self, entity: Entitlement) -> None:
        self.entitlements[entity.entitlement_id] = entity

    async def list_entitlements(self, *, tenant_id: str, family_id: str) -> list[Entitlement]:
        return [
            entitlement
            for entitlement in self.entitlements.values()
            if entitlement.tenant_id == tenant_id and entitlement.family_id == family_id
        ]
