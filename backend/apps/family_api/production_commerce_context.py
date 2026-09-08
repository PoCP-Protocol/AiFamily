"""Production read context for the Commerce catalogue.

This module deliberately stops at a trusted, family-scoped read context.  It
does not create orders, grant entitlements, or expose payment side effects.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.apps.family_api.trusted_experience_scope import (
    AuthenticatedPrincipal,
    SqlAlchemyBearerPrincipalResolver,
)
from backend.platform.identity.trusted_context import (
    SqlAlchemyTrustedTenantScopeStoreFactory,
    TrustedTenantScopeResolver,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@dataclass(frozen=True, slots=True)
class ProductionCommerceReadContext:
    account_id: str
    tenant_id: str
    family_id: str
    correlation_id: str
    causation_id: str


@dataclass(frozen=True, slots=True)
class ProductionCommerceReadContextResolver:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.engine, AsyncEngine):
            raise TypeError("engine must be an AsyncEngine")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def resolve(
        self,
        *,
        family_id: str,
        authorization: str | None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> ProductionCommerceReadContext:
        principal: AuthenticatedPrincipal = await SqlAlchemyBearerPrincipalResolver(
            self.engine,
            authorization,
            family_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )()
        trusted = await TrustedTenantScopeResolver(
            SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
        ).resolve(account_id=principal.account_id, family_id=family_id)
        return ProductionCommerceReadContext(
            account_id=principal.account_id,
            tenant_id=trusted.tenant_id,
            family_id=trusted.family_id,
            correlation_id=principal.correlation_id,
            causation_id=principal.causation_id,
        )


__all__ = ["ProductionCommerceReadContext", "ProductionCommerceReadContextResolver"]
