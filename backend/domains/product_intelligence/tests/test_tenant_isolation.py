"""PR-001R (chief-architect review on PR #27, item 3): Tenant B must not be
able to reference, load, validate, or chain-trace Tenant A's records, even
though ids are globally unique strings, not tenant-namespaced. Every
negative case here must raise `ProductIntelligenceNotFoundError` — not a
different error, and not a leaked "exists but forbidden" response, per the
"can't distinguish wrong id from wrong tenant" design in `ports.py`.
"""
from __future__ import annotations

import pytest

from ..application import commands, queries
from ..domain.errors import ProductIntelligenceNotFoundError


async def _make_signal(repo, context):
    return await commands.create_market_signal(repo, context, raw_text="tenant-a signal")


@pytest.mark.asyncio
async def test_cross_tenant_insight_creation_is_rejected(fake_repo, human_context, other_tenant_human_context):
    signal = await _make_signal(fake_repo, human_context)  # belongs to tenant-a

    with pytest.raises(ProductIntelligenceNotFoundError):
        await commands.create_customer_insight(
            fake_repo, other_tenant_human_context, signal_id=signal.id, statement="tenant-b trying to chain off tenant-a's signal",
        )


@pytest.mark.asyncio
async def test_cross_tenant_load_market_signal_is_rejected(fake_repo, human_context, other_tenant_human_context):
    signal = await _make_signal(fake_repo, human_context)

    with pytest.raises(ProductIntelligenceNotFoundError):
        await fake_repo.load_market_signal(signal.id, other_tenant_human_context.tenant_scope)


@pytest.mark.asyncio
async def test_cross_tenant_hypothesis_validation_is_rejected(fake_repo, human_context, other_tenant_human_context):
    signal = await _make_signal(fake_repo, human_context)
    insight = await commands.create_customer_insight(fake_repo, human_context, signal_id=signal.id, statement="i")
    opportunity = await commands.create_opportunity(fake_repo, human_context, insight_id=insight.id, statement="o")
    problem = await commands.create_growth_problem(fake_repo, human_context, opportunity_id=opportunity.id, symptom="p")
    hypothesis = await commands.create_growth_hypothesis(fake_repo, human_context, problem_id=problem.id, statement="h")

    with pytest.raises(ProductIntelligenceNotFoundError):
        await commands.validate_growth_hypothesis(
            fake_repo, other_tenant_human_context, hypothesis_id=hypothesis.id, reason="tenant-b should not reach this",
        )


@pytest.mark.asyncio
async def test_cross_tenant_chain_query_is_rejected(fake_repo, human_context, other_tenant_human_context):
    signal = await _make_signal(fake_repo, human_context)
    insight = await commands.create_customer_insight(fake_repo, human_context, signal_id=signal.id, statement="i")
    opportunity = await commands.create_opportunity(fake_repo, human_context, insight_id=insight.id, statement="o")
    problem = await commands.create_growth_problem(fake_repo, human_context, opportunity_id=opportunity.id, symptom="p")
    hypothesis = await commands.create_growth_hypothesis(fake_repo, human_context, problem_id=problem.id, statement="h")
    strategy = await commands.create_growth_strategy(fake_repo, human_context, problem_id=problem.id, hypothesis_ids=[hypothesis.id], statement="s")
    concept = await commands.create_product_concept(fake_repo, human_context, strategy_id=strategy.id, title="c")

    with pytest.raises(ProductIntelligenceNotFoundError):
        await queries.get_product_concept_chain(fake_repo, other_tenant_human_context, product_concept_id=concept.id)
