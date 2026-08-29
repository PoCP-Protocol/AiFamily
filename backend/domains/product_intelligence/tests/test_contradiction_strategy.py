"""PR-003 V1 (Contradiction & Strategy Intelligence + Value Architecture):
GrowthProblem -> multi-GrowthHypothesis -> ContradictionModel ->
ValueArchitecture -> GrowthStrategy.

Covers: >=2 hypothesis requirement, contradiction review lifecycle +
permission gate, "at most one primary contradiction per problem",
ValueArchitecture evidence gate, and GrowthStrategy requiring an APPROVED
contradiction when one is linked.
"""

from __future__ import annotations

import pytest

from ..application import commands, contradiction_commands
from ..application.context import ActorContext
from ..domain.errors import ProductIntelligenceForbiddenError, ProductIntelligenceValidationError


def _reviewer_context(tenant: str = "tenant-a") -> ActorContext:
    return ActorContext(
        actor_id="strategist-1",
        actor_type="HUMAN",
        tenant_scope=tenant,
        permissions=frozenset({contradiction_commands.CONTRADICTION_REVIEW_PERMISSION}),
    )


def _no_permission_context(tenant: str = "tenant-a") -> ActorContext:
    return ActorContext(actor_id="human-2", actor_type="HUMAN", tenant_scope=tenant)


def _ai_context(tenant: str = "tenant-a") -> ActorContext:
    return ActorContext(actor_id="ai:contradiction.analyze", actor_type="AI", tenant_scope=tenant)


async def _make_problem_with_two_hypotheses(repo, context):
    signal = await commands.create_market_signal(repo, context, raw_text="家长每天催作业太累")
    insight = await commands.create_customer_insight(
        repo, context, signal_id=signal.id, statement="家长控制与孩子自主的冲突"
    )
    opportunity = await commands.create_opportunity(
        repo, context, insight_id=insight.id, statement="学习责任转移"
    )
    problem = await commands.create_growth_problem(
        repo, context, opportunity_id=opportunity.id, symptom="孩子写作业拖延"
    )
    h1 = await commands.create_growth_hypothesis(
        repo, context, problem_id=problem.id, statement="家长控制增加导致孩子自主感下降"
    )
    h2 = await commands.create_growth_hypothesis(
        repo, context, problem_id=problem.id, statement="任务难度过高导致失败焦虑"
    )
    return problem, h1, h2


@pytest.mark.asyncio
async def test_contradiction_requires_at_least_two_hypotheses(fake_repo):
    context = _reviewer_context()
    problem, h1, _h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    with pytest.raises(ProductIntelligenceValidationError):
        await contradiction_commands.create_contradiction_model(
            fake_repo,
            context,
            problem_id=problem.id,
            hypothesis_ids=[h1.id],
            primary_factor_a="parent_control",
            primary_factor_b="child_autonomy",
            relationship="inverse",
        )


@pytest.mark.asyncio
async def test_contradiction_hypothesis_must_belong_to_same_problem(fake_repo):
    context = _reviewer_context()
    problem, h1, h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    # A hypothesis from a second, unrelated problem must be rejected even
    # though it belongs to the same tenant.
    other_problem, other_h1, _other_h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    with pytest.raises(ProductIntelligenceValidationError):
        await contradiction_commands.create_contradiction_model(
            fake_repo,
            context,
            problem_id=problem.id,
            hypothesis_ids=[h1.id, other_h1.id],
            primary_factor_a="parent_control",
            primary_factor_b="child_autonomy",
            relationship="inverse",
        )


@pytest.mark.asyncio
async def test_contradiction_lifecycle_and_permission_gate(fake_repo):
    context = _reviewer_context()
    problem, h1, h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    contradiction = await contradiction_commands.create_contradiction_model(
        fake_repo,
        context,
        problem_id=problem.id,
        hypothesis_ids=[h1.id, h2.id],
        primary_factor_a="parent_control",
        primary_factor_b="child_autonomy",
        relationship="inverse",
        evidence_refs=["evidence:1"],
    )
    assert contradiction.status == "DRAFT"

    submitted = await contradiction_commands.submit_contradiction_for_review(
        fake_repo, context, contradiction_id=contradiction.id
    )
    assert submitted.status == "UNDER_REVIEW"

    # No permission -> forbidden, even for a HUMAN.
    with pytest.raises(ProductIntelligenceForbiddenError):
        await contradiction_commands.decide_contradiction_review(
            fake_repo,
            _no_permission_context(),
            contradiction_id=contradiction.id,
            approved=True,
            reason="looks right",
        )

    # AI actor -> forbidden regardless of any permission string.
    with pytest.raises(ProductIntelligenceForbiddenError):
        await contradiction_commands.decide_contradiction_review(
            fake_repo, _ai_context(), contradiction_id=contradiction.id, approved=True, reason="x"
        )

    approved = await contradiction_commands.decide_contradiction_review(
        fake_repo,
        context,
        contradiction_id=contradiction.id,
        approved=True,
        reason="matches evidence",
    )
    assert approved.status == "APPROVED"
    assert approved.reviewed_by == context.actor_id


