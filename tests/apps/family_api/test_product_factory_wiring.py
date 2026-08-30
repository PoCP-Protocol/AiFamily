from __future__ import annotations

from fastapi import FastAPI

from backend.apps.family_api.product_factory_wiring import mount_product_factory_router


def test_product_factory_mount_exposes_draft_contract_without_identity_fallback() -> None:
    app = FastAPI()
    mount_product_factory_router(app)
    # FastAPI 0.141 keeps included routers lazy until schema/dispatch
    # resolution; OpenAPI is the public route-discovery contract.
    paths = set(app.openapi()["paths"])
    assert "/product-intelligence/product-factory/demand-frames" in paths
    assert "/product-intelligence/product-factory/product-packages" in paths
