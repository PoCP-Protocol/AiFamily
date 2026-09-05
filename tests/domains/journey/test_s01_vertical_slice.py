from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.domains.journey.application.outcome_loop import (
    ActionFactStatus,
    ChallengeDecision,
    GrowthOutcomeLoop,
)
from backend.domains.journey.application.s01_vertical_slice import (
    AssessmentSignal,
    AuditEventName,
    HypothesisDecision,
    HypothesisStatus,
    InMemoryAssessmentSignalPort,
    S01VerticalSlice,
)
from backend.domains.journey.domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)
from backend.platform.consent import (
    ConsentGrant,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)

NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
SESSION = "123e4567-e89b-12d3-a456-426614174000"


def _loader(state: dict[str, ConsentStatus]):
    def load(subject: str, purpose):
        return (
            ConsentGrant(
                consent_id=f"consent:{purpose.value}",
                subject_person_id=subject,
                guardian_person_id="parent-1",
                purpose=purpose,
                status=state["status"],
                granted_at=NOW,
                expires_at=NOW + timedelta(days=30),
                subject_age=SubjectAge(years=18),
                guardian_relation=GuardianRelation.GUARDIAN,
            ),
        )

    return load


def _signal(summary: str = "亲子沟通出现一个可观察线索") -> AssessmentSignal:
    return AssessmentSignal(
        signal_id="signal-1",
        tenant_id="tenant-a",
        family_id="family-a",
        subject_ref="child-1",
        assessment_session_id=SESSION,
        evidence_refs=("assessment-evidence-1",),
        summary=summary,
        captured_at=NOW,
        locale="zh-CN",
    )


def _slice(state: dict[str, ConsentStatus] | None = None) -> S01VerticalSlice:
    state = state or {"status": ConsentStatus.GRANTED}
    loader = _loader(state)
    port = InMemoryAssessmentSignalPort((_signal(),))
    loop = GrowthOutcomeLoop(now=lambda: NOW, consent_loader=loader)
    return S01VerticalSlice(
        signal_port=port,
        outcome_loop=loop,
        consent_loader=loader,
        now=lambda: NOW,
    )


def test_signal_to_hypothesis_requires_uuid_consent_and_keeps_ai_draft() -> None:
    slice_ = _slice()
    signal = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-accept-1",
        correlation_id="corr-1",
    )
    hypothesis = slice_.draft_hypothesis(
        signal=signal,
        actor_id="ai:principal",
        idempotency_key="hypothesis-1",
        correlation_id="corr-1",
    )
    assert hypothesis.status is HypothesisStatus.PROPOSED
    assert hypothesis.source_refs == signal.evidence_refs
    assert "NOT_DIAGNOSIS" in hypothesis.limitations
    assert not any(token in repr(hypothesis).lower() for token in ("score", "rank", "percentile"))
    assert [event.name for event in slice_.audit_events] == [
        AuditEventName.SIGNAL_ACCEPTED,
        AuditEventName.PERSPECTIVE_DRAFTED,
        AuditEventName.HYPOTHESIS_DRAFTED,
    ]


def test_signal_and_hypothesis_idempotency_replay_and_conflict() -> None:
    slice_ = _slice()
    first = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-1",
        correlation_id="corr-1",
    )
    assert (
        slice_.accept_signal(
            tenant_id="tenant-a",
            family_id="family-a",
            assessment_session_id=SESSION,
            actor_id="parent-1",
            idempotency_key="signal-1",
            correlation_id="corr-2",
        )
        == first
    )
    with pytest.raises(JourneyConflictError, match="idempotency_conflict"):
        slice_.accept_signal(
            tenant_id="tenant-a",
            family_id="family-a",
            assessment_session_id=SESSION,
            actor_id="parent-2",
            idempotency_key="signal-1",
            correlation_id="corr-1",
        )
    hypothesis = slice_.draft_hypothesis(
        signal=first,
        actor_id="ai:principal",
        idempotency_key="hypothesis-1",
        correlation_id="corr-1",
    )
    assert (
        slice_.draft_hypothesis(
            signal=first,
            actor_id="ai:principal",
            idempotency_key="hypothesis-1",
            correlation_id="corr-2",
        )
        == hypothesis
    )


