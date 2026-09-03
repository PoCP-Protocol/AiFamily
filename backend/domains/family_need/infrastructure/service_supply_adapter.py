"""Service-booking-backed implementation of `SupplyReferencePort`.

Read-only, mirroring `commerce_supply_adapter.py`.  This adapter never books a
slot, never assigns a provider, and never mutates a `ServiceOffering`.  It only
translates an existing `ServiceOffering` into the family_need domain's own
`SolutionComponentRef`.

It depends only on `ServiceRepositoryPort` (the service application port),
never on the concrete `FakeServiceRepository` / SQLAlchemy repository, so the
choice of persistence stays with whoever wires this adapter (`main.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...service.application.ports import ServiceRepositoryPort
from ..domain.value_objects import ResourceGap, ResourceGapReason, SolutionComponentRef, SupplyShape

if TYPE_CHECKING:
    from ...service.domain.entities import ServiceOffering

# `SolutionComponentRef.shape` and service_booking's own vocabulary do not
# share an enum: a `ServiceOffering` has no "shape" field at all, it is always
# a service.  SERVICE is the only family_need shape that this adapter answers.
_SUPPORTED_SHAPES = frozenset({SupplyShape.SERVICE})


class ServiceSupplyAdapter:
    """Resolves `SupplyShape.SERVICE` references against the service catalogue."""

    def __init__(self, service_repository: ServiceRepositoryPort) -> None:
        self._service_repository = service_repository

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
        del region, locale  # not modelled by the service read model today.
        if shape not in _SUPPORTED_SHAPES:
            return None

        offering = await self._find_offering(tenant_id=tenant_id, component_id=component_id)
        if offering is None or not offering.is_bookable:
            return None
        if version and str(offering.version_no) != version:
            return None

        return SolutionComponentRef(
            component_id=offering.service_offering_ref,
            shape=SupplyShape.SERVICE,
            version=str(offering.version_no),
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
        offerings_by_ref = {
            offering.service_offering_ref: offering
            for offering in await self._service_repository.list_offerings(tenant_id)
        }
        for component_ref in component_refs:
            if component_ref.shape is not SupplyShape.SERVICE:
                continue
            offering = offerings_by_ref.get(component_ref.component_id)
            if offering is None or not offering.is_bookable:
                return ResourceGap.now(
                    need_id,
                    ResourceGapReason.NO_CAPACITY,
                    f"service_offering_not_available:{component_ref.component_id}",
                )
        return None

    async def get_resource_gap(
        self, *, need_id: str, reason: ResourceGapReason, detail: str
    ) -> ResourceGap:
        return ResourceGap.now(need_id, reason, detail)

    async def _find_offering(self, *, tenant_id: str, component_id: str) -> ServiceOffering | None:
        offerings = await self._service_repository.list_offerings(tenant_id)
        for offering in offerings:
            if offering.service_offering_ref == component_id:
                return offering
        return None


__all__ = ["ServiceSupplyAdapter"]
