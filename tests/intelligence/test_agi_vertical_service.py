import pytest

from backend.intelligence.agi_vertical_durable import DurableVerticalLedgerAdapter
from backend.intelligence.agi_vertical_runtime import EvaluationLedger, VerticalFamilyGrowthRuntime
from backend.intelligence.agi_vertical_service import DurableVerticalFamilyGrowthService
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger, RunScope
from tests.intelligence.test_agi_vertical_runtime import Context, Feedback, Gateway, Knowledge


@pytest.mark.asyncio
async def test_service_persists_runtime_draft_and_replays_from_durable_port() -> None:
    runtime = VerticalFamilyGrowthRuntime(
        gateway=Gateway(),
        context=Context({}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    adapter = DurableVerticalLedgerAdapter(InMemoryExperienceRunLedger())
    service = DurableVerticalFamilyGrowthService(runtime, adapter)
    scope = RunScope("tenant-1", "family-1", ("child-1",))

    saved = await service.run(
        scope=scope,
        family_need_id="need-1",
        path_id="path-1",
        run_id="run-service-1",
        family_id="family-1",
        knowledge_ref="growth.v1",
    )
    replay = await service.replay(run_id="run-service-1", scope=scope)

    assert saved.snapshot.draft_payload["family_need_id"] == "need-1"
    assert replay.draft_payload["lineage_ref"] == saved.snapshot.draft_payload["lineage_ref"]
