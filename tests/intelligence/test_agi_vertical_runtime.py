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


class FeedbackWithPreferences(Feedback):
    async def preferences(self, *, family_id, family_need_id):
        return {"signal_counts": {"helpful": 1, "not_helpful": 2}, "sample_size": 3}


class Consent:
    def __init__(self, active: bool = True):
        self.active = active
        self.calls = 0

    async def is_current(self, *, family_id, subject_ids, purpose, consent_version):
        self.calls += 1
        return self.active


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


class RevisionGateway(Gateway):
    async def generate_structured(self, request, *, provider_id=None):
        self.calls += 1
        self.last_request = request
        next_step = (
            "采用视觉计时器"
            if request.payload.get("guardian_calibration")
            else "开始仪式"
        )
        return ModelDraft(
            {"understanding": "启动阻力", "next_step": next_step, "path": []},
            AiProvenance(
                "fake", "model", "v1", request.prompt_version,
                request.schema_version, request.context_snapshot_ref, 1,
                request.data_class, request.use_case,
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
async def test_feedback_preferences_are_scoped_and_reach_next_generation_payload():
    gateway = Gateway()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"focus": "作业启动"}),
        knowledge=Knowledge(),
        feedback=FeedbackWithPreferences(),
        ledger=EvaluationLedger(),
    )
    await runtime.run(
        family_need_id="need-preferences",
        path_id="path-preferences",
        run_id="run-preferences",
        family_id="family-preferences",
        knowledge_ref="growth.v1",
    )

    assert gateway.last_request.payload["feedback_preferences"] == {
        "signal_counts": {"helpful": 1, "not_helpful": 2},
        "sample_size": 3,
    }


@pytest.mark.asyncio
async def test_withdrawn_consent_fails_closed_before_gateway_generation():
    gateway = Gateway()
    consent = Consent(active=False)
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"focus": "作业启动"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
        consent=consent,
    )

    with pytest.raises(VerticalRuntimeError, match="CONSENT_NOT_ACTIVE"):
        await runtime.run(
            family_need_id="need-consent",
            path_id="path-consent",
            run_id="run-consent",
            family_id="family-consent",
            knowledge_ref="growth.v1",
        )
    assert consent.calls == 1
    assert gateway.calls == 0


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
    assert entry.lineage_ref.startswith("lineage:")
    assert len(entry.lineage_ref) == len("lineage:") + 32
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


