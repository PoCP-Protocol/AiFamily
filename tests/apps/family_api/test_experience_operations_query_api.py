from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.experience_operations_query_api import (
    get_experience_operations_cursor_signer,
    get_experience_operations_query_service,
    router,
)
from backend.apps.family_api.experience_operations_query_wiring import (
    build_http_production_experience_operations_query_wiring,
    build_production_experience_operations_query_wiring,
)
from backend.apps.family_api.main import create_app
from backend.intelligence.evaluation.operator_identity import OperatorIdentity
from backend.intelligence.experience.operations_audit_persistence import (
    ExperienceOperationsAuditPersistenceBase,
    SqlAlchemyExperienceOperationsAuditSink,
)
from backend.intelligence.experience.operations_query import (
    EXPERIENCE_OPERATIONS_READ_SCOPE,
    AuthorizedExperienceOperationsQueryService,
    HmacExperienceOperationsCursorSigner,
)
from backend.intelligence.experience.persistence import (
    ExperienceDeliveryAttemptCursor,
    ExperienceDeliveryAttemptPage,
    ExperienceDeliveryAttemptStatus,
    ExperienceDeliveryAttemptSummary,
    StoredExperienceDeliveryAttempt,
)


def test_create_app_mounts_internal_experience_operations_routes() -> None:
    paths = create_app().openapi()["paths"]

    assert "/internal/ai/experience/delivery-attempts" in paths
    assert "/internal/ai/experience/delivery-attempts/summary" in paths


def test_create_app_exposes_explicit_operations_wiring_hook() -> None:
    calls: list[FastAPI] = []

    def wiring(application: FastAPI) -> None:
        calls.append(application)

    application = create_app(experience_operations_query_wiring=wiring)

    assert calls == [application]


def test_create_app_rejects_conflicting_operations_wiring() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        create_app(
            experience_operations_query_wiring=lambda _: None,
            experience_operations_cursor_signer=HmacExperienceOperationsCursorSigner(
                b"0123456789abcdef"
            ),
        )


def test_production_operations_wiring_validates_cursor_signer_early() -> None:
    with pytest.raises(TypeError, match="cursor signer"):
        build_production_experience_operations_query_wiring(
            environment="production",
            identity_port=_IdentityPort((EXPERIENCE_OPERATIONS_READ_SCOPE,)),
            runtime=_Runtime(),
            cursor_signer=object(),  # type: ignore[arg-type]
            session_factory=object(),  # type: ignore[arg-type]
        )


@pytest.fixture
async def operations_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperienceOperationsAuditPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class _IdentityPort:
    def __init__(self, scopes: tuple[str, ...]) -> None:
        self.scopes = scopes

    async def resolve(self, *, environment: str) -> OperatorIdentity:
        return OperatorIdentity("operator-1", environment, "auth-ref", self.scopes)


class _Runtime:
    async def delivery_attempts_page(self, *, after=None, **_kwargs):
        first = StoredExperienceDeliveryAttempt(
            message_id="attempt-a",
            attempts=2,
            status=ExperienceDeliveryAttemptStatus.PENDING,
            last_error="temporary",
            updated_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
            terminal_at=None,
            lease_owner="worker-a",
            lease_until=datetime(2026, 8, 30, 12, 5, tzinfo=UTC),
        )
        second = StoredExperienceDeliveryAttempt(
            message_id="attempt-b",
            attempts=1,
            status=ExperienceDeliveryAttemptStatus.PENDING,
            last_error=None,
            updated_at=datetime(2026, 8, 30, 11, tzinfo=UTC),
            terminal_at=datetime(2026, 8, 30, 11, tzinfo=UTC),
            lease_owner=None,
            lease_until=None,
        )
        if after is None:
            return ExperienceDeliveryAttemptPage(
                items=(first,),
                next_cursor=ExperienceDeliveryAttemptCursor(first.updated_at, first.message_id),
            )
        return ExperienceDeliveryAttemptPage(items=(second,), next_cursor=None)

    async def delivery_attempt_summary(self):
        return ExperienceDeliveryAttemptSummary(
            counts=(
                (ExperienceDeliveryAttemptStatus.PENDING, 1),
                (ExperienceDeliveryAttemptStatus.PUBLISHED, 1),
            )
        )


def _service(scopes: tuple[str, ...] = (EXPERIENCE_OPERATIONS_READ_SCOPE,)):
    return AuthorizedExperienceOperationsQueryService(
        environment="production",
        identity_port=_IdentityPort(scopes),
        runtime=_Runtime(),
    )


@pytest.mark.asyncio
async def test_production_operations_wiring_composes_query_and_durable_audit(
    operations_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    wiring = build_production_experience_operations_query_wiring(
        environment="production",
        identity_port=_IdentityPort((EXPERIENCE_OPERATIONS_READ_SCOPE,)),
        runtime=_Runtime(),
        cursor_signer=HmacExperienceOperationsCursorSigner(b"0123456789abcdef"),
        session_factory=operations_session_factory,
    )
    app = create_app(experience_operations_query_wiring=wiring)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-operator"},
    ) as client:
        response = await client.get("/internal/ai/experience/delivery-attempts/summary")

    assert response.status_code == 200
    async with operations_session_factory() as session:
        events = await SqlAlchemyExperienceOperationsAuditSink(session).list_events()
    assert len(events) == 1
    assert events[0].operation == "summary"


