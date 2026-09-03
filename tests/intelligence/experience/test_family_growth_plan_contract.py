from copy import deepcopy

import pytest

from backend.intelligence.experience.family_growth_plan_contract import (
    build_family_growth_plan_request,
    family_growth_plan_output_schema,
    validate_family_growth_plan_output,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError


def _understanding() -> dict:
    return {
        "hypotheses": [{"evidence": [{"source_ref": "input:concern"}]}],
        "strengths": [{"evidence_refs": ["input:exception"]}],
        "desired_change": {
            "statement": "晚间开始学习时减少催促和争执",
            "observable_signs": ["孩子能说明自己准备何时开始"],
        },
    }


def _knowledge() -> tuple[dict, ...]:
    return ({"knowledge_ref": "knowledge:transition:v1", "content": "活动转换需要准备"},)


def _output() -> dict:
    stage = {
        "stage_id": "observe-transition",
        "title": "看清晚间转换发生了什么",
        "purpose": "共同辨认开始前最容易卡住的时刻",
        "family_practices": ["连续记录三次从自由活动转向学习的过程"],
        "parent_role": "描述观察，不提前解释原因",
        "child_participation": "选择愿意说明的一次体验",
        "success_signals": ["双方能说出一个具体卡点"],
        "adaptation_triggers": ["记录本身引发争执时改为家长单独记录"],
        "reflection_question": "哪一次转换比预想中更顺利，发生了什么？",
        "evidence_refs": ["input:concern"],
        "knowledge_refs": ["knowledge:transition:v1"],
    }
    return {
        "title": "让晚间学习从拉扯变成共同准备",
        "family_goal": {
            "statement": "晚间开始学习时减少催促和争执",
            "observable_signs": ["孩子能说明自己准备何时开始"],
            "evidence_refs": ["input:concern"],
        },
        "why_this_plan": "家庭已发现拥有选择时更容易开始，因此先理解转换再共同设计节奏。",
        "duration": {"days": 28, "rationale": "需要覆盖多个上学日和周末情境。"},
        "stages": [stage, {**stage, "stage_id": "co-design-rhythm", "title": "共同设计晚间节奏"}],
        "adjustable_choices": [
            {
                "choice_id": "review-time",
                "question": "你们更愿意在什么时候一起复盘？",
                "options": ["当天睡前", "第二天晚饭后"],
            }
        ],
        "unknowns_to_watch": ["不同科目的启动困难是否相同"],
        "review_rhythm": {
            "frequency": "每周一次",
            "questions": ["什么正在变好？", "下一周要保留或调整什么？"],
        },
        "limitations": ["目前主要依据家长表达，仍需孩子愿意参与后的观察。"],
    }


def test_builds_a_real_generation_request_without_fixed_plan_content() -> None:
    request = build_family_growth_plan_request(
        run_id="run:plan:1",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:plan:1",
        confirmed_understanding_ref="understanding:confirmed:1",
        confirmed_understanding=_understanding(),
        reviewed_knowledge=_knowledge(),
    )

    assert request.use_case == "family_growth_plan_draft"
    assert request.payload["generation_contract"]["fixed_horizon_forbidden"] is True
    assert "duration" not in request.payload
    assert "stages" not in request.payload
    assert request.input_refs == (
        "understanding:confirmed:1",
        "input:concern",
        "input:exception",
        "knowledge:transition:v1",
    )


def test_validates_generated_depth_and_reference_grounding() -> None:
    validated = validate_family_growth_plan_output(
        _output(),
        allowed_evidence_refs=frozenset({"input:concern", "input:exception"}),
        allowed_knowledge_refs=frozenset({"knowledge:transition:v1"}),
    )

    assert validated["duration"]["days"] == 28
    assert len(validated["stages"]) == 2
    assert validated["stages"][0]["adaptation_triggers"]


def test_rejects_invented_evidence_or_knowledge_refs() -> None:
    invented_evidence = deepcopy(_output())
    invented_evidence["family_goal"]["evidence_refs"] = ["input:invented"]
    with pytest.raises(ValueError, match="evidence outside"):
        validate_family_growth_plan_output(
            invented_evidence,
            allowed_evidence_refs=frozenset({"input:concern"}),
            allowed_knowledge_refs=frozenset({"knowledge:transition:v1"}),
        )

    invented_knowledge = deepcopy(_output())
    invented_knowledge["stages"][0]["knowledge_refs"] = ["knowledge:invented"]
    with pytest.raises(ValueError, match="knowledge outside"):
        validate_family_growth_plan_output(
            invented_knowledge,
            allowed_evidence_refs=frozenset({"input:concern"}),
            allowed_knowledge_refs=frozenset({"knowledge:transition:v1"}),
        )


def test_schema_copy_is_isolated_and_requires_meaningful_stages() -> None:
    first = family_growth_plan_output_schema()
    first["properties"].clear()
    second = family_growth_plan_output_schema()

    assert "stages" in second["properties"]
    shallow = _output()
    shallow["stages"] = [shallow["stages"][0]]
    with pytest.raises(ModelGatewayError, match="minItems 2"):
        validate_family_growth_plan_output(
            shallow,
            allowed_evidence_refs=frozenset({"input:concern"}),
            allowed_knowledge_refs=frozenset({"knowledge:transition:v1"}),
        )
