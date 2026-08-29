"""Chain-traversal query — satisfies the PR-001 acceptance criterion
("每一步均可追溯前一对象" / instruction 03's `strategy-map` shape) by walking
the acceptance chain backward from a `ProductConcept` to its `MarketSignal`.

PR-001R (chief-architect review on PR #27, item 3): takes `ActorContext` and
passes `context.tenant_scope` into every load — without this, a caller
could GET another tenant's chain just by guessing/enumerating a
`product_concept_id`, even though every *write* path in `commands.py` was
tenant-scoped.
"""
from __future__ import annotations

from .context import ActorContext
from .ports import ProductIntelligenceRepositoryPort


async def get_product_concept_chain(
    repo: ProductIntelligenceRepositoryPort, context: ActorContext, *, product_concept_id: str,
) -> dict:
    tenant = context.tenant_scope
    concept = await repo.load_product_concept(product_concept_id, tenant)
    strategy = await repo.load_growth_strategy(concept.strategy_id, tenant)
    problem = await repo.load_growth_problem(strategy.problem_id, tenant)
    hypotheses = [await repo.load_growth_hypothesis(h, tenant) for h in strategy.hypothesis_ids]
    opportunity = await repo.load_opportunity(problem.opportunity_id, tenant) if problem.opportunity_id else None
    insight = await repo.load_customer_insight(opportunity.insight_id, tenant) if opportunity else None
    signal = await repo.load_market_signal(insight.signal_id, tenant) if insight and insight.signal_id else None
    return {
        "product_concept": concept,
        "growth_strategy": strategy,
        "growth_problem": problem,
        "growth_hypotheses": hypotheses,
        "opportunity": opportunity,
        "customer_insight": insight,
        "market_signal": signal,
    }
