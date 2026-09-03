from __future__ import annotations

import json

import httpx
import pytest

from backend.intelligence.experience.family_problem_understanding_contract import (
    FAMILY_PROBLEM_UNDERSTANDING_INSTRUCTIONS,
    FAMILY_PROBLEM_UNDERSTANDING_PROMPT_VERSION,
    FAMILY_PROBLEM_UNDERSTANDING_SCHEMA_VERSION,
    FAMILY_PROBLEM_UNDERSTANDING_USE_CASE,
    FamilyConversationTurn,
    ReviewedKnowledgeExcerpt,
    build_family_problem_understanding_request,
    family_problem_understanding_output_schema,
)
from backend.intelligence.model_gateway.contracts import MediaInput
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from backend.intelligence.model_gateway.validation import SchemaValidator


def _concern() -> FamilyConversationTurn:
    return FamilyConversationTurn(
        input_ref="input:concern-1",
        kind="CONCERN",
        text="孩子每天写作业前都会拖很久，我越催越生气。",
        created_at="2026-09-03T09:00:00+08:00",
    )


def _follow_up() -> FamilyConversationTurn:
    return FamilyConversationTurn(
        input_ref="input:follow-up-1",
        kind="FOLLOW_UP",
        text="周末他自己选先做哪一科时，通常能顺利开始。",
        created_at="2026-09-03T09:08:00+08:00",
    )


def _knowledge() -> ReviewedKnowledgeExcerpt:
    return ReviewedKnowledgeExcerpt(
        knowledge_ref="knowledge:transition:reviewed:v1",
        source_ref="source:family-learning-review:v1",
        version="1.0",
        chunk_ref="chunk:task-transition",
        content="任务开始困难可能与活动转换、控制感和任务难度有关，应结合例外情境区分。",
        applicability="家庭学习任务开始阶段的互动循环",
        limitations=("不能仅据家长一次表达判断孩子能力",),
    )


def _valid_output() -> dict[str, object]:
    return {
        "understanding": {
            "lived_experience": "每天临近作业时，家长像在与时间赛跑，孩子则迟迟难以进入任务。",
            "central_tension": "家长希望尽快开始，与孩子需要选择感和转换时间之间形成拉扯。",
            "care_intent": "家长催促背后既有学习责任，也有不希望孩子持续受挫的担心。",
        },
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "启动困难可能与从自由活动切换到学习任务有关。",
                "rationale": "冲突发生在开始前，而周末拥有选择权时更顺利。",
                "evidence": [
                    {
                        "source_type": "PARENT_TEXT",
                        "source_ref": "input:follow-up-1",
                        "observation": "自己选择顺序时能够开始。",
                    }
                ],
                "knowledge_refs": ["knowledge:transition:reviewed:v1"],
                "confidence": "MEDIUM",
                "disconfirming_evidence_needed": "需要了解拥有选择权但仍无法开始的情形。",
            }
        ],
        "unknowns": [
            {
                "unknown_id": "U1",
                "description": "不同科目之间是否存在明显差异",
                "why_it_matters": "可区分转换困难与具体任务难度",
                "related_hypothesis_ids": ["H1"],
            }
        ],
        "follow_up_questions": [
            {
                "question_id": "Q1",
                "question": "当他可以自己决定先做哪一科时，哪种安排最容易开始？",
                "purpose": "检验选择感是否真正影响启动",
                "answers_unknown_ids": ["U1"],
            }
        ],
        "strengths": [
            {
                "statement": "家庭已经观察到一个能够顺利开始的例外。",
                "evidence_refs": ["input:follow-up-1"],
                "why_it_matters": "例外为理解有效条件提供了真实线索。",
            }
        ],
        "desired_change": {
            "statement": "希望作业开始前减少催促与冲突。",
            "basis": "EXPLICIT",
            "observable_signs": ["开始前催促次数下降", "孩子能表达自己的开始安排"],
            "confirmation_question": "这是否是你最希望先发生的变化？",
        },
        "limitations": ["当前主要来自家长视角，仍需要更多日常例外与孩子表达。"],
    }


