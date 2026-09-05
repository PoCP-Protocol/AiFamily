"""Production composition seam for the UI-03 AI vertical slice.

The HTTP host creates one instance per authenticated request and supplies the
request actor resolver plus its request-scoped assessment repository.  Test and
production may use different admitted providers, but they use this same
composition and therefore keep functional parity.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.assessment_ai_wiring import (
    ActorIdResolver,
    AssessmentAgentResolver,
    AssessmentAiAssets,
    AssessmentAiInterpretationAdapter,
    SqlAlchemyAssessmentAuthorizationResolver,
    SqlAlchemyAssessmentRunReplayResolver,
)
from backend.domains.assessment.application.growth_hypothesis_commands import (
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.ports import AssessmentRepositoryPort
from backend.domains.assessment.application.queries import AssessmentQueryHandler
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort

PRODUCTION_LIKE_ENVIRONMENTS = frozenset({"test", "staging", "production"})


@dataclass(frozen=True, slots=True)
class ProductionAssessmentAiComposition:
    """Bind Context, authorization, replay and Agent Runtime exactly once."""

    environment: str
    session_factory: async_sessionmaker[AsyncSession]
    runtime_resolver: AssessmentAgentResolver
    context_broker: AsyncContextBrokerPort
    actor_id_resolver: ActorIdResolver
    assets: AssessmentAiAssets
    clock: Callable[[], datetime]

    def __post_init__(self) -> None:
        if self.environment not in PRODUCTION_LIKE_ENVIRONMENTS:
            raise ValueError("assessment AI composition requires test/staging/production")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not callable(getattr(self.runtime_resolver, "resolve", None)):
            raise TypeError("runtime_resolver must implement resolve")
        if not isinstance(self.context_broker, AsyncContextBrokerPort):
            raise TypeError("context_broker must implement AsyncContextBrokerPort")
        if self.context_broker.durability_mode != "DURABLE":
            raise ValueError("assessment AI composition requires durable Context Broker")
        resolver_broker = getattr(self.runtime_resolver, "context_broker", self.context_broker)
        if resolver_broker is not self.context_broker:
            raise ValueError("assessment adapter and Agent Runtime must share Context Broker")
        resolver_sessions = getattr(self.runtime_resolver, "session_factory", self.session_factory)
        if resolver_sessions is not self.session_factory:
            raise ValueError("assessment AI stores must share the runtime session factory")
        resolver_environment = getattr(self.runtime_resolver, "environment", self.environment)
        if resolver_environment != self.environment and not (
            self.environment == "test" and resolver_environment == "staging"
        ):
            raise ValueError("assessment AI runtime environment mismatch")
        if not callable(self.actor_id_resolver) or not callable(self.clock):
            raise TypeError("assessment actor and clock resolvers must be callable")

    def build_interpretation_adapter(self) -> AssessmentAiInterpretationAdapter:
        return AssessmentAiInterpretationAdapter(
            runtime_resolver=self.runtime_resolver,
            context_broker=self.context_broker,
            authorization_resolver=SqlAlchemyAssessmentAuthorizationResolver(
                session_factory=self.session_factory,
                actor_id_resolver=self.actor_id_resolver,
                clock=self.clock,
            ),
            run_replay_resolver=SqlAlchemyAssessmentRunReplayResolver(self.session_factory),
            assets=self.assets,
            clock=self.clock,
        )

    def build_query_handler(
        self,
        repository: AssessmentRepositoryPort,
    ) -> AssessmentQueryHandler:
        return AssessmentQueryHandler(repository, self.build_interpretation_adapter())

    def build_growth_hypothesis_handler(
        self,
        repository: AssessmentRepositoryPort,
    ) -> GrowthHypothesisCommandHandler:
        return GrowthHypothesisCommandHandler(repository, self.build_interpretation_adapter())


__all__ = ["ProductionAssessmentAiComposition"]
