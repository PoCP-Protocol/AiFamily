"""Production identity, consent and router wiring for AI growth plans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.growth_plan_ai_api import (
    CompositionResolver,
    GrowthPlanAiHttpDependencies,
    GrowthPlanHttpIdentity,
    build_growth_plan_ai_router,
)
from backend.apps.family_api.trusted_experience_scope import (
    AuthenticatedExperienceScopeResolver,
    AuthenticatedPrincipal,
    SqlAlchemyBearerPrincipalResolver,
    SqlAlchemyConsentSnapshotResolver,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.platform.consent.models import ConsentPurpose
from backend.platform.identity.trusted_context import (
    SqlAlchemyTrustedTenantScopeStoreFactory,
    TrustedTenantScopeResolver,
)


@dataclass(frozen=True, slots=True)
class SqlAlchemyGrowthPlanIdentityResolver:
    """Resolve bearer session, tenant/family binding and one active guardian."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def __call__(
        self,
        family_id: str,
        authorization: str | None,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> GrowthPlanHttpIdentity:
        try:
            principal = await SqlAlchemyBearerPrincipalResolver(
                self.engine,
                authorization,
                family_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )()
            trusted = await TrustedTenantScopeResolver(
                SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
            ).resolve(account_id=principal.account_id, family_id=family_id)
        except PermissionError as error:
            raise PermissionError("GROWTH_PLAN_AUTHENTICATION_FAILED") from error
        actor_id = await self._guardian_actor(principal, family_id)
        return GrowthPlanHttpIdentity(trusted.tenant_id, trusted.family_id, actor_id)

    async def _guardian_actor(
        self,
        principal: AuthenticatedPrincipal,
        family_id: str,
    ) -> str:
        statement = text(
            """
            SELECT fm.person_id
            FROM account_person_bindings AS apb
            JOIN family_memberships AS fm
              ON fm.family_id = :family_id
             AND fm.person_id = apb.person_id
             AND fm.status = 'ACTIVE'
             AND fm.role IN ('OWNER_GUARDIAN', 'GUARDIAN')
            WHERE apb.account_id = :account_id
              AND apb.status = 'ACTIVE'
            ORDER BY fm.membership_id
            LIMIT 2
            """
        )
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    statement,
                    {"family_id": family_id, "account_id": principal.account_id},
                )
            ).all()
        if len(rows) != 1 or not str(rows[0][0] or "").strip():
            raise PermissionError("GROWTH_PLAN_GUARDIAN_REQUIRED")
        return str(rows[0][0])


@dataclass(frozen=True, slots=True)
class SqlAlchemyGrowthPlanContextScopeResolver:
    """Resolve current Growth Tracking consent for one server-validated subject."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def __call__(
        self,
        identity: GrowthPlanHttpIdentity,
        subject_id: str,
        authorization: str | None,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> ContextScope:
        principal_resolver = SqlAlchemyBearerPrincipalResolver(
            self.engine,
            authorization,
            identity.family_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

        async def exact_subject(trusted) -> tuple[str, ...]:
            if trusted.tenant_id != identity.tenant_id:
                raise PermissionError("GROWTH_PLAN_TENANT_SCOPE_MISMATCH")
            async with self.session_factory() as session:
                rows = (
                    await session.execute(
                        text(
                            "SELECT person_id FROM persons "
                            "WHERE family_id = :family_id AND person_id = :subject_id LIMIT 2"
                        ),
                        {"family_id": trusted.family_id, "subject_id": subject_id},
                    )
                ).all()
            if len(rows) != 1:
                raise PermissionError("GROWTH_PLAN_SUBJECT_SCOPE_UNAVAILABLE")
            return (subject_id,)

        return await AuthenticatedExperienceScopeResolver(
            principal_resolver=principal_resolver,
            trusted_scope_resolver=TrustedTenantScopeResolver(
                SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
            ),
            subject_ids_resolver=exact_subject,
            consent_resolver=SqlAlchemyConsentSnapshotResolver(self.session_factory),
            purpose=ConsentPurpose.GROWTH_TRACKING,
            data_class=DataClass.MINOR_PERSONAL_DATA,
            locale="zh-CN",
        ).resolve(identity.family_id)


def install_production_growth_plan_http_wiring(
    app: FastAPI,
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    composition_resolver: CompositionResolver,
    clock: Callable[[], datetime],
) -> None:
    """Mount the same authenticated route graph in test, staging and production."""

    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI instance")
    if not isinstance(engine, AsyncEngine):
        raise TypeError("engine must be an AsyncEngine")
    if not callable(composition_resolver) or not callable(clock):
        raise TypeError("growth plan composition resolver and clock are required")
    app.include_router(
        build_growth_plan_ai_router(
            GrowthPlanAiHttpDependencies(
                session_factory=session_factory,
                identity_resolver=SqlAlchemyGrowthPlanIdentityResolver(
                    engine,
                    session_factory,
                ),
                scope_resolver=SqlAlchemyGrowthPlanContextScopeResolver(
                    engine,
                    session_factory,
                ),
                composition_resolver=composition_resolver,
                clock=clock,
            )
        )
    )


__all__ = [
    "SqlAlchemyGrowthPlanContextScopeResolver",
    "SqlAlchemyGrowthPlanIdentityResolver",
    "install_production_growth_plan_http_wiring",
]
