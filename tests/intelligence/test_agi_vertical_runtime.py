from __future__ import annotations

import pytest

from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedger,
    FamilyGrowthContext,
    GuardianDecision,
    PublishedKnowledge,
    VerticalFamilyGrowthRuntime,
    VerticalRuntimeError,
)
from backend.intelligence.model_gateway.attempts import InMemoryAttemptSink
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider


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


def real_gateway(provider: FakeProvider, *, timeout_seconds: float = 1.0) -> ModelGateway:
    record = ProviderRecord(
        provider_id=provider.provider_id,
        vendor="aifamily-internal",
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        security_assessment_ref="N/A",
        processing_agreement_ref="N/A",
        deletion_on_termination_committed=True,
        minor_data_allowed=True,
        timeout_seconds=timeout_seconds,
    )
    return ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry([record]),
        attempt_sink=InMemoryAttemptSink(),
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


@pytest.mark.asyncio
async def test_guardian_decision_is_carried_into_next_round_and_replay_is_read_only():
    gateway = Gateway()
    ledger = EvaluationLedger()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"delay": "high"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=ledger,
    )
    decision = GuardianDecision("decision:edit-1", "need-1", "EDIT", {"next_step": "visual timer"})
    await runtime.run(
        family_need_id="need-1",
        path_id="path-1",
        run_id="run-2",
        family_id="family-1",
        knowledge_ref="growth.v1",
        guardian_decision=decision,
    )
    calls_after_run = gateway.calls
    replayed = ledger.replay("run-2")
    assert replayed.feedback_refs[-1] == "decision:edit-1"
    assert gateway.calls == calls_after_run
    deletion_ref = ledger.delete("run-2")
    assert deletion_ref == "deletion:run-2"
    with pytest.raises(VerticalRuntimeError, match="EVALUATION_ENTRY_NOT_FOUND"):
        ledger.replay("run-2")


@pytest.mark.asyncio
async def test_runtime_uses_real_model_gateway_and_returns_structured_draft():
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "启动阻力",
                "next_step": "开始仪式",
                "path": ["拆解任务"],
            }
        }
    )
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({"delay": "high"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    entry = await runtime.run(
        family_need_id="need-real",
        path_id="path-real",
        run_id="run-real",
        family_id="family-real",
        knowledge_ref="growth.v1",
        provider_id=provider.provider_id,
    )
    assert entry.draft.output["path"] == ["拆解任务"]
    assert entry.draft.provenance.provider_id == provider.provider_id
    assert len(provider.invocations) == 1


@pytest.mark.asyncio
async def test_real_gateway_invalid_schema_fails_closed():
    provider = FakeProvider({"vertical_family_growth": {"understanding": "only"}})
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    from backend.intelligence.model_gateway.errors import ModelGatewayError

    with pytest.raises(ModelGatewayError, match="schema"):
        await runtime.run(
            family_need_id="need-invalid",
            path_id="path-invalid",
            run_id="run-invalid",
            family_id="family-invalid",
            knowledge_ref="growth.v1",
            provider_id=provider.provider_id,
        )
