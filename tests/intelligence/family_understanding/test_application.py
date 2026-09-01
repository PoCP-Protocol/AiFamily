from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from backend.intelligence.family_understanding.application import (
    FamilyUnderstandingApplication,
    GenerateUnderstandingCommand,
)
from backend.intelligence.family_understanding.contracts import KnowledgeRef
from backend.intelligence.family_understanding.eval import FamilyUnderstandingEvaluator
from backend.intelligence.family_understanding.snapshot import (
    UnderstandingDraftSnapshot,
    UnderstandingNeedCandidate,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import deterministic_provider
from backend.intelligence.model_gateway.providers.openai_compatible import (
    build_openai_compatible_provider,
)


def approved_record(provider_id: str = "generative-test", *, timeout: float = 1.0):
    return ProviderRecord(
        provider_id=provider_id,
        vendor="approved-test-vendor",
        model="semantic-test-model",
        model_version="2026-09-01",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        private_text_allowed=True,
        security_assessment_ref="test-assessment",
        processing_agreement_ref="test-agreement",
        deletion_on_termination_committed=True,
        timeout_seconds=timeout,
    )


def knowledge() -> tuple[KnowledgeRef, ...]:
    return (
        KnowledgeRef(
            ref="knowledge-reviewed-001",
            source="reviewed-guidance",
            version="1",
            chunk_ref="chunk-001",
            content_digest="sha256:reviewed-001",
            applicability="Family routine reflection",
            limitations=("Not a diagnosis",),
        ),
    )


def semantic_output(text: str, source_ref: str = "guardian-input-1") -> dict[str, object]:
    if "睡" in text:
        topic = "睡前节奏"
        hypothesis = "睡前活动衔接不稳定，可能让入睡准备更困难。"
        unknown = "周末与工作日的入睡过程是否不同？"
    elif "转学" in text:
        topic = "转学适应"
        hypothesis = "新环境中的不确定感，可能让早晨出门更困难。"
        unknown = "困难主要发生在离家前，还是到校以后？"
    else:
        topic = "作业启动"
        hypothesis = "开始步骤不够清楚，可能增加反复提醒。"
        unknown = "步骤明确时，摩擦是否仍会发生？"
    return {
        "perspective": {
            "summary": f"当前表达更接近{topic}问题，但原因仍需核对。",
            "source_refs": [source_ref],
            "knowledge_refs": ["knowledge-reviewed-001"],
            "uncertainty": "中等",
            "limitations": ["这是待家长修正的理解，不是事实或诊断。"],
        },
        "hypotheses": [
            {
                "statement": hypothesis,
                "source_refs": [source_ref],
                "knowledge_refs": ["knowledge-reviewed-001"],
                "uncertainty": "待核对",
                "disconfirming_question": unknown,
            }
        ],
        "unknowns": [{"question": unknown, "reason": "现有表达不足以确认原因。"}],
        "follow_up_questions": [unknown],
        "strengths": [
            {
                "statement": "家长已经主动描述并希望理解当前困难。",
                "source_refs": [source_ref],
                "uncertainty": "低",
            }
        ],
        "desired_change": {
            "statement": f"希望改善{topic}时的家庭体验。",
            "source_refs": [source_ref],
            "uncertainty": "低",
        },
    }


class SnapshotStore:
    def __init__(self) -> None:
        self.values: list[UnderstandingDraftSnapshot] = []

    async def save(self, snapshot: UnderstandingDraftSnapshot) -> None:
        existing = next(
            (
                value
                for value in self.values
                if value.tenant_id == snapshot.tenant_id
                and value.family_id == snapshot.family_id
                and value.artifact_ref == snapshot.artifact_ref
                and value.artifact_version == snapshot.artifact_version
            ),
            None,
        )
        if existing is None:
            self.values.append(snapshot)
        elif existing != snapshot:
            raise RuntimeError("understanding snapshot immutable binding conflict")


class NeedCandidates:
    async def project(self, **values: object) -> UnderstandingNeedCandidate:
        source_refs = tuple(str(value) for value in values["source_refs"])  # type: ignore[index]
        knowledge_refs = tuple(str(value) for value in values["knowledge_refs"])  # type: ignore[index]
        return UnderstandingNeedCandidate(
            need_type="PARENT_CHILD_COMMUNICATION_CONFLICT",
            required_capability_keys=("CAP_PARENT_COACHING",),
            evidence_refs=(*source_refs, *knowledge_refs),
        )


def application_with(
    provider,
    *,
    timeout: float = 1.0,
    snapshots: SnapshotStore | None = None,
) -> FamilyUnderstandingApplication:
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry([approved_record(provider.provider_id, timeout=timeout)]),
    )
    return FamilyUnderstandingApplication(
        FamilyUnderstandingEvaluator(gateway, provider_id=provider.provider_id),
        snapshots or SnapshotStore(),
        NeedCandidates(),
    )


