from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from ..api.evidence_receipt_health_contracts import EvidenceReceiptHealthResponse
from ..api.evidence_receipt_health_dependencies import (
    clear_evidence_receipt_health_session_factory,
    get_authorized_evidence_receipt_health_context,
    get_evidence_receipt_health_clock,
    get_evidence_receipt_health_reader,
)
from ..api.evidence_receipt_health_routes import router
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceNotFoundError,
)
from .test_evidence_receipt_health import NOW, FakeReader, context


def test_health_router_remains_unmounted_from_production_composition() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    composition_files = list((repo_root / "backend/apps/family_api").glob("*.py"))
    composition_files.append(
        repo_root / "backend/domains/product_intelligence/api/routes.py"
    )
    content = "\n".join(path.read_text(encoding="utf-8") for path in composition_files)
    assert "evidence_receipt_health" not in content


def app_with(reader: FakeReader, *, allowed: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_authorized_evidence_receipt_health_context] = (
        lambda: context(allowed=allowed)
    )
    app.dependency_overrides[get_evidence_receipt_health_reader] = lambda: reader
    app.dependency_overrides[get_evidence_receipt_health_clock] = lambda: NOW
    return app


@pytest.mark.asyncio
async def test_health_http_is_no_store_unknown_and_not_an_admission() -> None:
    app = app_with(FakeReader())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/product-intelligence/evidence-verification-receipts/receipt:one/health"
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["current_policy_precheck"] == "PASS"
    assert body["receipt_traceability_health"] == "UNKNOWN"
    assert body["authoritative_admission"] is False
    assert body["final_revalidation_required"] is True
    assert body["claim_applicability_evaluated"] is False
    assert body["admission_state"] == "NOT_EVALUATED"
    assert body["human_gate_state"] == "NOT_EVALUATED"
    serialized = str(body).lower()
    for forbidden in ("decision_reason", "claim_scope", "applicability_scope", "score", "rank"):
        assert forbidden not in serialized

    contradictory_fail = {
        **body,
        "current_policy_precheck": "FAIL",
        "receipt_traceability_health": "UNHEALTHY",
    }
    contradictory_lifecycle = {**body, "receipt_lifecycle": "EXPIRED"}
    with pytest.raises(ValidationError):
        EvidenceReceiptHealthResponse.model_validate(contradictory_fail)
    with pytest.raises(ValidationError):
        EvidenceReceiptHealthResponse.model_validate(contradictory_lifecycle)


@pytest.mark.asyncio
async def test_health_http_maps_authorization_before_reader_io() -> None:
    reader = FakeReader()
    app = app_with(reader, allowed=False)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/product-intelligence/evidence-verification-receipts/receipt:one/health"
        )

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"] == "PRODUCT_PACKAGE_READ_FORBIDDEN"
    assert reader.receipt_calls == 0
    assert reader.evidence_calls == 0


@pytest.mark.asyncio
async def test_health_http_keeps_missing_receipt_and_corruption_distinct() -> None:
    missing = FakeReader()
    missing.receipt_value = ProductIntelligenceNotFoundError(
        "evidence_verification_receipt_not_found"
    )
    corrupt = FakeReader(
        receipt_value=ProductIntelligenceConflictError(
            "evidence_verification_persisted_payload_invalid"
        )
    )
    async with AsyncClient(
        transport=ASGITransport(app=app_with(missing)),
        base_url="http://test",
    ) as client:
        missing_response = await client.get(
            "/product-intelligence/evidence-verification-receipts/missing/health"
        )
    async with AsyncClient(
        transport=ASGITransport(app=app_with(corrupt)),
        base_url="http://test",
    ) as client:
        corrupt_response = await client.get(
            "/product-intelligence/evidence-verification-receipts/receipt:one/health"
        )

    assert missing_response.status_code == 404
    assert corrupt_response.status_code == 409
    assert missing_response.headers["cache-control"] == "no-store"
    assert corrupt_response.headers["cache-control"] == "no-store"
    assert corrupt_response.json()["detail"] == "EVIDENCE_RECEIPT_PERSISTED_STATE_INVALID"


@pytest.mark.asyncio
async def test_unconfigured_health_reader_fails_closed() -> None:
    clear_evidence_receipt_health_session_factory()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_authorized_evidence_receipt_health_context] = context
    app.dependency_overrides[get_evidence_receipt_health_clock] = lambda: NOW
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/product-intelligence/evidence-verification-receipts/receipt:one/health"
        )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"] == (
        "EVIDENCE_RECEIPT_HEALTH_REPOSITORY_NOT_CONFIGURED"
    )


@pytest.mark.asyncio
async def test_runtime_reader_failure_is_stable_retryable_boundary() -> None:
    unavailable = FakeReader(receipt_value=RuntimeError("database offline"))
    async with AsyncClient(
        transport=ASGITransport(app=app_with(unavailable)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/product-intelligence/evidence-verification-receipts/receipt:one/health"
        )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"] == "EVIDENCE_RECEIPT_HEALTH_REPOSITORY_UNAVAILABLE"
