"""AIFAMILY-WM-005 acceptance tests: Guardian Goal Decision.

Pure/no-model module: only direct construction tests — no `FakeProvider`,
no `AgentRuntime`, no model call of any kind."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.intelligence.context_engine.contracts import ContextContractError
from backend.intelligence.context_engine.guardian_goal_decision import (
    GuardianGoalDecision,
    GuardianGoalDecisionType,
    record_guardian_decision,
)

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def test_valid_accept_decision() -> None:
    decision = record_guardian_decision(
        decision_id="decision-1",
        goal_proposal_ref="goal-1",
        decision=GuardianGoalDecisionType.ACCEPT,
        final_goal_text="帮助孩子在未来两周内更愿意谈论学校话题",
        reason="这个目标很合理",
        guardian_actor_ref="guardian:mother-1",
        decided_at=NOW,
    )
    assert isinstance(decision, GuardianGoalDecision)
    assert decision.decision is GuardianGoalDecisionType.ACCEPT
    assert decision.final_goal_text == "帮助孩子在未来两周内更愿意谈论学校话题"


def test_valid_edit_decision() -> None:
    decision = record_guardian_decision(
        decision_id="decision-2",
        goal_proposal_ref="goal-1",
        decision=GuardianGoalDecisionType.EDIT,
        final_goal_text="调整后的目标文本",
        reason="原目标范围太宽，家长缩小了范围",
        guardian_actor_ref="guardian:father-1",
        decided_at=NOW,
    )
    assert decision.decision is GuardianGoalDecisionType.EDIT
    assert decision.final_goal_text == "调整后的目标文本"


def test_valid_reject_decision_with_no_final_text() -> None:
    decision = record_guardian_decision(
        decision_id="decision-3",
        goal_proposal_ref="goal-1",
        decision=GuardianGoalDecisionType.REJECT,
        final_goal_text=None,
        reason="这个目标不适合我们家庭现在的情况",
        guardian_actor_ref="guardian:mother-1",
        decided_at=NOW,
    )
    assert decision.decision is GuardianGoalDecisionType.REJECT
    assert decision.final_goal_text is None


def test_reject_with_final_goal_text_set_must_raise() -> None:
    with pytest.raises(ContextContractError, match="REJECTED_GOAL_MUST_NOT_CARRY_FINAL_TEXT"):
        record_guardian_decision(
            decision_id="decision-4",
            goal_proposal_ref="goal-1",
            decision=GuardianGoalDecisionType.REJECT,
            final_goal_text="不应该出现的文本",
            reason="拒绝但不小心写了 final text",
            guardian_actor_ref="guardian:mother-1",
            decided_at=NOW,
        )


def test_accept_with_final_goal_text_none_must_raise() -> None:
    with pytest.raises(ContextContractError, match="GUARDIAN_DECISION_REQUIRES_FINAL_GOAL_TEXT"):
        record_guardian_decision(
            decision_id="decision-5",
            goal_proposal_ref="goal-1",
            decision=GuardianGoalDecisionType.ACCEPT,
            final_goal_text=None,
            reason="接受但没有写最终目标文本",
            guardian_actor_ref="guardian:mother-1",
            decided_at=NOW,
        )


def test_edit_with_final_goal_text_none_must_raise() -> None:
    with pytest.raises(ContextContractError, match="GUARDIAN_DECISION_REQUIRES_FINAL_GOAL_TEXT"):
        record_guardian_decision(
            decision_id="decision-6",
            goal_proposal_ref="goal-1",
            decision=GuardianGoalDecisionType.EDIT,
            final_goal_text="",
            reason="编辑但最终文本为空字符串",
            guardian_actor_ref="guardian:mother-1",
            decided_at=NOW,
        )


def test_empty_reason_must_raise() -> None:
    with pytest.raises(ContextContractError):
        record_guardian_decision(
            decision_id="decision-7",
            goal_proposal_ref="goal-1",
            decision=GuardianGoalDecisionType.ACCEPT,
            final_goal_text="目标文本",
            reason="",
            guardian_actor_ref="guardian:mother-1",
            decided_at=NOW,
        )


def test_ai_actor_ref_must_raise() -> None:
    with pytest.raises(ContextContractError, match="AI_CANNOT_ACCEPT_GOAL"):
        record_guardian_decision(
            decision_id="decision-8",
            goal_proposal_ref="goal-1",
            decision=GuardianGoalDecisionType.ACCEPT,
            final_goal_text="目标文本",
            reason="AI 不应能接受目标",
            guardian_actor_ref="ai:family-principal",
            decided_at=NOW,
        )


def test_bare_ai_actor_ref_must_raise() -> None:
    with pytest.raises(ContextContractError, match="AI_CANNOT_ACCEPT_GOAL"):
        record_guardian_decision(
            decision_id="decision-9",
            goal_proposal_ref="goal-1",
            decision=GuardianGoalDecisionType.REJECT,
            final_goal_text=None,
            reason="裸 AI 标识也应被拒绝",
            guardian_actor_ref="AI",
            decided_at=NOW,
        )


def test_decided_at_requires_timezone() -> None:
    with pytest.raises(ContextContractError, match="decided_at_requires_timezone"):
        record_guardian_decision(
            decision_id="decision-10",
            goal_proposal_ref="goal-1",
            decision=GuardianGoalDecisionType.ACCEPT,
            final_goal_text="目标文本",
            reason="时间缺少时区",
            guardian_actor_ref="guardian:mother-1",
            decided_at=datetime(2026, 9, 13),  # naive, no tzinfo
        )
