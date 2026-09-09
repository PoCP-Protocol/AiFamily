"""Single composition-root entry point for the governed family AI surface.

The assessment and growth-plan seams are intentionally implemented in separate
modules because they own different domain contracts.  Deployment must still
install them as one platform, otherwise a process can expose UI-03 without
UI-04 (or the reverse) and silently run with different Context/identity
authorities.  This module is the one application-level installer.

This is wiring only: it never selects a provider, creates credentials, or
installs a synthetic runtime.  A deployment must supply already-admitted
composition resolvers and the same database engine/session factory.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.assessment_ai_wiring import AssessmentAiAssets
from backend.apps.family_api.growth_plan_ai_wiring import GrowthPlanAiAssets
from backend.apps.family_api.production_agent_wiring import (
    AttemptSinkFactory,
    ProductionAgentRuntimeResolver,
    RegistryFactory,
    SafetySinkFactory,
    TelemetrySinkFactory,
)
from backend.apps.family_api.production_ai_growth_surface_wiring import (
    install_production_ai_growth_surface,
)
from backend.apps.family_api.production_assessment_http_wiring import (
    CompositionResolver as AssessmentCompositionResolver,
)
from backend.apps.family_api.production_assessment_http_wiring import (
    IdentityResolver as AssessmentIdentityResolver,
)
from backend.apps.family_api.production_assessment_http_wiring import (
    ProductionAssessmentAiCompositionResolver,
    SqlAlchemyAssessmentIdentityResolver,
    install_production_assessment_http_wiring,
)
from backend.apps.family_api.production_growth_plan_ai_wiring import (
    ProductionGrowthPlanAiComposition,
)
from backend.apps.family_api.production_growth_plan_http_wiring import (
    CompositionResolver as GrowthPlanCompositionResolver,
)
from backend.apps.family_api.production_vertical_family_growth_wiring import (
    ProductionVerticalFamilyGrowthComposition,
)
from backend.domains.assessment.application.ports import AssessmentRepositoryPort
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort
from backend.intelligence.model_gateway.gateway import ModelGateway


def build_production_ai_platform_wiring(
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    provider_id: str,
    registry_path: str,
    context_broker: AsyncContextBrokerPort,
    assessment_assets: AssessmentAiAssets,
    growth_plan_assets: GrowthPlanAiAssets,
    attempt_sink_factory: AttemptSinkFactory,
    safety_sink_factory: SafetySinkFactory,
    telemetry_sink_factory: TelemetrySinkFactory,
    environment: str,
    clock: Callable[[], datetime],
    prompt_registry: object | None = None,
    schema_registry: object | None = None,
    prompt_registry_factory: RegistryFactory | None = None,
    schema_registry_factory: RegistryFactory | None = None,
    assessment_repository_factory: Callable[[object], AssessmentRepositoryPort] | None = None,
    vertical_family_growth_composition: ProductionVerticalFamilyGrowthComposition | None = None,
) -> ProductionAiPlatformWiring:
    """Build the one deployment-owned AI composition for both family flows.

    The function accepts only already-admitted runtime dependencies.  It does
    not read credentials, select a provider, or install a FakeProvider.  A
    deployment with no compliant provider must fail before exposing AI routes.
    """

    if not isinstance(gateway, ModelGateway):
        raise TypeError("production AI platform requires a ModelGateway")
    if provider_id not in gateway.available_provider_ids():
        raise ValueError("provider_id must be available in the ModelGateway")
    if gateway.safety_runtime is None:
        raise ValueError("production AI platform requires Gateway SafetyRuntime")
    if not isinstance(context_broker, AsyncContextBrokerPort):
        raise TypeError("production AI platform requires an AsyncContextBrokerPort")
    if context_broker.durability_mode != "DURABLE":
        raise ValueError("production AI platform requires a durable Context Broker")
    if environment not in {"test", "staging", "production"}:
        raise ValueError(
            "production AI platform environment must be test, staging or production"
        )
    if prompt_registry_factory is None and not callable(
        getattr(prompt_registry, "resolve", None)
    ):
        raise ValueError("production AI platform requires a Prompt Registry")
    if schema_registry_factory is None and not callable(
        getattr(schema_registry, "resolve", None)
    ):
        raise ValueError("production AI platform requires a Schema Registry")
    if not all(
        callable(value)
        for value in (attempt_sink_factory, safety_sink_factory, telemetry_sink_factory, clock)
    ):
        raise TypeError("production AI platform sinks and clock must be callable")

    assessment_identity = SqlAlchemyAssessmentIdentityResolver(engine, session_factory)
    assessment_composition = ProductionAssessmentAiCompositionResolver(
        engine=engine,
        session_factory=session_factory,
        gateway=gateway,
        provider_id=provider_id,
        registry_path=registry_path,
        attempt_sink_factory=attempt_sink_factory,
        safety_sink_factory=safety_sink_factory,
        telemetry_sink_factory=telemetry_sink_factory,
        context_broker=context_broker,
        assets=assessment_assets,
        environment=environment,
        clock=clock,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        prompt_registry_factory=prompt_registry_factory,
        schema_registry_factory=schema_registry_factory,
    )

    async def growth_plan_composition(identity, scope):
        runtime_resolver = ProductionAgentRuntimeResolver(
            scope_resolver=lambda _family_id: scope,
            session_factory=session_factory,
            gateway=gateway,
            provider_id=provider_id,
            registry_path=registry_path,
            attempt_sink_factory=attempt_sink_factory,
            safety_sink_factory=safety_sink_factory,
            telemetry_sink_factory=telemetry_sink_factory,
            context_broker=context_broker,
            environment=environment,
            prompt_registry=prompt_registry,
            schema_registry=schema_registry,
            prompt_registry_factory=prompt_registry_factory,
            schema_registry_factory=schema_registry_factory,
            clock=clock,
        )
        return ProductionGrowthPlanAiComposition(
            environment=environment,
            session_factory=session_factory,
            runtime_resolver=runtime_resolver,
            context_broker=context_broker,
            actor_id_resolver=lambda: identity.actor_id,
            assets=growth_plan_assets,
            clock=clock,
        )

    return ProductionAiPlatformWiring(
        engine=engine,
        session_factory=session_factory,
        assessment_identity_resolver=assessment_identity,
        assessment_composition_resolver=assessment_composition,
        growth_plan_composition_resolver=growth_plan_composition,
        clock=clock,
        assessment_repository_factory=assessment_repository_factory,
        vertical_family_growth_composition=vertical_family_growth_composition,
    )


@dataclass(frozen=True, slots=True)
class ProductionAiPlatformWiring:
    """Validated inputs required to mount the complete family AI platform."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    assessment_identity_resolver: AssessmentIdentityResolver
    assessment_composition_resolver: AssessmentCompositionResolver
    growth_plan_composition_resolver: GrowthPlanCompositionResolver
    clock: Callable[[], datetime]
    assessment_repository_factory: Callable[[object], AssessmentRepositoryPort] | None = None
    vertical_family_growth_composition: ProductionVerticalFamilyGrowthComposition | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.engine, AsyncEngine):
            raise TypeError("production AI platform engine is required")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("production AI platform session_factory is required")
        if not all(
            callable(value)
            for value in (
                self.assessment_identity_resolver,
                self.assessment_composition_resolver,
                self.growth_plan_composition_resolver,
                self.clock,
            )
        ):
            raise TypeError("production AI platform resolvers and clock must be callable")
        if self.assessment_repository_factory is not None and not callable(
            self.assessment_repository_factory
        ):
            raise TypeError("assessment_repository_factory must be callable")
        if self.vertical_family_growth_composition is not None and not isinstance(
            self.vertical_family_growth_composition,
            ProductionVerticalFamilyGrowthComposition,
        ):
            raise TypeError(
                "vertical_family_growth_composition must be "
                "ProductionVerticalFamilyGrowthComposition"
            )

    def install(self, app: FastAPI) -> None:
        """Mount assessment, plan review, daily action and feedback routes once."""

        if not isinstance(app, FastAPI):
            raise TypeError("app must be a FastAPI instance")
        marker_name = "_aifamily_production_ai_platform_wiring"
        installed = getattr(app.state, marker_name, None)
        if installed is not None:
            if installed is self:
                return
            raise RuntimeError("production AI platform wiring already configured")
        install_production_assessment_http_wiring(
            app,
            engine=self.engine,
            identity_resolver=self.assessment_identity_resolver,
            composition_resolver=self.assessment_composition_resolver,
            **(
                {"repository_factory": self.assessment_repository_factory}
                if self.assessment_repository_factory is not None
                else {}
            ),
        )
        install_production_ai_growth_surface(
            app,
            engine=self.engine,
            session_factory=self.session_factory,
            growth_plan_composition_resolver=self.growth_plan_composition_resolver,
            clock=self.clock,
        )
        if self.vertical_family_growth_composition is not None:
            self.vertical_family_growth_composition.install(app)
        setattr(app.state, marker_name, self)


__all__ = ["ProductionAiPlatformWiring", "build_production_ai_platform_wiring"]
