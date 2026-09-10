import pytest

from backend.domains.commerce.application.commands import request_refund, submit_order_intent
from backend.domains.commerce.application.master_data import ensure_mobile_product_master_data
from backend.domains.commerce.application.queries import get_customer_projection
from backend.domains.commerce.domain.errors import CommerceValidationError
from backend.domains.commerce.infrastructure.fake_repository import FakeCommerceRepository


@pytest.mark.asyncio
async def test_refund_revokes_entitlement_and_is_idempotent():
    repo = FakeCommerceRepository()
    await ensure_mobile_product_master_data(repo)
    intent, _ = await submit_order_intent(
        repo, tenant_id="t1", family_id="f1", actor_person_id="p1",
        product_ref="PRODUCT_PARENT_CHILD_CAMP", product_version=1,
        page_id="UI-14", idempotency_key="order-1", correlation_id="c1",
    )
    refund, entitlement = await request_refund(
        repo, tenant_id="t1", family_id="f1", source_order_intent_id=intent.order_intent_id,
        idempotency_key="refund-1", reason="family changed plans",
        evidence_receipt_ref="evidence:refund-recovery@v1",
    )
    again, same = await request_refund(
        repo, tenant_id="t1", family_id="f1", source_order_intent_id=intent.order_intent_id,
        idempotency_key="refund-1", reason="ignored",
    )
    assert refund.status == "PROCESSED"
    assert entitlement.status == "REVOKED"
    assert entitlement.attributes["evidence_refs"] == ["evidence:refund-recovery@v1"]
    projection = await get_customer_projection(repo, tenant_id="t1", family_id="f1")
    assert projection["evidence_receipt_refs"] == ["evidence:refund-recovery@v1"]
    assert again == refund and same == entitlement


@pytest.mark.asyncio
async def test_refund_requires_reason():
    with pytest.raises(CommerceValidationError, match="refund_reason"):
        await request_refund(FakeCommerceRepository(), tenant_id="t", family_id="f",
                             source_order_intent_id="missing", idempotency_key="r", reason=" ")


@pytest.mark.asyncio
async def test_refund_rejects_invalid_evidence_receipt() -> None:
    with pytest.raises(CommerceValidationError, match="refund_evidence_receipt_invalid"):
        await request_refund(
            FakeCommerceRepository(), tenant_id="t", family_id="f",
            source_order_intent_id="missing", idempotency_key="r", reason="changed",
            evidence_receipt_ref="evidence:refund-recovery",
        )
