"""Production composition contract for the vertical family-growth surface.

This module intentionally does not manufacture a fallback runtime.  The
vertical draft route may only be advertised as production-ready when the
caller supplies durable Context and run-ledger adapters.  Keeping this check
at the composition root prevents an in-memory ``EvaluationLedger`` from being
mistaken for a cross-process implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.agi_vertical_composition import VerticalFamilyGrowthComposition
from backend.intelligence.agi_vertical_durable import (
    DurableVerticalGrowthRuntime,
    DurableVerticalLedgerAdapter,
)
from backend.intelligence.agi_vertical_feedback import (
    CombinedFeedbackPort,
    FamilyNeedOutcomeFeedbackPort,
    LedgerFeedbackPort,
)
from backend.intelligence.agi_vertical_runtime import (
    CapabilityPort,
    ConsentPort,
    EvaluationLedger,
    FeedbackPort,
    KnowledgePort,
    ModelGatewayPort,
    VerticalFamilyGrowthRuntime,
)
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort
from backend.intelligence.context_engine.family_growth_port import SqlFamilyGrowthContextPort
from backend.intelligence.experience.run_http import RunScope

PRODUCTION_VERTICAL_ENVIRONMENTS = frozenset({"test", "staging", "production"})


@dataclass(frozen=True, slots=True)
class ProductionVerticalFamilyGrowthComposition:
    """Validated dependency bundle for one vertical runtime instance.

    ``runtime`` remains the business pipeline, while ``durable_ledger`` and
    ``context_broker`` are the persistence seams that must be shared by the
    request resolver.  The class is deliberately a contract, not a hidden
    dependency builder: production callers must pass every adapter explicitly.
    """

    environment: str
    session_factory: async_sessionmaker[AsyncSession]
    runtime: VerticalFamilyGrowthRuntime
    context_broker: AsyncContextBrokerPort
    durable_ledger: DurableVerticalLedgerAdapter
    scope_factory: Any

    def __post_init__(self) -> None:
        if self.environment not in PRODUCTION_VERTICAL_ENVIRONMENTS:
            raise ValueError("vertical family-growth composition requires test/staging/production")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not isinstance(self.runtime, VerticalFamilyGrowthRuntime):
            raise TypeError("runtime must be a VerticalFamilyGrowthRuntime")
        if self.runtime.context_durability_mode != "DURABLE":
            raise ValueError("vertical family-growth runtime requires durable Context Port")
        if not isinstance(self.context_broker, AsyncContextBrokerPort):
            raise TypeError("context_broker must implement AsyncContextBrokerPort")
        if self.context_broker.durability_mode != "DURABLE":
            raise ValueError("vertical family-growth composition requires durable Context Broker")
        broker_session_factory = getattr(self.context_broker, "session_factory", None)
        if (
            broker_session_factory is not None
            and broker_session_factory is not self.session_factory
        ):
            raise ValueError("vertical family-growth session factory mismatch")
        runtime_context_broker = self.runtime.context_port
        if hasattr(runtime_context_broker, "broker") and (
            runtime_context_broker.broker is not self.context_broker
        ):
            raise ValueError("vertical family-growth runtime/context broker mismatch")
        if not isinstance(self.durable_ledger, DurableVerticalLedgerAdapter):
            raise TypeError("durable_ledger must be a DurableVerticalLedgerAdapter")
        if not callable(self.scope_factory):
            raise TypeError("scope_factory must be callable")

    def install(self, application: Any) -> None:
        """Install only an explicitly composed runtime on an app state object."""

        state = getattr(application, "state", None)
        if state is None:
            raise TypeError("application must expose state")
        state.vertical_family_growth_runtime = DurableVerticalGrowthRuntime(
            self.runtime,
            self.durable_ledger,
            self.scope_factory,
        )
        state.vertical_family_growth_context_broker = self.context_broker
        state.vertical_family_growth_durable_ledger = self.durable_ledger


def build_production_vertical_family_growth_composition(
    *,
    environment: str,
    session_factory: async_sessionmaker[AsyncSession],
    runtime: VerticalFamilyGrowthRuntime,
    context_broker: AsyncContextBrokerPort,
    durable_ledger: DurableVerticalLedgerAdapter,
    scope_factory: Any,
) -> ProductionVerticalFamilyGrowthComposition:
    """Validate and return the production vertical-growth dependency bundle.

    This is intentionally a *constructor*, not a hidden dependency factory:
    deployments own creation of the gateway, knowledge, consent and context
    adapters and pass the already-composed runtime here.  Keeping this helper
    at the app boundary makes startup code uniform while preserving the
    fail-closed checks in :class:`ProductionVerticalFamilyGrowthComposition`.
    """

    return ProductionVerticalFamilyGrowthComposition(
        environment=environment,
        session_factory=session_factory,
        runtime=runtime,
        context_broker=context_broker,
        durable_ledger=durable_ledger,
        scope_factory=scope_factory,
    )


def build_sql_production_vertical_family_growth_composition(
    *,
    environment: str,
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGatewayPort,
    knowledge: KnowledgePort,
    feedback: FeedbackPort,
    ledger: EvaluationLedger,
    durable_ledger: DurableVerticalLedgerAdapter,
    context_broker: AsyncContextBrokerPort,
    scope_factory: Any,
    capabilities: CapabilityPort | None = None,
    consent: ConsentPort | None = None,
    outcome_repository: Any | None = None,
) -> ProductionVerticalFamilyGrowthComposition:
    """Compose the vertical runtime with the durable SQL Context adapter.

    Deployments still own gateway, knowledge, consent and ledger construction;
    this helper only assembles their ports at the application boundary.  The
    resulting runtime reads context through ``SqlFamilyGrowthContextPort`` so
    every generation uses the same durable broker that is installed on app
    state.  ``scope_factory`` must derive an authenticated ``ContextScope``;
    request payloads never provide tenant, subject or consent fields.
    """

    if not callable(scope_factory):
        raise TypeError("scope_factory must be callable")

    async def feedback_scope_factory(family_id: str) -> RunScope:
        context_scope = scope_factory(family_id)
        if hasattr(context_scope, "__await__"):
            context_scope = await context_scope
        return RunScope(
            tenant_id=context_scope.tenant_id,
            family_id=context_scope.family_id,
            subject_ids=context_scope.subject_ids,
        )

    feedback_port = CombinedFeedbackPort(
        LedgerFeedbackPort(durable_ledger, feedback_scope_factory),
        feedback,
        *(
            (FamilyNeedOutcomeFeedbackPort(outcome_repository, feedback_scope_factory),)
            if outcome_repository is not None
            else ()
        ),
    )
    context = SqlFamilyGrowthContextPort(context_broker, scope_factory)
    runtime = VerticalFamilyGrowthComposition(
        gateway=gateway,
        context=context,
        knowledge=knowledge,
        feedback=feedback_port,
        ledger=ledger,
        capabilities=capabilities,
        consent=consent,
    ).build_runtime()
    return build_production_vertical_family_growth_composition(
        environment=environment,
        session_factory=session_factory,
        runtime=runtime,
        context_broker=context_broker,
        durable_ledger=durable_ledger,
        scope_factory=scope_factory,
    )


def install_production_vertical_family_growth_wiring(
    application: Any,
    composition: ProductionVerticalFamilyGrowthComposition,
) -> None:
    """Install one validated production composition on a FastAPI app.

    The application object is deliberately duck-typed to keep this module
    independent of FastAPI internals; ``composition.install`` performs the
    state-contract validation and never creates an in-memory fallback.
    """

    if not isinstance(composition, ProductionVerticalFamilyGrowthComposition):
        raise TypeError("composition must be a ProductionVerticalFamilyGrowthComposition")
    composition.install(application)


__all__ = [
    "PRODUCTION_VERTICAL_ENVIRONMENTS",
    "ProductionVerticalFamilyGrowthComposition",
    "build_production_vertical_family_growth_composition",
    "build_sql_production_vertical_family_growth_composition",
    "install_production_vertical_family_growth_wiring",
]
