from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.product_intelligence.api.course_routes import router


def test_commercial_readiness_exposes_blockers_without_side_effects() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/product-intelligence/courses/commercial-readiness",
        json={
            "lesson_count": 24,
            "courseware_approved": True,
            "product_package_released": True,
            "evidence_verified": True,
            "payment_sandbox_verified": False,
            "entitlement_grant_verified": False,
            "delivery_readback_verified": False,
            "refund_recovery_verified": False,
            "human_gate_accepted": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert "payment_sandbox_verified" in body["blockers"]


def test_commercial_readiness_rejects_unsupported_product_scope() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/product-intelligence/courses/commercial-readiness",
        json={
            "lesson_count": 90,
            "courseware_approved": True,
            "product_package_released": True,
            "evidence_verified": True,
            "payment_sandbox_verified": True,
            "entitlement_grant_verified": True,
            "delivery_readback_verified": True,
            "refund_recovery_verified": True,
            "human_gate_accepted": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["blockers"] == ["lesson_scope_valid"]