def test_server_builds_deep_multimodal_request_without_client_prompt_or_schema() -> None:
    media = MediaInput(
        media_type="IMAGE",
        uri="media:authorized:homework-scene",
        mime_type="image/jpeg",
        sha256="a" * 64,
    )
    request = build_family_problem_understanding_request(
        run_id="run-understanding-2",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:family:2",
        conversation_turns=(_concern(), _follow_up()),
        media_inputs=(media,),
        reviewed_knowledge=(_knowledge(),),
        prior_run_id="run-understanding-1",
    )

    assert request.use_case == FAMILY_PROBLEM_UNDERSTANDING_USE_CASE
    assert request.prompt_version == FAMILY_PROBLEM_UNDERSTANDING_PROMPT_VERSION
    assert request.schema_version == FAMILY_PROBLEM_UNDERSTANDING_SCHEMA_VERSION
    assert request.payload["server_instructions"] == FAMILY_PROBLEM_UNDERSTANDING_INSTRUCTIONS
    assert "固定模板" in FAMILY_PROBLEM_UNDERSTANDING_INSTRUCTIONS
    assert "小步骤" not in FAMILY_PROBLEM_UNDERSTANDING_INSTRUCTIONS
    assert request.payload["prior_run_id"] == "run-understanding-1"
    assert request.payload["generation_contract"] == {
        "regenerate_all_hypotheses_on_follow_up": True,
        "cite_only_supplied_refs": True,
        "return_json_only": True,
    }
    assert request.input_refs == (
        "input:concern-1",
        "input:follow-up-1",
        "media:authorized:homework-scene",
        "knowledge:transition:reviewed:v1",
    )
    assert request.output_schema["required"] == [
        "understanding",
        "hypotheses",
        "unknowns",
        "follow_up_questions",
        "strengths",
        "desired_change",
        "limitations",
    ]


def test_schema_accepts_deep_generated_understanding_and_rejects_shallow_copy() -> None:
    validator = SchemaValidator()
    assert (
        validator.validate(
            _valid_output(),
            family_problem_understanding_output_schema(),
            provider_id="contract-test",
        )
        == _valid_output()
    )

    with pytest.raises(ModelGatewayError) as excinfo:
        validator.validate(
            {
                "understanding": "我理解你的感受",
                "next_step": "今天先做一件小事",
                "limitations": ["仅供参考"],
            },
            family_problem_understanding_output_schema(),
            provider_id="contract-test",
        )
    assert excinfo.value.kind == "SCHEMA_INVALID"


def test_follow_up_requires_lineage_and_server_schema_copies_are_isolated() -> None:
    with pytest.raises(ValueError, match="prior_run_id"):
        build_family_problem_understanding_request(
            run_id="run-invalid-follow-up",
            data_class="SYNTHETIC",
            context_snapshot_ref="context:invalid",
            conversation_turns=(_concern(), _follow_up()),
        )

    first = family_problem_understanding_output_schema()
    second = family_problem_understanding_output_schema()
    first["required"].append("client_override")
    assert "client_override" not in second["required"]


@pytest.mark.asyncio
async def test_server_contract_drives_openai_compatible_generation() -> None:
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "model": "family-vision-livecheck-2026-09",
                "choices": [
                    {"message": {"content": json.dumps(_valid_output(), ensure_ascii=False)}}
                ],
                "usage": {
                    "prompt_tokens": 500,
                    "completion_tokens": 700,
                    "total_tokens": 1200,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            provider_id="family-understanding-livecheck",
            base_url="https://model.example.invalid/v1",
            api_key="test-only-key",
            model="family-vision-livecheck",
            client=client,
        )
        record = ProviderRecord(
            provider_id=provider.provider_id,
            vendor="openai-compatible",
            model="family-vision-livecheck",
            model_version="2026-09",
            status="INTERNAL_APPROVED",
            approved_environments=("test",),
            sub_delegates=False,
            security_assessment_ref="synthetic-contract-test",
            processing_agreement_ref="synthetic-contract-test",
            deletion_on_termination_committed=True,
        )
        gateway = ModelGateway(
            {provider.provider_id: provider},
            environment="test",
            registry=ProviderRegistry((record,)),
        )
        model_draft = await gateway.generate_structured(
            build_family_problem_understanding_request(
                run_id="run-generative-contract",
                data_class="SYNTHETIC",
                context_snapshot_ref="context:generative-contract",
                conversation_turns=(_concern(), _follow_up()),
                reviewed_knowledge=(_knowledge(),),
                prior_run_id="run-generative-contract-prior",
            ),
            provider_id=provider.provider_id,
        )

    assert model_draft.output == _valid_output()
    assert model_draft.provenance.provider_id == provider.provider_id
    assert model_draft.provenance.model == "family-vision-livecheck-2026-09"
    assert len(captured) == 1
    payload = json.loads(captured[0]["messages"][1]["content"])
    assert payload["server_instructions"] == FAMILY_PROBLEM_UNDERSTANDING_INSTRUCTIONS
    assert payload["conversation_turns"][-1]["kind"] == "FOLLOW_UP"
    system_prompt = captured[0]["messages"][0]["content"]
    assert f"use_case={FAMILY_PROBLEM_UNDERSTANDING_USE_CASE}" in system_prompt
    assert f"prompt_version={FAMILY_PROBLEM_UNDERSTANDING_PROMPT_VERSION}" in system_prompt
