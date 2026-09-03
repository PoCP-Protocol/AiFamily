"""Family-scoped read model for the mobile product catalogue."""

from .ports import CommerceRepositoryPort


async def list_product_catalogue(
    repo: CommerceRepositoryPort, *, tenant_id: str
) -> dict:
    products = [
        product
        for product in await repo.list_products(tenant_id=tenant_id)
        if product.is_bookable
    ]
    products.sort(key=lambda product: product.product_ref)
    return {
        "tenant_id": tenant_id,
        "products": [
            {
                "product_id": product.product_id,
                "product_ref": product.product_ref,
                "product_version": product.version_no,
                "title": product.title,
                "admission_status": product.admission_status,
                "source_ref": product.source_ref,
                "fixture_only": product.fixture_only,
                "attributes_schema_version": product.attributes_schema_version,
                "attributes": product.attributes,
            }
            for product in products
        ],
    }


async def get_customer_projection(
    repo: CommerceRepositoryPort, *, tenant_id: str, family_id: str
) -> dict:
    intents = await repo.list_order_intents(tenant_id=tenant_id, family_id=family_id)
    entitlements = await repo.list_entitlements(tenant_id=tenant_id, family_id=family_id)
    return {
        "family_id": family_id,
        "projection_version": 1,
        "visibility": "FAMILY_PRIVATE",
        "order_intents": [
            {
                "order_intent_id": intent.order_intent_id,
                "status": intent.status,
                "product_ref": intent.product_ref,
                "product_version": intent.product_version,
                "created_at": intent.created_at,
            }
            for intent in sorted(intents, key=lambda item: item.created_at, reverse=True)
        ],
        "entitlements": [
            {
                "entitlement_id": entitlement.entitlement_id,
                "status": entitlement.status,
                "source_order_intent_id": entitlement.source_order_intent_id,
                "available_at": entitlement.available_at,
                "expires_at": entitlement.expires_at,
            }
            for entitlement in entitlements
        ],
        "text_equivalent": "购买意向仅保存于本家庭，不会扣款或自动开通权益。",
    }