@pytest.mark.asyncio
async def test_at_most_one_primary_contradiction_per_problem(fake_repo):
    context = _reviewer_context()
    problem, h1, h2 = await _make_problem_with_two_hypotheses(fake_repo, context)

    async def _approved_contradiction(factor_a: str) -> str:
        c = await contradiction_commands.create_contradiction_model(
            fake_repo,
            context,
            problem_id=problem.id,
            hypothesis_ids=[h1.id, h2.id],
            primary_factor_a=factor_a,
            primary_factor_b="child_autonomy",
            relationship="inverse",
            evidence_refs=["evidence:1"],
        )
        c = await contradiction_commands.decide_contradiction_review(
            fake_repo, context, contradiction_id=c.id, approved=True, reason="ok"
        )
        return c.id

    first_id = await _approved_contradiction("parent_control")
    second_id = await _approved_contradiction("task_difficulty")

    first_marked = await contradiction_commands.mark_contradiction_primary(
        fake_repo, context, contradiction_id=first_id
    )
    assert first_marked.primary_rank == 1

    second_marked = await contradiction_commands.mark_contradiction_primary(
        fake_repo, context, contradiction_id=second_id
    )
    assert second_marked.primary_rank == 1

    reloaded_first = await fake_repo.load_contradiction_model(first_id, context.tenant_scope)
    assert reloaded_first.primary_rank is None, "marking a second primary must demote the first"


@pytest.mark.asyncio
async def test_mark_primary_requires_approved_status(fake_repo):
    context = _reviewer_context()
    problem, h1, h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    contradiction = await contradiction_commands.create_contradiction_model(
        fake_repo,
        context,
        problem_id=problem.id,
        hypothesis_ids=[h1.id, h2.id],
        primary_factor_a="parent_control",
        primary_factor_b="child_autonomy",
        relationship="inverse",
    )
    with pytest.raises(ProductIntelligenceValidationError):
        await contradiction_commands.mark_contradiction_primary(
            fake_repo, context, contradiction_id=contradiction.id
        )


@pytest.mark.asyncio
async def test_value_architecture_requires_evidence(fake_repo):
    context = _reviewer_context()
    problem, _h1, _h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    with pytest.raises(ProductIntelligenceValidationError):
        await contradiction_commands.create_value_architecture(
            fake_repo,
            context,
            problem_id=problem.id,
            emotional_current_state="焦虑、无力",
            emotional_desired_state="被理解、有掌控感",
            action_next_best_action="今晚只做一次5分钟倾听",
            rationale="家长长期催促已产生对抗循环",
            evidence_refs=[],
        )


@pytest.mark.asyncio
async def test_value_architecture_created_with_evidence(fake_repo):
    context = _reviewer_context()
    problem, _h1, _h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    value_architecture = await contradiction_commands.create_value_architecture(
        fake_repo,
        context,
        problem_id=problem.id,
        emotional_current_state="焦虑、无力",
        emotional_desired_state="被理解、有掌控感",
        action_next_best_action="今晚只做一次5分钟倾听",
        rationale="家长长期催促已产生对抗循环",
        evidence_refs=["evidence:parent-interview-1"],
        growth_outcomes=["催促次数下降"],
        economic_outcomes=["家长每日陪写时间减少"],
    )
    assert value_architecture.status == "DRAFT"
    assert value_architecture.growth_outcomes == ["催促次数下降"]


