from __future__ import annotations

import pytest

from backend.intelligence.agi_vertical_durable import (
    DurableVerticalGrowthRuntime,
    DurableVerticalLedgerAdapter,
)
from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedger,
    EvaluationLedgerEntry,
    GuardianDecision,
    VerticalFamilyGrowthRuntime,
)
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    RunHttpError,
    RunScope,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft


def entry() -> EvaluationLedgerEntry:
    draft = ModelDraft(
        {"understanding": "启动阻力", "next_step": "开始仪式", "path": ["拆解任务"]},
        AiProvenance("fake", "model", "v1", "p1", "s1", "ctx-1", 1, "SYNTHETIC", "vertical"),
    )
    return EvaluationLedgerEntry("need-1", "path-1", "run-1", "ctx-1", draft, ())


@pytest.mark.asyncio
async def test_adapter_uses_existing_scope_isolated_durable_port():
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    saved = await adapter.save_entry(entry(), scope=scope)
    replay = await adapter.replay(run_id="run-1", scope=scope)
    assert saved.snapshot.draft_payload == replay.draft_payload
    assert replay.draft_payload["family_need_id"] == "need-1"


@pytest.mark.asyncio
async def test_adapter_delete_hides_draft_and_artifacts():
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    await adapter.save_entry(entry(), scope=scope)
    deleted = await adapter.delete(run_id="run-1", scope=scope)
    assert deleted.deletion_state == "deleted"
    assert deleted.draft_payload is None
    assert not deleted.artifact_refs


@pytest.mark.asyncio
async def test_guardian_decision_uses_explicit_run_correlation():
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    await adapter.save_entry(entry(), scope=scope)
    decision = GuardianDecision("decision:edit-1", "need-1", "run-1", "path-1", "EDIT")
    await adapter.record_guardian_decision(decision, scope=scope)
    replay = await adapter.replay(run_id="run-1", scope=scope)
    assert replay.interactions[-1].payload["decision_ref"] == "decision:edit-1"
    assert replay.interactions[-1].payload["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_replay_projects_latest_guardian_calibration_into_entry():
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    await adapter.save_entry(entry(), scope=scope)
    decision = GuardianDecision(
        "decision:edit-1",
        "need-1",
        "run-1",
        "path-1",
        "EDIT",
        {"next_step": "视觉计时器"},
    )
    await adapter.record_guardian_decision(decision, scope=scope)

    runtime = DurableVerticalGrowthRuntime(
        runtime=VerticalFamilyGrowthRuntime(
            gateway=object(),
            context=object(),
            knowledge=object(),
            feedback=object(),
            ledger=EvaluationLedger(),
        ),
        ledger=adapter,
        scope_factory=lambda family_id: scope,
    )
    replay = await runtime.replay(run_id="run-1", family_id="family-1")

    assert replay.guardian_calibration == {
        "decision_ref": "decision:edit-1",
        "state": "EDIT",
        "edits": {"next_step": "视觉计时器"},
    }
    assert replay.feedback_refs[-1] == "decision:edit-1"


@pytest.mark.asyncio
async def test_cross_family_replay_is_rejected_without_leaking_draft():
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    owner_scope = RunScope("tenant-1", "family-1", ("child-1",))
    foreign_scope = RunScope("tenant-1", "family-2", ("child-2",))
    await adapter.save_entry(entry(), scope=owner_scope)
    with pytest.raises(RunHttpError):
        await adapter.replay(run_id="run-1", scope=foreign_scope)


@pytest.mark.asyncio
async def test_cross_family_decision_is_rejected_before_interaction_write():
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    owner_scope = RunScope("tenant-1", "family-1", ("child-1",))
    foreign_scope = RunScope("tenant-1", "family-2", ("child-2",))
    await adapter.save_entry(entry(), scope=owner_scope)
    decision = GuardianDecision("decision:foreign", "need-1", "run-1", "path-1", "EDIT")
    with pytest.raises(RunHttpError):
        await adapter.record_guardian_decision(decision, scope=foreign_scope)
    replay = await adapter.replay(run_id="run-1", scope=owner_scope)
    assert not replay.interactions


@pytest.mark.asyncio
async def test_decision_for_different_need_or_path_is_rejected_before_write():
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    await adapter.save_entry(entry(), scope=scope)
    decision = GuardianDecision(
        "decision:wrong-correlation", "need-other", "run-1", "path-other", "EDIT"
    )
    with pytest.raises(ValueError, match="GUARDIAN_DECISION_CORRELATION_MISMATCH"):
        await adapter.record_guardian_decision(decision, scope=scope)
    replay = await adapter.replay(run_id="run-1", scope=scope)
    assert not replay.interactions


@pytest.mark.asyncio
async def test_adapter_projects_growth_path_from_same_durable_run():
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    scope = RunScope("tenant-1", "family-1", ("child-1",))
    await adapter.save_entry(entry(), scope=scope)
    decision = GuardianDecision("decision:accept", "need-1", "run-1", "path-1", "ACCEPT")
    await adapter.record_guardian_decision(decision, scope=scope)
    projection = await adapter.project_growth_path(run_id="run-1", scope=scope)
    assert projection.family_need_id == "need-1"
    assert projection.path_id == "path-1"
    assert projection.decision_ref == "decision:accept"
    assert projection.decision_state == "ACCEPT"
