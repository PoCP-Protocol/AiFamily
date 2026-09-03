from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceNode,
    ExperienceProvenance,
    ExperienceScope,
    FeedbackSignal,
    FeedbackSignalType,
    FeedbackTargetType,
    ProvenanceKind,
    RecommendationDecision,
)
from backend.intelligence.experience.gateway import ExperienceGateway
from backend.platform.idempotency.keys import IdempotencyKey


def _scope(
    *,
    tenant_id: str = "tenant-a",
    region_id: str = "CN",
    family_id: str = "family-a",
    subjects: tuple[str, ...] = ("child-a",),
    purpose: str = "growth_support",
) -> ExperienceScope:
    return ExperienceScope(
        global_id=f"global-{tenant_id}-{family_id}",
        tenant_id=tenant_id,
        region_id=region_id,
        family_id=family_id,
        subject_ids=subjects,
        purpose=purpose,
        consent_version="consent.v1",
        consent_granted=True,
        data_class="OPERATIONAL_TEXT",  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete-001", "experience.v1"),
        correlation_id="corr-001",
        causation_id="cause-001",
    )


def _provenance() -> ExperienceProvenance:
    return ExperienceProvenance(
        provenance_ref="provenance-001",
        source_refs=("mobile:UI-03",),
        kind=ProvenanceKind.USER,
        policy_version="experience-policy.v1",
    )


def _event(
    *,
    event_id: str = "event-001",
    scope: ExperienceScope | None = None,
    occurred_at: datetime | None = None,
    event_type: ExperienceEventType = ExperienceEventType.CONTENT_SHOWN,
) -> ExperienceEvent:
    return ExperienceEvent(
        event_id=event_id,
        event_type=event_type,
        node=ExperienceNode.N1,
        scope=scope or _scope(),
        idempotency_key=IdempotencyKey((scope or _scope()).tenant_id, event_id),
        provenance=_provenance(),
        actor_id="guardian-a",
        occurred_at=occurred_at or datetime.now(UTC),
    )


def _decision(*, decision_id: str = "decision-001") -> RecommendationDecision:
    scope = _scope()
    return RecommendationDecision(
        decision_id=decision_id,
        request_id=f"request-{decision_id}",
        scope=scope,
        idempotency_key=IdempotencyKey(scope.tenant_id, decision_id),
        provenance=_provenance(),
        strategy_version="curator.v1",
        candidate_ids=("content-001",),
    )


def _feedback(*, feedback_id: str = "feedback-001", target_id: str = "event-001") -> FeedbackSignal:
    scope = _scope()
    return FeedbackSignal(
        feedback_id=feedback_id,
        target_type=FeedbackTargetType.EVENT,
        target_id=target_id,
        signal=FeedbackSignalType.HELPFUL,
        scope=scope,
        idempotency_key=IdempotencyKey(scope.tenant_id, feedback_id),
        provenance=_provenance(),
    )


def test_gateway_unifies_records_and_returns_a_sorted_scoped_timeline() -> None:
    gateway = ExperienceGateway()
    now = datetime.now(UTC)
    gateway.record_event(_event(event_id="event-old", occurred_at=now - timedelta(minutes=1)))
    gateway.record_event(_event(event_id="event-new", occurred_at=now))
    decision = gateway.publish_decision(_decision())
    gateway.record_feedback(_feedback(target_id="event-new"))

    timeline = gateway.timeline(_scope())

    assert tuple(type(record) for record in timeline.records) == (
        ExperienceEvent,
        ExperienceEvent,
        RecommendationDecision,
        FeedbackSignal,
    )
    assert timeline.records[0] == gateway.get_target("event-old", _scope())
    assert timeline.records[1] == gateway.get_target("event-new", _scope())
    assert timeline.records[2] == decision
    assert len(timeline.events) == 2
    assert timeline.decisions == (decision,)
    assert len(timeline.feedback) == 1


def test_gateway_replay_is_idempotent_but_key_reuse_with_new_payload_is_rejected() -> None:
    gateway = ExperienceGateway()
    first = gateway.record_event(_event())
    replay = gateway.record_event(_event())

    assert replay is first
    assert len(gateway.timeline(_scope()).events) == 1

    conflicting = _event(event_id="event-conflict")
    conflicting = ExperienceEvent(
        event_id=conflicting.event_id,
        event_type=ExperienceEventType.ACTION_STARTED,
        node=conflicting.node,
        scope=conflicting.scope,
        idempotency_key=first.idempotency_key,
        provenance=conflicting.provenance,
        actor_id=conflicting.actor_id,
    )
    with pytest.raises(ExperienceContractError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
        gateway.record_event(conflicting)


def test_feedback_requires_an_existing_same_type_target() -> None:
    gateway = ExperienceGateway()
    with pytest.raises(ExperienceContractError, match="EXPERIENCE_TARGET_NOT_FOUND"):
        gateway.record_feedback(_feedback())

    gateway.publish_decision(_decision())
    wrong_type = _feedback(target_id="decision-001")
    with pytest.raises(ExperienceContractError, match="FEEDBACK_TARGET_TYPE_MISMATCH"):
        gateway.record_feedback(wrong_type)


def test_feedback_cannot_bind_across_tenant_or_action_proposal_without_registration() -> None:
    gateway = ExperienceGateway()
    gateway.record_event(_event())

    other_scope = _scope(tenant_id="tenant-b", family_id="family-b")
    cross_tenant = FeedbackSignal(
        feedback_id="feedback-cross",
        target_type=FeedbackTargetType.EVENT,
        target_id="event-001",
        signal=FeedbackSignalType.HELPFUL,
        scope=other_scope,
        idempotency_key=IdempotencyKey("tenant-b", "feedback-cross"),
        provenance=_provenance(),
    )
    with pytest.raises(ExperienceContractError, match="EXPERIENCE_TARGET_NOT_FOUND"):
        gateway.record_feedback(cross_tenant)

    action_feedback = FeedbackSignal(
        feedback_id="feedback-action",
        target_type=FeedbackTargetType.ACTION_PROPOSAL,
        target_id="action-001",
        signal=FeedbackSignalType.ACCEPTED,
        scope=_scope(),
        idempotency_key=IdempotencyKey("tenant-a", "feedback-action"),
        provenance=_provenance(),
    )
    with pytest.raises(ExperienceContractError, match="ACTION_PROPOSAL_TARGET_NOT_REGISTERED"):
        gateway.record_feedback(action_feedback)


def test_timeline_does_not_join_region_or_subject_scopes_and_honors_limit() -> None:
    gateway = ExperienceGateway()
    gateway.record_event(_event(event_id="event-1"))
    gateway.record_event(_event(event_id="event-2"))
    gateway.record_event(_event(event_id="event-eu", scope=_scope(region_id="EU")))
    gateway.record_event(_event(event_id="event-child-b", scope=_scope(subjects=("child-b",))))

    timeline = gateway.timeline(_scope(), limit=1)
    assert tuple(event.event_id for event in timeline.events) == ("event-2",)
    assert gateway.timeline(_scope(region_id="EU")).events[0].event_id == "event-eu"
    assert gateway.timeline(_scope(subjects=("child-b",))).events[0].event_id == "event-child-b"

    with pytest.raises(ValueError, match="non-negative"):
        gateway.timeline(_scope(), limit=-1)