def test_human_hypothesis_decision_issues_intent_then_records_action_and_readback() -> None:
    slice_ = _slice()
    signal = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-1",
        correlation_id="corr-1",
    )
    hypothesis = slice_.draft_hypothesis(
        signal=signal,
        actor_id="ai:principal",
        idempotency_key="hypothesis-1",
        correlation_id="corr-1",
    )
    with pytest.raises(JourneyForbiddenError, match="human_confirmation_required"):
        slice_.decide_hypothesis(
            tenant_id="tenant-a",
            family_id="family-a",
            hypothesis_id=hypothesis.hypothesis_id,
            decision=HypothesisDecision.CONFIRM,
            actor_id="ai:principal",
            idempotency_key="decision-ai",
            correlation_id="corr-1",
        )
    intent = slice_.decide_hypothesis(
        tenant_id="tenant-a",
        family_id="family-a",
        hypothesis_id=hypothesis.hypothesis_id,
        decision=HypothesisDecision.CONFIRM,
        actor_id="parent-1",
        idempotency_key="decision-1",
        correlation_id="corr-1",
    )
    assert intent is not None
    assert intent.boundary == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
    assert (
        slice_.decide_hypothesis(
            tenant_id="tenant-a",
            family_id="family-a",
            hypothesis_id=hypothesis.hypothesis_id,
            decision=HypothesisDecision.CONFIRM,
            actor_id="parent-1",
            idempotency_key="decision-1",
            correlation_id="corr-2",
        )
        == intent
    )
    assert (
        slice_.decide_hypothesis(
            tenant_id="tenant-a",
            family_id="family-a",
            hypothesis_id=hypothesis.hypothesis_id,
            decision=HypothesisDecision.CONFIRM,
            actor_id="parent-1",
            idempotency_key="decision-retry-with-new-key",
            correlation_id="corr-3",
        )
        == intent
    )
    action = slice_.record_today_action(
        tenant_id="tenant-a",
        family_id="family-a",
        intent_id=intent.intent_id,
        plan_id="plan-90",
        task_ref=intent.next_task_ref,
        actor_id="parent-1",
        idempotency_key="action-1",
        correlation_id="corr-1",
        status=ActionFactStatus.COMPLETED,
        evidence_refs=("checkin-1",),
    )
    assert (
        slice_.record_today_action(
            tenant_id="tenant-a",
            family_id="family-a",
            intent_id=intent.intent_id,
            plan_id="plan-90",
            task_ref=intent.next_task_ref,
            actor_id="parent-1",
            idempotency_key="action-1",
            correlation_id="corr-2",
            status=ActionFactStatus.COMPLETED,
            evidence_refs=("checkin-1",),
        )
        == action
    )
    readback = slice_.readback(
        tenant_id="tenant-a",
        family_id="family-a",
        plan_id="plan-90",
        actor_id="parent-1",
        idempotency_key="readback-1",
        correlation_id="corr-1",
    )
    assert readback.action_ids == (action.action_id,)
    assert "PROCESS_NOT_OUTCOME" in readback.limitations
    review = slice_.close_challenge(
        tenant_id="tenant-a",
        family_id="family-a",
        plan_id="plan-90",
        decision=ChallengeDecision.ADJUST,
        actor_id="parent-1",
        idempotency_key="review-1",
        correlation_id="corr-1",
    )
    assert (
        slice_.close_challenge(
            tenant_id="tenant-a",
            family_id="family-a",
            plan_id="plan-90",
            decision=ChallengeDecision.ADJUST,
            actor_id="parent-1",
            idempotency_key="review-1",
            correlation_id="corr-2",
        )
        == review
    )


def test_dismissal_is_idempotent_and_does_not_issue_intent() -> None:
    slice_ = _slice()
    signal = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-1",
        correlation_id="corr-1",
    )
    hypothesis = slice_.draft_hypothesis(
        signal=signal,
        actor_id="ai:principal",
        idempotency_key="hypothesis-1",
        correlation_id="corr-1",
    )
    assert (
        slice_.decide_hypothesis(
            tenant_id="tenant-a",
            family_id="family-a",
            hypothesis_id=hypothesis.hypothesis_id,
            decision=HypothesisDecision.DISMISS,
            actor_id="parent-1",
            idempotency_key="dismiss-1",
            correlation_id="corr-1",
        )
        is None
    )
    assert (
        slice_.decide_hypothesis(
            tenant_id="tenant-a",
            family_id="family-a",
            hypothesis_id=hypothesis.hypothesis_id,
            decision=HypothesisDecision.DISMISS,
            actor_id="parent-1",
            idempotency_key="dismiss-1",
            correlation_id="corr-2",
        )
        is None
    )
    assert slice_._hypotheses[hypothesis.hypothesis_id].status is HypothesisStatus.DISMISSED


def test_hypothesis_draft_rejects_unaccepted_or_tampered_signal() -> None:
    slice_ = _slice()
    unaccepted = _signal()
    with pytest.raises(JourneyNotFoundError, match="assessment_signal_not_accepted"):
        slice_.draft_hypothesis(
            signal=unaccepted,
            actor_id="ai:principal",
            idempotency_key="unaccepted-hypothesis",
            correlation_id="corr-unaccepted",
        )
    accepted = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-tamper",
        correlation_id="corr-tamper",
    )
    tampered = AssessmentSignal(
        **{**accepted.__dict__, "summary": "被篡改的观察"},
    )
    with pytest.raises(JourneyConflictError, match="assessment_signal_snapshot_conflict"):
        slice_.draft_hypothesis(
            signal=tampered,
            actor_id="ai:principal",
            idempotency_key="tampered-hypothesis",
            correlation_id="corr-tamper",
        )