@pytest.mark.asyncio
async def test_top_level_capability_refs_are_also_grounded():
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

    class DeclaredOnlyGateway(Gateway):
        async def generate_structured(self, request, *, provider_id=None):
            self.calls += 1
            return ModelDraft(
                {
                    "understanding": "x",
                    "next_step": "y",
                    "path": [],
                    "capability_refs": ["practice:unpublished@9.0.0"],
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
        gateway=DeclaredOnlyGateway(),
        context=Context({"need_type": "routine"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
        capabilities=registry,
    )
    with pytest.raises(VerticalRuntimeError, match="CAPABILITY_GROUNDING_VIOLATION"):
        await runtime.run(
            family_need_id="need-top-level",
            path_id="path-top-level",
            run_id="run-top-level",
            family_id="family-top-level",
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
    edited_lineage = ledger.read("run-2").lineage_ref
    clean_ledger = EvaluationLedger()
    clean_runtime = VerticalFamilyGrowthRuntime(
        gateway=Gateway(),
        context=Context({"delay": "high"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=clean_ledger,
    )
    await clean_runtime.run(
        family_need_id="need-1",
        path_id="path-1",
        run_id="run-clean",
        family_id="family-1",
        knowledge_ref="growth.v1",
    )
    assert edited_lineage != clean_ledger.read("run-clean").lineage_ref
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
async def test_guardian_revision_creates_changed_next_draft_without_rewriting_source():
    gateway = RevisionGateway()
    ledger = EvaluationLedger()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=gateway,
        context=Context({"delay": "high"}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=ledger,
    )
    await runtime.run(
        family_need_id="need-revision",
        path_id="path-revision",
        run_id="run-original",
        family_id="family-revision",
        knowledge_ref="growth.v1",
    )
    revised = await runtime.revise(
        run_id="run-original",
        next_run_id="run-revised",
        family_id="family-revision",
        decision=GuardianDecision(
            "decision:revision",
            "need-revision",
            "run-original",
            "path-revision",
            "EDIT",
            {"next_step": "视觉计时器"},
        ),
    )
    assert revised.run_id == "run-revised"
    assert revised.parent_run_id == "run-original"
    assert revised.draft.output["next_step"] == "采用视觉计时器"
    assert ledger.read("run-original").draft.output["next_step"] == "开始仪式"
    assert revised.lineage_ref != ledger.read("run-original").lineage_ref


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["run_id", "path_id"])
async def test_guardian_decision_correlation_must_match_requested_run(field: str):
    decision_values = {
        "decision_ref": "decision:mismatch",
        "family_need_id": "need-1",
        "run_id": "run-1",
        "path_id": "path-1",
        "state": "EDIT",
    }
    decision_values[field] = "other"
    runtime = VerticalFamilyGrowthRuntime(
        gateway=Gateway(),
        context=Context({}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    with pytest.raises(VerticalRuntimeError, match="GUARDIAN_DECISION_SCOPE_MISMATCH"):
        await runtime.run(
            family_need_id="need-1",
            path_id="path-1",
            run_id="run-1",
            family_id="family-1",
            knowledge_ref="growth.v1",
            guardian_decision=GuardianDecision(**decision_values),
        )


@pytest.mark.asyncio
async def test_lineage_changes_when_guardian_calibration_changes():
    first_ledger = EvaluationLedger()
    first = VerticalFamilyGrowthRuntime(
        gateway=Gateway(),
        context=Context({}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=first_ledger,
    )
    await first.run(
        family_need_id="need-lineage",
        path_id="path-1",
        run_id="run-lineage",
        family_id="family-1",
        knowledge_ref="growth.v1",
        guardian_decision=GuardianDecision(
            "decision:accept",
            "need-lineage",
            "run-lineage",
            "path-1",
            "ACCEPT",
        ),
    )
    second_ledger = EvaluationLedger()
    second = VerticalFamilyGrowthRuntime(
        gateway=Gateway(),
        context=Context({}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=second_ledger,
    )
    await second.run(
        family_need_id="need-lineage",
        path_id="path-1",
        run_id="run-lineage",
        family_id="family-1",
        knowledge_ref="growth.v1",
        guardian_decision=GuardianDecision(
            "decision:defer",
            "need-lineage",
            "run-lineage",
            "path-1",
            "DEFER",
        ),
    )
    first_ref = first_ledger.read("run-lineage").lineage_ref
    second_ref = second_ledger.read("run-lineage").lineage_ref
    assert first_ref != second_ref


@pytest.mark.asyncio
async def test_identical_generation_inputs_have_stable_lineage_across_ledgers():
    first_ledger = EvaluationLedger()
    second_ledger = EvaluationLedger()
    for ledger in (first_ledger, second_ledger):
        runtime = VerticalFamilyGrowthRuntime(
            gateway=Gateway(),
            context=Context({"focus": "作业启动"}),
            knowledge=Knowledge(),
            feedback=Feedback(),
            ledger=ledger,
        )
        await runtime.run(
            family_need_id="need-stable",
            path_id="path-stable",
            run_id="run-stable",
            family_id="family-stable",
            knowledge_ref="growth.v1",
        )
    assert (
        first_ledger.read("run-stable").lineage_ref == second_ledger.read("run-stable").lineage_ref
    )


@pytest.mark.asyncio
async def test_context_evidence_changes_lineage_ref():
    first_ledger = EvaluationLedger()
    second_ledger = EvaluationLedger()
    for ledger, source_ref in ((first_ledger, "obs:a"), (second_ledger, "obs:b")):
        runtime = VerticalFamilyGrowthRuntime(
            gateway=Gateway(),
            context=Context({"focus": "作业启动", "source_refs": [source_ref]}),
            knowledge=Knowledge(),
            feedback=Feedback(),
            ledger=ledger,
        )
        await runtime.run(
            family_need_id="need-evidence-lineage",
            path_id="path-evidence-lineage",
            run_id="run-evidence-lineage",
            family_id="family-evidence-lineage",
            knowledge_ref="growth.v1",
        )
    assert (
        first_ledger.read("run-evidence-lineage").lineage_ref
        != second_ledger.read("run-evidence-lineage").lineage_ref
    )


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
async def test_gateway_failure_does_not_append_evaluation_entry():
    from backend.intelligence.model_gateway.errors import ModelGatewayError

    provider = FakeProvider(
        {"vertical_family_growth": {}},
        fail_with="PROVIDER_5XX",
    )
    ledger = EvaluationLedger()
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=ledger,
    )
    with pytest.raises(ModelGatewayError, match="PROVIDER_5XX"):
        await runtime.run(
            family_need_id="need-failure",
            path_id="path-failure",
            run_id="run-failure",
            family_id="family-failure",
            knowledge_ref="growth.v1",
            provider_id=provider.provider_id,
        )
    with pytest.raises(VerticalRuntimeError, match="EVALUATION_ENTRY_NOT_FOUND"):
        ledger.replay("run-failure")


@pytest.mark.asyncio
async def test_structured_dimensions_require_evidence_or_explicit_unknown():
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "启动阻力",
                "next_step": "开始仪式",
                "path": [],
                "dimensions": [{"name": "沟通", "value": "存在阻力"}],
                "evidence_refs": ["obs:1"],
                "unknowns": [],
                "contradictions": [],
            }
        }
    )
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    with pytest.raises(VerticalRuntimeError, match="DIMENSION_EVIDENCE_MISSING"):
        await runtime.run(
            family_need_id="need-evidence",
            path_id="path-evidence",
            run_id="run-evidence",
            family_id="family-evidence",
            knowledge_ref="growth.v1",
            provider_id=provider.provider_id,
        )


@pytest.mark.asyncio
async def test_structured_unknown_and_contradiction_are_preserved():
    output = {
        "understanding": "证据存在分歧",
        "next_step": "先补一次观察",
        "path": [],
        "dimensions": [{"name": "沟通", "state": "UNKNOWN"}],
        "evidence_refs": ["obs:1", "obs:2"],
        "unknowns": [{"dimension": "沟通", "reason": "证据不足"}],
        "contradictions": [{"refs": ["obs:1", "obs:2"]}],
    }
    provider = FakeProvider({"vertical_family_growth": output})
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    entry = await runtime.run(
        family_need_id="need-honesty",
        path_id="path-honesty",
        run_id="run-honesty",
        family_id="family-honesty",
        knowledge_ref="growth.v1",
        provider_id=provider.provider_id,
    )
    assert entry.draft.output["unknowns"] == output["unknowns"]
    assert entry.draft.output["contradictions"] == output["contradictions"]


@pytest.mark.asyncio
async def test_declared_understanding_dimensions_require_complete_evidence_envelope():
    dimensions = ("情境", "关系", "节奏", "能力", "支持")
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "证据不足，先保留未知",
                "next_step": "补一次观察",
                "path": [],
                "dimensions": [
                    {"name": "情境", "evidence_refs": ["obs:1"]},
                    {"name": "关系", "state": "UNKNOWN"},
                    {"name": "节奏", "evidence_refs": ["obs:1"]},
                    {"name": "能力", "state": "UNKNOWN"},
                    {"name": "支持", "evidence_refs": ["obs:1"]},
                ],
                "evidence_refs": ["obs:1"],
                "unknowns": [
                    {"dimension": "关系", "reason": "没有足够观察"},
                    {"dimension": "能力", "reason": "没有足够观察"},
                ],
                "contradictions": [],
            }
        }
    )
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({"source_refs": ["obs:1"], "required_dimensions": dimensions}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    entry = await runtime.run(
        family_need_id="need-five-dimensions",
        path_id="path-five-dimensions",
        run_id="run-five-dimensions",
        family_id="family-five-dimensions",
        knowledge_ref="growth.v1",
        provider_id=provider.provider_id,
    )
    assert tuple(item["name"] for item in entry.draft.output["dimensions"]) == dimensions


@pytest.mark.asyncio
async def test_declared_understanding_dimensions_reject_missing_dimension():
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "不完整",
                "next_step": "补充观察",
                "path": [],
                "dimensions": [{"name": "情境", "state": "UNKNOWN"}],
                "evidence_refs": [],
                "unknowns": [{"dimension": "情境", "reason": "缺证据"}],
                "contradictions": [],
            }
        }
    )
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({"required_dimensions": ("情境", "关系")}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    with pytest.raises(VerticalRuntimeError, match="DIMENSION_SET_INVALID"):
        await runtime.run(
            family_need_id="need-missing-dimension",
            path_id="path-missing-dimension",
            run_id="run-missing-dimension",
            family_id="family-missing-dimension",
            knowledge_ref="growth.v1",
            provider_id=provider.provider_id,
        )


@pytest.mark.asyncio
async def test_declared_understanding_dimensions_reject_legacy_output_without_envelope():
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "旧格式",
                "next_step": "继续",
                "path": [],
            }
        }
    )
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({"required_dimensions": ("情境", "关系")}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    with pytest.raises(VerticalRuntimeError, match="UNDERSTANDING_ENVELOPE_REQUIRED"):
        await runtime.run(
            family_need_id="need-legacy-envelope",
            path_id="path-legacy-envelope",
            run_id="run-legacy-envelope",
            family_id="family-legacy-envelope",
            knowledge_ref="growth.v1",
            provider_id=provider.provider_id,
        )


@pytest.mark.asyncio
async def test_structured_evidence_must_belong_to_context_snapshot():
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "有观察依据",
                "next_step": "继续观察",
                "path": [],
                "dimensions": [{"name": "沟通", "evidence_refs": ["obs:missing"]}],
                "evidence_refs": ["obs:missing"],
                "unknowns": [],
                "contradictions": [],
            }
        }
    )
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({"source_refs": ["obs:real"]}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    with pytest.raises(VerticalRuntimeError, match="EVIDENCE_REF_UNGROUNDED"):
        await runtime.run(
            family_need_id="need-grounding",
            path_id="path-grounding",
            run_id="run-grounding",
            family_id="family-grounding",
            knowledge_ref="growth.v1",
            provider_id=provider.provider_id,
        )


@pytest.mark.asyncio
async def test_dimension_evidence_must_be_declared_at_top_level():
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "观察",
                "next_step": "继续",
                "path": [],
                "dimensions": [{"name": "沟通", "evidence_refs": ["obs:real"]}],
                "evidence_refs": [],
                "unknowns": [],
                "contradictions": [],
            }
        }
    )
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({"source_refs": ["obs:real"]}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    with pytest.raises(VerticalRuntimeError, match="EVIDENCE_NOT_DECLARED"):
        await runtime.run(
            family_need_id="need-declared",
            path_id="path-declared",
            run_id="run-declared",
            family_id="family-declared",
            knowledge_ref="growth.v1",
            provider_id=provider.provider_id,
        )


@pytest.mark.asyncio
async def test_contradictions_cannot_bypass_structured_evidence_envelope():
    provider = FakeProvider(
        {
            "vertical_family_growth": {
                "understanding": "证据分歧",
                "next_step": "补充观察",
                "path": [],
                "contradictions": [{"refs": ["obs:1"]}],
            }
        }
    )
    runtime = VerticalFamilyGrowthRuntime(
        gateway=real_gateway(provider),
        context=Context({"source_refs": ["obs:1"]}),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    with pytest.raises(VerticalRuntimeError, match="EVIDENCE_REFS_INVALID"):
        await runtime.run(
            family_need_id="need-contradiction",
            path_id="path-contradiction",
            run_id="run-contradiction",
            family_id="family-contradiction",
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
