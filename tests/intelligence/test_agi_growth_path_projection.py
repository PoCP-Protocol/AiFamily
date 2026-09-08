from __future__ import annotations

import pytest

from backend.intelligence.agi_growth_path_projection import project_next_growth_path
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    InteractionType,
    RunScope,
)


@pytest.mark.asyncio
async def test_projection_reads_decision_and_returns_same_need_path_run_chain():
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    snapshot = ledger.create_draft(
        scope=scope,
        run_id="run-1",
        request_ref="request-1",
        draft_payload={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "context_snapshot_ref": "ctx-1",
            "output": {"next_step": "开始仪式", "path": ["拆解任务"]},
            "status": "DRAFT",
        },
        idempotency_key="create-1",
    )
    ledger.append_interaction(
        scope=scope,
        run_id="run-1",
        interaction_type=InteractionType.DECISION,
        payload={"decision": "rewrite", "decision_ref": "decision-1", "state": "EDIT"},
        idempotency_key="decision-1",
    )
    snapshot = ledger.replay(scope=scope, run_id="run-1")
    projection = project_next_growth_path(snapshot)
    assert projection.family_need_id == "need-1"
    assert projection.path_id == "path-1"
    assert projection.run_id == "run-1"
    assert projection.decision_ref == "decision-1"
    assert projection.decision_state == "EDIT"
    assert projection.path == ("拆解任务",)


def test_projection_carries_feedback_refs_for_next_round_learning():
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-feedback",
        request_ref="request-feedback",
        draft_payload={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "context_snapshot_ref": "ctx-1",
            "output": {"next_step": "开始仪式", "path": ["拆解任务"]},
            "status": "DRAFT",
        },
        idempotency_key="create-feedback",
    )
    ledger.append_interaction(
        scope=scope,
        run_id="run-feedback",
        interaction_type=InteractionType.FEEDBACK,
        payload={"signal": "not_helpful"},
        idempotency_key="feedback-1",
    )
    projection = project_next_growth_path(ledger.replay(scope=scope, run_id="run-feedback"))
    assert projection.feedback_refs


def test_edit_decision_overlays_revised_next_step_without_promoting_fact():
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-edit",
        request_ref="request-edit",
        draft_payload={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "context_snapshot_ref": "ctx-1",
            "output": {"next_step": "原建议", "path": ["原路径"]},
            "status": "DRAFT",
        },
        idempotency_key="create-edit",
    )
    ledger.append_interaction(
        scope=scope,
        run_id="run-edit",
        interaction_type=InteractionType.DECISION,
        payload={
            "decision": "rewrite",
            "decision_ref": "decision-edit",
            "state": "EDIT",
            "edits": {"next_step": "家长修改后的第一步", "path": ["新路径"]},
        },
        idempotency_key="decision-edit",
    )
    projection = project_next_growth_path(ledger.replay(scope=scope, run_id="run-edit"))
    assert projection.next_step == "家长修改后的第一步"
    assert projection.path == ("新路径",)
    assert projection.status == "DRAFT"


def test_deleted_run_projection_fails_closed():
    class Deleted:
        deletion_state = "deleted"
        draft_payload = None

    with pytest.raises(ValueError, match="DELETED_RUN_NOT_READABLE"):
        project_next_growth_path(Deleted())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("decision", "state", "expected_status", "expected_path"),
    [
        ("rejected", "REJECT", "REJECTED", ()),
        ("pending_human_confirmation", "DEFER", "REVIEW_REQUIRED", ("原路径",)),
    ],
)
def test_reject_and_defer_do_not_look_like_accepted_actions(
    decision, state, expected_status, expected_path
):
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id=f"run-{state}",
        request_ref=f"request-{state}",
        draft_payload={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "context_snapshot_ref": "ctx-1",
            "output": {"next_step": "原建议", "path": ["原路径"]},
            "status": "DRAFT",
        },
        idempotency_key=f"create-{state}",
    )
    ledger.append_interaction(
        scope=scope,
        run_id=f"run-{state}",
        interaction_type=InteractionType.DECISION,
        payload={"decision": decision, "decision_ref": f"decision-{state}", "state": state},
        idempotency_key=f"decision-{state}",
    )
    projection = project_next_growth_path(ledger.replay(scope=scope, run_id=f"run-{state}"))
    assert projection.status == expected_status
    assert projection.path == expected_path
