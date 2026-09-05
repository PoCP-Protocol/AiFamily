"""Commerce-backed implementation of `SupplyReferencePort`.

Read-only.  This adapter never creates a product, never mutates the commerce
catalogue, and never charges anything.  It only translates a already-existing
`ProductOffering` into the family_need domain's own `SolutionComponentRef` so
the need context never has to know commerce's entity shape.

It depends only on `CommerceRepositoryPort` (the commerce application port),
never on a concrete `FakeCommerceRepository` / SQLAlchemy repository, so the
choice of persistence stays with whoever wires this adapter (`main.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...commerce.application.ports import CommerceRepositoryPort
from ..domain.value_objects import ResourceGap, ResourceGapReason, SolutionComponentRef, SupplyShape

if TYPE_CHECKING:
    from ...commerce.domain.entities import ProductOffering

# Shapes this adapter knows how to resolve.  `SolutionComponentRef.shape` and
# commerce's own vocabulary do not share an enum: commerce has no notion of
# "shape" at all (a `ProductOffering` is always a product).  PRODUCT is the
# only family_need shape that commerce can answer for.
_SUPPORTED_SHAPES = frozenset({SupplyShape.PRODUCT})


class CommerceSupplyAdapter:
    """Resolves `SupplyShape.PRODUCT` references against the commerce catalogue."""

    def __init__(self, commerce_repository: CommerceRepositoryPort) -> None:
        self._commerce_repository = commerce_repository

    async def resolve_component(
        self,
        *,
        tenant_id: str,
        region: str,
        locale: str,
        shape: SupplyShape,
        component_id: str,
        version: str,
    ) -> SolutionComponentRef | None:
        del region, locale  # not modelled by the commerce read model today.
        if shape not in _SUPPORTED_SHAPES:
            return None

        product = await self._find_product(tenant_id=tenant_id, component_id=component_id)
        if product is None or not product.is_bookable:
            return None
        if version and str(product.version_no) != version:
            return None

        return SolutionComponentRef(
            component_id=product.product_ref,
            shape=SupplyShape.PRODUCT,
            version=str(product.version_no),
        )

    async def check_resource_capacity(
        self,
        *,
        tenant_id: str,
        family_id: str,
        need_id: str = "",
        component_refs: tuple[SolutionComponentRef, ...],
    ) -> ResourceGap | None:
        del family_id
        products_by_ref = {
            product.product_ref: product
            for product in await self._commerce_repository.list_products(tenant_id=tenant_id)
        }
        for component_ref in component_refs:
            if component_ref.shape is not SupplyShape.PRODUCT:
                continue
            product = products_by_ref.get(component_ref.component_id)
            if product is None or not product.is_bookable:
                return ResourceGap.now(
                    need_id,
                    ResourceGapReason.NO_CAPACITY,
                    f"product_not_available:{component_ref.component_id}",
                )
        return None

    async def get_resource_gap(
        self, *, need_id: str, reason: ResourceGapReason, detail: str
    ) -> ResourceGap:
        return ResourceGap.now(need_id, reason, detail)

    async def _find_product(self, *, tenant_id: str, component_id: str) -> ProductOffering | None:
        products = await self._commerce_repository.list_products(tenant_id=tenant_id)
        for product in products:
            if product.product_ref == component_id:
                return product
        return None


__all__ = ["CommerceSupplyAdapter"]
