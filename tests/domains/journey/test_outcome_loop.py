from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.domains.journey.application.outcome_loop import (
    S05_S08_NODE_CONTRACTS,
    ActionFactStatus,
    ChallengeDecision,
    ChallengeReviewStatus,
    GrowthOutcomeLoop,
    OutcomeStatus,
    RecommendationStatus,
    ServiceCaseStatus,
    StoryVisibility,
)
from backend.domains.journey.domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)

FIXED_NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


def _loop() -> GrowthOutcomeLoop:
    return GrowthOutcomeLoop(now=lambda: FIXED_NOW)


def test_result_loop_has_l4_l5_contract_for_each_transition_and_locale_boundary() -> None:
    assert [item.node_id for item in S05_S08_NODE_CONTRACTS] == [
        "S07-N03",
        "S07-N05",
        "S08-N02",
        "S08-N03",
        "S09-N03",
        "S10-N01",
        "S08-N04",
    ]
    assert all(
        item.inputs and item.outputs and item.command and item.event
        for item in S05_S08_NODE_CONTRACTS
    )
    loop = GrowthOutcomeLoop(now=lambda: FIXED_NOW, locale="en-US")
    action = loop.record_action(
        tenant_id="tenant-a",
        family_id="family-a",
        plan_id="plan-90",
        task_id="task-locale",
        day_number=1,
        status=ActionFactStatus.PARTIAL,
        actor_id="parent-1",
        idempotency_key="locale-action",
    )
    assert action.locale == "en-US"
    assert loop.snapshot(tenant_id="tenant-a", family_id="family-a").locale == "en-US"


def _closed_review(loop: GrowthOutcomeLoop, *, tenant_id: str = "tenant-a"):
    for day in (1, 2):
        loop.record_action(
            tenant_id=tenant_id,
            family_id="family-a",
            plan_id="plan-90",
            task_id=f"task-{day}",
            day_number=day,
            status=ActionFactStatus.COMPLETED,
            actor_id="parent-1",
            idempotency_key=f"action-{day}",
            evidence_refs=(f"checkin-{day}",),
        )
    return loop.close_challenge(
        tenant_id=tenant_id,
        family_id="family-a",
        plan_id="plan-90",
        decision=ChallengeDecision.CONTINUE,
        actor_id="parent-1",
        idempotency_key="close-1",
    )


def _confirmed_outcome(loop: GrowthOutcomeLoop):
    review = _closed_review(loop)
    proposed = loop.propose_outcome(
        tenant_id="tenant-a",
        family_id="family-a",
        review_id=review.review_id,
        subject_ref="child-1",
        statement="孩子愿意在冲突后再次沟通",
        evidence_refs=("checkin-1",),
        actor_id="ai:principal",
        idempotency_key="outcome-proposal-1",
    )
    return loop.confirm_outcome(
        tenant_id="tenant-a",
        family_id="family-a",
        outcome_id=proposed.outcome_id,
        actor_id="parent-1",
        idempotency_key="outcome-confirm-1",
    )


def test_action_to_challenge_review_preserves_missing_days_without_a_score() -> None:
    loop = _loop()
    review = _closed_review(loop)

    assert review.status is ChallengeReviewStatus.ACCEPTED
    assert review.observed_days == (1, 2)
    assert review.missing_days == tuple(range(3, 22))
    assert review.limitations == ("MISSING_ACTION_DAYS_EXPLICIT",)
    projection = loop.snapshot(tenant_id="tenant-a", family_id="family-a")
    assert len(projection.actions) == 2
    assert not any(
        "score" in field.lower() or "rank" in field.lower()
        for field in projection.__dataclass_fields__
    )


def test_action_replay_is_idempotent_and_conflicting_retry_is_rejected() -> None:
    loop = _loop()
    first = loop.record_action(
        tenant_id="tenant-a",
        family_id="family-a",
        plan_id="plan-90",
        task_id="task-1",
        day_number=1,
        status=ActionFactStatus.COMPLETED,
        actor_id="parent-1",
        idempotency_key="same-key",
        evidence_refs=("checkin-1",),
    )
    assert (
        loop.record_action(
            tenant_id="tenant-a",
            family_id="family-a",
            plan_id="plan-90",
            task_id="task-1",
            day_number=1,
            status=ActionFactStatus.COMPLETED,
            actor_id="parent-1",
            idempotency_key="same-key",
            evidence_refs=("checkin-1",),
        )
        == first
    )
    with pytest.raises(JourneyConflictError, match="idempotency_conflict"):
        loop.record_action(
            tenant_id="tenant-a",
            family_id="family-a",
            plan_id="plan-90",
            task_id="task-1",
            day_number=1,
            status=ActionFactStatus.SKIPPED,
            actor_id="parent-1",
            idempotency_key="same-key",
            evidence_refs=(),
        )


