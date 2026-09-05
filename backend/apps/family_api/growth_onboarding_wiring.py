"""Composition roots for the GrowthIntent -> Onboarding HTTP slice.

This module is deliberately separate from the concurrently owned
``family_api/main.py`` and legacy Journey routes.  The API owner can mount the
returned router by calling one of the explicit installers without changing
the command boundary or introducing a route-local fake.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.domains.journey.api.growth_onboarding_routes import (
    GrowthOnboardingActorContext,
    get_growth_onboarding_actor_context,
    get_growth_onboarding_application,
    router,
)
from backend.domains.journey.application.growth_onboarding import (
    GrowthOnboardingApplication,
)
from backend.domains.journey.domain.growth_onboarding import ConfirmedGrowthIntent
from backend.domains.journey.infrastructure.growth_onboarding_fake import (
    FakeConfirmedGrowthIntentReader,
    FakeGrowthOnboardingConsent,
    FakeGrowthOnboardingPolicy,
    FakeGrowthOnboardingRepository,
    FakeGrowthOnboardingTransaction,
)
from backend.domains.journey.infrastructure.growth_onboarding_postgres import (
    build_postgres_growth_onboarding_application,
)
from backend.platform.persistence.session import (
    get_engine,
    is_postgres_url,
    resolve_database_url,
)


class GrowthOnboardingAuthenticationError(Exception):
    """The bearer session is absent, invalid, expired, or revoked."""


class GrowthOnboardingScopeError(Exception):
    """The authenticated account cannot act in the requested family."""


class GrowthOnboardingActorResolver(Protocol):
    async def resolve(
        self, authorization: str | None, family_id: str
    ) -> GrowthOnboardingActorContext: ...


class SqlAlchemyGrowthOnboardingActorResolver:
    """Resolve human actor and tenant from the canonical identity chain."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def resolve(
        self, authorization: str | None, family_id: str
    ) -> GrowthOnboardingActorContext:
        token = _bearer_token(authorization)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self._engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    select distinct tfb.tenant_id,fm.person_id
                    from identity_sessions s
                    join accounts a on a.account_id=s.account_ref
                    join tenant_account_memberships tam
                      on tam.account_id=a.account_id
                     and tam.status='ACTIVE'
                     and tam.valid_from<=CURRENT_TIMESTAMP
                     and (tam.valid_to is null or tam.valid_to>CURRENT_TIMESTAMP)
                    join tenant_family_bindings tfb
                      on tfb.tenant_id=tam.tenant_id
                     and tfb.family_id=cast(:family_id as uuid)
                     and tfb.status='ACTIVE'
                     and tfb.effective_from<=CURRENT_TIMESTAMP
                     and (tfb.effective_to is null or tfb.effective_to>CURRENT_TIMESTAMP)
                    join account_person_bindings apb
                      on apb.account_id=a.account_id and apb.status='ACTIVE'
                    join family_memberships fm
                      on fm.family_id=tfb.family_id
                     and fm.person_id=apb.person_id
                     and fm.status='ACTIVE'
                     and fm.role in ('OWNER_GUARDIAN','GUARDIAN')
                    where s.token_hash=:token_hash
                      and s.revoked_at is null
                      and s.expires_at>CURRENT_TIMESTAMP
                      and a.status='ACTIVE'
                    """
                ),
                {"token_hash": token_hash, "family_id": family_id},
            )
            rows = result.all()
        if len(rows) != 1:
            raise GrowthOnboardingScopeError("trusted_family_context_not_found")
        return GrowthOnboardingActorContext(
            tenant_id=str(rows[0].tenant_id),
            family_id=family_id,
            actor_id=str(rows[0].person_id),
            actor_type="HUMAN",
        )


class InMemoryGrowthOnboardingActorResolver:
    """Explicit dev/test resolver; no default identity or family is invented."""

    def __init__(self, contexts: dict[str, GrowthOnboardingActorContext] | None = None):
        self.contexts = contexts or {}

    def register(self, token: str, context: GrowthOnboardingActorContext) -> None:
        self.contexts[token] = context

    async def resolve(
        self, authorization: str | None, family_id: str
    ) -> GrowthOnboardingActorContext:
        token = _bearer_token(authorization)
        context = self.contexts.get(token)
        if context is None:
            raise GrowthOnboardingAuthenticationError("invalid_or_expired_identity_session")
        return context


@dataclass(frozen=True)
class FakeGrowthOnboardingRuntime:
    application: GrowthOnboardingApplication
    reader: FakeConfirmedGrowthIntentReader
    repository: FakeGrowthOnboardingRepository
    policy: FakeGrowthOnboardingPolicy
    consent: FakeGrowthOnboardingConsent
    transaction: FakeGrowthOnboardingTransaction


def build_fake_growth_onboarding_runtime(
    intents: Iterable[ConfirmedGrowthIntent] = (),
) -> FakeGrowthOnboardingRuntime:
    reader = FakeConfirmedGrowthIntentReader(list(intents))
    repository = FakeGrowthOnboardingRepository()
    policy = FakeGrowthOnboardingPolicy()
    consent = FakeGrowthOnboardingConsent()
    transaction = FakeGrowthOnboardingTransaction(
        intent_reader=reader,
        repository=repository,
        policy=policy,
        consent=consent,
    )
    return FakeGrowthOnboardingRuntime(
        application=GrowthOnboardingApplication(transaction),
        reader=reader,
        repository=repository,
        policy=policy,
        consent=consent,
        transaction=transaction,
    )


def install_growth_onboarding_wiring(
    app: FastAPI,
    *,
    application: GrowthOnboardingApplication,
    actor_resolver: GrowthOnboardingActorResolver,
) -> None:
    """Mount the route and resolve both dependencies outside the route body."""

    app.include_router(router)

    async def resolve_actor(
        family_id: str = Path(...),
        authorization: str | None = Header(default=None),
    ) -> GrowthOnboardingActorContext:
        try:
            return await actor_resolver.resolve(authorization, family_id)
        except GrowthOnboardingAuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        except GrowthOnboardingScopeError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    async def resolve_application() -> GrowthOnboardingApplication:
        return application

    app.dependency_overrides[get_growth_onboarding_actor_context] = resolve_actor
    app.dependency_overrides[get_growth_onboarding_application] = resolve_application


def install_growth_onboarding_production_wiring(
    app: FastAPI, *, database_url: str | None = None
) -> None:
    """Install the PostgreSQL application and canonical identity resolver."""

    resolved_url = database_url or resolve_database_url()
    if not is_postgres_url(resolved_url):
        raise RuntimeError("growth_onboarding_production_requires_postgresql")
    engine = get_engine(resolved_url)
    install_growth_onboarding_wiring(
        app,
        application=build_postgres_growth_onboarding_application(resolved_url),
        actor_resolver=SqlAlchemyGrowthOnboardingActorResolver(engine),
    )


def install_growth_onboarding_dev_wiring(
    app: FastAPI,
    *,
    runtime: FakeGrowthOnboardingRuntime,
    actor_resolver: InMemoryGrowthOnboardingActorResolver,
) -> None:
    """Install an explicit fake runtime with the production-shaped boundary."""

    install_growth_onboarding_wiring(
        app,
        application=runtime.application,
        actor_resolver=actor_resolver,
    )


def _bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise GrowthOnboardingAuthenticationError("authorization_required")
    token = authorization[7:].strip()
    if not token:
        raise GrowthOnboardingAuthenticationError("authorization_required")
    return token


__all__ = [
    "FakeGrowthOnboardingRuntime",
    "GrowthOnboardingAuthenticationError",
    "GrowthOnboardingActorResolver",
    "GrowthOnboardingScopeError",
    "InMemoryGrowthOnboardingActorResolver",
    "SqlAlchemyGrowthOnboardingActorResolver",
    "build_fake_growth_onboarding_runtime",
    "install_growth_onboarding_dev_wiring",
    "install_growth_onboarding_production_wiring",
    "install_growth_onboarding_wiring",
]
