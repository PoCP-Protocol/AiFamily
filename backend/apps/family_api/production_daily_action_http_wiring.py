"""Production-equivalent HTTP wiring for the UI-09 Action capability."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.growth_plan_ai_api import GrowthPlanHttpIdentity
from backend.apps.family_api.trusted_experience_scope import (
    AuthenticatedExperienceScopeResolver,
    AuthenticatedPrincipal,
    SqlAlchemyConsentSnapshotResolver,
)
from backend.domains.action.api.routes import (
    DailyActionHttpDependencies,
    build_daily_action_router,
)
from backend.domains.action.infrastructure.postgres import (
    SqlAlchemyDailyActionApplication,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.platform.consent.models import ConsentPurpose
from backend.platform.identity.trusted_context import (
    SqlAlchemyTrustedTenantScopeStoreFactory,
    TrustedTenantScopeResolver,
)


@dataclass(frozen=True, slots=True)
class SqlAlchemyActionPrincipalResolver:
    """Resolve a bearer session while normalising legacy UUID/text account columns."""

    engine: AsyncEngine
    authorization: str | None
    family_id: str
    correlation_id: str
    causation_id: str

    async def __call__(self) -> AuthenticatedPrincipal:
        token = _bearer_token(self.authorization)
        async with self.engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT s.session_id,
                               COALESCE(CAST(a.account_id AS text), s.account_id) AS account_id
                        FROM identity_sessions AS s
                        LEFT JOIN accounts AS a ON a.account_id = s.account_ref
                        WHERE s.token_hash = :token_hash
                          AND s.revoked_at IS NULL
                          AND s.expires_at > CURRENT_TIMESTAMP
                          AND (a.status = 'ACTIVE' OR a.status IS NULL)
                        LIMIT 2
                        """
                    ),
                    {
                        "token_hash": sha256(token.encode("utf-8")).hexdigest(),
                    },
                )
            ).mappings().all()
        if len(rows) != 1 or not str(rows[0]["account_id"] or "").strip():
            raise PermissionError("DAILY_ACTION_PRINCIPAL_UNAVAILABLE")
        return AuthenticatedPrincipal(
            account_id=str(rows[0]["account_id"]),
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
        )


@dataclass(frozen=True, slots=True)
class SqlAlchemyDailyActionIdentityResolver:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def __call__(
        self,
        family_id: str,
        authorization: str | None,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> GrowthPlanHttpIdentity:
        request_correlation = correlation_id or "daily-action-request"
        request_causation = causation_id or request_correlation
        principal = await SqlAlchemyActionPrincipalResolver(
            self.engine,
            authorization,
            family_id,
            request_correlation,
            request_causation,
        )()
        trusted = await TrustedTenantScopeResolver(
            SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
        ).resolve(account_id=principal.account_id, family_id=family_id)
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    text(
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
                        LIMIT 2
                        """
                    ),
                    {"family_id": family_id, "account_id": principal.account_id},
                )
            ).all()
        if len(rows) != 1:
            raise PermissionError("DAILY_ACTION_GUARDIAN_REQUIRED")
        return GrowthPlanHttpIdentity(
            trusted.tenant_id,
            trusted.family_id,
            str(rows[0][0]),
        )


@dataclass(frozen=True, slots=True)
class SqlAlchemyDailyActionScopeResolver:
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
        request_correlation = correlation_id or "daily-action-request"
        request_causation = causation_id or request_correlation
        principal = SqlAlchemyActionPrincipalResolver(
            self.engine,
            authorization,
            identity.family_id,
            request_correlation,
            request_causation,
        )

        async def exact_subject(trusted) -> tuple[str, ...]:
            if trusted.tenant_id != identity.tenant_id:
                raise PermissionError("DAILY_ACTION_TENANT_SCOPE_MISMATCH")
            async with self.session_factory() as session:
                rows = (
                    await session.execute(
                        text(
                            "SELECT person_id FROM persons "
                            "WHERE family_id=:family_id AND person_id=:subject_id LIMIT 2"
                        ),
                        {"family_id": identity.family_id, "subject_id": subject_id},
                    )
                ).all()
            if len(rows) != 1:
                raise PermissionError("DAILY_ACTION_SUBJECT_SCOPE_UNAVAILABLE")
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
        ).resolve(identity.family_id)


@dataclass(frozen=True, slots=True)
class SqlAlchemyCurrentActionSubjectResolver:
    session_factory: async_sessionmaker[AsyncSession]

    async def __call__(self, identity: GrowthPlanHttpIdentity) -> str:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT gp.subject_person_id
                        FROM family_journey_plans AS jp
                        JOIN growth_priorities AS gp
                          ON gp.priority_id = jp.priority_id
                         AND gp.family_id = jp.family_id
                         AND gp.status = 'ACTIVE'
                        WHERE jp.family_id = :family_id
                          AND jp.status = 'ACTIVE'
                          AND gp.subject_person_id IS NOT NULL
                        ORDER BY jp.created_at DESC
                        LIMIT 2
                        """
                    ),
                    {"family_id": identity.family_id},
                )
            ).all()
        if len(rows) != 1 or not str(rows[0][0] or "").strip():
            raise PermissionError("DAILY_ACTION_ACTIVE_SUBJECT_UNAVAILABLE")
        return str(rows[0][0])


def install_production_daily_action_http_wiring(
    app: FastAPI,
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Mount one route graph for connected development, test and production."""
    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI instance")
    if not isinstance(engine, AsyncEngine):
        raise TypeError("engine must be an AsyncEngine")
    app.include_router(
        build_daily_action_router(
            DailyActionHttpDependencies(
                application=SqlAlchemyDailyActionApplication(engine),
                identity_resolver=SqlAlchemyDailyActionIdentityResolver(
                    engine,
                    session_factory,
                ),
                subject_resolver=SqlAlchemyCurrentActionSubjectResolver(session_factory),
                scope_resolver=SqlAlchemyDailyActionScopeResolver(
                    engine,
                    session_factory,
                ),
            )
        )
    )


__all__ = [
    "SqlAlchemyActionPrincipalResolver",
    "SqlAlchemyCurrentActionSubjectResolver",
    "SqlAlchemyDailyActionIdentityResolver",
    "SqlAlchemyDailyActionScopeResolver",
    "install_production_daily_action_http_wiring",
]


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise PermissionError("DAILY_ACTION_BEARER_REQUIRED")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise PermissionError("DAILY_ACTION_BEARER_INVALID")
    return token.strip()