def test_outcome_requires_evidence_and_human_confirmation_before_recommendation() -> None:
    loop = _loop()
    review = _closed_review(loop)
    with pytest.raises(JourneyValidationError, match="outcome_evidence_required"):
        loop.propose_outcome(
            tenant_id="tenant-a",
            family_id="family-a",
            review_id=review.review_id,
            subject_ref="child-1",
            statement="没有来源的结论",
            evidence_refs=(),
            actor_id="ai:principal",
            idempotency_key="missing-evidence",
        )
    pending = loop.propose_outcome(
        tenant_id="tenant-a",
        family_id="family-a",
        review_id=review.review_id,
        subject_ref="child-1",
        statement="孩子愿意在冲突后再次沟通",
        evidence_refs=("checkin-1",),
        actor_id="ai:principal",
        idempotency_key="outcome-proposal-1",
    )
    assert pending.status is OutcomeStatus.PENDING
    with pytest.raises(JourneyConflictError, match="recommendation_requires_confirmed_outcomes"):
        loop.draft_recommendation(
            tenant_id="tenant-a",
            family_id="family-a",
            outcome_ids=(pending.outcome_id,),
            candidate_refs=("service:family-dialogue",),
            purpose="growth_support",
            rationale="基于已记录的行动证据",
            actor_id="ai:principal",
            idempotency_key="recommendation-before-confirm",
        )
    with pytest.raises(JourneyForbiddenError, match="human_confirmation_required"):
        loop.confirm_outcome(
            tenant_id="tenant-a",
            family_id="family-a",
            outcome_id=pending.outcome_id,
            actor_id="ai:principal",
            idempotency_key="ai-confirm",
        )


def test_confirmed_result_creates_private_story_and_draft_recommendation_then_case() -> None:
    loop = _loop()
    outcome = _confirmed_outcome(loop)
    private_story = loop.create_story(
        tenant_id="tenant-a",
        family_id="family-a",
        outcome_ids=(outcome.outcome_id,),
        title="我们又开始好好说话",
        body="这是家庭自己的记录",
        actor_id="parent-1",
        idempotency_key="story-private",
    )
    assert private_story.visibility is StoryVisibility.PRIVATE
    with pytest.raises(JourneyForbiddenError, match="shared_story_requires_explicit_consent"):
        loop.create_story(
            tenant_id="tenant-a",
            family_id="family-a",
            outcome_ids=(outcome.outcome_id,),
            title="公开故事",
            body="没有授权不能公开",
            actor_id="parent-1",
            idempotency_key="story-shared-no-consent",
            visibility=StoryVisibility.SHARED,
        )
    shared_story = loop.create_story(
        tenant_id="tenant-a",
        family_id="family-a",
        outcome_ids=(outcome.outcome_id,),
        title="公开故事",
        body="家庭明确授权后的故事",
        actor_id="parent-1",
        idempotency_key="story-shared",
        visibility=StoryVisibility.SHARED,
        story_consent_ref="consent:story:v1",
    )
    recommendation = loop.draft_recommendation(
        tenant_id="tenant-a",
        family_id="family-a",
        outcome_ids=(outcome.outcome_id,),
        candidate_refs=("service:family-dialogue", "service:coach-session"),
        purpose="growth_support",
        rationale="来自家庭已确认的行动结果",
        actor_id="ai:principal",
        idempotency_key="recommendation-1",
        limitations=("AI_DRAFT_REQUIRES_FAMILY_DECISION",),
    )
    assert recommendation.status is RecommendationStatus.DRAFT
    case = loop.accept_recommendation(
        tenant_id="tenant-a",
        family_id="family-a",
        recommendation_id=recommendation.recommendation_id,
        candidate_ref="service:family-dialogue",
        actor_id="parent-1",
        idempotency_key="accept-recommendation-1",
    )
    assert case.status is ServiceCaseStatus.REQUESTED
    assert (
        loop.accept_recommendation(
            tenant_id="tenant-a",
            family_id="family-a",
            recommendation_id=recommendation.recommendation_id,
            candidate_ref="service:family-dialogue",
            actor_id="parent-1",
            idempotency_key="accept-recommendation-1",
        )
        == case
    )
    loop.withdraw_story(
        tenant_id="tenant-a",
        family_id="family-a",
        story_id=shared_story.story_id,
        actor_id="parent-1",
        idempotency_key="withdraw-story",
    )
    projection = loop.build_annual_review(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="family-api",
        idempotency_key="annual-1",
        include_story_ids=(private_story.story_id, shared_story.story_id),
    )
    assert projection.outcome_ids == (outcome.outcome_id,)
    assert projection.story_ids == (private_story.story_id,)
    assert "score" not in repr(projection).lower()


