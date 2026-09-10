from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api.production_commerce_api import build_production_commerce_router


class Resolver:
    async def resolve(self, **kwargs):
        from backend.apps.family_api.production_commerce_context import (
            ProductionCommerceReadContext,
        )

        return ProductionCommerceReadContext(
            account_id="account-1",
            tenant_id="tenant-1",
            family_id=kwargs["family_id"],
            correlation_id="corr-1",
            causation_id="cause-1",
        )


class Repository:
    async def list_products(self, *, tenant_id):
        return []

    async def list_order_intents(self, *, tenant_id, family_id):
        return []

    async def list_entitlements(self, *, tenant_id, family_id):
        return []


def test_production_catalogue_is_read_only_and_family_bound() -> None:
    app = FastAPI()
    app.include_router(
        build_production_commerce_router(
            context_resolver=Resolver(), repository_factory=lambda: _repo()
        )
    )
    response = TestClient(app).get("/families/family-1/commerce/products")
    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "tenant-1",
        "family_id": "family-1",
        "products": [],
        "read_only": True,
    }


def test_production_projection_is_family_scoped_and_read_only() -> None:
    app = FastAPI()
    app.include_router(
        build_production_commerce_router(
            context_resolver=Resolver(), repository_factory=lambda: _repo()
        )
    )
    response = TestClient(app).get("/families/family-1/commerce/projection")
    assert response.status_code == 200
    assert response.json()["family_id"] == "family-1"
    assert response.json()["tenant_id"] == "tenant-1"
    assert response.json()["read_only"] is True
    assert response.json()["order_intents"] == []
    assert response.json()["entitlements"] == []


async def _repo() -> Repository:
    return Repository()
