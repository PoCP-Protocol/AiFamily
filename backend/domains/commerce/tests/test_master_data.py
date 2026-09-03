from backend.domains.commerce.application.commands import submit_order_intent
from backend.domains.commerce.application.master_data import ensure_mobile_product_master_data
from backend.domains.commerce.application.queries import list_product_catalogue
from backend.domains.commerce.infrastructure.fake_repository import FakeCommerceRepository


async def test_product_master_data_is_idempotent_and_admitted():
    repo = FakeCommerceRepository()
    await ensure_mobile_product_master_data(repo)
    await ensure_mobile_product_master_data(repo)

    result = await list_product_catalogue(repo, tenant_id="family-1")
    assert len(result["products"]) == 4
    assert {item["product_ref"] for item in result["products"]} == {
        "PRODUCT_PARENT_CHILD_CAMP",
        "PRODUCT_FAMILY_ASSESSMENT_CARD",
        "PRODUCT_PARENT_CHILD_READING_TOOLKIT",
        "PRODUCT_FAMILY_FOCUS_CAMP",
    }
    assert all(item["fixture_only"] is True for item in result["products"])


async def test_product_catalogue_is_platform_scoped_for_each_family():
    repo = FakeCommerceRepository()
    await ensure_mobile_product_master_data(repo)

    first = await list_product_catalogue(repo, tenant_id="family-1")
    second = await list_product_catalogue(repo, tenant_id="family-2")
    assert first["tenant_id"] == "family-1"
    assert second["tenant_id"] == "family-2"
    assert [item["product_ref"] for item in first["products"]] == [
        item["product_ref"] for item in second["products"]
    ]


async def test_order_intent_is_idempotent_and_family_private():
    repo = FakeCommerceRepository()
    await ensure_mobile_product_master_data(repo)
    args = {
        "tenant_id": "family-1",
        "family_id": "family-1",
        "actor_person_id": "parent-1",
        "product_ref": "PRODUCT_PARENT_CHILD_CAMP",
        "product_version": 1,
        "page_id": "UI-14",
        "idempotency_key": "intent-family-1-camp-v1",
        "correlation_id": "corr-1",
    }
    first = await submit_order_intent(repo, **args)
    second = await submit_order_intent(repo, **args)
    assert first[0].order_intent_id == second[0].order_intent_id
    assert len(await repo.list_order_intents(tenant_id="family-1", family_id="family-1")) == 1
    projection = await repo.list_entitlements(tenant_id="family-1", family_id="family-1")
    assert len(projection) == 1
    assert projection[0].external_effect is False
