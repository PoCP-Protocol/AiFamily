from datetime import UTC, datetime

import pytest

from backend.domains.commerce.application.queries import get_customer_projection
from backend.domains.commerce.domain.facts import Entitlement, OrderIntent
from backend.domains.commerce.infrastructure.fake_repository import FakeCommerceRepository


@pytest.mark.asyncio
async def test_customer_projection_exposes_deduplicated_evidence_receipts() -> None:
    repo = FakeCommerceRepository()
    now = datetime.now(UTC)
    repo.order_intents["order-1"] = OrderIntent(
        order_intent_id="order-1", tenant_id="tenant-1", family_id="family-1",
        actor_person_id="person-1", intent_ref="intent-1", product_id="product-1",
        product_ref="PRODUCT_21D", product_version=1, source_page_id="UI-14",
        idempotency_key="order-key", created_at=now, updated_at=now,
        attributes={
            "evidence_refs": ["evidence:payment-sandbox@v1", "evidence:delivery-readback@v1"]
        },
    )
    repo.entitlements["ent-1"] = Entitlement(
        entitlement_id="ent-1", tenant_id="tenant-1", family_id="family-1",
        source_order_intent_id="order-1", entitlement_ref="ENTITLEMENT_PRODUCT_21D_V1",
        status="REVOKED", created_at=now, updated_at=now,
        attributes={
            "evidence_refs": ["evidence:refund-recovery@v1", "evidence:delivery-readback@v1"]
        },
    )

    projection = await get_customer_projection(repo, tenant_id="tenant-1", family_id="family-1")

    assert projection["evidence_receipt_refs"] == [
        "evidence:delivery-readback@v1", "evidence:payment-sandbox@v1",
        "evidence:refund-recovery@v1",
    ]
