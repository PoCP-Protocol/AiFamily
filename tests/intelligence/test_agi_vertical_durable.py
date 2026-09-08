from __future__ import annotations

import pytest

from backend.intelligence.agi_vertical_durable import DurableVerticalLedgerAdapter
from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedgerEntry,
    GuardianDecision,
)
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
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
