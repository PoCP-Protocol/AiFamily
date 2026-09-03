"""Server-owned generative contract for a family growth-plan draft.

The model creates a proposal from a parent-confirmed understanding and reviewed
knowledge.  It does not create or activate a JourneyPlan; the journey domain
may adopt a validated draft only through its own parent-confirmation action.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from backend.intelligence.model_gateway.contracts import DataClass, StructuredRequest
from backend.intelligence.model_gateway.validation import SchemaValidator

FAMILY_GROWTH_PLAN_USE_CASE = "family_growth_plan_draft"
FAMILY_GROWTH_PLAN_PROMPT_VERSION = "family-growth-plan.v1"
FAMILY_GROWTH_PLAN_SCHEMA_VERSION = "family-growth-plan-output.v1"

FAMILY_GROWTH_PLAN_INSTRUCTIONS = """你是 AiFamily 的家庭成长方案设计伙伴。

输入已经经过家长确认，包含家庭希望发生的变化、仍待验证的理解、家庭已有能力，以及经审核的
专业知识。请据此生成一份可以与家长共同修改的成长方案草案，而不是套用固定天数、固定阶段或
通用任务清单。

工作方法：
1. 先说明方案回应了家庭的什么真实处境，以及为什么这样安排。
2. 方案应有足够深度：每个阶段都要有目标、核心实践、家长与孩子各自的参与方式、观察信号、
   调整触发条件和复盘问题。不得把方案缩减为一句“小行动”。
3. 引用输入中真实存在的 evidence_ref 与 reviewed knowledge_ref；不得创造来源。
4. 充分利用家庭已有优势和例外经验，不把家庭描述成需要被修理的对象。
5. 周期、阶段数和节奏由家庭目标与投入能力决定，不得默认21天、90天或四个阶段。
6. 明确家长可调整的选择，并保留仍未知、需要继续观察的部分。
7. 如果现有信息不足以形成可靠阶段，应输出需要补充的信息，不得用模板填满空白。

