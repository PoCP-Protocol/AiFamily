from __future__ import annotations

from copy import deepcopy

import pytest

from backend.intelligence.experience.family_problem_understanding_contract import (
    family_problem_understanding_output_schema,
)
from backend.intelligence.experience.family_problem_understanding_eval import (
    FamilyProblemUnderstandingEvaluator,
    FamilyUnderstandingEvalSpec,
)
from backend.intelligence.experience.multimodal_eval import (
    GoldCase,
    MultimodalAdapterResult,
    MultimodalEvalError,
)


def _case() -> GoldCase:
    return GoldCase(
        case_id="evening-homework-transition",
        version="family-understanding-output.v2",
        fixture_kind="synthetic",
        modalities=("text",),
        locale="zh-CN",
        safety_labels=(),
        expected_schema=family_problem_understanding_output_schema(),
    )


def _spec(*, revision: bool = False) -> FamilyUnderstandingEvalSpec:
    return FamilyUnderstandingEvalSpec(
        allowed_evidence_refs=frozenset({"input:concern", "input:follow-up"}),
        allowed_knowledge_refs=frozenset({"knowledge:transition:v1"}),
        expected_signal_terms=(
            frozenset({"转换", "切换"}),
            frozenset({"选择", "控制感"}),
        ),
        prior_hypothesis_statements=("孩子缺乏学习动力。",) if revision else (),
        requires_revision=revision,
    )


def _output() -> dict[str, object]:
    return {
        "understanding": {
            "lived_experience": "临近作业时，家长和孩子都像被时间推着走。",
            "central_tension": "尽快开始的期待与活动切换需要之间形成拉扯。",
            "care_intent": "催促背后是家长不希望孩子持续受挫的担心。",
        },
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "启动困难可能首先与从自由活动转换到学习有关。",
                "rationale": "困难集中发生在开始前。",
                "evidence": [
                    {
                        "source_type": "PARENT_TEXT",
                        "source_ref": "input:concern",
                        "observation": "写作业前拖延",
                    }
                ],
                "knowledge_refs": ["knowledge:transition:v1"],
                "confidence": "MEDIUM",
                "disconfirming_evidence_needed": "了解其他活动切换是否同样困难。",
            },
            {
                "hypothesis_id": "H2",
                "statement": "自己选择任务顺序带来的控制感也可能影响启动。",
                "rationale": "拥有选择权时出现了顺利开始的例外。",
                "evidence": [
                    {
                        "source_type": "PARENT_TEXT",
                        "source_ref": "input:follow-up",
                        "observation": "周末可自行选择顺序",
                    }
                ],
                "knowledge_refs": ["knowledge:transition:v1"],
                "confidence": "MEDIUM",
                "disconfirming_evidence_needed": "了解有选择权但仍无法开始的情况。",
            },
        ],
        "unknowns": [
            {
                "unknown_id": "U1",
                "description": "不同科目是否有差异",
                "why_it_matters": "区分任务难度和转换困难",
                "related_hypothesis_ids": ["H1", "H2"],
            }
        ],
        "follow_up_questions": [
            {
                "question_id": "Q1",
                "question": "当他自己决定顺序时，什么情况下仍然难开始？",
                "purpose": "区分选择感与任务难度",
                "answers_unknown_ids": ["U1"],
            }
        ],
        "strengths": [
            {
                "statement": "家庭已经发现一个顺利开始的例外。",
                "evidence_refs": ["input:follow-up"],
                "why_it_matters": "它提供了可继续理解的真实线索。",
            }
        ],
        "desired_change": {
            "statement": "减少开始前的催促和冲突。",
            "basis": "EXPLICIT",
            "observable_signs": ["催促次数下降"],
            "confirmation_question": "这是不是你最希望先发生的变化？",
        },
        "limitations": ["目前主要来自家长视角。"],
    }


