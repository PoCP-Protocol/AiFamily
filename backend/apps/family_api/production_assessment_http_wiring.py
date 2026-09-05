"""Request-scoped FastAPI wiring for the production assessment vertical slice."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path as FilePath

from fastapi import FastAPI, Header, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.assessment_ai_wiring import AssessmentAiAssets
from backend.apps.family_api.production_agent_wiring import (
    AttemptSinkFactory,
    ProductionAgentRuntimeResolver,
    RegistryFactory,
    SafetySinkFactory,
    TelemetrySinkFactory,
)
from backend.apps.family_api.production_assessment_ai_wiring import (
    ProductionAssessmentAiComposition,
)
from backend.apps.family_api.trusted_experience_scope import (
    AuthenticatedExperienceScopeResolver,
    AuthenticatedPrincipal,
    SqlAlchemyBearerPrincipalResolver,
    SqlAlchemyConsentSnapshotResolver,
)
from backend.domains.assessment.api import dependencies as assessment_dependencies
from backend.domains.assessment.api.dependencies import FamilyContext
from backend.domains.assessment.application.commands import AssessmentCommandHandler
from backend.domains.assessment.application.growth_hypothesis_commands import (
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.ports import AssessmentRepositoryPort
from backend.domains.assessment.application.queries import AssessmentQueryHandler
from backend.domains.assessment.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAssessmentRepository,
)
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort
from backend.intelligence.context_engine.contracts import ContextScope, ContextScopeError, DataClass
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.platform.consent.models import ConsentPurpose
from backend.platform.identity.trusted_context import (
    SqlAlchemyTrustedTenantScopeStoreFactory,
    TrustedTenantScopeResolver,
)

IdentityResolver = Callable[
    [str, str | None, str | None, str | None],
    FamilyContext | Awaitable[FamilyContext],
]
CompositionResolver = Callable[
    [FamilyContext, str | None, str | None, str | None],
    ProductionAssessmentAiComposition | Awaitable[ProductionAssessmentAiComposition],
]
RepositoryFactory = Callable[[AsyncConnection], AssessmentRepositoryPort]


@dataclass(frozen=True, slots=True)
class SqlAlchemyAssessmentIdentityResolver:
    """Resolve bearer → trusted tenant/family → active guardian person."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.engine, AsyncEngine):
            raise TypeError("engine must be an AsyncEngine")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def __call__(
        self,
        family_id: str,
        authorization: str | None,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> FamilyContext:
        try:
            principal = await SqlAlchemyBearerPrincipalResolver(
                self.engine,
                authorization,
                family_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )()
        except PermissionError as exc:
            raise HTTPException(
                status_code=401,
                detail="authenticated assessment identity required",
            ) from exc
        if not isinstance(principal, AuthenticatedPrincipal):
            raise HTTPException(
                status_code=401,
                detail="authenticated assessment identity required",
            )
        try:
            trusted = await TrustedTenantScopeResolver(
                SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
            ).resolve(account_id=principal.account_id, family_id=family_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="assessment family access denied") from exc

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
            raise HTTPException(status_code=403, detail="assessment guardian access denied")
        return FamilyContext(
            tenant_id=trusted.tenant_id,
            family_id=trusted.family_id,
            person_id=str(rows[0][0]),
        )


@dataclass(frozen=True, slots=True)
class SqlAlchemyAssessmentContextScopeResolver:
    """Resolve current ASSESSMENT consent for exactly one evidence subject."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    authorization: str | None
    correlation_id: str | None = None
    causation_id: str | None = None
    locale: str = "zh-CN"

    def __post_init__(self) -> None:
        if not isinstance(self.engine, AsyncEngine):
            raise TypeError("engine must be an AsyncEngine")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def __call__(self, family_id: str, subject_id: str) -> ContextScope:
        principal_resolver = SqlAlchemyBearerPrincipalResolver(
            self.engine,
            self.authorization,
            family_id,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
        )

        async def subject_ids_resolver(trusted) -> tuple[str, ...]:
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
                raise PermissionError("ASSESSMENT_SUBJECT_SCOPE_UNAVAILABLE")
            return (subject_id,)

        resolver = AuthenticatedExperienceScopeResolver(
            principal_resolver=principal_resolver,
            trusted_scope_resolver=TrustedTenantScopeResolver(
                SqlAlchemyTrustedTenantScopeStoreFactory(self.session_factory)
            ),
            subject_ids_resolver=subject_ids_resolver,
            consent_resolver=SqlAlchemyConsentSnapshotResolver(self.session_factory),
            purpose=ConsentPurpose.ASSESSMENT,
            data_class=DataClass.MINOR_PERSONAL_DATA,
            locale=self.locale,
        )
        return await resolver.resolve(family_id)


@dataclass(frozen=True, slots=True)
class ProductionAssessmentAiCompositionResolver:
    """Deployment-owned factory for one authenticated assessment request."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    gateway: ModelGateway
    provider_id: str
    registry_path: str | FilePath
    attempt_sink_factory: AttemptSinkFactory
    safety_sink_factory: SafetySinkFactory
    telemetry_sink_factory: TelemetrySinkFactory
    context_broker: AsyncContextBrokerPort
    assets: AssessmentAiAssets
    environment: str
    clock: Callable[[], datetime]
    prompt_registry: object | None = None
    schema_registry: object | None = None
    prompt_registry_factory: RegistryFactory | None = None
    schema_registry_factory: RegistryFactory | None = None

    async def __call__(
        self,
        identity: FamilyContext,
        authorization: str | None,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> ProductionAssessmentAiComposition:
        subject_scope_resolver = SqlAlchemyAssessmentContextScopeResolver(
            engine=self.engine,
            session_factory=self.session_factory,
            authorization=authorization,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

        async def require_subject_scope(family_id: str) -> ContextScope:
            raise ContextScopeError("ASSESSMENT_EVIDENCE_SUBJECT_REQUIRED")

        runtime_resolver = ProductionAgentRuntimeResolver(
            scope_resolver=require_subject_scope,
            subject_scope_resolver=subject_scope_resolver,
            session_factory=self.session_factory,
            gateway=self.gateway,
            provider_id=self.provider_id,
            registry_path=self.registry_path,
            attempt_sink_factory=self.attempt_sink_factory,
            safety_sink_factory=self.safety_sink_factory,
            telemetry_sink_factory=self.telemetry_sink_factory,
            context_broker=self.context_broker,
            environment=self.environment,
            prompt_registry=self.prompt_registry,
            schema_registry=self.schema_registry,
            prompt_registry_factory=self.prompt_registry_factory,
            schema_registry_factory=self.schema_registry_factory,
            clock=self.clock,
        )
        return ProductionAssessmentAiComposition(
            environment=self.environment,
            session_factory=self.session_factory,
            runtime_resolver=runtime_resolver,
            context_broker=self.context_broker,
            actor_id_resolver=lambda: identity.person_id,
            assets=self.assets,
            clock=self.clock,
        )


def install_production_assessment_http_wiring(
    app: FastAPI,
    *,
    engine: AsyncEngine,
    identity_resolver: IdentityResolver,
    composition_resolver: CompositionResolver,
    repository_factory: RepositoryFactory = SqlAlchemyAssessmentRepository,
) -> None:
    """Install the assessment dependencies as one production-parity unit.

    Test may inject a fake repository and admitted fake provider, but it still
    runs through the same request identity, transaction, Principal, Context,
    Agent Runtime, Model Gateway and Named Action dependency graph.
    """

    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI instance")
    if not isinstance(engine, AsyncEngine):
        raise TypeError("engine must be an AsyncEngine")
    if not callable(identity_resolver) or not callable(composition_resolver):
        raise TypeError("assessment identity and composition resolvers must be callable")
    if not callable(repository_factory):
        raise TypeError("assessment repository_factory must be callable")

    async def family_context(
        family_id: str = Path(...),
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> FamilyContext:
        return await _resolve_identity(
            identity_resolver,
            family_id,
            authorization,
            x_correlation_id,
            x_causation_id,
        )

    async def command_handler() -> AsyncIterator[AssessmentCommandHandler]:
        async with engine.begin() as connection:
            yield AssessmentCommandHandler(repository_factory(connection))

    async def query_handler(
        family_id: str = Path(...),
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> AsyncIterator[AssessmentQueryHandler]:
        identity = await _resolve_identity(
            identity_resolver,
            family_id,
            authorization,
            x_correlation_id,
            x_causation_id,
        )
        composition = await _resolve_composition(
            composition_resolver,
            identity,
            authorization,
            x_correlation_id,
            x_causation_id,
        )
        async with engine.begin() as connection:
            yield composition.build_query_handler(repository_factory(connection))

    async def growth_hypothesis_handler(
        family_id: str = Path(...),
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> AsyncIterator[GrowthHypothesisCommandHandler]:
        identity = await _resolve_identity(
            identity_resolver,
            family_id,
            authorization,
            x_correlation_id,
            x_causation_id,
        )
        composition = await _resolve_composition(
            composition_resolver,
            identity,
            authorization,
            x_correlation_id,
            x_causation_id,
        )
        async with engine.begin() as connection:
            yield composition.build_growth_hypothesis_handler(repository_factory(connection))

    app.dependency_overrides[assessment_dependencies.get_family_context] = family_context
    app.dependency_overrides[assessment_dependencies.get_command_handler] = command_handler
    app.dependency_overrides[assessment_dependencies.get_query_handler] = query_handler
    app.dependency_overrides[assessment_dependencies.get_growth_hypothesis_handler] = (
        growth_hypothesis_handler
    )


async def _resolve_identity(
    resolver: IdentityResolver,
    family_id: str,
    authorization: str | None,
    correlation_id: str | None,
    causation_id: str | None,
) -> FamilyContext:
    resolved = resolver(family_id, authorization, correlation_id, causation_id)
    identity = await resolved if inspect.isawaitable(resolved) else resolved
    if not isinstance(identity, FamilyContext):
        raise TypeError("identity_resolver must return FamilyContext")
    if identity.family_id != family_id:
        raise PermissionError("ASSESSMENT_IDENTITY_FAMILY_MISMATCH")
    return identity


async def _resolve_composition(
    resolver: CompositionResolver,
    identity: FamilyContext,
    authorization: str | None,
    correlation_id: str | None,
    causation_id: str | None,
) -> ProductionAssessmentAiComposition:
    resolved = resolver(identity, authorization, correlation_id, causation_id)
    composition = await resolved if inspect.isawaitable(resolved) else resolved
    if not isinstance(composition, ProductionAssessmentAiComposition):
        raise TypeError("composition_resolver must return ProductionAssessmentAiComposition")
    return composition


__all__ = [
    "ProductionAssessmentAiCompositionResolver",
    "SqlAlchemyAssessmentContextScopeResolver",
    "SqlAlchemyAssessmentIdentityResolver",
    "install_production_assessment_http_wiring",
]
