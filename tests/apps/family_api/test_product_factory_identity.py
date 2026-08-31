from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api.product_factory_identity import (
    ProductFactoryBearerActorResolver,
)
from backend.domains.product_intelligence.api.dependencies import get_actor_context
from backend.domains.product_intelligence.application.context import ActorContext
from backend.platform.identity.session_port import VerifiedIdentitySession


class FakeSessionPort:
    def __init__(self, session: VerifiedIdentitySession | Exception):
        self.session = session
        self.tokens: list[str] = []

    async def introspect(self, *, access_token: str) -> VerifiedIdentitySession:
        self.tokens.append(access_token)
        if isinstance(self.session, Exception):
            raise self.session
        return self.session


def _app(resolver: ProductFactoryBearerActorResolver) -> FastAPI:
    app = FastAPI()

    async def actor(context: ActorContext = Depends(get_actor_context)) -> dict[str, object]:
        return {
            "actor_id": context.actor_id,
            "tenant_scope": context.tenant_scope,
            "trace_id": context.trace_id or "",
            "permissions": sorted(context.permissions),
        }

    app.get("/actor")(actor)
    from backend.apps.family_api.product_factory_wiring import (
        clear_product_factory_actor_resolver,
        install_product_factory_bearer_identity,
    )

    install_product_factory_bearer_identity(
        resolver.session_port,
        resolver.tenant_scope_resolver,
        resolver.permission_resolver,
    )
    app.state.clear_product_factory_actor_resolver = clear_product_factory_actor_resolver
    return app


def test_bearer_bridge_introspects_and_resolves_tenant() -> None:
    session_port = FakeSessionPort(
        VerifiedIdentitySession(
            session_id="session-1",
            account_id="account-1",
            family_id="family-1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )

    async def tenant_scope(session, _request):
        assert session.family_id == "family-1"
        return "tenant-a"

    app = _app(ProductFactoryBearerActorResolver(session_port, tenant_scope))
    try:
        response = TestClient(app).get("/actor", headers={"Authorization": "Bearer opaque-token"})
    finally:
        app.state.clear_product_factory_actor_resolver()

    assert response.status_code == 200
    assert response.json() == {
        "actor_id": "account:account-1",
        "tenant_scope": "tenant-a",
        "trace_id": "identity-session:session-1",
        "permissions": [],
    }
    assert session_port.tokens == ["opaque-token"]


def test_bearer_bridge_rejects_missing_or_expired_identity() -> None:
    session_port = FakeSessionPort(
        VerifiedIdentitySession(
            session_id="session-expired",
            account_id="account-1",
            family_id="family-1",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )

    async def tenant_scope(_session, _request):
        return "tenant-a"

    app = _app(ProductFactoryBearerActorResolver(session_port, tenant_scope))
    try:
        missing = TestClient(app, raise_server_exceptions=False).get("/actor")
        expired = TestClient(app, raise_server_exceptions=False).get(
            "/actor", headers={"Authorization": "Bearer expired-token"}
        )
    finally:
        app.state.clear_product_factory_actor_resolver()

    assert missing.status_code == 500
    assert expired.status_code == 500
    assert session_port.tokens == ["expired-token"]


def test_bearer_bridge_rejects_tenant_resolver_failure() -> None:
    session_port = FakeSessionPort(
        VerifiedIdentitySession(
            session_id="session-1",
            account_id="account-1",
            family_id="family-1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )

    async def tenant_scope(_session, _request):
        raise RuntimeError("untrusted")

    app = _app(ProductFactoryBearerActorResolver(session_port, tenant_scope))
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/actor", headers={"Authorization": "Bearer opaque-token"}
        )
    finally:
        app.state.clear_product_factory_actor_resolver()

    assert response.status_code == 500


def test_bearer_bridge_resolves_permissions_from_trusted_policy() -> None:
    session_port = FakeSessionPort(
        VerifiedIdentitySession(
            session_id="session-1",
            account_id="account-1",
            family_id="family-1",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )

    async def tenant_scope(_session, _request):
        return "tenant-a"

    async def permissions(session, tenant, _request):
        assert session.account_id == "account-1"
        assert tenant == "tenant-a"
        return frozenset({"product_intelligence.product_definition.review"})

    app = _app(
        ProductFactoryBearerActorResolver(
            session_port,
            tenant_scope,
            permission_resolver=permissions,
        )
    )
    try:
        response = TestClient(app).get("/actor", headers={"Authorization": "Bearer opaque-token"})
    finally:
        app.state.clear_product_factory_actor_resolver()

    assert response.status_code == 200
    assert response.json()["permissions"] == ["product_intelligence.product_definition.review"]