@pytest.mark.asyncio
async def test_growth_strategy_requires_contradiction_to_be_approved(fake_repo):
    context = _reviewer_context()
    problem, h1, h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    contradiction = await contradiction_commands.create_contradiction_model(
        fake_repo,
        context,
        problem_id=problem.id,
        hypothesis_ids=[h1.id, h2.id],
        primary_factor_a="parent_control",
        primary_factor_b="child_autonomy",
        relationship="inverse",
    )
    # Still DRAFT — linking it to a strategy must be rejected.
    with pytest.raises(ProductIntelligenceValidationError):
        await commands.create_growth_strategy(
            fake_repo,
            context,
            problem_id=problem.id,
            hypothesis_ids=[h1.id],
            statement="先完成学习责任逐步转移",
            contradiction_id=contradiction.id,
        )


@pytest.mark.asyncio
async def test_growth_strategy_links_approved_contradiction_and_value_architecture(fake_repo):
    context = _reviewer_context()
    problem, h1, h2 = await _make_problem_with_two_hypotheses(fake_repo, context)
    contradiction = await contradiction_commands.create_contradiction_model(
        fake_repo,
        context,
        problem_id=problem.id,
        hypothesis_ids=[h1.id, h2.id],
        primary_factor_a="parent_control",
        primary_factor_b="child_autonomy",
        relationship="inverse",
        evidence_refs=["evidence:1"],
    )
    approved = await contradiction_commands.decide_contradiction_review(
        fake_repo,
        context,
        contradiction_id=contradiction.id,
        approved=True,
        reason="matches evidence",
    )
    value_architecture = await contradiction_commands.create_value_architecture(
        fake_repo,
        context,
        problem_id=problem.id,
        emotional_current_state="焦虑",
        emotional_desired_state="有掌控感",
        action_next_best_action="今晚只做一次5分钟倾听",
        rationale="家长长期催促已产生对抗循环",
        evidence_refs=["evidence:2"],
    )

    strategy = await commands.create_growth_strategy(
        fake_repo,
        context,
        problem_id=problem.id,
        hypothesis_ids=[h1.id, h2.id],
        statement="先完成学习责任逐步转移",
        contradiction_id=approved.id,
        value_architecture_id=value_architecture.id,
    )
    assert strategy.contradiction_id == approved.id
    assert strategy.value_architecture_id == value_architecture.id


@pytest.mark.asyncio
async def test_full_chain_via_sqlalchemy_repo(sqlalchemy_repo):
    context = _reviewer_context()
    problem, h1, h2 = await _make_problem_with_two_hypotheses(sqlalchemy_repo, context)
    contradiction = await contradiction_commands.create_contradiction_model(
        sqlalchemy_repo,
        context,
        problem_id=problem.id,
        hypothesis_ids=[h1.id, h2.id],
        primary_factor_a="parent_control",
        primary_factor_b="child_autonomy",
        relationship="inverse",
        evidence_refs=["evidence:1"],
    )
    approved = await contradiction_commands.decide_contradiction_review(
        sqlalchemy_repo, context, contradiction_id=contradiction.id, approved=True, reason="ok"
    )
    marked = await contradiction_commands.mark_contradiction_primary(
        sqlalchemy_repo, context, contradiction_id=approved.id
    )
    value_architecture = await contradiction_commands.create_value_architecture(
        sqlalchemy_repo,
        context,
        problem_id=problem.id,
        emotional_current_state="焦虑",
        emotional_desired_state="有掌控感",
        action_next_best_action="今晚只做一次5分钟倾听",
        rationale="家长长期催促已产生对抗循环",
        evidence_refs=["evidence:2"],
    )
    strategy = await commands.create_growth_strategy(
        sqlalchemy_repo,
        context,
        problem_id=problem.id,
        hypothesis_ids=[h1.id, h2.id],
        statement="先完成学习责任逐步转移",
        contradiction_id=marked.id,
        value_architecture_id=value_architecture.id,
    )

    reloaded_strategy = await sqlalchemy_repo.load_growth_strategy(
        strategy.id, context.tenant_scope
    )
    assert reloaded_strategy.contradiction_id == marked.id
    assert reloaded_strategy.value_architecture_id == value_architecture.id

    reloaded_contradiction = await sqlalchemy_repo.load_contradiction_model(
        marked.id, context.tenant_scope
    )
    assert reloaded_contradiction.primary_rank == 1

    reloaded_value_architecture = await sqlalchemy_repo.load_value_architecture(
        value_architecture.id, context.tenant_scope
    )
    assert reloaded_value_architecture.rationale == "家长长期催促已产生对抗循环"
