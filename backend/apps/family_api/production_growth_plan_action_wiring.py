"""Production current-scope resolver and worker composition for growth plans."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.accepted_action_wiring import (
    FGCNAcceptedActionRuntime,
    GrowthPlanJourneyApplication,
)
from backend.apps.family_api.growth_plan_activation_wiring import DailyActionInitializer
from backend.apps.family_api.trusted_experience_scope import (
    AuthenticatedExperienceScopeResolver,
    AuthenticatedPrincipal,
    SqlAlchemyConsentSnapshotResolver,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.human_gate import NamedActionRequest
from backend.platform.consent.models import ConsentPurpose
from backend.platform.identity.trusted_context import (
    SqlAlchemyTrustedTenantScopeStoreFactory,
    TrustedTenantScopeResolver,
)


@dataclass(frozen=True, slots=True)
class SqlAlchemyGrowthPlanAcceptedActionScopeResolver:
    """Re-authorize the deciding guardian and current consent at worker time."""

    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("growth plan action scope requires async_sessionmaker")

    async def __call__(self, request: NamedActionRequest) -> ContextScope:
        family_id = request.scope.family_id
        if family_id is None or len(request.scope.subject_ids) != 1:
            raise PermissionError("GROWTH_PLAN_ACTION_SCOPE_INVALID")
        account_id = await self._active_guardian_account(
            family_id=family_id,
            actor_id=request.actor_id,
        )

        async def principal() -> AuthenticatedPrincipal:
            return AuthenticatedPrincipal(
                account_id=account_id,
                correlation_id=request.scope.correlation_id,
                causation_id=request.request_id,
            )

        async def exact_subject(trusted) -> tuple[str, ...]:
            if trusted.tenant_id != request.scope.tenant_id:
                raise PermissionError("GROWTH_PLAN_ACTION_TENANT_MISMATCH")
            subject_id = request.scope.subject_ids[0]
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
                raise PermissionError("GROWTH_PLAN_ACTION_SUBJECT_UNAVAILABLE")
            return (subject_id,)

        return await AuthenticatedExperienceScopeResolver(
            principal_resolver=principal,
            trusted_scope_resolver=TrustedTenantScopeResolver(
                SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
            ),
            subject_ids_resolver=exact_subject,
            consent_resolver=SqlAlchemyConsentSnapshotResolver(self.session_factory),
            purpose=ConsentPurpose.GROWTH_TRACKING,
            data_class=DataClass.MINOR_PERSONAL_DATA,
            locale="zh-CN",
        ).resolve(family_id)

    async def _active_guardian_account(self, *, family_id: str, actor_id: str) -> str:
        statement = text(
            """
            SELECT apb.account_id
            FROM account_person_bindings AS apb
            JOIN family_memberships AS fm
              ON fm.person_id = apb.person_id
             AND fm.family_id = :family_id
             AND fm.status = 'ACTIVE'
             AND fm.role IN ('OWNER_GUARDIAN', 'GUARDIAN')
            JOIN accounts AS a
              ON a.account_id = apb.account_id
             AND a.status = 'ACTIVE'
            WHERE apb.person_id = :actor_id
              AND apb.status = 'ACTIVE'
            ORDER BY apb.account_id
            LIMIT 2
            """
        )
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    statement,
                    {"family_id": family_id, "actor_id": actor_id},
                )
            ).all()
        if len(rows) != 1 or not str(rows[0][0] or "").strip():
            raise PermissionError("GROWTH_PLAN_ACTION_GUARDIAN_NOT_CURRENT")
        return str(rows[0][0])


def build_production_growth_plan_action_runtime(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    journey_application: GrowthPlanJourneyApplication,
    daily_action_initializer: DailyActionInitializer,
    claim_owner: str,
    clock: Callable[[], datetime],
) -> FGCNAcceptedActionRuntime:
    """Build the restart-safe shared worker with execution-time reauthorization."""

    return FGCNAcceptedActionRuntime(
        session_factory=session_factory,
        claim_owner=claim_owner,
        growth_plan_scope_resolver=SqlAlchemyGrowthPlanAcceptedActionScopeResolver(
            session_factory
        ),
        journey_application=journey_application,
        growth_plan_daily_action_initializer=daily_action_initializer,
        clock=clock,
    )


__all__ = [
    "SqlAlchemyGrowthPlanAcceptedActionScopeResolver",
    "build_production_growth_plan_action_runtime",
]
