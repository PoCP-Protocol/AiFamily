"""Executable synthetic tests for human moderation and the stop switch."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poc.standalone_live_moderation_sandbox.moderation import (
    SANDBOX_SOURCE,
    ActorType,
    InMemoryAuditOutboxFixture,
    LiveSessionFixture,
    ModerationAction,
    ModerationBoundaryError,
    ModerationIdempotencyConflict,
    ModerationRejected,
    ModerationScopeViolation,
    ReportStatus,
    SandboxModerator,
    ScopedActor,
    SessionState,
)

NOW = datetime(2026, 8, 30, 22, 30, tzinfo=UTC)
ADULT = ScopedActor("tenant.synthetic", "family.synthetic", "adult.1", ActorType.ADULT_VIEWER)
OTHER_ADULT = ScopedActor("tenant.synthetic", "family.other", "adult.2", ActorType.ADULT_VIEWER)
MODERATOR = ScopedActor(
    "tenant.synthetic", "family.synthetic", "moderator.1", ActorType.HUMAN_MODERATOR
)
AI = ScopedActor("tenant.synthetic", "family.synthetic", "agent.1", ActorType.AI_AGENT)
CHILD = ScopedActor("tenant.synthetic", "family.synthetic", "child.1", ActorType.CHILD)


def make_moderator() -> tuple[SandboxModerator, InMemoryAuditOutboxFixture]:
    audit = InMemoryAuditOutboxFixture()
    moderator = SandboxModerator(audit_outbox=audit)
    moderator.register_session(
        LiveSessionFixture(
            tenant_id="tenant.synthetic",
            family_id="family.synthetic",
            session_ref="live.synthetic.1",
        )
    )
    return moderator, audit


def test_report_is_pending_until_human_decision_and_stop_is_audited() -> None:
    moderator, audit = make_moderator()
    report = moderator.submit_report(
        session_ref="live.synthetic.1",
        reporter=ADULT,
        report_ref="report.1",
        reason="疑似不当内容，等待人工核验",
    )
    assert report.status is ReportStatus.PENDING
    assert len(audit.commits) == 0

    decided = moderator.review_report(
        report_ref="report.1",
        moderator=MODERATOR,
        action=ModerationAction.STOP_SESSION,
        decision_key="decision.1",
        reason="人工审核确认，触发停止展示",
        occurred_at=NOW,
    )

    assert decided.status is ReportStatus.STOPPED
    assert len(audit.commits) == 1
    assert audit.commits[0][0].action == "moderation.stop_session"


def test_dismiss_keeps_session_live_and_is_human_audited() -> None:
    moderator, audit = make_moderator()
    moderator.submit_report(
        session_ref="live.synthetic.1",
        reporter=ADULT,
        report_ref="report.dismiss",
        reason="需要核验",
    )
    decided = moderator.review_report(
        report_ref="report.dismiss",
        moderator=MODERATOR,
        action=ModerationAction.DISMISS,
        decision_key="decision.dismiss",
        reason="人工复核未发现违规",
        occurred_at=NOW,
    )
    assert decided.status is ReportStatus.DISMISSED
    assert audit.commits[0][0].action == "moderation.dismiss"


def test_report_does_not_auto_stop_and_replay_is_idempotent() -> None:
    moderator, audit = make_moderator()
    moderator.submit_report(
        session_ref="live.synthetic.1",
        reporter=ADULT,
        report_ref="report.replay",
        reason="等待人工处理",
    )
    first = moderator.review_report(
        report_ref="report.replay",
        moderator=MODERATOR,
        action=ModerationAction.STOP_SESSION,
        decision_key="decision.replay",
        reason="确认停止",
        occurred_at=NOW,
    )
    second = moderator.review_report(
        report_ref="report.replay",
        moderator=MODERATOR,
        action=ModerationAction.STOP_SESSION,
        decision_key="decision.replay",
        reason="重复请求",
        occurred_at=NOW,
    )
    assert second == first
    assert len(audit.commits) == 1


def test_scope_child_ai_and_non_human_actions_fail_closed() -> None:
    moderator, _ = make_moderator()
    with pytest.raises(ModerationScopeViolation):
        moderator.submit_report(
            session_ref="live.synthetic.1",
            reporter=OTHER_ADULT,
            report_ref="report.scope",
            reason="跨家庭",
        )
    with pytest.raises(ModerationRejected):
        moderator.submit_report(
            session_ref="live.synthetic.1",
            reporter=CHILD,
            report_ref="report.child",
            reason="儿童不能公开互动",
        )
    moderator.submit_report(
        session_ref="live.synthetic.1",
        reporter=ADULT,
        report_ref="report.ai",
        reason="等待人工",
    )
    with pytest.raises(ModerationRejected):
        moderator.review_report(
            report_ref="report.ai",
            moderator=AI,
            action=ModerationAction.STOP_SESSION,
            decision_key="decision.ai",
            reason="AI 不得自动停止",
            occurred_at=NOW,
        )


def test_decision_key_conflict_and_atomic_failure_do_not_change_state() -> None:
    moderator, audit = make_moderator()
    moderator.submit_report(
        session_ref="live.synthetic.1",
        reporter=ADULT,
        report_ref="report.conflict",
        reason="等待人工",
    )
    moderator.review_report(
        report_ref="report.conflict",
        moderator=MODERATOR,
        action=ModerationAction.DISMISS,
        decision_key="decision.conflict",
        reason="人工驳回",
        occurred_at=NOW,
    )
    with pytest.raises(ModerationIdempotencyConflict):
        moderator.review_report(
            report_ref="report.conflict",
            moderator=MODERATOR,
            action=ModerationAction.STOP_SESSION,
            decision_key="decision.conflict",
            reason="冲突动作",
            occurred_at=NOW,
        )

    second, second_audit = make_moderator()
    second.submit_report(
        session_ref="live.synthetic.1",
        reporter=ADULT,
        report_ref="report.failure",
        reason="等待人工",
    )
    second_audit.fail_next_commit = True
    with pytest.raises(RuntimeError, match="commit failure"):
        second.review_report(
            report_ref="report.failure",
            moderator=MODERATOR,
            action=ModerationAction.STOP_SESSION,
            decision_key="decision.failure",
            reason="模拟审计失败",
            occurred_at=NOW,
        )
    assert second._sessions["live.synthetic.1"].state is SessionState.LIVE
    assert second._reports["report.failure"].status is ReportStatus.PENDING
    assert second_audit.commits == []


def test_global_stop_switch_is_human_scoped_and_idempotent_per_session() -> None:
    moderator, audit = make_moderator()
    moderator.register_session(
        LiveSessionFixture("tenant.synthetic", "family.synthetic", "live.synthetic.2")
    )
    stopped = moderator.engage_stop_switch(
        moderator=MODERATOR,
        decision_key="switch.1",
        reason="人工紧急止播演练",
        occurred_at=NOW,
    )
    assert stopped == ("live.synthetic.1", "live.synthetic.2")
    assert len(audit.commits) == 2
    assert all(
        session.state is SessionState.STOPPED for session in moderator._sessions.values()
    )

    assert moderator.engage_stop_switch(
        moderator=MODERATOR,
        decision_key="switch.1",
        reason="重复演练",
        occurred_at=NOW,
    ) == stopped
    assert len(audit.commits) == 2


def test_stop_switch_failure_is_atomic_across_all_sessions() -> None:
    moderator, audit = make_moderator()
    moderator.register_session(
        LiveSessionFixture("tenant.synthetic", "family.synthetic", "live.synthetic.2")
    )
    audit.fail_next_commit = True
    with pytest.raises(RuntimeError, match="commit failure"):
        moderator.engage_stop_switch(
            moderator=MODERATOR,
            decision_key="switch.failure",
            reason="模拟批量审计失败",
            occurred_at=NOW,
        )
    assert all(
        session.state is SessionState.LIVE for session in moderator._sessions.values()
    )
    assert audit.commits == []


def test_fixture_boundary_is_explicit() -> None:
    with pytest.raises(ModerationBoundaryError):
        LiveSessionFixture("tenant.synthetic", "family.synthetic", "real-session", source="real")
    with pytest.raises(ModerationBoundaryError):
        LiveSessionFixture("tenant.synthetic", "family.synthetic", "unmarked", fixture_only=False)
    fixture = LiveSessionFixture("tenant.synthetic", "family.synthetic", "live.synthetic.3")
    assert fixture.source == SANDBOX_SOURCE
    assert fixture.fixture_only is True
