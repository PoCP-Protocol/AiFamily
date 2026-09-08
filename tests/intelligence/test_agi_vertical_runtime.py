from __future__ import annotations

import pytest

from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedger,
    FamilyGrowthContext,
    GuardianDecision,
    PublishedKnowledge,
    RegistryKnowledgePort,
    VerticalFamilyGrowthRuntime,
    VerticalRuntimeError,
)
from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway.attempts import InMemoryAttemptSink
from backend.intelligence.model_gateway.contracts import AiProvenance, MediaInput, ModelDraft
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.packages.contracts.evidence import Provenance


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
        self.last_request = None

    async def generate_structured(self, request, *, provider_id=None):
        self.calls += 1
        self.last_request = request
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


def test_guardian_decision_rejects_unbounded_calibration_fields():
    with pytest.raises(VerticalRuntimeError, match="GUARDIAN_CALIBRATION_FIELD_INVALID"):
        GuardianDecision("d", "n", "r", "p", "EDIT", {"raw_prompt": "secret"})


def test_guardian_decision_rejects_oversized_calibration_text():
    with pytest.raises(VerticalRuntimeError, match="GUARDIAN_CALIBRATION_TEXT_INVALID"):
        GuardianDecision("d", "n", "r", "p", "EDIT", {"focus": "x" * 2001})


@pytest.mark.asyncio
async def test_registry_knowledge_port_requires_published_in_scope_claim():
    registry = KnowledgeRegistry(
        sources=(KnowledgeSource("src", "Reviewed", "lic", "owner", "family_growth", True),),
        claims=(
            KnowledgeClaim(
                "claim:1",
                "先拆成可完成的小步。",
                "src",
                Provenance(level="E6", source_ref="src"),
                "family_growth",
                status="REVIEWED",
                allowed_purposes=("vertical_family_growth",),
            ),
        ),
    )
    port = RegistryKnowledgePort(registry, purpose="vertical_family_growth", scope="family_growth")
    assert await port.published(ref="claim:1") is None
    registry.transition_claim("claim:1", "PUBLISHED")
    material = await port.published(ref="claim:1")
    assert material is not None
    assert material.content == "先拆成可完成的小步。"
    assert await port.published(ref="claim:missing") is None


@pytest.mark.asyncio
async def test_two_family_contexts_reach_generation_as_distinct_inputs():
    gateway = Gateway()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"focus": "作业启动"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    await runtime.run(
        family_need_id="need-a",
        path_id="path-a",
        run_id="run-a",
        family_id="family-a",
        knowledge_ref="growth.v1",
    )
    first_payload = dict(gateway.last_request.payload)

    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"focus": "亲子沟通"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    await runtime.run(
        family_need_id="need-b",
        path_id="path-b",
        run_id="run-b",
        family_id="family-b",
        knowledge_ref="growth.v1",
    )
    second_payload = dict(gateway.last_request.payload)
    assert first_payload["context"] != second_payload["context"]
    assert first_payload["family_need_id"] != second_payload["family_need_id"]


@pytest.mark.asyncio
async def test_published_capability_versions_are_part_of_request_identity():
    from backend.intelligence.capability_registry import CapabilityOffer, CapabilityRegistry

    registry = CapabilityRegistry(
        (
            CapabilityOffer(
                "practice:focus",
                "1.0.0",
                "专注练习",
                "家庭可选择的专注练习",
                "growth_path_design",
                "family_growth",
                need_types=("routine",),
                owner="growth-team",
            ),
        )
    )
    registry.transition("practice:focus", "1.0.0", "REVIEWED")
    registry.transition("practice:focus", "1.0.0", "PUBLISHED")
    gateway = Gateway()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"need_type": "routine"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
        capabilities=registry,
    )
    await runtime.run(
        family_need_id="need-c",
        path_id="path-c",
        run_id="run-c",
        family_id="family-c",
        knowledge_ref="growth.v1",
    )
    assert gateway.last_request.input_refs[-1] == "practice:focus@1.0.0"
    entry = runtime._ledger.read("run-c")
    assert entry.capability_refs == ("practice:focus@1.0.0",)
    assert entry.knowledge_ref == "growth.v1"
    assert entry.knowledge_version == "v1"
    assert "knowledge:growth.v1@v1" in gateway.last_request.input_refs
    assert (
        gateway.last_request.payload["capability_candidates"][0]["capability_ref"]
        == "practice:focus"
    )


