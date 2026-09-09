from __future__ import annotations

from backend.intelligence.agi_growth_path_projection import (
    project_next_growth_path,
)
from backend.intelligence.experience.api import GrowthPathResponse
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    InteractionType,
    RunScope,
)


def _snapshot(*, run_id: str, path: list[object], next_step: str = "先做第一小步"):
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id=run_id,
        request_ref=f"request-{run_id}",
        draft_payload={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "context_snapshot_ref": "ctx-1",
            "output": {"next_step": next_step, "path": path},
            "status": "DRAFT",
        },
        idempotency_key=f"create-{run_id}",
    )
    return ledger.replay(scope=scope, run_id=run_id)


def test_guardian_reject_is_not_an_accepted_growth_path() -> None:
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-reject",
        request_ref="request-reject",
        draft_payload={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "context_snapshot_ref": "ctx-1",
            "output": {"next_step": "原建议", "path": ["原路径"]},
            "status": "DRAFT",
        },
        idempotency_key="create-reject",
    )
    ledger.append_interaction(
        scope=scope,
        run_id="run-reject",
        interaction_type=InteractionType.DECISION,
        payload={"decision": "rejected", "decision_ref": "decision-reject", "state": "REJECT"},
        idempotency_key="decision-reject",
    )

    projection = project_next_growth_path(
        ledger.replay(scope=scope, run_id="run-reject")
    )

    assert projection.status == "REJECTED"
    assert projection.path == ()
    assert projection.next_step is None
    response = GrowthPathResponse(
        family_need_id=projection.family_need_id,
        path_id=projection.path_id,
        run_id=projection.run_id,
        context_snapshot_ref=projection.context_snapshot_ref,
        decision_ref=projection.decision_ref,
        decision_state=projection.decision_state,
        next_step=projection.next_step,
        path=projection.path,
        status=projection.status,
        requires_human_confirmation=projection.requires_human_confirmation,
        guardian_calibration=projection.guardian_calibration,
    )
    assert response.status == "REJECTED"


def test_guardian_defer_requires_review_and_never_displays_success() -> None:
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-defer",
        request_ref="request-defer",
        draft_payload={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "context_snapshot_ref": "ctx-1",
            "output": {"next_step": "原建议", "path": ["原路径"]},
            "status": "DRAFT",
        },
        idempotency_key="create-defer",
    )
    ledger.append_interaction(
        scope=scope,
        run_id="run-defer",
        interaction_type=InteractionType.DECISION,
        payload={
            "decision": "pending_human_confirmation",
            "decision_ref": "decision-defer",
            "state": "DEFER",
        },
        idempotency_key="decision-defer",
    )

    projection = project_next_growth_path(
        ledger.replay(scope=scope, run_id="run-defer")
    )

    assert projection.status == "DEFERRED"
    assert projection.path == ("原路径",)
    response = GrowthPathResponse(
        family_need_id=projection.family_need_id,
        path_id=projection.path_id,
        run_id=projection.run_id,
        context_snapshot_ref=projection.context_snapshot_ref,
        decision_ref=projection.decision_ref,
        decision_state=projection.decision_state,
        next_step=projection.next_step,
        path=projection.path,
        status=projection.status,
        requires_human_confirmation=projection.requires_human_confirmation,
        guardian_calibration=projection.guardian_calibration,
    )
    assert response.status == "DEFERRED"


def test_empty_path_cannot_be_serialized_as_a_successful_draft() -> None:
    snapshot = _snapshot(run_id="run-empty", path=[])
    projection = project_next_growth_path(snapshot)

    assert projection.path == ()
    response = GrowthPathResponse(
        family_need_id=projection.family_need_id,
        path_id=projection.path_id,
        run_id=projection.run_id,
        context_snapshot_ref=projection.context_snapshot_ref,
        decision_ref=projection.decision_ref,
        decision_state=projection.decision_state,
        next_step=projection.next_step,
        path=projection.path,
        status=projection.status,
        requires_human_confirmation=projection.requires_human_confirmation,
        guardian_calibration=projection.guardian_calibration,
    )
    assert response.status == "EMPTY"
    assert response.status != "DRAFT"


def test_unbound_structured_node_fails_closed() -> None:
    snapshot = _snapshot(
        run_id="run-unbound",
        path=[{"title": "没有能力来源"}],
        next_step="下一步",
    )
    projection = project_next_growth_path(snapshot)
    assert projection.path == ()
    assert projection.status == "EMPTY"
