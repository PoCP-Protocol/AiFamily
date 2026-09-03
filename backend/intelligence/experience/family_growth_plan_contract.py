"""Server-owned generative contract for a family growth-plan draft.

The model creates a proposal from a parent-confirmed understanding and reviewed
knowledge.  It does not create or activate a JourneyPlan; the journey domain
may adopt a validated draft only through its own parent-confirmation action.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol

from backend.intelligence.model_gateway.contracts import DataClass, StructuredRequest
from backend.intelligence.model_gateway.validation import SchemaValidator

FAMILY_GROWTH_PLAN_USE_CASE = "family_growth_plan_draft"
FAMILY_GROWTH_PLAN_PROMPT_VERSION = "family-growth-plan.v1"
FAMILY_GROWTH_PLAN_SCHEMA_VERSION = "family-growth-plan-output.v1"


@dataclass(frozen=True, slots=True)
class ConfirmedUnderstandingReceipt:
    receipt_ref: str
    tenant_id: str
    family_id: str
    subject_refs: tuple[str, ...]
    confirmed_by: str
    confirmed_at: str
    version: str
    content_sha256: str
    understanding: Mapping[str, Any]
    status: str = "CONFIRMED"

    def __post_init__(self) -> None:
        if self.status != "CONFIRMED":
            raise ValueError("family understanding must be confirmed")
        values = (
            self.receipt_ref,
            self.tenant_id,
            self.family_id,
            self.confirmed_by,
            self.confirmed_at,
            self.version,
        )
        if not all(value.strip() for value in values) or not self.subject_refs:
            raise ValueError("confirmed understanding receipt identity is incomplete")
        parsed = datetime.fromisoformat(self.confirmed_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("confirmed_at must include a timezone")
        if self.content_sha256 != _content_digest(self.understanding):
            raise ValueError("confirmed understanding content hash mismatch")


@dataclass(frozen=True, slots=True)
class PublishedPlanKnowledge:
    knowledge_ref: str
    source_ref: str
    version: str
    chunk_ref: str
    content: str
    applicability: str
    limitations: tuple[str, ...]
    purpose: str
    scope: str
    status: str = "PUBLISHED"
    source_status: str = "ACTIVE"
    source_verified: bool = True

    def __post_init__(self) -> None:
        if self.status != "PUBLISHED" or self.source_status != "ACTIVE":
            raise ValueError("growth plan knowledge must be published and active")
        if self.source_verified is not True:
            raise ValueError("growth plan knowledge source must be verified")
        values = (
            self.knowledge_ref,
            self.source_ref,
            self.version,
            self.chunk_ref,
            self.content,
            self.applicability,
            self.purpose,
            self.scope,
        )
        if not all(value.strip() for value in values) or not self.limitations:
            raise ValueError("published knowledge metadata is incomplete")

    def as_payload(self) -> dict[str, object]:
        return {
            "knowledge_ref": self.knowledge_ref,
            "source_ref": self.source_ref,
            "version": self.version,
            "chunk_ref": self.chunk_ref,
            "content": self.content,
            "applicability": self.applicability,
            "limitations": list(self.limitations),
            "purpose": self.purpose,
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class FamilyGrowthPlanScope:
    tenant_id: str
    family_id: str
    subject_refs: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str, tuple[str, ...]]:
        return self.tenant_id, self.family_id, self.subject_refs


@dataclass(frozen=True, slots=True)
class PublishedKnowledgeSelection:
    selection_ref: str
    scope: FamilyGrowthPlanScope
    purpose: str
    items: tuple[PublishedPlanKnowledge, ...]


class ConfirmedUnderstandingRepository(Protocol):
    def load_confirmed(
        self, *, scope: FamilyGrowthPlanScope, confirmation_ref: str
    ) -> ConfirmedUnderstandingReceipt | Any: ...


class PlanKnowledgeSelectionRepository(Protocol):
    def load_published(
        self, *, scope: FamilyGrowthPlanScope, selection_ref: str, purpose: str
    ) -> PublishedKnowledgeSelection | Any: ...


@dataclass(frozen=True, slots=True)
class FamilyGrowthPlanPreparation:
    request: StructuredRequest
    scope: FamilyGrowthPlanScope
    confirmation_ref: str
    knowledge_selection_ref: str
    request_fingerprint: str

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
_OPTIONAL_REFS: dict[str, Any] = {
    "type": "array",
    "minItems": 0,
    "uniqueItems": True,
    "items": _TEXT,
}

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["result_status"],
    "properties": {
        "result_status": {
            "type": "string",
            "enum": ["PLAN_DRAFT", "NEEDS_MORE_INFORMATION"],
        },
        "information_needed": {"type": "array", "minItems": 0, "items": _TEXT},
        "known_context_summary": _TEXT,
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
            "minItems": 0,
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "stage_id",
                    "title",
                    "purpose",
                    "practices",
                    "child_participation_mode",
                    "signals",
                    "reflection_question",
                    "evidence_refs",
                    "knowledge_refs",
                ],
                "properties": {
                    "stage_id": _TEXT,
                    "title": _TEXT,
                    "purpose": _TEXT,
                    "practices": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "practice_id",
                                "description",
                                "actor",
                                "cadence",
                                "effort",
                                "stop_condition",
                                "repair_option",
                            ],
                            "properties": {
                                "practice_id": _TEXT,
                                "description": _TEXT,
                                "actor": {
                                    "type": "string",
                                    "enum": ["ADULT", "FAMILY", "CHILD_OPTIONAL"],
                                },
                                "cadence": _TEXT,
                                "effort": _TEXT,
                                "stop_condition": _TEXT,
                                "repair_option": _TEXT,
                            },
                        },
                    },
                    "child_participation_mode": {
                        "type": "string",
                        "enum": ["ADULT_ONLY", "OPTIONAL", "ASSENT_REQUIRED"],
                    },
                    "signals": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["signal_type", "description"],
                            "properties": {
                                "signal_type": {
                                    "type": "string",
                                    "enum": ["OUTCOME", "PROTECTION", "ADAPT", "STOP"],
                                },
                                "description": _TEXT,
                            },
                        },
                    },
                    "reflection_question": _TEXT,
                    "evidence_refs": _REFS,
                    "knowledge_refs": _OPTIONAL_REFS,
                },
            },
        },
        "adjustable_choices": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["choice_id", "question", "options", "target_stage_ids"],
                "properties": {
                    "choice_id": _TEXT,
                    "question": _TEXT,
                    "options": {"type": "array", "minItems": 2, "maxItems": 5, "items": _TEXT},
                    "target_stage_ids": _REFS,
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


async def prepare_family_growth_plan_request(
    *,
    confirmation_repository: ConfirmedUnderstandingRepository,
    knowledge_repository: PlanKnowledgeSelectionRepository,
    scope: FamilyGrowthPlanScope,
    confirmation_ref: str,
    knowledge_selection_ref: str,
    run_id: str,
    data_class: DataClass,
    context_snapshot_ref: str,
    locale: str = "zh-CN",
) -> FamilyGrowthPlanPreparation:
    confirmation = confirmation_repository.load_confirmed(
        scope=scope, confirmation_ref=confirmation_ref
    )
    if inspect.isawaitable(confirmation):
        confirmation = await confirmation
    selection = knowledge_repository.load_published(
        scope=scope,
        selection_ref=knowledge_selection_ref,
        purpose=FAMILY_GROWTH_PLAN_USE_CASE,
    )
    if inspect.isawaitable(selection):
        selection = await selection
    if not isinstance(confirmation, ConfirmedUnderstandingReceipt):
        raise ValueError("canonical confirmation repository returned an invalid receipt")
    if not isinstance(selection, PublishedKnowledgeSelection):
        raise ValueError("canonical knowledge repository returned an invalid selection")
    if (
        (confirmation.tenant_id, confirmation.family_id, confirmation.subject_refs)
        != scope.key
        or selection.scope.key != scope.key
    ):
        raise ValueError("growth plan preparation scope mismatch")
    if confirmation.receipt_ref != confirmation_ref:
        raise ValueError("confirmation repository returned the wrong receipt")
    if selection.selection_ref != knowledge_selection_ref:
        raise ValueError("knowledge repository returned the wrong selection")
    if selection.purpose != FAMILY_GROWTH_PLAN_USE_CASE:
        raise ValueError("knowledge selection purpose mismatch")
    request = _build_family_growth_plan_request(
        run_id=run_id,
        data_class=data_class,
        context_snapshot_ref=context_snapshot_ref,
        confirmation=confirmation,
        reviewed_knowledge=selection.items,
        knowledge_selection_ref=selection.selection_ref,
        locale=locale,
    )
    return FamilyGrowthPlanPreparation(
        request=request,
        scope=scope,
        confirmation_ref=confirmation_ref,
        knowledge_selection_ref=knowledge_selection_ref,
        request_fingerprint=_request_fingerprint(request),
    )


def _build_family_growth_plan_request(
    *,
    run_id: str,
    data_class: DataClass,
    context_snapshot_ref: str,
    confirmation: ConfirmedUnderstandingReceipt,
    reviewed_knowledge: tuple[PublishedPlanKnowledge, ...],
    knowledge_selection_ref: str,
    locale: str,
) -> StructuredRequest:
    if not all(
        value.strip()
        for value in (run_id, context_snapshot_ref, locale)
    ):
        raise ValueError("growth plan request identity fields are required")
    if not reviewed_knowledge:
        raise ValueError("growth plan generation requires reviewed knowledge")
    evidence_refs = _understanding_evidence_refs(confirmation.understanding)
    knowledge_refs = _reviewed_knowledge_refs(reviewed_knowledge)
    payload = {
        "server_instructions": FAMILY_GROWTH_PLAN_INSTRUCTIONS,
        "locale": locale,
        "confirmation": {
            "receipt_ref": confirmation.receipt_ref,
            "tenant_id": confirmation.tenant_id,
            "family_id": confirmation.family_id,
            "subject_refs": list(confirmation.subject_refs),
            "confirmed_by": confirmation.confirmed_by,
            "confirmed_at": confirmation.confirmed_at,
            "version": confirmation.version,
            "content_sha256": confirmation.content_sha256,
        },
        "confirmed_understanding": dict(confirmation.understanding),
        "reviewed_knowledge": [item.as_payload() for item in reviewed_knowledge],
        "knowledge_selection_ref": knowledge_selection_ref,
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
        input_refs=(confirmation.receipt_ref, *sorted(evidence_refs), *sorted(knowledge_refs)),
        request_id=run_id,
    )


def validate_family_growth_plan_output(
    output: Mapping[str, Any],
    *,
    preparation: FamilyGrowthPlanPreparation,
) -> dict[str, Any]:
    request = preparation.request
    if (
        request.use_case != FAMILY_GROWTH_PLAN_USE_CASE
        or request.prompt_version != FAMILY_GROWTH_PLAN_PROMPT_VERSION
        or request.schema_version != FAMILY_GROWTH_PLAN_SCHEMA_VERSION
        or _request_fingerprint(request) != preparation.request_fingerprint
    ):
        raise ValueError("family growth plan preparation is not server-owned or was modified")
    validated = SchemaValidator().validate(
        dict(output), family_growth_plan_output_schema(), provider_id="family-growth-plan"
    )
    allowed_evidence_refs = frozenset(request.payload["allowed_evidence_refs"])
    allowed_knowledge_refs = frozenset(request.payload["allowed_knowledge_refs"])
    if validated["result_status"] == "NEEDS_MORE_INFORMATION":
        required = {"result_status", "information_needed", "known_context_summary", "limitations"}
        if set(validated) != required or not validated["information_needed"]:
            raise ValueError("information-needed result must be minimal and complete")
        return validated
    required = {
        "result_status",
        "information_needed",
        "title",
        "family_goal",
        "why_this_plan",
        "duration",
        "stages",
        "adjustable_choices",
        "unknowns_to_watch",
        "review_rhythm",
        "limitations",
    }
    if set(validated) != required:
        raise ValueError("plan draft fields are incomplete or mixed with information-needed fields")
    if len(validated["stages"]) < 2 or validated["information_needed"]:
        raise ValueError("plan draft requires at least two stages and no information gap")
    cited_evidence = set(validated["family_goal"]["evidence_refs"])
    cited_knowledge: set[str] = set()
    for stage in validated["stages"]:
        cited_evidence.update(stage["evidence_refs"])
        cited_knowledge.update(stage["knowledge_refs"])
    stage_ids = [stage["stage_id"] for stage in validated["stages"]]
    if len(set(stage_ids)) != len(stage_ids):
        raise ValueError("growth plan stage ids must be unique")
    practices = [
        practice["description"].strip().casefold()
        for stage in validated["stages"]
        for practice in stage["practices"]
    ]
    if len(set(practices)) != len(practices):
        raise ValueError("growth plan practices must not repeat across stages")
    generic = {"多沟通", "保持耐心", "每天试一下", "好好沟通"}
    if any(description in generic for description in practices):
        raise ValueError("growth plan contains a generic practice")
    for stage in validated["stages"]:
        signal_types = {signal["signal_type"] for signal in stage["signals"]}
        if "OUTCOME" not in signal_types or not signal_types & {"PROTECTION", "STOP"}:
            raise ValueError("each growth plan stage requires outcome and stop/protection signals")
    for choice in validated["adjustable_choices"]:
        if not set(choice["target_stage_ids"]) <= set(stage_ids):
            raise ValueError("adjustable choice targets an unknown stage")
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


def _reviewed_knowledge_refs(items: tuple[PublishedPlanKnowledge, ...]) -> frozenset[str]:
    refs = {item.knowledge_ref for item in items}
    if len(refs) != len(items):
        raise ValueError("each reviewed knowledge item requires a unique knowledge_ref")
    return frozenset(refs)


def _content_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _request_fingerprint(request: StructuredRequest) -> str:
    value = {
        "use_case": request.use_case,
        "prompt_version": request.prompt_version,
        "schema_version": request.schema_version,
        "context_snapshot_ref": request.context_snapshot_ref,
        "input_refs": request.input_refs,
        "payload": request.payload,
        "output_schema": request.output_schema,
        "request_id": request.request_id,
    }
    return _content_digest(value)


__all__ = [
    "FAMILY_GROWTH_PLAN_INSTRUCTIONS",
    "FAMILY_GROWTH_PLAN_PROMPT_VERSION",
    "FAMILY_GROWTH_PLAN_SCHEMA_VERSION",
    "FAMILY_GROWTH_PLAN_USE_CASE",
    "ConfirmedUnderstandingReceipt",
    "ConfirmedUnderstandingRepository",
    "FamilyGrowthPlanPreparation",
    "FamilyGrowthPlanScope",
    "PlanKnowledgeSelectionRepository",
    "PublishedKnowledgeSelection",
    "PublishedPlanKnowledge",
    "prepare_family_growth_plan_request",
    "family_growth_plan_output_schema",
    "validate_family_growth_plan_output",
]