@pytest.mark.asyncio
async def test_http_production_operations_wiring_uses_request_identity(
    operations_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "operator_id": "operator-http",
                "environment": "production",
                "authorization_ref": "auth-http",
                "scopes": [EXPERIENCE_OPERATIONS_READ_SCOPE],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as identity_client:
        wiring = build_http_production_experience_operations_query_wiring(
            environment="production",
            identity_base_url="https://identity.example",
            runtime=_Runtime(),
            cursor_signer=HmacExperienceOperationsCursorSigner(b"0123456789abcdef"),
            session_factory=operations_session_factory,
            identity_client=identity_client,
        )
        app = create_app(experience_operations_query_wiring=wiring)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer request-operator"},
        ) as client:
            response = await client.get(
                "/internal/ai/experience/delivery-attempts/summary"
            )

    assert response.status_code == 200
    assert calls[0].headers["authorization"] == "Bearer request-operator"
    assert calls[0].headers["x-ai-environment"] == "production"


async def _client(service=None, signer=None) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(router)
    if service is not None:
        app.dependency_overrides[get_experience_operations_query_service] = (
            lambda service=service: service
        )
    if signer is not None:
        app.dependency_overrides[get_experience_operations_cursor_signer] = (
            lambda signer=signer: signer
        )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-operator"},
    )


@pytest.mark.asyncio
async def test_operations_api_is_fail_closed_without_service_or_signer() -> None:
    async with await _client() as client:
        response = await client.get("/internal/ai/experience/delivery-attempts")
    assert response.status_code == 503
    assert response.json()["detail"] == "experience_operations_query_runtime_not_configured"

    async with await _client(_service()) as client:
        response = await client.get("/internal/ai/experience/delivery-attempts")
    assert response.status_code == 503
    assert response.json()["detail"] == "experience_operations_cursor_signer_not_configured"


@pytest.mark.asyncio
async def test_operations_api_requires_request_bearer() -> None:
    signer = HmacExperienceOperationsCursorSigner(b"0123456789abcdef")
    async with await _client(_service(), signer) as client:
        response = await client.get(
            "/internal/ai/experience/delivery-attempts",
            headers={"Authorization": "Basic not-bearer"},
        )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_operations_api_requires_scope_and_returns_signed_cursor_page() -> None:
    signer = HmacExperienceOperationsCursorSigner(b"0123456789abcdef")
    denied = _service(("ai.other.read",))
    async with await _client(denied, signer) as client:
        response = await client.get("/internal/ai/experience/delivery-attempts")
    assert response.status_code == 403

    async with await _client(_service(), signer) as client:
        response = await client.get(
            "/internal/ai/experience/delivery-attempts",
            params={"limit": 1, "status": "PENDING"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["items"][0]["message_id"] == "attempt-a"
        assert body["items"][0]["status"] == "PENDING"
        assert body["items"][0]["last_error"] == "DELIVERY_ERROR_REDACTED"
        cursor = body["next_cursor"]
        assert isinstance(cursor, str)
        next_page = await client.get(
            "/internal/ai/experience/delivery-attempts",
            params={"limit": 1, "status": "PENDING", "cursor": cursor},
        )
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["message_id"] == "attempt-b"


@pytest.mark.asyncio
async def test_operations_api_rejects_tampered_or_expired_cursor() -> None:
    signer = HmacExperienceOperationsCursorSigner(
        b"0123456789abcdef", ttl=timedelta(minutes=1)
    )
    async with await _client(_service(), signer) as client:
        first = await client.get("/internal/ai/experience/delivery-attempts")
        cursor = first.json()["next_cursor"]
        tampered = await client.get(
            "/internal/ai/experience/delivery-attempts",
            params={"cursor": f"{cursor}x"},
        )
    assert tampered.status_code == 400

    stale = signer.encode(
        ExperienceDeliveryAttemptCursor(
            datetime(2026, 8, 30, 10, tzinfo=UTC), "attempt-stale"
        ),
        now=datetime(2026, 8, 30, 10, tzinfo=UTC),
    )
    async with await _client(_service(), signer) as client:
        expired = await client.get(
            "/internal/ai/experience/delivery-attempts",
            params={"cursor": stale},
        )
    assert expired.status_code == 400


@pytest.mark.asyncio
async def test_operations_summary_endpoint_is_metadata_only() -> None:
    signer = HmacExperienceOperationsCursorSigner(b"0123456789abcdef")
    async with await _client(_service(), signer) as client:
        response = await client.get("/internal/ai/experience/delivery-attempts/summary")
    assert response.status_code == 200
    assert response.json() == {"counts": {"PENDING": 1, "PUBLISHED": 1}}
