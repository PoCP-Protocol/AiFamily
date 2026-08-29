"""Adversarial / negative-path tests for the product_intelligence domain
(Agent D scope, chief-architect G9 review on PR #33).

These deliberately try to break the domain with invalid inputs, illegal
state transitions, and mid-transaction failures — complementing the
happy-path acceptance chain in `test_acceptance_chain.py` and the guardrail
tests in `test_hypothesis_validation_guardrail.py`, not duplicating them.
"""
from __future__ import annotations

import pytest

from ..application import commands
from ..domain.entities import CustomerInsight, MarketSignal
from ..domain.errors import ProductIntelligenceNotFoundError, ProductIntelligenceValidationError


# ---------------------------------------------------------------------------
# confidence bounds — structural pydantic validation on the entity itself,
# independent of any application-layer command path.
# ---------------------------------------------------------------------------

def _entity_kwargs(**overrides):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    base = dict(
        id="insight-adversarial-1",
        created_at=now,
        updated_at=now,
        created_by="human-reviewer-1",
        tenant_scope="tenant-a",
        statement="statement",
        signal_id="signal-1",
    )
    base.update(overrides)
    return base


def test_confidence_below_zero_is_rejected():
    with pytest.raises(ProductIntelligenceValidationError):
        CustomerInsight(**_entity_kwargs(
            generated_by="ai:x", model_ref="m", prompt_use_case_version="v1", confidence=-0.01,
        ))


def test_confidence_above_one_is_rejected():
    with pytest.raises(ProductIntelligenceValidationError):
        CustomerInsight(**_entity_kwargs(
            generated_by="ai:x", model_ref="m", prompt_use_case_version="v1", confidence=1.01,
        ))


@pytest.mark.asyncio
async def test_confidence_below_zero_is_rejected_via_command(fake_repo, ai_context):
    signal = await commands.create_market_signal(fake_repo, ai_context.__class__(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
    ), raw_text="x")
    with pytest.raises(ProductIntelligenceValidationError):
        await commands.create_customer_insight(
            fake_repo, ai_context, signal_id=signal.id, statement="i",
            model_ref="m", prompt_use_case_version="v1", confidence=-0.01,
        )


@pytest.mark.asyncio
async def test_confidence_above_one_is_rejected_via_command(fake_repo, ai_context):
    signal = await commands.create_market_signal(fake_repo, ai_context.__class__(
        actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a",
    ), raw_text="x")
    with pytest.raises(ProductIntelligenceValidationError):
        await commands.create_customer_insight(
            fake_repo, ai_context, signal_id=signal.id, statement="i",
            model_ref="m", prompt_use_case_version="v1", confidence=1.01,
        )


# ---------------------------------------------------------------------------
# illegal state transition — REJECTED is terminal too, not just RETIRED
# (test_hypothesis_validation_guardrail.py only covers the RETIRED case).
# ---------------------------------------------------------------------------

async def _make_problem(repo, context):
    signal = await commands.create_market_signal(repo, context, raw_text="x")
    insight = await commands.create_customer_insight(repo, context, signal_id=signal.id, statement="i")
    opportunity = await commands.create_opportunity(repo, context, insight_id=insight.id, statement="o")
    return await commands.create_growth_problem(repo, context, opportunity_id=opportunity.id, symptom="p")


@pytest.mark.asyncio
async def test_rejected_hypothesis_cannot_be_validated(fake_repo, human_context):
    problem = await _make_problem(fake_repo, human_context)
    hypothesis = await commands.create_growth_hypothesis(fake_repo, human_context, problem_id=problem.id, statement="h")
    rejected = hypothesis.model_copy(update={"status": "REJECTED"})
    await fake_repo.save_growth_hypothesis(rejected)

    with pytest.raises(ProductIntelligenceValidationError):
        await commands.validate_growth_hypothesis(fake_repo, human_context, hypothesis_id=rejected.id, reason="trying anyway")


# ---------------------------------------------------------------------------
# blank / whitespace-only required text fields.
#
# NOTE: `domain/entities.py::_require_non_empty` already rejects empty and
# whitespace-only `raw_text` on `MarketSignal` today (independent of any
# Agent B work-in-progress), so this is expected to PASS, not to be a
# forward-looking assertion.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_market_signal_whitespace_only_raw_text_is_rejected(fake_repo, human_context):
    with pytest.raises(ProductIntelligenceValidationError):
        await commands.create_market_signal(fake_repo, human_context, raw_text="   ")


@pytest.mark.asyncio
async def test_market_signal_empty_raw_text_is_rejected(fake_repo, human_context):
    with pytest.raises(ProductIntelligenceValidationError):
        await commands.create_market_signal(fake_repo, human_context, raw_text="")


# ---------------------------------------------------------------------------
# transaction rollback semantics (sqlalchemy_repo only — fake_repo has no
# transaction concept to exercise here).
#
# Create a MarketSignal (succeeds, flushed), then attempt to create a
# CustomerInsight against a signal_id that does not exist — this must raise
# ProductIntelligenceNotFoundError *before* any insight row is inserted, and
# must not roll back / hide the already-created, already-committed signal.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_child_creation_does_not_roll_back_already_committed_parent(sqlalchemy_repo, human_context):
    signal = await commands.create_market_signal(sqlalchemy_repo, human_context, raw_text="already committed parent")
    await sqlalchemy_repo._session.commit()

    with pytest.raises(ProductIntelligenceNotFoundError):
        await commands.create_customer_insight(
            sqlalchemy_repo, human_context, signal_id="signal-does-not-exist", statement="orphan insight",
        )

    # The failed lookup must not have touched the already-committed signal.
    reloaded = await sqlalchemy_repo.load_market_signal(signal.id, human_context.tenant_scope)
    assert reloaded.id == signal.id
    assert reloaded.raw_text == "already committed parent"


@pytest.mark.asyncio
async def test_failed_child_creation_before_commit_can_be_rolled_back_without_losing_flushed_parent(
    sqlalchemy_repo, human_context,
):
    """Same idea, but without an intervening commit: create+flush a signal in
    the same session, then hit the NotFoundError on a bad signal_id for the
    insight, roll back, and confirm the signal is still there afterwards
    (it was flushed as part of `save_market_signal`, and a later rollback of
    an *unrelated failed statement* — here, just the lookup itself raising
    before any write — must not resurrect or lose it).
    """
    signal = await commands.create_market_signal(sqlalchemy_repo, human_context, raw_text="flushed but not yet committed")

    with pytest.raises(ProductIntelligenceNotFoundError):
        await commands.create_customer_insight(
            sqlalchemy_repo, human_context, signal_id="signal-does-not-exist", statement="orphan insight",
        )

    # No write was attempted for the insight (the parent load fails first),
    # so there is nothing to roll back on the insight side; the signal
    # created earlier in this same session must still be visible.
    reloaded = await sqlalchemy_repo.load_market_signal(signal.id, human_context.tenant_scope)
    assert reloaded.id == signal.id
