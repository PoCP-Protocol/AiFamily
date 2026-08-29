"""Verifies the Permission Pattern (chief-architect review on PR #33):
`validate_growth_hypothesis` requires the caller to be `HUMAN` *and* to
hold the `product_intelligence.hypothesis.review` permission in
`ActorContext.permissions`. This is an application-layer eligibility
check layered on top of (not a replacement for) the domain-layer
`actor_type == "HUMAN"` check inside `GrowthHypothesis.mark_validated` —
see the module docstring in `application/commands.py`.
"""
from __future__ import annotations

import pytest

from ..application import commands
from ..application.context import ActorContext
from ..domain.errors import ProductIntelligenceForbiddenError

REVIEW_PERMISSION = "product_intelligence.hypothesis.review"


async def _make_problem(repo, context):
    signal = await commands.create_market_signal(repo, context, raw_text="x")
    insight = await commands.create_customer_insight(repo, context, signal_id=signal.id, statement="i")
    opportunity = await commands.create_opportunity(repo, context, insight_id=insight.id, statement="o")
    return await commands.create_growth_problem(repo, context, opportunity_id=opportunity.id, symptom="p")


@pytest.mark.asyncio
async def test_human_with_no_permissions_is_forbidden(fake_repo):
    context = ActorContext(actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a")
    problem = await _make_problem(fake_repo, context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, context, problem_id=problem.id, statement="h")

    with pytest.raises(ProductIntelligenceForbiddenError):
        await commands.validate_growth_hypothesis(fake_repo, context, hypothesis_id=hypothesis.id, reason="looks fine")


@pytest.mark.asyncio
async def test_human_with_unrelated_permissions_is_forbidden(fake_repo):
    context = ActorContext(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
        permissions=frozenset({"product_intelligence.market_signal.create", "some.other.permission"}),
    )
    problem = await _make_problem(fake_repo, context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, context, problem_id=problem.id, statement="h")

    with pytest.raises(ProductIntelligenceForbiddenError):
        await commands.validate_growth_hypothesis(fake_repo, context, hypothesis_id=hypothesis.id, reason="looks fine")


@pytest.mark.asyncio
async def test_human_with_review_permission_can_validate(fake_repo):
    context = ActorContext(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
        permissions=frozenset({REVIEW_PERMISSION}),
    )
    problem = await _make_problem(fake_repo, context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, context, problem_id=problem.id, statement="h")

    validated = await commands.validate_growth_hypothesis(
        fake_repo, context, hypothesis_id=hypothesis.id, reason="matches evidence",
    )
    assert validated.status == "VALIDATED"
    assert validated.validated_by == context.actor_id


@pytest.mark.asyncio
async def test_ai_actor_with_review_permission_is_still_forbidden(fake_repo):
    creator_context = ActorContext(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
        permissions=frozenset({REVIEW_PERMISSION}),
    )
    problem = await _make_problem(fake_repo, creator_context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, creator_context, problem_id=problem.id, statement="h")

    ai_context = ActorContext(
        actor_id="ai-use-case:market.insight.generate", actor_type="AI", tenant_scope="tenant-a",
        permissions=frozenset({REVIEW_PERMISSION}),
    )
    with pytest.raises(ProductIntelligenceForbiddenError):
        await commands.validate_growth_hypothesis(fake_repo, ai_context, hypothesis_id=hypothesis.id, reason="looks fine")


@pytest.mark.asyncio
async def test_system_actor_with_review_permission_is_still_forbidden(fake_repo):
    creator_context = ActorContext(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
        permissions=frozenset({REVIEW_PERMISSION}),
    )
    problem = await _make_problem(fake_repo, creator_context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, creator_context, problem_id=problem.id, statement="h")

    system_context = ActorContext(
        actor_id="system-cron", actor_type="SYSTEM", tenant_scope="tenant-a",
        permissions=frozenset({REVIEW_PERMISSION}),
    )
    with pytest.raises(ProductIntelligenceForbiddenError):
        await commands.validate_growth_hypothesis(fake_repo, system_context, hypothesis_id=hypothesis.id, reason="looks fine")