def command(
    text: str,
    index: int,
    *,
    revision: int = 1,
    prior: str | None = None,
) -> GenerateUnderstandingCommand:
    return GenerateUnderstandingCommand(
        run_id=f"run-{index}-v{revision}",
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ref="guardian-1",
        consent_ref="consent-1",
        context_snapshot_ref=f"context-{index}-v{revision}",
        context_expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        guardian_input_ref=f"guardian-input-{index}",
        guardian_text=text,
        revision=revision,
        prior_draft_artifact_hash=prior,
        reviewed_knowledge_refs=knowledge(),
    )


def semantic_provider():
    return deterministic_provider(
        lambda request: semantic_output(
            request.payload["inputs"][0]["text"],
            request.payload["inputs"][0]["source_ref"],
        ),
        provider_id="generative-test",
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("一写作业就要反复提醒。", "作业启动"),
        ("最近很晚还不愿意睡。", "睡前节奏"),
        ("转学后早晨不愿出门。", "转学适应"),
    ],
)
async def test_three_semantic_inputs_generate_different_structured_drafts(
    text: str, expected: str
) -> None:
    provider = semantic_provider()
    app = application_with(provider)
    index = {"作业启动": 1, "睡前节奏": 2, "转学适应": 3}[expected]

    result = await app.generate(command(text, index))

    assert expected in result.summary
    assert len(result.hypotheses) == 1
    assert result.unknowns[0]["question"]
    assert result.source_refs == (f"guardian-input-{index}",)
    assert result.provider_id == "generative-test"
    assert result.may_mutate_business_state is False


async def test_correction_v2_generates_a_new_draft_and_replay_is_stable() -> None:
    provider = semantic_provider()
    snapshots = SnapshotStore()
    app = application_with(provider, snapshots=snapshots)
    first = await app.generate(command("一写作业就要反复提醒。", 1))
    corrected_command = command(
        "补充：不是作业问题，主要是最近很晚还不愿意睡。",
        1,
        revision=2,
        prior=first.artifact_hash,
    )

    corrected = await app.generate(corrected_command)
    replay = await app.generate(corrected_command)

    assert corrected.version == 2
    assert corrected.prior_draft_artifact_hash == first.artifact_hash
    assert "睡前节奏" in corrected.summary
    assert corrected.artifact_hash != first.artifact_hash
    assert corrected.provenance_ref != first.provenance_ref
    assert replay == corrected
    assert len(provider.invocations) == 2
    assert [value.artifact_version for value in snapshots.values] == [1, 2]
    assert snapshots.values[1].prior_artifact_ref == first.artifact_hash
    assert snapshots.values[1].provenance_ref == corrected.provenance_ref
    assert snapshots.values[1].desired_change == corrected.desired_change["statement"]
    assert snapshots.values[1].need_type == "PARENT_CHILD_COMMUNICATION_CONFLICT"


async def test_real_openai_compatible_adapter_is_used_when_explicitly_configured() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        payload = json.loads(body["messages"][1]["content"])
        output = semantic_output(payload["inputs"][0]["text"], payload["inputs"][0]["source_ref"])
        return httpx.Response(
            200,
            json={
                "model": "approved-model-2026-09",
                "choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = build_openai_compatible_provider(
        provider_id="openai-approved-test",
        model="approved-model",
        base_url_env_var="MODEL_BASE_URL",
        credential_env_var="MODEL_API_KEY",
        env={"MODEL_BASE_URL": "https://model.invalid", "MODEL_API_KEY": "test-secret"},
        client=client,
    )
    app = application_with(provider)
    try:
        result = await app.generate(command("最近很晚还不愿意睡。", 2))
    finally:
        await client.aclose()

    assert "睡前节奏" in result.summary
    assert result.model == "approved-model-2026-09"
    assert len(calls) == 1
    assert "test-secret" not in repr(result)
