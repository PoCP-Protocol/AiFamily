from __future__ import annotations

import pytest

from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedger,
    FamilyGrowthContext,
    PublishedKnowledge,
    VerticalFamilyGrowthRuntime,
    VerticalRuntimeError,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft


class Context:
    def __init__(self, value):
        self.value = value

    async def read(self, *, family_id, context_snapshot_ref):
        return FamilyGrowthContext(
            "tenant-1",
            family_id,
            ("child-1",),
            "family-growth",
            "consent-v1",
            context_snapshot_ref,
            self.value,
        )


class Knowledge:
    async def published(self, *, ref):
        return PublishedKnowledge(
            ref, "v1", "source:education", "learning-start", "digest-v1", "reviewed guidance"
        )


class Feedback:
    async def latest(self, *, family_need_id):
        return ("feedback:guardian-edit",)


class Gateway:
    def __init__(self):
        self.calls = 0

    async def generate_structured(self, request, *, provider_id=None):
        self.calls += 1
        return ModelDraft(
            {"understanding": "启动阻力", "next_step": "开始仪式", "path": ["拆解任务"]},
            AiProvenance(
                "fake",
                "model",
                "v1",
                request.prompt_version,
                request.schema_version,
                request.context_snapshot_ref,
                1,
                request.data_class,
                request.use_case,
            ),
        )


@pytest.mark.asyncio
async def test_runtime_produces_scoped_draft_without_fact_mutation():
    gateway = Gateway()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"delay": "high"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    entry = await runtime.run(
        family_need_id="need-1",
        path_id="path-1",
        run_id="run-1",
        family_id="family-1",
        knowledge_ref="growth.v1",
    )
    assert entry.draft.status == "DRAFT"
    assert entry.draft.may_mutate_business_state is False
    assert gateway.calls == 1


@pytest.mark.asyncio
async def test_missing_published_knowledge_fails_before_gateway():
    class Missing(Knowledge):
        async def published(self, *, ref):
            return None

    gateway = Gateway()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({}),
        knowledge=Missing(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    with pytest.raises(VerticalRuntimeError, match="KNOWLEDGE_NOT_PUBLISHED"):
        await runtime.run(
            family_need_id="need-1",
            path_id="path-1",
            run_id="run-1",
            family_id="family-1",
            knowledge_ref="missing",
        )
    assert gateway.calls == 0
