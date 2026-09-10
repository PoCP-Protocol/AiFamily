from __future__ import annotations

import pytest

from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedger,
    FamilyGrowthContext,
    VerticalFamilyGrowthRuntime,
)
from backend.intelligence.capability_registry import CapabilityOffer, CapabilityRegistry
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft


class _Context:
    async def read(self, *, family_id: str, context_snapshot_ref: str) -> FamilyGrowthContext:
        return FamilyGrowthContext(
            "tenant-1", family_id, ("child-1",), "growth", "consent-v1",
            context_snapshot_ref,
            {"need_type": "routine", "required_capability_keys": ["family_practice"]},
        )


class _Knowledge:
    async def published(self, *, ref: str):
        from backend.intelligence.agi_vertical_runtime import PublishedKnowledge

        return PublishedKnowledge(ref, "v1", "source", "family_growth", "digest", "guidance")


class _Feedback:
    async def latest(self, *, family_need_id: str) -> tuple[str, ...]:
        return ()


class _Gateway:
    def __init__(self) -> None:
        self.request = None

    async def generate_structured(self, request, *, provider_id=None):
        self.request = request
        return ModelDraft(
            {"understanding": "u", "next_step": "n", "path": ["p"]},
            AiProvenance("fake", "model", "v1", request.prompt_version,
                         request.schema_version, request.context_snapshot_ref, 1,
                         request.data_class, request.use_case),
        )


@pytest.mark.asyncio
async def test_published_capabilities_are_passed_as_supply_side_candidates() -> None:
    registry = CapabilityRegistry((CapabilityOffer(
        capability_ref="practice:bedtime", version="1", title="睡前练习",
        description="家庭可选择练习", purpose="growth_path_design", scope="family_growth",
        required_capability_keys=("family_practice",), need_types=("routine",), owner="team",
    ),))
    registry.transition("practice:bedtime", "1", "REVIEWED")
    registry.transition("practice:bedtime", "1", "PUBLISHED")
    gateway = _Gateway()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway, context=_Context(), knowledge=_Knowledge(), feedback=_Feedback(),
        ledger=EvaluationLedger(), capabilities=registry,
    )
    entry = await runtime.run(
        family_need_id="need-1", path_id="path-1", run_id="run-1", family_id="family-1",
        knowledge_ref="claim:1",
    )
    assert entry.draft.output["path"] == ["p"]
    assert gateway.request.payload["capability_candidates"] == ({
        "capability_ref": "practice:bedtime", "version": "1", "title": "睡前练习",
        "description": "家庭可选择练习", "delivery_kind": "PRACTICE",
    },)
