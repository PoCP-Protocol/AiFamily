"""Verifies Override #6 item 3 / project-owner instruction 03 rule 4:
AI-generated hypotheses are created DRAFT and no path except an explicit
human-actor call can mark them VALIDATED.

PR-001R (chief-architect review on PR #27, items 4/5): actor identity/type
comes from `ActorContext` (`ai_context`/`human_context` fixtures), not a
string-prefix convention; validation records `validated_by/validated_at/
validation_reason` and bumps `version`; only `DRAFT`/`UNDER_REVIEW` may
transition to `VALIDATED`.
"""
from __future__ import annotations

import pytest

from ..application import commands
from ..domain.errors import ProductIntelligenceForbiddenError, ProductIntelligenceValidationError


async def _make_problem(repo, context):
    signal = await commands.create_market_signal(repo, context, raw_text="x")
    insight = await commands.create_customer_insight(repo, context, signal_id=signal.id, statement="i")
    opportunity = await commands.create_opportunity(repo, context, insight_id=insight.id, statement="o")
    return await commands.create_growth_problem(repo, context, opportunity_id=opportunity.id, symptom="p")


@pytest.mark.asyncio
async def test_ai_generated_hypothesis_starts_as_draft(fake_repo, human_context, ai_context):
    problem = await _make_problem(fake_repo, human_context)  # parent chain authored by a human; only the hypothesis itself is AI-generated
    hypothesis = await commands.create_growth_hypothesis(
        fake_repo, ai_context, problem_id=problem.id, statement="h",
        model_ref="m", prompt_use_case_version="growth.hypothesis.generate@1", confidence=0.5,
    )
    assert hypothesis.status == "DRAFT"
    assert hypothesis.generated_by == ai_context.actor_id


@pytest.mark.asyncio
async def test_ai_actor_creation_without_full_provenance_is_rejected(fake_repo, human_context, ai_context):
    problem = await _make_problem(fake_repo, human_context)
    with pytest.raises(ProductIntelligenceValidationError):
        await commands.create_growth_hypothesis(fake_repo, ai_context, problem_id=problem.id, statement="h")


@pytest.mark.asyncio
async def test_ai_actor_cannot_validate_hypothesis(fake_repo, human_context, ai_context):
    problem = await _make_problem(fake_repo, human_context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, human_context, problem_id=problem.id, statement="h")

    with pytest.raises(ProductIntelligenceForbiddenError):
        await commands.validate_growth_hypothesis(fake_repo, ai_context, hypothesis_id=hypothesis.id, reason="looks fine")


@pytest.mark.asyncio
async def test_human_actor_can_validate_hypothesis(fake_repo, human_context):
    problem = await _make_problem(fake_repo, human_context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, human_context, problem_id=problem.id, statement="h")

    validated = await commands.validate_growth_hypothesis(fake_repo, human_context, hypothesis_id=hypothesis.id, reason="matches evidence")
    assert validated.status == "VALIDATED"
    assert validated.validated_by == human_context.actor_id
    assert validated.validation_reason == "matches evidence"
    assert validated.version == hypothesis.version + 1
    assert validated.validated_at is not None
    assert validated.validated_at.tzinfo is not None  # timezone-aware, PR-001R item 6


@pytest.mark.asyncio
async def test_retired_hypothesis_cannot_be_revalidated(fake_repo, human_context):
    problem = await _make_problem(fake_repo, human_context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, human_context, problem_id=problem.id, statement="h")
    retired = hypothesis.model_copy(update={"status": "RETIRED"})
    await fake_repo.save_growth_hypothesis(retired)

    with pytest.raises(ProductIntelligenceValidationError):
        await commands.validate_growth_hypothesis(fake_repo, human_context, hypothesis_id=retired.id, reason="x")


@pytest.mark.asyncio
async def test_validation_without_reason_is_rejected(fake_repo, human_context):
    problem = await _make_problem(fake_repo, human_context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, human_context, problem_id=problem.id, statement="h")

    with pytest.raises(ProductIntelligenceValidationError):
        await commands.validate_growth_hypothesis(fake_repo, human_context, hypothesis_id=hypothesis.id, reason="")
