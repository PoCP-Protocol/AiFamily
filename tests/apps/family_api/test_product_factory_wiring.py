from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api.product_factory_wiring import (
    clear_product_factory_actor_resolver,
    install_product_factory_actor_resolver,
    mount_product_factory_router,
)
from backend.domains.product_intelligence.api.dependencies import get_actor_context
from backend.domains.product_intelligence.application.context import ActorContext


def test_product_factory_mount_exposes_draft_contract_without_identity_fallback() -> None:
    app = FastAPI()
    mount_product_factory_router(app)
    # FastAPI 0.141 keeps included routers lazy until schema/dispatch
    # resolution; OpenAPI is the public route-discovery contract.
    paths = set(app.openapi()["paths"])
    assert "/product-intelligence/product-factory/demand-frames" in paths
    assert "/product-intelligence/product-factory/product-packages" in paths


def test_product_factory_mount_is_idempotent() -> None:
    app = FastAPI()
    mount_product_factory_router(app)
    mount_product_factory_router(app)

    routes = [
        route
        for route in app.routes
        if getattr(route, "path", "").startswith("/product-intelligence/product-factory/")
    ]
    signatures = [(route.path, frozenset(route.methods or ())) for route in routes]
    assert len(signatures) == len(set(signatures))


def test_product_factory_actor_resolver_is_explicitly_injectable() -> None:
    app = FastAPI()

    @app.get("/actor")
    async def actor(context: ActorContext = Depends(get_actor_context)) -> dict[str, str]:
        return {"actor_id": context.actor_id, "tenant_scope": context.tenant_scope}

    async def resolver(_request):
        return ActorContext(
            actor_id="human:pm",
            actor_type="HUMAN",
            tenant_scope="tenant-a",
        )

    install_product_factory_actor_resolver(resolver)
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/actor")
    finally:
        clear_product_factory_actor_resolver()

    assert response.status_code == 200
    assert response.json() == {"actor_id": "human:pm", "tenant_scope": "tenant-a"}


def test_product_factory_actor_resolver_rejects_invalid_context() -> None:
    app = FastAPI()

    @app.get("/actor")
    async def actor(context: ActorContext = Depends(get_actor_context)) -> dict[str, str]:
        return {"actor_id": context.actor_id}

    async def invalid_resolver(_request):
        return {"actor_id": "untrusted"}

    install_product_factory_actor_resolver(invalid_resolver)
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/actor")
    finally:
        clear_product_factory_actor_resolver()

    assert response.status_code == 500