输出必须严格匹配服务端JSON Schema。结果始终是待家长确认的生成式草案。
"""

_TEXT: dict[str, Any] = {"type": "string", "minLength": 1}
_REFS: dict[str, Any] = {
    "type": "array",
    "minItems": 1,
    "uniqueItems": True,
    "items": _TEXT,
}

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title",
        "family_goal",
        "why_this_plan",
        "duration",
        "stages",
        "adjustable_choices",
        "unknowns_to_watch",
        "review_rhythm",
        "limitations",
    ],
    "properties": {
        "title": _TEXT,
        "family_goal": {
            "type": "object",
            "additionalProperties": False,
            "required": ["statement", "observable_signs", "evidence_refs"],
            "properties": {
                "statement": _TEXT,
                "observable_signs": {"type": "array", "minItems": 1, "items": _TEXT},
                "evidence_refs": _REFS,
            },
        },
        "why_this_plan": _TEXT,
        "duration": {
            "type": "object",
            "additionalProperties": False,
            "required": ["days", "rationale"],
            "properties": {
                "days": {"type": "integer", "minimum": 7, "maximum": 180},
                "rationale": _TEXT,
            },
        },
        "stages": {
            "type": "array",
            "minItems": 2,
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "stage_id",
                    "title",
                    "purpose",
                    "family_practices",
                    "parent_role",
                    "child_participation",
                    "success_signals",
                    "adaptation_triggers",
                    "reflection_question",
                    "evidence_refs",
                    "knowledge_refs",
                ],
                "properties": {
                    "stage_id": _TEXT,
                    "title": _TEXT,
                    "purpose": _TEXT,
                    "family_practices": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 4,
                        "items": _TEXT,
                    },
                    "parent_role": _TEXT,
                    "child_participation": _TEXT,
                    "success_signals": {"type": "array", "minItems": 1, "items": _TEXT},
                    "adaptation_triggers": {
                        "type": "array",
                        "minItems": 1,
                        "items": _TEXT,
                    },
                    "reflection_question": _TEXT,
                    "evidence_refs": _REFS,
                    "knowledge_refs": _REFS,
                },
            },
        },
        "adjustable_choices": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["choice_id", "question", "options"],
                "properties": {
                    "choice_id": _TEXT,
                    "question": _TEXT,
                    "options": {"type": "array", "minItems": 2, "maxItems": 5, "items": _TEXT},
                },
            },
        },
        "unknowns_to_watch": {"type": "array", "minItems": 1, "items": _TEXT},
        "review_rhythm": {
            "type": "object",
            "additionalProperties": False,
            "required": ["frequency", "questions"],
            "properties": {
                "frequency": _TEXT,
                "questions": {"type": "array", "minItems": 2, "items": _TEXT},
            },
        },
        "limitations": {"type": "array", "minItems": 1, "items": _TEXT},
    },
}


def family_growth_plan_output_schema() -> dict[str, Any]:
    return deepcopy(_OUTPUT_SCHEMA)


def build_family_growth_plan_request(
    *,
    run_id: str,
    data_class: DataClass,
    context_snapshot_ref: str,
    confirmed_understanding_ref: str,
    confirmed_understanding: Mapping[str, Any],
    reviewed_knowledge: tuple[Mapping[str, Any], ...],
    locale: str = "zh-CN",
) -> StructuredRequest:
    if not all(
        value.strip()
        for value in (run_id, context_snapshot_ref, confirmed_understanding_ref, locale)
    ):
        raise ValueError("growth plan request identity fields are required")
    if not reviewed_knowledge:
        raise ValueError("growth plan generation requires reviewed knowledge")
    evidence_refs = _understanding_evidence_refs(confirmed_understanding)
    knowledge_refs = _reviewed_knowledge_refs(reviewed_knowledge)
    payload = {
        "server_instructions": FAMILY_GROWTH_PLAN_INSTRUCTIONS,
        "locale": locale,
        "confirmed_understanding_ref": confirmed_understanding_ref,
        "confirmed_understanding": dict(confirmed_understanding),
        "reviewed_knowledge": [dict(item) for item in reviewed_knowledge],
        "allowed_evidence_refs": sorted(evidence_refs),
        "allowed_knowledge_refs": sorted(knowledge_refs),
        "generation_contract": {
            "fixed_horizon_forbidden": True,
            "parent_confirmation_required": True,
            "cite_only_supplied_refs": True,
            "return_json_only": True,
        },
    }
    return StructuredRequest(
        use_case=FAMILY_GROWTH_PLAN_USE_CASE,
        prompt_version=FAMILY_GROWTH_PLAN_PROMPT_VERSION,
        schema_version=FAMILY_GROWTH_PLAN_SCHEMA_VERSION,
        data_class=data_class,
        payload=payload,
        output_schema=family_growth_plan_output_schema(),
        context_snapshot_ref=context_snapshot_ref,
        input_refs=(confirmed_understanding_ref, *sorted(evidence_refs), *sorted(knowledge_refs)),
        request_id=run_id,
    )


def validate_family_growth_plan_output(
    output: Mapping[str, Any],
    *,
    allowed_evidence_refs: frozenset[str],
    allowed_knowledge_refs: frozenset[str],
) -> dict[str, Any]:
    validated = SchemaValidator().validate(
        dict(output), family_growth_plan_output_schema(), provider_id="family-growth-plan"
    )
    cited_evidence = set(validated["family_goal"]["evidence_refs"])
    cited_knowledge: set[str] = set()
    for stage in validated["stages"]:
        cited_evidence.update(stage["evidence_refs"])
        cited_knowledge.update(stage["knowledge_refs"])
    if not cited_evidence <= allowed_evidence_refs:
        raise ValueError("growth plan cites evidence outside the confirmed understanding")
    if not cited_knowledge <= allowed_knowledge_refs:
        raise ValueError("growth plan cites knowledge outside the reviewed selection")
    return validated


def _understanding_evidence_refs(understanding: Mapping[str, Any]) -> frozenset[str]:
    refs: set[str] = set()
    desired_change = understanding.get("desired_change")
    if not isinstance(desired_change, Mapping):
        raise ValueError("confirmed understanding requires desired_change")
    for hypothesis in understanding.get("hypotheses", ()):  # type: ignore[union-attr]
        if not isinstance(hypothesis, Mapping):
            continue
        for evidence in hypothesis.get("evidence", ()):  # type: ignore[union-attr]
            if isinstance(evidence, Mapping) and isinstance(evidence.get("source_ref"), str):
                refs.add(evidence["source_ref"])
    for strength in understanding.get("strengths", ()):  # type: ignore[union-attr]
        if isinstance(strength, Mapping):
            refs.update(ref for ref in strength.get("evidence_refs", ()) if isinstance(ref, str))
    if not refs:
        raise ValueError("confirmed understanding requires evidence refs")
    return frozenset(refs)


def _reviewed_knowledge_refs(items: tuple[Mapping[str, Any], ...]) -> frozenset[str]:
    refs = {
        str(item["knowledge_ref"])
        for item in items
        if isinstance(item.get("knowledge_ref"), str) and str(item["knowledge_ref"]).strip()
    }
    if len(refs) != len(items):
        raise ValueError("each reviewed knowledge item requires a unique knowledge_ref")
    return frozenset(refs)


__all__ = [
    "FAMILY_GROWTH_PLAN_INSTRUCTIONS",
    "FAMILY_GROWTH_PLAN_PROMPT_VERSION",
    "FAMILY_GROWTH_PLAN_SCHEMA_VERSION",
    "FAMILY_GROWTH_PLAN_USE_CASE",
    "build_family_growth_plan_request",
    "family_growth_plan_output_schema",
    "validate_family_growth_plan_output",
]
