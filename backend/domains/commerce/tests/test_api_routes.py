from fastapi.testclient import TestClient

from backend.apps.family_api.dev_wiring import reset_dev_state
from backend.apps.family_api.main import create_app


def test_dev_product_catalogue_route_returns_admitted_products():
    reset_dev_state()
    client = TestClient(create_app())
    session = client.post(
        "/auth/account-session",
        json={"external_ref": "parent-commerce:family-commerce"},
        headers={"idempotency-key": "commerce-session-1"},
    )
    assert session.status_code == 200, session.text
    token = session.json()["token"]
    response = client.get(
        "/families/family-commerce/orchestration/test-loop/commerce/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["tenant_id"] == "family-commerce"
    assert len(payload["products"]) == 4
    assert all(item["admission_status"] == "ADMITTED" for item in payload["products"])


def test_product_catalogue_route_rejects_foreign_family():
    reset_dev_state()
    client = TestClient(create_app())
    session = client.post(
        "/auth/account-session",
        json={"external_ref": "parent-commerce:family-commerce"},
        headers={"idempotency-key": "commerce-session-2"},
    )
    token = session.json()["token"]
    response = client.get(
        "/families/other-family/orchestration/test-loop/commerce/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_dev_order_intent_is_idempotent_and_projected():
    reset_dev_state()
    client = TestClient(create_app())
    session = client.post(
        "/auth/account-session",
        json={"external_ref": "parent-commerce:family-commerce"},
        headers={"idempotency-key": "commerce-session-3"},
    )
    token = session.json()["token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "idempotency-key": "commerce-intent-1",
    }
    body = {
        "page_id": "UI-14",
        "product_ref": "PRODUCT_PARENT_CHILD_CAMP",
        "product_version": 1,
    }
    first = client.post(
        "/families/family-commerce/orchestration/test-loop/commerce/order-intents",
        headers=headers,
        json=body,
    )
    second = client.post(
        "/families/family-commerce/orchestration/test-loop/commerce/order-intents",
        headers=headers,
        json=body,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["intent"]["order_intent_id"] == second.json()["intent"]["order_intent_id"]
    projection = client.get(
        "/families/family-commerce/orchestration/test-loop/commerce/customer-projection",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert projection.status_code == 200
    assert len(projection.json()["order_intents"]) == 1
    assert projection.json()["visibility"] == "FAMILY_PRIVATE"
