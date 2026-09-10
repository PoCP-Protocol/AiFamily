"""Production Commerce catalogue read-only HTTP boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Header, HTTPException

from backend.domains.commerce.application import queries
from backend.domains.commerce.application.ports import CommerceRepositoryPort

from .production_commerce_context import (
    ProductionCommerceReadContext,
    ProductionCommerceReadContextResolver,
)

RepositoryFactory = Callable[[], Awaitable[CommerceRepositoryPort]]


def build_production_commerce_router(
    *,
    context_resolver: ProductionCommerceReadContextResolver,
    repository_factory: RepositoryFactory,
) -> APIRouter:
    router = APIRouter(prefix="/families/{family_id}/commerce", tags=["commerce"])

    @router.get("/products")
    async def get_products(
        family_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> dict:
        try:
            context: ProductionCommerceReadContext = await context_resolver.resolve(
                family_id=family_id,
                authorization=authorization,
                correlation_id=x_correlation_id,
                causation_id=x_causation_id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="commerce_family_access_denied") from exc
        if context.family_id != family_id:
            raise HTTPException(status_code=403, detail="commerce_family_scope_mismatch")
        repository = await repository_factory()
        result = await queries.list_product_catalogue(repository, tenant_id=context.tenant_id)
        result["family_id"] = context.family_id
        result["read_only"] = True
        return result

    @router.get("/projection")
    async def get_customer_projection(
        family_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> dict:
        """Return the durable family-scoped commerce delivery projection.

        This is deliberately a read boundary: payment, fulfilment, and refund
        side effects are owned by their respective command workers.  Exposing
        the projection here lets the Web product workspace verify delivery and
        recovery after a restart without mistaking a UI draft for entitlement.
        """
        try:
            context: ProductionCommerceReadContext = await context_resolver.resolve(
                family_id=family_id,
                authorization=authorization,
                correlation_id=x_correlation_id,
                causation_id=x_causation_id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="commerce_family_access_denied") from exc
        if context.family_id != family_id:
            raise HTTPException(status_code=403, detail="commerce_family_scope_mismatch")
        repository = await repository_factory()
        result = await queries.get_customer_projection(
            repository, tenant_id=context.tenant_id, family_id=context.family_id
        )
        result["tenant_id"] = context.tenant_id
        result["read_only"] = True
        return result

    return router


__all__ = ["build_production_commerce_router"]
