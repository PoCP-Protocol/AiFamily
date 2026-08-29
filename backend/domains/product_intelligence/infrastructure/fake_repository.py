"""In-memory fake repository — mirrors
`domains/assessment/infrastructure/fake_repository.py`'s role (FakeProvider
test double). Useful for pure application-layer unit tests that don't need
to exercise the real SQLAlchemy mapping (see `sqlalchemy_repository.py` /
`tests/conftest.py` for the SQLite-backed "real" repository tests).
"""
from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class FakeProductIntelligenceRepository:
    _market_signals: dict = field(default_factory=dict)
    _signal_clusters: dict = field(default_factory=dict)
    _market_trends: dict = field(default_factory=dict)
    _customer_segments: dict = field(default_factory=dict)
    _evidence: dict = field(default_factory=dict)
    _customer_insights: dict = field(default_factory=dict)
    _unmet_needs: dict = field(default_factory=dict)
    _opportunities: dict = field(default_factory=dict)
    _growth_problems: dict = field(default_factory=dict)
    _growth_hypotheses: dict = field(default_factory=dict)
    _contradiction_models: dict = field(default_factory=dict)
    _growth_strategies: dict = field(default_factory=dict)
    _product_concepts: dict = field(default_factory=dict)
    _product_components: dict = field(default_factory=dict)
    _product_patterns: dict = field(default_factory=dict)
    _product_definitions: dict = field(default_factory=dict)
    _service_blueprint_versions: dict = field(default_factory=dict)

    async def save_market_signal(self, entity: MarketSignal) -> None:
        self._market_signals[entity.id] = entity

    async def load_market_signal(self, entity_id: str, tenant_scope: str) -> MarketSignal:
        return self._get_scoped(self._market_signals, entity_id, tenant_scope, "market_signal_not_found")

    async def save_signal_cluster(self, entity: SignalCluster) -> None:
        self._signal_clusters[entity.id] = entity

    async def save_market_trend(self, entity: MarketTrend) -> None:
        self._market_trends[entity.id] = entity

    async def save_customer_segment(self, entity: CustomerSegment) -> None:
        self._customer_segments[entity.id] = entity

    async def save_evidence(self, entity: Evidence) -> None:
        self._evidence[entity.id] = entity

    async def save_customer_insight(self, entity: CustomerInsight) -> None:
        self._customer_insights[entity.id] = entity

    async def load_customer_insight(self, entity_id: str, tenant_scope: str) -> CustomerInsight:
        return self._get_scoped(self._customer_insights, entity_id, tenant_scope, "customer_insight_not_found")

    async def save_unmet_need(self, entity: UnmetNeed) -> None:
        self._unmet_needs[entity.id] = entity

    async def save_opportunity(self, entity: Opportunity) -> None:
        self._opportunities[entity.id] = entity

    async def load_opportunity(self, entity_id: str, tenant_scope: str) -> Opportunity:
        return self._get_scoped(self._opportunities, entity_id, tenant_scope, "opportunity_not_found")

    async def save_growth_problem(self, entity: GrowthProblem) -> None:
        self._growth_problems[entity.id] = entity

    async def load_growth_problem(self, entity_id: str, tenant_scope: str) -> GrowthProblem:
        return self._get_scoped(self._growth_problems, entity_id, tenant_scope, "growth_problem_not_found")

    async def save_growth_hypothesis(self, entity: GrowthHypothesis) -> None:
        self._growth_hypotheses[entity.id] = entity

    async def load_growth_hypothesis(self, entity_id: str, tenant_scope: str) -> GrowthHypothesis:
        return self._get_scoped(self._growth_hypotheses, entity_id, tenant_scope, "growth_hypothesis_not_found")

    async def list_growth_hypotheses_by_problem(self, problem_id: str, tenant_scope: str) -> list[GrowthHypothesis]:
        return [h for h in self._growth_hypotheses.values() if h.problem_id == problem_id and h.tenant_scope == tenant_scope]

    async def save_contradiction_model(self, entity: ContradictionModel) -> None:
        self._contradiction_models[entity.id] = entity

    async def save_growth_strategy(self, entity: GrowthStrategy) -> None:
        self._growth_strategies[entity.id] = entity

    async def load_growth_strategy(self, entity_id: str, tenant_scope: str) -> GrowthStrategy:
        return self._get_scoped(self._growth_strategies, entity_id, tenant_scope, "growth_strategy_not_found")

    async def save_product_concept(self, entity: ProductConcept) -> None:
        self._product_concepts[entity.id] = entity

    async def load_product_concept(self, entity_id: str, tenant_scope: str) -> ProductConcept:
        return self._get_scoped(self._product_concepts, entity_id, tenant_scope, "product_concept_not_found")

    async def save_product_component(self, entity: ProductComponent) -> None:
        self._product_components[entity.id] = entity

    async def save_product_pattern(self, entity: ProductPattern) -> None:
        self._product_patterns[entity.id] = entity

    async def save_product_definition(self, entity: ProductDefinition) -> None:
        self._product_definitions[entity.id] = entity

    async def save_service_blueprint_version(self, entity: ServiceBlueprintVersion) -> None:
        self._service_blueprint_versions[entity.id] = entity

    @staticmethod
    def _get_scoped(store: dict, entity_id: str, tenant_scope: str, error_code: str):
        """PR-001R item 3: raises the same `error_code` whether the row is
        missing entirely or exists but belongs to a different tenant — a
        caller cannot distinguish "wrong id" from "right id, wrong tenant".
        """
        entity = store.get(entity_id)
        if entity is None or entity.tenant_scope != tenant_scope:
            raise ProductIntelligenceNotFoundError(error_code)
        return entity
