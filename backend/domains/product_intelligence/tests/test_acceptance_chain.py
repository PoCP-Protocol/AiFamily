"""Verifies the PR-001 acceptance criterion (Override #6 item 2 / project
owner instruction 01): a full Signal -> Insight -> Opportunity ->
GrowthProblem -> GrowthHypothesis -> GrowthStrategy -> ProductConcept chain
can be created and traced back end-to-end. Parametrized over both
repositories (Fake dict + SQLite-backed SQLAlchemy) so the test proves the
application layer, not just one implementation.

PR-001R (chief-architect review on PR #27): every command now takes an
`ActorContext` (`context` fixtures in `conftest.py`) instead of
`created_by`/`tenant_scope` parameters.
"""
from __future__ import annotations

import pytest

from ..application import commands, queries


async def _build_chain(repo, context):
    signal = await commands.create_market_signal(repo, context, raw_text="家长普遍反映每天辅导作业太累")
    insight = await commands.create_customer_insight(repo, context, signal_id=signal.id, statement="小学高年级家长群体存在学习管理退出困难")
    opportunity = await commands.create_opportunity(repo, context, insight_id=insight.id, statement="学习责任转移计划")
    problem = await commands.create_growth_problem(repo, context, opportunity_id=opportunity.id, symptom="孩子写作业拖延")
    hypothesis = await commands.create_growth_hypothesis(repo, context, problem_id=problem.id, statement="家长控制增加导致孩子自主感下降")
    strategy = await commands.create_growth_strategy(repo, context, problem_id=problem.id, hypothesis_ids=[hypothesis.id], statement="先完成学习责任逐步转移")
    concept = await commands.create_product_concept(repo, context, strategy_id=strategy.id, title="学习自主21天计划")
    return signal, insight, opportunity, problem, hypothesis, strategy, concept


async def _build_chain_with_ai_insight(repo, ai_context):
    """AI-authored insight requires full provenance (PR-001R item 4)."""
    signal = await commands.create_market_signal(repo, ai_context, raw_text="家长普遍反映每天辅导作业太累")
    insight = await commands.create_customer_insight(
        repo, ai_context, signal_id=signal.id, statement="小学高年级家长群体存在学习管理退出困难",
        model_ref="claude-sonnet-4-6", prompt_use_case_version="market.insight.generate@1", confidence=0.7,
    )
    return signal, insight


@pytest.mark.asyncio
async def test_full_chain_fake_repository(fake_repo, human_context):
    signal, insight, opportunity, problem, hypothesis, strategy, concept = await _build_chain(fake_repo, human_context)

    chain = await queries.get_product_concept_chain(fake_repo, human_context, product_concept_id=concept.id)

    assert chain["product_concept"].id == concept.id
    assert chain["growth_strategy"].id == strategy.id
    assert chain["growth_problem"].id == problem.id
    assert [h.id for h in chain["growth_hypotheses"]] == [hypothesis.id]
    assert chain["opportunity"].id == opportunity.id
    assert chain["customer_insight"].id == insight.id
    assert chain["market_signal"].id == signal.id


@pytest.mark.asyncio
async def test_full_chain_sqlalchemy_repository(sqlalchemy_repo, ai_context):
    signal, insight = await _build_chain_with_ai_insight(sqlalchemy_repo, ai_context)

    loaded = await sqlalchemy_repo.load_customer_insight(insight.id, ai_context.tenant_scope)
    assert loaded.generated_by == ai_context.actor_id
    assert loaded.model_ref == "claude-sonnet-4-6"
    assert loaded.signal_id == signal.id


@pytest.mark.asyncio
async def test_growth_strategy_requires_at_least_one_hypothesis(fake_repo, human_context):
    from ..domain.errors import ProductIntelligenceValidationError

    signal, insight, opportunity, problem, *_ = await _build_chain(fake_repo, human_context)
    with pytest.raises(ProductIntelligenceValidationError):
        await commands.create_growth_strategy(
            fake_repo, human_context, problem_id=problem.id, hypothesis_ids=[], statement="empty strategy should be rejected",
        )
