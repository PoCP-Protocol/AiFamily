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
            "evidence_refs": ["evidence:payment-sandbox@v1", "evidence:refund-recovery@v1"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "FULL_24"
    assert body["execution_mode"] == "EVALUATION_ONLY"
    assert body["evaluated_at"].endswith("Z")
    assert body["evidence_refs"] == ["evidence:payment-sandbox@v1", "evidence:refund-recovery@v1"]
    assert body["ready"] is False
    assert "payment_sandbox_verified" in body["blockers"]


def test_commercial_readiness_deduplicates_evidence_refs() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/product-intelligence/courses/commercial-readiness",
        json={
            "lesson_count": 4,
            "courseware_approved": True,
            "product_package_released": True,
            "evidence_verified": True,
            "payment_sandbox_verified": True,
            "entitlement_grant_verified": True,
            "delivery_readback_verified": True,
            "refund_recovery_verified": True,
            "human_gate_accepted": True,
            "evidence_refs": [" evidence:pilot@v1 ", "evidence:pilot@v1"],
        },
    )

    assert response.status_code == 200
    assert response.json()["evidence_refs"] == ["evidence:pilot@v1"]


def test_commercial_readiness_rejects_unversioned_evidence_ref() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/product-intelligence/courses/commercial-readiness",
        json={
            "lesson_count": 4,
            "courseware_approved": True,
            "product_package_released": True,
            "evidence_verified": True,
            "payment_sandbox_verified": True,
            "entitlement_grant_verified": True,
            "delivery_readback_verified": True,
            "refund_recovery_verified": True,
            "human_gate_accepted": True,
            "evidence_refs": ["evidence:pilot"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "READINESS_EVIDENCE_REF_INVALID"


def test_commercial_readiness_requires_evidence_refs() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/product-intelligence/courses/commercial-readiness",
        json={
            "lesson_count": 4,
            "courseware_approved": True,
            "product_package_released": True,
            "evidence_verified": True,
            "payment_sandbox_verified": True,
            "entitlement_grant_verified": True,
            "delivery_readback_verified": True,
            "refund_recovery_verified": True,
            "human_gate_accepted": True,
            "evidence_refs": [],
        },
    )

    assert response.status_code == 422


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
                "evidence_refs": [
                    "evidence:unsupported-scope@v1",
                    "evidence:payment-sandbox@v1",
                    "evidence:entitlement-grant@v1",
                    "evidence:delivery-readback@v1",
                    "evidence:refund-recovery@v1",
                ],
        },
    )

    assert response.status_code == 200
    assert response.json()["scope"] == "FULL_24"
    assert response.json()["ready"] is False
    assert response.json()["blockers"] == ["lesson_scope_valid"]


def test_commercial_readiness_only_returns_ready_when_every_paid_pilot_gate_is_verified() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/product-intelligence/courses/commercial-readiness",
        json={
            "lesson_count": 4,
            "courseware_approved": True,
            "product_package_released": True,
            "evidence_verified": True,
            "payment_sandbox_verified": True,
            "entitlement_grant_verified": True,
            "delivery_readback_verified": True,
            "refund_recovery_verified": True,
            "human_gate_accepted": True,
            "evidence_refs": [
                "evidence:payment-sandbox@v1",
                "evidence:entitlement-grant@v1",
                "evidence:delivery-readback@v1",
                "evidence:refund-recovery@v1",
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["scope"] == "PILOT_21D"
    assert body["blockers"] == []
    assert all(body["checks"].values())
