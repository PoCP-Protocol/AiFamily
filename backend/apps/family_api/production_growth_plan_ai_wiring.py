"""Production-parity composition seam for the UI-05 AI plan draft."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.growth_plan_ai_wiring import (
    ActorIdResolver,
    GrowthPlanAgentResolver,
    GrowthPlanAiAssets,
    GrowthPlanAiDraftAdapter,
    SqlAlchemyGrowthPlanAuthorizationResolver,
    SqlAlchemyGrowthPlanRunReplayResolver,
)
from backend.apps.family_api.growth_plan_evidence_reader import (
    SqlAlchemyGrowthPlanEvidenceReader,
)
from backend.apps.family_api.growth_plan_review_wiring import (
    GrowthPlanHumanGateApplication,
    SqlAlchemyGrowthPlanDraftRegistry,
)
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort

PRODUCTION_LIKE_ENVIRONMENTS = frozenset({"test", "staging", "production"})


@dataclass(frozen=True, slots=True)
class ProductionGrowthPlanAiComposition:
    """Bind the runtime and every durable governance store exactly once."""

    environment: str
    session_factory: async_sessionmaker[AsyncSession]
    runtime_resolver: GrowthPlanAgentResolver
    context_broker: AsyncContextBrokerPort
    actor_id_resolver: ActorIdResolver
    assets: GrowthPlanAiAssets
    clock: Callable[[], datetime]

    def __post_init__(self) -> None:
        if self.environment not in PRODUCTION_LIKE_ENVIRONMENTS:
            raise ValueError("growth plan AI composition requires test/staging/production")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not callable(getattr(self.runtime_resolver, "resolve", None)):
            raise TypeError("runtime_resolver must implement resolve")
        if not isinstance(self.context_broker, AsyncContextBrokerPort):
            raise TypeError("context_broker must implement AsyncContextBrokerPort")
        if self.context_broker.durability_mode != "DURABLE":
            raise ValueError("growth plan AI composition requires durable Context Broker")
        resolver_broker = getattr(self.runtime_resolver, "context_broker", self.context_broker)
        if resolver_broker is not self.context_broker:
            raise ValueError("growth plan adapter and Agent Runtime must share Context Broker")
        resolver_sessions = getattr(
            self.runtime_resolver,
            "session_factory",
            self.session_factory,
        )
        if resolver_sessions is not self.session_factory:
            raise ValueError("growth plan AI stores must share the runtime session factory")
        resolver_environment = getattr(
            self.runtime_resolver,
            "environment",
            self.environment,
        )
        if resolver_environment != self.environment and not (
            self.environment == "test" and resolver_environment == "staging"
        ):
            raise ValueError("growth plan AI runtime environment mismatch")
        if not callable(self.actor_id_resolver) or not callable(self.clock):
            raise TypeError("growth plan actor and clock resolvers must be callable")

    def build_draft_adapter(self) -> GrowthPlanAiDraftAdapter:
        return GrowthPlanAiDraftAdapter(
            runtime_resolver=self.runtime_resolver,
            context_broker=self.context_broker,
            authorization_resolver=SqlAlchemyGrowthPlanAuthorizationResolver(
                session_factory=self.session_factory,
                actor_id_resolver=self.actor_id_resolver,
                clock=self.clock,
            ),
            run_replay_resolver=SqlAlchemyGrowthPlanRunReplayResolver(self.session_factory),
            draft_store=SqlAlchemyGrowthPlanDraftRegistry(self.session_factory),
            assets=self.assets,
            clock=self.clock,
        )

    def build_evidence_reader(self) -> SqlAlchemyGrowthPlanEvidenceReader:
        return SqlAlchemyGrowthPlanEvidenceReader(
            session_factory=self.session_factory,
            actor_id_resolver=self.actor_id_resolver,
        )

    def build_review_application(self) -> GrowthPlanHumanGateApplication:
        return GrowthPlanHumanGateApplication(
            session_factory=self.session_factory,
            clock=self.clock,
        )


__all__ = ["ProductionGrowthPlanAiComposition"]
