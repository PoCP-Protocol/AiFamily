"""Real SQLAlchemy repository — async session-based, implements
`ProductIntelligenceRepositoryPort`. No real-Postgres integration test in
this PR (Override #6 item 4); tests run this same repository against an
in-memory SQLite engine via `tests/conftest.py`; a separate real-Postgres
integration test is added per PR-001R item 7 (`tests/test_postgres_integration.py`).

PR-001R (chief-architect review on PR #27):
- item 3: every `load_*` takes `tenant_scope` and filters by it — a row
  belonging to another tenant is indistinguishable from a missing row.
- item 6: `save_*` no longer calls `session.commit()` — it only
  `merge()`s and `flush()`es. Transaction commit is the caller's
  responsibility (the API dependency / a `UnitOfWork`, see
  `infrastructure/unit_of_work.py`), not the repository's. This matters
  once a single request needs to write more than one aggregate atomically
  (e.g. the future Compiler writing a `ProductDefinition` +
  `ServiceBlueprintVersion` together) — a repository that commits on every
  save cannot participate in a larger atomic unit of work.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.entities import (
    ContradictionModel,
    CustomerInsight,
    CustomerSegment,
    Evidence,
    GrowthHypothesis,
    GrowthProblem,
    GrowthStrategy,
    MarketSignal,
    MarketTrend,
    Opportunity,
    ProductComponent,
    ProductConcept,
    ProductDefinition,
    ProductPattern,
    ServiceBlueprintVersion,
    SignalCluster,
    UnmetNeed,
)
from ..domain.errors import ProductIntelligenceNotFoundError
from . import sqlalchemy_models as m


class SqlAlchemyProductIntelligenceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    # -- MarketSignal --
    async def save_market_signal(self, entity: MarketSignal) -> None:
        await self._merge(m.MarketSignalRow(**entity.model_dump()))

    async def load_market_signal(self, entity_id: str, tenant_scope: str) -> MarketSignal:
        row = await self._get_scoped(m.MarketSignalRow, entity_id, tenant_scope, "market_signal_not_found")
        return MarketSignal(**_row_to_dict(row))

    # -- supporting objects (create/save only, per Override #6 item 2) --
    async def save_signal_cluster(self, entity: SignalCluster) -> None:
        await self._merge(m.SignalClusterRow(**entity.model_dump()))

    async def save_market_trend(self, entity: MarketTrend) -> None:
        await self._merge(m.MarketTrendRow(**entity.model_dump()))

    async def save_customer_segment(self, entity: CustomerSegment) -> None:
        await self._merge(m.CustomerSegmentRow(**entity.model_dump()))

    async def save_evidence(self, entity: Evidence) -> None:
        await self._merge(m.EvidenceRow(**entity.model_dump()))

    # -- CustomerInsight --
    async def save_customer_insight(self, entity: CustomerInsight) -> None:
        await self._merge(m.CustomerInsightRow(**entity.model_dump()))

    async def load_customer_insight(self, entity_id: str, tenant_scope: str) -> CustomerInsight:
        row = await self._get_scoped(m.CustomerInsightRow, entity_id, tenant_scope, "customer_insight_not_found")
        return CustomerInsight(**_row_to_dict(row))

    async def save_unmet_need(self, entity: UnmetNeed) -> None:
        await self._merge(m.UnmetNeedRow(**entity.model_dump()))

    # -- Opportunity --
    async def save_opportunity(self, entity: Opportunity) -> None:
        await self._merge(m.OpportunityRow(**entity.model_dump()))

    async def load_opportunity(self, entity_id: str, tenant_scope: str) -> Opportunity:
        row = await self._get_scoped(m.OpportunityRow, entity_id, tenant_scope, "opportunity_not_found")
        return Opportunity(**_row_to_dict(row))

    # -- GrowthProblem --
    async def save_growth_problem(self, entity: GrowthProblem) -> None:
        await self._merge(m.GrowthProblemRow(**entity.model_dump()))

    async def load_growth_problem(self, entity_id: str, tenant_scope: str) -> GrowthProblem:
        row = await self._get_scoped(m.GrowthProblemRow, entity_id, tenant_scope, "growth_problem_not_found")
        return GrowthProblem(**_row_to_dict(row))

    # -- GrowthHypothesis --
    async def save_growth_hypothesis(self, entity: GrowthHypothesis) -> None:
        await self._merge(m.GrowthHypothesisRow(**entity.model_dump()))

    async def load_growth_hypothesis(self, entity_id: str, tenant_scope: str) -> GrowthHypothesis:
        row = await self._get_scoped(m.GrowthHypothesisRow, entity_id, tenant_scope, "growth_hypothesis_not_found")
        return GrowthHypothesis(**_row_to_dict(row))

    async def list_growth_hypotheses_by_problem(self, problem_id: str, tenant_scope: str) -> list[GrowthHypothesis]:
        result = await self._session.execute(
            select(m.GrowthHypothesisRow).where(
                m.GrowthHypothesisRow.problem_id == problem_id,
                m.GrowthHypothesisRow.tenant_scope == tenant_scope,
            )
        )
        return [GrowthHypothesis(**_row_to_dict(row)) for row in result.scalars().all()]

    # -- ContradictionModel --
    async def save_contradiction_model(self, entity: ContradictionModel) -> None:
        await self._merge(m.ContradictionModelRow(**entity.model_dump()))

    # -- GrowthStrategy --
    async def save_growth_strategy(self, entity: GrowthStrategy) -> None:
        await self._merge(m.GrowthStrategyRow(**entity.model_dump()))

    async def load_growth_strategy(self, entity_id: str, tenant_scope: str) -> GrowthStrategy:
        row = await self._get_scoped(m.GrowthStrategyRow, entity_id, tenant_scope, "growth_strategy_not_found")
        return GrowthStrategy(**_row_to_dict(row))

    # -- ProductConcept --
    async def save_product_concept(self, entity: ProductConcept) -> None:
        await self._merge(m.ProductConceptRow(**entity.model_dump()))

    async def load_product_concept(self, entity_id: str, tenant_scope: str) -> ProductConcept:
        row = await self._get_scoped(m.ProductConceptRow, entity_id, tenant_scope, "product_concept_not_found")
        return ProductConcept(**_row_to_dict(row))

    # -- ProductComponent / ProductPattern / ProductDefinition / ServiceBlueprintVersion --
    async def save_product_component(self, entity: ProductComponent) -> None:
        await self._merge(m.ProductComponentRow(**entity.model_dump()))

    async def save_product_pattern(self, entity: ProductPattern) -> None:
        await self._merge(m.ProductPatternRow(**entity.model_dump()))

    async def save_product_definition(self, entity: ProductDefinition) -> None:
        await self._merge(m.ProductDefinitionRow(**entity.model_dump()))

    async def save_service_blueprint_version(self, entity: ServiceBlueprintVersion) -> None:
        await self._merge(m.ServiceBlueprintVersionRow(**entity.model_dump()))

    async def _merge(self, row: object) -> None:
        await self._session.merge(row)
        await self._session.flush()

    async def _get_scoped(self, model_cls: type, entity_id: str, tenant_scope: str, error_code: str):
        row = await self._session.get(model_cls, entity_id)
        if row is None or row.tenant_scope != tenant_scope:
            raise ProductIntelligenceNotFoundError(error_code)
        return row


def _row_to_dict(row: object) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
