from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from backend.apps.family_api.evaluation_query_api import (
    router,
)
from backend.apps.family_api.evaluation_query_wiring import (
    build_http_production_evaluation_query_wiring,
    build_production_evaluation_query_service,
    install_evaluation_query_service,
)
from backend.intelligence.evaluation.operator_identity import OperatorIdentity
from backend.intelligence.evaluation.query import EVALUATION_READ_SCOPE
from backend.intelligence.evaluation.report_archive import InMemoryBenchmarkReportArchive
from backend.intelligence.evaluation.slice_archive import InMemoryBenchmarkSliceArchive
from tests.intelligence.evaluation.test_report_archive import _report


class _IdentityPort:
    def __init__(self, scopes: tuple[str, ...]) -> None:
        self.scopes = scopes

    async def resolve(self, *, environment: str) -> OperatorIdentity:
        return OperatorIdentity("operator-1", environment, "auth-ref", self.scopes)


class _ArchiveRuntime:
    def __init__(self) -> None:
        self.reports = InMemoryBenchmarkReportArchive(
            clock=lambda: datetime(2026, 8, 30, tzinfo=UTC)
        )
        self.slices = InMemoryBenchmarkSliceArchive(
            clock=lambda: datetime(2026, 8, 30, tzinfo=UTC)
        )

    async def list(self, **kwargs):
        return await self.reports.list(**kwargs)

    async def list_slices(self, **kwargs):
        return await self.slices.list(**kwargs)


async def _client(service=None) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(router)
    if service is not None:
        install_evaluation_query_service(app, service)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-operator"},
    )


@pytest.mark.asyncio
async def test_query_api_is_fail_closed_without_composed_runtime() -> None:
    async with await _client() as client:
        response = await client.get("/internal/ai/evaluations/reports")
    assert response.status_code == 503
    assert response.json()["detail"] == "evaluation_query_runtime_not_configured"


@pytest.mark.asyncio
async def test_query_api_requires_request_bearer() -> None:
    async with await _client() as client:
        response = await client.get(
            "/internal/ai/evaluations/reports",
            headers={"Authorization": "Basic invalid"},
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_query_api_requires_read_scope_and_returns_metadata_only() -> None:
    runtime = _ArchiveRuntime()
    report = _report()
    await runtime.reports.archive(report, dataset_fingerprint="a" * 64)
    denied = build_production_evaluation_query_service(
        environment="staging",
        identity_port=_IdentityPort(("ai.release.read",)),
        archive_runtime=runtime,
    )
    async with await _client(denied) as client:
        response = await client.get("/internal/ai/evaluations/reports")
    assert response.status_code == 403

    allowed = build_production_evaluation_query_service(
        environment="staging",
        identity_port=_IdentityPort((EVALUATION_READ_SCOPE,)),
        archive_runtime=runtime,
    )
    async with await _client(allowed) as client:
        response = await client.get("/internal/ai/evaluations/reports", params={"limit": 1})
    assert response.status_code == 200
    body = response.json()[0]
    assert body["report_ref"] == report.report_ref
    assert "output" not in str(body).lower()


@pytest.mark.asyncio
async def test_http_evaluation_query_wiring_uses_request_identity() -> None:
    runtime = _ArchiveRuntime()
    report = _report()
    await runtime.reports.archive(report, dataset_fingerprint="b" * 64)
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "operator_id": "operator-eval",
                "environment": "staging",
                "authorization_ref": "auth-eval",
                "scopes": [EVALUATION_READ_SCOPE],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as identity_client:
        wiring = build_http_production_evaluation_query_wiring(
            environment="staging",
            identity_base_url="https://identity.example",
            archive_runtime=runtime,
            identity_client=identity_client,
        )
        app = FastAPI()
        app.include_router(router)
        wiring(app)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer eval-request"},
        ) as client:
            response = await client.get("/internal/ai/evaluations/reports")

    assert response.status_code == 200
    assert response.json()[0]["dataset_fingerprint"] == "b" * 64
    assert calls[0].headers["authorization"] == "Bearer eval-request"