def test_delivery_evidence_is_required_before_explicit_renewal() -> None:
    loop = _loop()
    outcome = _confirmed_outcome(loop)
    recommendation = loop.draft_recommendation(
        tenant_id="tenant-a",
        family_id="family-a",
        outcome_ids=(outcome.outcome_id,),
        candidate_refs=("service:family-dialogue",),
        purpose="growth_support",
        rationale="家庭可以选择的下一步",
        actor_id="ai:principal",
        idempotency_key="recommendation-1",
    )
    case = loop.accept_recommendation(
        tenant_id="tenant-a",
        family_id="family-a",
        recommendation_id=recommendation.recommendation_id,
        candidate_ref="service:family-dialogue",
        actor_id="parent-1",
        idempotency_key="accept-1",
    )
    with pytest.raises(JourneyConflictError, match="renewal_requires_delivered_service"):
        loop.request_renewal(
            tenant_id="tenant-a",
            family_id="family-a",
            case_id=case.case_id,
            candidate_ref=case.selected_candidate_ref,
            actor_id="parent-1",
            idempotency_key="renewal-before-delivery",
        )
    delivered = loop.record_delivery(
        tenant_id="tenant-a",
        family_id="family-a",
        case_id=case.case_id,
        evidence_refs=("delivery:session-1",),
        actor_id="coach-1",
        idempotency_key="delivery-1",
    )
    assert delivered.status is ServiceCaseStatus.DELIVERED
    annual = loop.build_annual_review(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="family-api",
        idempotency_key="annual-1",
    )
    renewal = loop.request_renewal(
        tenant_id="tenant-a",
        family_id="family-a",
        case_id=case.case_id,
        candidate_ref=case.selected_candidate_ref,
        annual_projection_id=annual.projection_id,
        actor_id="parent-1",
        idempotency_key="renewal-1",
    )
    assert renewal.status.value == "REQUESTED"
    assert (
        loop.request_renewal(
            tenant_id="tenant-a",
            family_id="family-a",
            case_id=case.case_id,
            candidate_ref=case.selected_candidate_ref,
            annual_projection_id=annual.projection_id,
            actor_id="parent-1",
            idempotency_key="renewal-1",
        )
        == renewal
    )


def test_tenant_scope_isolation_and_deletion_refs_are_explicit() -> None:
    loop = _loop()
    outcome = _confirmed_outcome(loop)
    with pytest.raises(JourneyForbiddenError, match="family_tenant_scope_violation"):
        loop.confirm_outcome(
            tenant_id="tenant-b",
            family_id="family-a",
            outcome_id=outcome.outcome_id,
            actor_id="parent-1",
            idempotency_key="cross-tenant-confirm",
        )
    with pytest.raises(JourneyNotFoundError, match="outcome_not_found"):
        loop.draft_recommendation(
            tenant_id="tenant-a",
            family_id="family-a",
            outcome_ids=("missing",),
            candidate_refs=("service:family-dialogue",),
            purpose="growth_support",
            rationale="不存在的结果不能进入推荐",
            actor_id="ai:principal",
            idempotency_key="missing-outcome",
        )
    story = loop.create_story(
        tenant_id="tenant-a",
        family_id="family-a",
        outcome_ids=(outcome.outcome_id,),
        title="删除测试",
        body="撤回后仍需要删除引用",
        actor_id="parent-1",
        idempotency_key="story-1",
    )
    recommendation = loop.draft_recommendation(
        tenant_id="tenant-a",
        family_id="family-a",
        outcome_ids=(outcome.outcome_id,),
        candidate_refs=("service:family-dialogue",),
        purpose="growth_support",
        rationale="家庭确认结果后的下一步草案",
        actor_id="ai:principal",
        idempotency_key="recommendation-1",
    )
    assert set(loop.deletion_refs(tenant_id="tenant-a", family_id="family-a")) >= {
        outcome.deletion_ref,
        story.deletion_ref,
        recommendation.deletion_ref,
    }
