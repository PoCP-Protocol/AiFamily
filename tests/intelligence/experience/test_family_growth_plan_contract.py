import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256

import pytest

from backend.intelligence.experience.family_growth_plan_contract import (
    ConfirmedUnderstandingReceipt,
    FamilyGrowthPlanScope,
    PublishedKnowledgeSelection,
    PublishedPlanKnowledge,
    family_growth_plan_output_schema,
    prepare_family_growth_plan_request,
    validate_family_growth_plan_output,
)


def _understanding() -> dict:
    return {
        "hypotheses": [{"evidence": [{"source_ref": "input:concern"}]}],
        "strengths": [{"evidence_refs": ["input:exception"]}],
        "desired_change": {
            "statement": "晚间开始学习时减少催促和争执",
            "observable_signs": ["孩子能说明自己准备何时开始"],
        },
    }


def _confirmation(**overrides) -> ConfirmedUnderstandingReceipt:
    understanding = _understanding()
    values = {
        "receipt_ref": "confirmation:understanding:1",
        "tenant_id": "tenant:1",
        "family_id": "family:1",
        "subject_refs": ("guardian:1", "child:1"),
        "confirmed_by": "guardian:1",
        "actor_type": "GUARDIAN",
        "permission": "CONFIRM_UNDERSTANDING",
        "audit_receipt_ref": "audit:confirmation:1",
        "confirmed_at": "2026-09-03T12:00:00+08:00",
        "version": "understanding.v1",
        "content_sha256": sha256(
            json.dumps(
                understanding, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest(),
        "understanding": understanding,
    }
    values.update(overrides)
    return ConfirmedUnderstandingReceipt(**values)


def _knowledge(**overrides) -> tuple[PublishedPlanKnowledge, ...]:
    values = {
        "knowledge_ref": "knowledge:transition:v1",
        "source_ref": "source:reviewed:1",
        "version": "v1",
        "chunk_ref": "chunk:1",
        "content": "活动转换需要准备",
        "applicability": "晚间活动转换",
        "limitations": ("不代表所有启动困难原因相同",),
        "purpose": "family_growth_plan_draft",
        "scope": "tenant:1/family:1",
        "expires_at": "2099-09-03T12:00:00+08:00",
        "evidence_level": "REVIEWED_PRACTICE",
        "license_ref": "license:source:1",
        "source_digest": "sha256:" + "a" * 64,
    }
    values.update(overrides)
    return (PublishedPlanKnowledge(**values),)


def _output() -> dict:
    stage = {
        "stage_id": "observe-transition",
        "title": "看清晚间转换发生了什么",
        "purpose": "共同辨认开始前最容易卡住的时刻",
        "practices": [
            {
                "practice_id": "observe-1",
                "description": "连续记录三次从自由活动转向学习的过程",
                "actor": "ADULT",
                "cadence": "发生转换时记录",
                "effort": "每次约三分钟",
                "stop_condition": "记录引发新的争执",
                "repair_option": "改为当天结束后由家长单独回忆记录",
            }
        ],
        "child_participation_mode": "OPTIONAL",
        "signals": [
            {"signal_type": "OUTCOME", "description": "双方能说出一个具体卡点"},
            {"signal_type": "STOP", "description": "观察过程明显增加家庭压力"},
        ],
        "reflection_question": "哪一次转换比预想中更顺利，发生了什么？",
        "evidence_refs": ["input:concern"],
        "knowledge_refs": ["knowledge:transition:v1"],
    }
    return {
        "result_status": "PLAN_DRAFT",
        "information_needed": [],
        "title": "让晚间学习从拉扯变成共同准备",
        "family_goal": {
            "statement": "晚间开始学习时减少催促和争执",
            "observable_signs": ["孩子能说明自己准备何时开始"],
            "evidence_refs": ["input:concern"],
        },
        "why_this_plan": "家庭已发现拥有选择时更容易开始，因此先理解转换再共同设计节奏。",
        "duration": {"days": 28, "rationale": "需要覆盖多个上学日和周末情境。"},
        "stages": [
            stage,
            {
                **stage,
                "stage_id": "co-design-rhythm",
                "title": "共同设计晚间节奏",
                "practices": [
                    {
                        **stage["practices"][0],
                        "practice_id": "co-design-1",
                        "description": "家长与孩子共同选择一个可尝试的开始提示",
                    }
                ],
            },
        ],
        "adjustable_choices": [
            {
                "choice_id": "review-time",
                "question": "你们更愿意在什么时候一起复盘？",
                "options": ["当天睡前", "第二天晚饭后"],
                "target_stage_ids": ["observe-transition", "co-design-rhythm"],
            }
        ],
        "unknowns_to_watch": ["不同科目的启动困难是否相同"],
        "review_rhythm": {
            "frequency": "每周一次",
            "questions": ["什么正在变好？", "下一周要保留或调整什么？"],
        },
        "limitations": ["目前主要依据家长表达，仍需孩子愿意参与后的观察。"],
    }


class _ConfirmationRepository:
    def __init__(self, receipt=None):
        self.receipt = receipt or _confirmation()

    def load_confirmed(self, **_kwargs):
        return self.receipt


class _KnowledgeRepository:
    def __init__(self, selection=None):
        self.selection = selection or PublishedKnowledgeSelection(
            selection_ref="selection:1",
            scope=_scope(),
            purpose="family_growth_plan_draft",
            items=_knowledge(),
        )

    def load_published(self, **_kwargs):
        return self.selection


def _scope() -> FamilyGrowthPlanScope:
    return FamilyGrowthPlanScope("tenant:1", "family:1", ("guardian:1", "child:1"))


def test_builds_a_real_generation_request_without_fixed_plan_content() -> None:
    request = _preparation().request

    assert request.use_case == "family_growth_plan_draft"
    assert request.payload["generation_contract"]["fixed_horizon_forbidden"] is True
    assert "duration" not in request.payload
    assert "stages" not in request.payload
    assert request.input_refs == (
        "confirmation:understanding:1",
        "input:concern",
        "input:exception",
        "knowledge:transition:v1",
    )


def test_validates_generated_depth_and_reference_grounding() -> None:
    validated = validate_family_growth_plan_output(
        _output(), preparation=_preparation()
    )

    assert validated["duration"]["days"] == 28
    assert len(validated["stages"]) == 2
    assert validated["stages"][0]["practices"][0]["repair_option"]


def test_rejects_invented_evidence_or_knowledge_refs() -> None:
    invented_evidence = deepcopy(_output())
    invented_evidence["family_goal"]["evidence_refs"] = ["input:invented"]
    with pytest.raises(ValueError, match="evidence outside"):
        validate_family_growth_plan_output(invented_evidence, preparation=_preparation())

    invented_knowledge = deepcopy(_output())
    invented_knowledge["stages"][0]["knowledge_refs"] = ["knowledge:invented"]
    with pytest.raises(ValueError, match="knowledge outside"):
        validate_family_growth_plan_output(invented_knowledge, preparation=_preparation())


def test_schema_copy_is_isolated_and_requires_meaningful_stages() -> None:
    first = family_growth_plan_output_schema()
    first["properties"].clear()
    second = family_growth_plan_output_schema()

    assert "stages" in second["properties"]
    shallow = _output()
    shallow["stages"] = [shallow["stages"][0]]
    with pytest.raises(ValueError, match="at least two stages"):
        validate_family_growth_plan_output(shallow, preparation=_preparation())


def test_rejects_unconfirmed_or_unpublished_inputs() -> None:
    with pytest.raises(ValueError, match="active and confirmed"):
        _confirmation(status="WITHDRAWN")
    with pytest.raises(ValueError, match="content hash mismatch"):
        _confirmation(content_sha256="0" * 64)
    with pytest.raises(ValueError, match="published and active"):
        _knowledge(status="RETIRED")
    with pytest.raises(ValueError, match="source must be verified"):
        _knowledge(source_verified=False)
    with pytest.raises(ValueError, match="unexpired"):
        _knowledge(expires_at="2020-01-01T00:00:00+00:00")
    with pytest.raises(ValueError, match="guardian permission"):
        _confirmation(actor_type="MEMBER")


def test_information_gap_does_not_fabricate_a_plan() -> None:
    output = {
        "result_status": "NEEDS_MORE_INFORMATION",
        "information_needed": ["孩子愿意如何参与这段计划"],
        "known_context_summary": "家庭希望减少晚间开始学习前的拉扯。",
        "limitations": ["目前缺少孩子愿意参与的方式。"],
    }

    validated = validate_family_growth_plan_output(output, preparation=_preparation())
    assert "duration" not in validated
    assert "stages" not in validated


def test_rejects_duplicate_or_generic_practices() -> None:
    duplicate = _output()
    duplicate["stages"][1]["practices"][0]["description"] = (
        duplicate["stages"][0]["practices"][0]["description"]
    )
    with pytest.raises(ValueError, match="must not repeat"):
        validate_family_growth_plan_output(duplicate, preparation=_preparation())

    generic = _output()
    generic["stages"][0]["practices"][0]["description"] = "多沟通"
    with pytest.raises(ValueError, match="generic practice"):
        validate_family_growth_plan_output(generic, preparation=_preparation())


def test_repositories_cannot_return_cross_family_or_wrong_purpose_records() -> None:
    wrong_scope = FamilyGrowthPlanScope("tenant:1", "family:other", ("guardian:1",))
    with pytest.raises(ValueError, match="scope mismatch"):
        asyncio.run(
            prepare_family_growth_plan_request(
                confirmation_repository=_ConfirmationRepository(),
                knowledge_repository=_KnowledgeRepository(),
                scope=wrong_scope,
                confirmation_ref="confirmation:understanding:1",
                knowledge_selection_ref="selection:1",
                run_id="run:plan:1",
                data_class="SYNTHETIC",
                context_snapshot_ref="context:plan:1",
            )
        )
    wrong = PublishedKnowledgeSelection(
        selection_ref="selection:1",
        scope=_scope(),
        purpose="marketing",
        items=_knowledge(),
    )
    with pytest.raises(ValueError, match="purpose mismatch"):
        asyncio.run(
            prepare_family_growth_plan_request(
                confirmation_repository=_ConfirmationRepository(),
                knowledge_repository=_KnowledgeRepository(wrong),
                scope=_scope(),
                confirmation_ref="confirmation:understanding:1",
                knowledge_selection_ref="selection:1",
                run_id="run:plan:1",
                data_class="SYNTHETIC",
                context_snapshot_ref="context:plan:1",
            )
        )
    wrong_item = PublishedKnowledgeSelection(
        selection_ref="selection:1",
        scope=_scope(),
        purpose="family_growth_plan_draft",
        items=_knowledge(scope="tenant:1/family:other"),
    )
    with pytest.raises(ValueError, match="item purpose or scope mismatch"):
        asyncio.run(
            prepare_family_growth_plan_request(
                confirmation_repository=_ConfirmationRepository(),
                knowledge_repository=_KnowledgeRepository(wrong_item),
                scope=_scope(),
                confirmation_ref="confirmation:understanding:1",
                knowledge_selection_ref="selection:1",
                run_id="run:plan:1",
                data_class="SYNTHETIC",
                context_snapshot_ref="context:plan:1",
            )
        )


def test_validator_rejects_modified_preparation_request() -> None:
    preparation = _preparation()
    preparation.request.payload["allowed_evidence_refs"].append("input:invented")
    with pytest.raises(ValueError, match="modified"):
        validate_family_growth_plan_output(_output(), preparation=preparation)

    preparation = _preparation()
    changed = replace(preparation.request, data_class="FAMILY_PRIVATE_TEXT")
    with pytest.raises(ValueError, match="modified"):
        validate_family_growth_plan_output(
            _output(), preparation=replace(preparation, request=changed)
        )


def _preparation():
    return asyncio.run(
        prepare_family_growth_plan_request(
            confirmation_repository=_ConfirmationRepository(),
            knowledge_repository=_KnowledgeRepository(),
            scope=_scope(),
            confirmation_ref="confirmation:understanding:1",
            knowledge_selection_ref="selection:1",
            run_id="run:plan:1",
            data_class="SYNTHETIC",
            context_snapshot_ref="context:plan:1",
        )
    )