def _result(output: dict[str, object]) -> MultimodalAdapterResult:
    return MultimodalAdapterResult(
        provider_id="provider",
        model="model",
        model_version="v1",
        output=output,
        refused=False,
        safety_labels=(),
        safety_passed=True,
        provenance=None,
        latency_ms=10,
        cost_microusd=1,
    )


def test_scores_grounded_competing_hypotheses_and_high_information_follow_up() -> None:
    evaluator = FamilyProblemUnderstandingEvaluator({_case().case_id: _spec(revision=True)})
    report = evaluator.evaluate(_case(), _result(_output()))

    assert report.evidence_grounding == 1.0
    assert report.knowledge_grounding == 1.0
    assert report.hypothesis_quality > 0.8
    assert report.follow_up_information_gain == 1.0
    assert report.revision_quality > 0.8
    assert report.strengths_and_goal_grounding == 1.0
    assert report.score > 0.85


def test_penalizes_generic_copy_unsupported_certainty_and_invented_refs() -> None:
    output = deepcopy(_output())
    output["understanding"]["lived_experience"] = "我理解你的感受，保持耐心。"
    output["hypotheses"] = [
        {
            **output["hypotheses"][0],
            "statement": "这一定就是孩子缺乏学习动力。",
            "confidence": "HIGH",
            "evidence": [
                {
                    "source_type": "PARENT_TEXT",
                    "source_ref": "input:invented",
                    "observation": "并不存在的观察",
                }
            ],
            "knowledge_refs": ["knowledge:invented"],
        }
    ]
    evaluator = FamilyProblemUnderstandingEvaluator({_case().case_id: _spec()})
    report = evaluator.evaluate(_case(), _result(output))

    assert report.evidence_grounding <= 0.5
    assert report.knowledge_grounding == 0.0
    assert report.generic_response_penalty > 0.0
    assert report.unsupported_certainty_penalty >= 0.2
    assert report.score < 0.55


def test_revision_score_requires_follow_up_to_change_the_hypothesis() -> None:
    output = _output()
    output["hypotheses"] = [{**output["hypotheses"][0], "statement": "孩子缺乏学习动力。"}]
    evaluator = FamilyProblemUnderstandingEvaluator({_case().case_id: _spec(revision=True)})

    assert evaluator.evaluate(_case(), _result(output)).revision_quality == 0.0


def test_missing_case_spec_and_invalid_feedback_evidence_fail_closed() -> None:
    evaluator = FamilyProblemUnderstandingEvaluator({"another-case": _spec()})
    with pytest.raises(MultimodalEvalError, match="missing eval spec"):
        evaluator(_case(), _result(_output()))
    with pytest.raises(MultimodalEvalError, match="evidence status"):
        FamilyUnderstandingEvalSpec(
            allowed_evidence_refs=frozenset({"input:1"}),
            allowed_knowledge_refs=frozenset(),
            parent_feedback_evidence_status="WINNER",
        )


def test_parent_feedback_cannot_change_model_quality_score() -> None:
    baseline = FamilyProblemUnderstandingEvaluator({_case().case_id: _spec()}).evaluate(
        _case(), _result(_output())
    )
    descriptive_spec = FamilyUnderstandingEvalSpec(
        allowed_evidence_refs=_spec().allowed_evidence_refs,
        allowed_knowledge_refs=_spec().allowed_knowledge_refs,
        expected_signal_terms=_spec().expected_signal_terms,
        parent_feedback_evidence_status="DESCRIPTIVE_READY",
        parent_feedback_policy_version="test.v1",
        parent_feedback_response_count=10,
        parent_feedback_coverage_rate=1.0,
        parent_feedback_rating_distribution=((1, 5), (5, 5)),
        parent_feedback_high_understanding_rate=0.5,
        parent_feedback_low_understanding_rate=0.5,
    )
    descriptive = FamilyProblemUnderstandingEvaluator(
        {_case().case_id: descriptive_spec}
    ).evaluate(_case(), _result(_output()))

    assert descriptive.score == baseline.score
