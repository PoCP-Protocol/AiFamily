"""Composition root for the Family Need HTTP dependency seam.

Mirrors ``backend/apps/family_api/growth_onboarding_wiring.py``: dev/test
installs an explicit fake runtime with the same route contract as production;
production installs a PostgreSQL-backed application service and actor
resolver only when an explicit PostgreSQL URL exists, otherwise the route
stays mounted with its fail-closed 503 defaults.

This module owns no business rule.  It only assembles already-existing
adapters (``SqlAlchemyFamilyNeedRepository``, ``SqlAlchemyFamilyNeedActorResolver``,
``CommerceSupplyAdapter``, ``ServiceSupplyAdapter``) behind the same
``FamilyNeedApplicationService`` shape the fake runtime uses.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI, Header, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncEngine

from ..api import dependencies as family_need_deps
from ..application.ports import SupplyReferencePort
from ..application.service import FamilyNeedApplicationService
from ..domain.value_objects import SupplyShape
from .actor_resolver import FamilyNeedAuthenticationError
from .commerce_supply_adapter import CommerceSupplyAdapter
from .course_supply_adapter import CourseSupplyAdapter
from .fake_repository import FakeFamilyNeedPolicy, FakeFamilyNeedRepository
from .service_supply_adapter import ServiceSupplyAdapter


@dataclass(frozen=True)
class FakeFamilyNeedRuntime:
    """Explicit dev/test runtime; same shapes production assembles."""

    service: FamilyNeedApplicationService
    repository: FakeFamilyNeedRepository
    policy: FakeFamilyNeedPolicy


def build_fake_family_need_runtime(
    *, supply_port: SupplyReferencePort | None = None
) -> FakeFamilyNeedRuntime:
    repository = FakeFamilyNeedRepository()
    policy = FakeFamilyNeedPolicy()
    service = FamilyNeedApplicationService(repository, policy, supply_port=supply_port)
    return FakeFamilyNeedRuntime(service=service, repository=repository, policy=policy)


class CompositeSupplyAdapter:
    """Fans a component reference out to the adapter that owns its shape.

    A solution draft may mix PRODUCT, SERVICE and SOLUTION component
    references in one request (family_need's own contract allows several
    `component_refs`). This is not a DI framework: it is a lookup by
    `SupplyShape`, kept here rather than in the domain because routing to a
    concrete catalogue adapter is an infrastructure concern.
    """

    def __init__(
        self,
        *,
        commerce: CommerceSupplyAdapter,
        service: ServiceSupplyAdapter,
        course: CourseSupplyAdapter | None = None,
    ) -> None:
        self._by_shape: dict[SupplyShape, SupplyReferencePort] = {
            SupplyShape.PRODUCT: commerce,
            SupplyShape.SERVICE: service,
        }
        if course is not None:
            self._by_shape[SupplyShape.SOLUTION] = course

    def _adapter_for(self, shape: SupplyShape) -> SupplyReferencePort | None:
        return self._by_shape.get(shape)

    async def resolve_component(
        self,
        *,
        tenant_id: str,
        region: str,
        locale: str,
        shape: SupplyShape,
        component_id: str,
        version: str,
    ):
        adapter = self._adapter_for(shape)
        if adapter is None:
            return None
        return await adapter.resolve_component(
            tenant_id=tenant_id,
            region=region,
            locale=locale,
            shape=shape,
            component_id=component_id,
            version=version,
        )

    async def check_resource_capacity(
        self, *, tenant_id: str, family_id: str, need_id: str = "", component_refs: tuple
    ):
        by_shape: dict[SupplyShape, list] = {}
        for component_ref in component_refs:
            by_shape.setdefault(component_ref.shape, []).append(component_ref)
        for shape, refs in by_shape.items():
            adapter = self._adapter_for(shape)
            if adapter is None:
                continue
            gap = await adapter.check_resource_capacity(
                tenant_id=tenant_id,
                family_id=family_id,
                need_id=need_id,
                component_refs=tuple(refs),
            )
            if gap is not None:
                return gap
        return None

    async def get_resource_gap(self, *, need_id: str, reason, detail: str):
        # Either adapter answers identically (both delegate to
        # `ResourceGap.now`); using the SERVICE one is not shape-specific.
        return await self._by_shape[SupplyShape.SERVICE].get_resource_gap(
            need_id=need_id, reason=reason, detail=detail
        )


def install_family_need_wiring(
    app: FastAPI,
    *,
    service: FamilyNeedApplicationService,
    actor_resolver,
) -> None:
    """Mount both dependencies outside the route body, same pattern as GrowthOnboarding."""

    async def resolve_actor(
        family_id: str = Path(...),
        authorization: str | None = Header(default=None),
    ) -> family_need_deps.FamilyNeedActor:
        try:
            return await actor_resolver.resolve(authorization, family_id)
        except FamilyNeedAuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    async def resolve_service() -> FamilyNeedApplicationService:
        return service

    app.dependency_overrides[family_need_deps.get_family_need_actor] = resolve_actor
    app.dependency_overrides[family_need_deps.get_family_need_service] = resolve_service


def install_family_need_dev_wiring(
    app: FastAPI,
    *,
    runtime: FakeFamilyNeedRuntime,
    actor_resolver,
) -> None:
    install_family_need_wiring(app, service=runtime.service, actor_resolver=actor_resolver)


def install_family_need_production_wiring(
    app: FastAPI, *, database_url: str, engine: AsyncEngine
) -> None:
    """Install PostgreSQL-backed repository/actor-resolver/supply adapters.

    One request-scoped `AsyncSession` backs the family_need repository and
    both supply adapters for the duration of a single request, mirroring the
    unit-of-work convention `SqlAlchemyServiceRepository`/`SqlAlchemyCommerceRepository`
    already use.

    There is no PostgreSQL-backed `FamilyNeedPolicyPort` implementation yet —
    only `FakeFamilyNeedPolicy`, which synthesises tenant/actor/consent grants
    and must never answer a real authorization decision. Rather than install
    it here and fail open, this installer raises so a production deployment
    discovers the missing policy adapter at startup instead of serving
    requests under a synthetic authorization decision. See
    governance/DOMAIN_REGISTRY.yaml -> family_need.known_gaps.
    """

    del database_url, engine
    raise RuntimeError(
        "family_need_production_policy_adapter_not_implemented: only "
        "FakeFamilyNeedPolicy exists; a real tenant/subject/consent policy "
        "port must be implemented before production wiring can install a "
        "PostgreSQL-backed FamilyNeedApplicationService"
    )


__all__ = [
    "CompositeSupplyAdapter",
    "FakeFamilyNeedRuntime",
    "build_fake_family_need_runtime",
    "install_family_need_dev_wiring",
    "install_family_need_production_wiring",
    "install_family_need_wiring",
]