@pytest.mark.asyncio
async def test_capability_registry_with_no_matching_offer_fails_before_model_call():
    from backend.intelligence.capability_registry import CapabilityOffer, CapabilityRegistry

    registry = CapabilityRegistry(
        (
            CapabilityOffer(
                "practice:sleep",
                "1.0.0",
                "睡前练习",
                "家庭可选择的睡前练习",
                "growth_path_design",
                "family_growth",
                need_types=("sleep",),
                owner="growth-team",
            ),
        )
    )
    registry.transition("practice:sleep", "1.0.0", "REVIEWED")
    registry.transition("practice:sleep", "1.0.0", "PUBLISHED")
    gateway = Gateway()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"need_type": "routine"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
        capabilities=registry,
    )
    with pytest.raises(VerticalRuntimeError, match="NO_PUBLISHED_CAPABILITY_CANDIDATES"):
        await runtime.run(
            family_need_id="need-empty",
            path_id="path-empty",
            run_id="run-empty",
            family_id="family-empty",
            knowledge_ref="growth.v1",
        )
    assert gateway.calls == 0


@pytest.mark.asyncio
async def test_model_cannot_invent_capability_outside_published_catalogue():
    from backend.intelligence.capability_registry import CapabilityOffer, CapabilityRegistry

    registry = CapabilityRegistry(
        (
            CapabilityOffer(
                "practice:focus",
                "1.0.0",
                "专注练习",
                "家庭可选择的专注练习",
                "growth_path_design",
                "family_growth",
                need_types=("routine",),
                owner="growth-team",
            ),
        )
    )
    registry.transition("practice:focus", "1.0.0", "REVIEWED")
    registry.transition("practice:focus", "1.0.0", "PUBLISHED")

    class HallucinatingGateway(Gateway):
        async def generate_structured(self, request, *, provider_id=None):
            self.calls += 1
            return ModelDraft(
                {
                    "understanding": "x",
                    "next_step": "y",
                    "path": [{"capability_ref": "service:invented", "version": "9.9.9"}],
                },
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

    runtime = VerticalFamilyGrowthRuntime(
        gateway=HallucinatingGateway(),
        context=Context({"need_type": "routine"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
        capabilities=registry,
    )
    with pytest.raises(VerticalRuntimeError, match="CAPABILITY_GROUNDING_VIOLATION"):
        await runtime.run(
            family_need_id="need-h",
            path_id="path-h",
            run_id="run-h",
            family_id="family-h",
            knowledge_ref="growth.v1",
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
    decision = GuardianDecision(
        "decision:edit-1",
        "need-1",
        "run-2",
        "path-1",
        "EDIT",
        {"next_step": "visual timer"},
    )
    await runtime.run(
        family_need_id="need-1",
        path_id="path-1",
        run_id="run-2",
        family_id="family-1",
        knowledge_ref="growth.v1",
        guardian_decision=decision,
    )
    assert gateway.last_request.payload["guardian_calibration"] == {
        "decision_ref": "decision:edit-1",
        "state": "EDIT",
        "edits": {"next_step": "visual timer"},
    }
    assert ledger.read("run-2").guardian_calibration == {
        "decision_ref": "decision:edit-1",
        "state": "EDIT",
        "edits": {"next_step": "visual timer"},
    }
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


@pytest.mark.asyncio
async def test_multimodal_media_reference_uses_same_gateway_and_keeps_digest_only():
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "图片中的作业启动线索",
                "next_step": "先做第一小步",
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
    media = MediaInput(
        media_type="IMAGE",
        uri="https://media.example/short-lived/object",
        mime_type="image/jpeg",
        sha256="a" * 64,
    )
    await runtime.run(
        family_need_id="need-media",
        path_id="path-media",
        run_id="run-media",
        family_id="family-media",
        knowledge_ref="growth.v1",
        provider_id=provider.provider_id,
        media_inputs=(media,),
    )
    request = provider.invocations[0]
    assert request.media_inputs[0].sha256 == "a" * 64
    assert request.media_inputs[0].uri.startswith("https://")