def test_cross_tenant_consent_revoke_expiry_and_invalid_uuid_fail_closed() -> None:
    state = {"status": ConsentStatus.GRANTED}
    slice_ = _slice(state)
    with pytest.raises(JourneyValidationError, match="assessment_session_id_must_be_uuid"):
        slice_.accept_signal(
            tenant_id="tenant-a",
            family_id="family-a",
            assessment_session_id="not-a-uuid",
            actor_id="parent-1",
            idempotency_key="bad-uuid",
            correlation_id="corr-1",
        )
    with pytest.raises(JourneyNotFoundError, match="submitted_assessment_signal_not_found"):
        slice_.accept_signal(
            tenant_id="tenant-b",
            family_id="family-b",
            assessment_session_id=SESSION,
            actor_id="parent-1",
            idempotency_key="cross-tenant",
            correlation_id="corr-1",
        )
    signal = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-1",
        correlation_id="corr-1",
    )
    state["status"] = ConsentStatus.WITHDRAWN
    with pytest.raises(JourneyForbiddenError, match="consent_required"):
        slice_.draft_hypothesis(
            signal=signal,
            actor_id="ai:principal",
            idempotency_key="hypothesis-revoked",
            correlation_id="corr-2",
        )


def test_forbidden_score_payload_and_outbox_ready_audit_envelope() -> None:
    state = {"status": ConsentStatus.GRANTED}
    loader = _loader(state)
    port = InMemoryAssessmentSignalPort((_signal("家庭 score 应该越高越好"),))
    slice_ = S01VerticalSlice(
        signal_port=port,
        outcome_loop=GrowthOutcomeLoop(now=lambda: NOW, consent_loader=loader),
        consent_loader=loader,
        now=lambda: NOW,
    )
    with pytest.raises(JourneyValidationError, match="forbidden_score_or_rank_field"):
        slice_.accept_signal(
            tenant_id="tenant-a",
            family_id="family-a",
            assessment_session_id=SESSION,
            actor_id="parent-1",
            idempotency_key="forbidden-score",
            correlation_id="corr-1",
        )
    signal = _signal()
    port.add(signal)
    accepted = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-2",
        correlation_id="corr-2",
    )
    assert accepted.signal_id == "signal-1"
    assert all(event.tenant_id == "tenant-a" for event in slice_.audit_events)
    assert all(event.correlation_id for event in slice_.audit_events)


def test_s01_deletion_refs_cover_projections_audit_and_delegated_loop() -> None:
    slice_ = _slice()
    signal = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-delete",
        correlation_id="corr-delete",
    )
    hypothesis = slice_.draft_hypothesis(
        signal=signal,
        actor_id="ai:principal",
        idempotency_key="hypothesis-delete",
        correlation_id="corr-delete",
    )
    intent = slice_.decide_hypothesis(
        tenant_id="tenant-a",
        family_id="family-a",
        hypothesis_id=hypothesis.hypothesis_id,
        decision=HypothesisDecision.CONFIRM,
        actor_id="parent-1",
        idempotency_key="decision-delete",
        correlation_id="corr-delete",
    )
    assert intent is not None
    action = slice_.record_today_action(
        tenant_id="tenant-a",
        family_id="family-a",
        intent_id=intent.intent_id,
        plan_id="plan-delete",
        task_ref=intent.next_task_ref,
        actor_id="parent-1",
        idempotency_key="action-delete",
        correlation_id="corr-delete",
    )
    readback = slice_.readback(
        tenant_id="tenant-a",
        family_id="family-a",
        plan_id="plan-delete",
        actor_id="parent-1",
        idempotency_key="readback-delete",
        correlation_id="corr-delete",
    )
    slice_.close_challenge(
        tenant_id="tenant-a",
        family_id="family-a",
        plan_id="plan-delete",
        decision=ChallengeDecision.CONTINUE,
        actor_id="parent-1",
        idempotency_key="review-delete",
        correlation_id="corr-delete",
    )

    refs = slice_.deletion_refs(tenant_id="tenant-a", family_id="family-a")
    assert f"assessment-signal:tenant-a:family-a:{signal.signal_id}" in refs
    assert f"s01:hypothesis:tenant-a:family-a:{hypothesis.hypothesis_id}" in refs
    assert f"s01:intent:tenant-a:family-a:{intent.intent_id}" in refs
    assert f"s01:task:tenant-a:family-a:{intent.next_task_ref}" in refs
    assert f"s01:readback:tenant-a:family-a:{readback.readback_id}" in refs
    assert f"action:tenant-a:family-a:{action.task_id}" in refs
    assert any(ref.startswith("s01:audit:tenant-a:family-a:") for ref in refs)
    assert all("tenant-b" not in ref for ref in refs)


def test_expired_consent_is_denied_before_ai_draft() -> None:
    state = {"status": ConsentStatus.GRANTED}
    slice_ = _slice(state)
    signal = slice_.accept_signal(
        tenant_id="tenant-a",
        family_id="family-a",
        assessment_session_id=SESSION,
        actor_id="parent-1",
        idempotency_key="signal-expired",
        correlation_id="corr-expired",
    )
    state["status"] = ConsentStatus.EXPIRED
    with pytest.raises(JourneyForbiddenError, match="consent_required"):
        slice_.draft_hypothesis(
            signal=signal,
            actor_id="ai:principal",
            idempotency_key="hypothesis-expired",
            correlation_id="corr-expired",
        )
