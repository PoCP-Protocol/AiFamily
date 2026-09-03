"""Server-owned generative contract for S3 family problem understanding.

This module contains instructions and structured output requirements, not canned
answers.  A model must generate every ``ProblemUnderstandingDraft`` from the
current conversation, authorised context and reviewed knowledge excerpts.  The
client supplies observations; it never selects the prompt or output schema.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from backend.intelligence.model_gateway.contracts import (
    DataClass,
    MediaInput,
    StructuredRequest,
)

FAMILY_PROBLEM_UNDERSTANDING_USE_CASE = "family_problem_understanding"
FAMILY_PROBLEM_UNDERSTANDING_PROMPT_VERSION = "family-understanding.v2"
FAMILY_PROBLEM_UNDERSTANDING_SCHEMA_VERSION = "family-understanding-output.v2"

TurnKind = Literal["CONCERN", "FOLLOW_UP", "CORRECTION"]

FAMILY_PROBLEM_UNDERSTANDING_INSTRUCTIONS = """你是 AiFamily 的家庭理解伙伴。

你的首要任务不是给建议，而是帮助家长更准确地看见：正在发生什么、家长和孩子各自可能在经历
什么、冲突为何反复出现、哪些解释有证据、哪些仍然未知。你必须根据本次真实表达、授权材料、
历史上下文和经审核的知识材料生成本轮内容，不得复述固定模板。

工作方法：
1. 先用具体、自然、尊重的语言复述家庭的生活经验，让家长感到自己的处境被准确理解。
2. 区分观察、解释与假设。提出一至三个可竞争的解释，不要过早锁定单一原因。
3. 每个假设都要说明推理依据，引用实际输入或知识材料，并指出什么新证据可能推翻它。
4. 主动寻找家庭已有的能力、例外时刻和照顾意图，不把家庭描述成问题集合。
5. 只追问最能改变当前理解的问题。追问应自然、有上下文，不得像问卷或审讯。
6. 收到 FOLLOW_UP 或 CORRECTION 后，重新评估全部假设；不得只把新文字拼接到旧答案。
7. 明确当前理解的局限。证据不足时应保持多种可能性，不得制造事实或引用不存在的知识。

输出必须严格匹配服务端 JSON Schema。所有内容都是待家长确认的生成式理解草案。
"""


@dataclass(frozen=True, slots=True)
class FamilyConversationTurn:
    """One authorised observation in the family conversation."""

    input_ref: str
    kind: TurnKind
    text: str
    created_at: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.input_ref, self.text, self.created_at)):
            raise ValueError("conversation turn fields must be non-empty")
        if self.kind not in {"CONCERN", "FOLLOW_UP", "CORRECTION"}:
            raise ValueError(f"unsupported conversation turn kind: {self.kind!r}")
        try:
            parsed = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("conversation turn created_at must be RFC3339") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("conversation turn created_at must include a timezone")

    def as_payload(self) -> dict[str, str]:
        return {
            "input_ref": self.input_ref,
            "kind": self.kind,
            "text": self.text,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ReviewedKnowledgeExcerpt:
    """A content-addressed knowledge excerpt approved for this model request."""

    knowledge_ref: str
    source_ref: str
    version: str
    chunk_ref: str
    content: str
    applicability: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        values = (
            self.knowledge_ref,
            self.source_ref,
            self.version,
            self.chunk_ref,
            self.content,
            self.applicability,
        )
        if not all(value.strip() for value in values):
            raise ValueError("reviewed knowledge fields must be non-empty")
        if not self.limitations or any(not item.strip() for item in self.limitations):
            raise ValueError("reviewed knowledge limitations must be non-empty")

    def as_payload(self) -> dict[str, object]:
        return {
            "knowledge_ref": self.knowledge_ref,
            "source_ref": self.source_ref,
            "version": self.version,
            "chunk_ref": self.chunk_ref,
            "content": self.content,
            "applicability": self.applicability,
            "limitations": list(self.limitations),
        }


_NON_EMPTY_STRING: dict[str, Any] = {"type": "string", "minLength": 1}

_EVIDENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["source_type", "source_ref", "observation"],
    "additionalProperties": False,
    "properties": {
        "source_type": {
            "type": "string",
            "minLength": 1,
            "enum": ["PARENT_TEXT", "AUTHORIZED_IMAGE"],
        },
        "source_ref": _NON_EMPTY_STRING,
        "observation": _NON_EMPTY_STRING,
    },
}

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "understanding",
        "hypotheses",
        "unknowns",
        "follow_up_questions",
        "strengths",
        "desired_change",
        "limitations",
    ],
    "properties": {
        "understanding": {
            "type": "object",
            "required": ["lived_experience", "central_tension", "care_intent"],
            "additionalProperties": False,
            "properties": {
                "lived_experience": _NON_EMPTY_STRING,
                "central_tension": _NON_EMPTY_STRING,
                "care_intent": _NON_EMPTY_STRING,
            },
        },
        "hypotheses": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": [
                    "hypothesis_id",
                    "statement",
                    "rationale",
                    "evidence",
                    "knowledge_refs",
                    "confidence",
                    "disconfirming_evidence_needed",
                ],
                "additionalProperties": False,
                "properties": {
                    "hypothesis_id": _NON_EMPTY_STRING,
                    "statement": _NON_EMPTY_STRING,
                    "rationale": _NON_EMPTY_STRING,
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": _EVIDENCE_SCHEMA,
                    },
                    "knowledge_refs": {
                        "type": "array",
                        "minItems": 1,
                        "items": _NON_EMPTY_STRING,
                    },
                    "confidence": {
                        "type": "string",
                        "minLength": 1,
                        "enum": ["LOW", "MEDIUM", "HIGH"],
                    },
                    "disconfirming_evidence_needed": _NON_EMPTY_STRING,
                },
            },
        },
        "unknowns": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "unknown_id",
                    "description",
                    "why_it_matters",
                    "related_hypothesis_ids",
                ],
                "additionalProperties": False,
                "properties": {
                    "unknown_id": _NON_EMPTY_STRING,
                    "description": _NON_EMPTY_STRING,
                    "why_it_matters": _NON_EMPTY_STRING,
                    "related_hypothesis_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": _NON_EMPTY_STRING,
                    },
                },
            },
        },
        "follow_up_questions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["question_id", "question", "purpose", "answers_unknown_ids"],
                "additionalProperties": False,
                "properties": {
                    "question_id": _NON_EMPTY_STRING,
                    "question": _NON_EMPTY_STRING,
                    "purpose": _NON_EMPTY_STRING,
                    "answers_unknown_ids": {
                        "type": "array",
                        "minItems": 1,
                        "items": _NON_EMPTY_STRING,
                    },
                },
            },
        },
        "strengths": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["statement", "evidence_refs", "why_it_matters"],
                "additionalProperties": False,
                "properties": {
                    "statement": _NON_EMPTY_STRING,
                    "evidence_refs": {
                        "type": "array",
                        "minItems": 1,
                        "items": _NON_EMPTY_STRING,
                    },
                    "why_it_matters": _NON_EMPTY_STRING,
                },
            },
        },
        "desired_change": {
            "type": "object",
            "required": ["statement", "basis", "observable_signs", "confirmation_question"],
            "additionalProperties": False,
            "properties": {
                "statement": _NON_EMPTY_STRING,
                "basis": {
                    "type": "string",
                    "minLength": 1,
                    "enum": ["EXPLICIT", "INFERRED"],
                },
                "observable_signs": {
                    "type": "array",
                    "minItems": 1,
                    "items": _NON_EMPTY_STRING,
                },
                "confirmation_question": _NON_EMPTY_STRING,
            },
        },
        "limitations": {
            "type": "array",
            "minItems": 1,
            "items": _NON_EMPTY_STRING,
        },
    },
}


def family_problem_understanding_output_schema() -> dict[str, Any]:
    """Return an isolated transport copy of the server-owned output schema."""

    return deepcopy(_OUTPUT_SCHEMA)


def build_family_problem_understanding_request(
    *,
    run_id: str,
    data_class: DataClass,
    context_snapshot_ref: str,
    conversation_turns: tuple[FamilyConversationTurn, ...],
    media_inputs: tuple[MediaInput, ...] = (),
    reviewed_knowledge: tuple[ReviewedKnowledgeExcerpt, ...] = (),
    prior_run_id: str | None = None,
    locale: str = "zh-CN",
) -> StructuredRequest:
    """Build the only model request shape accepted by the S3 use case."""

    if not run_id.strip() or not context_snapshot_ref.strip():
        raise ValueError("run_id and context_snapshot_ref are required")
    if not conversation_turns:
        raise ValueError("at least one conversation turn is required")
    if conversation_turns[0].kind != "CONCERN":
        raise ValueError("the first conversation turn must be CONCERN")
    if len({item.input_ref for item in conversation_turns}) != len(conversation_turns):
        raise ValueError("conversation input refs must be unique")
    if prior_run_id is None and any(
        item.kind in {"FOLLOW_UP", "CORRECTION"} for item in conversation_turns
    ):
        raise ValueError("follow-up or correction requires prior_run_id")
    if prior_run_id is not None and len(conversation_turns) < 2:
        raise ValueError("prior_run_id requires conversation history")

    input_refs = tuple(item.input_ref for item in conversation_turns)
    media_refs = tuple(item.uri for item in media_inputs)
    evidence_refs = input_refs + media_refs
    if len(set(evidence_refs)) != len(evidence_refs):
        raise ValueError("request evidence refs must be unique")

    payload: dict[str, object] = {
        "server_instructions": FAMILY_PROBLEM_UNDERSTANDING_INSTRUCTIONS,
        "locale": locale,
        "conversation_turns": [item.as_payload() for item in conversation_turns],
        "prior_run_id": prior_run_id,
        "reviewed_knowledge": [item.as_payload() for item in reviewed_knowledge],
        "generation_contract": {
            "regenerate_all_hypotheses_on_follow_up": True,
            "cite_only_supplied_refs": True,
            "return_json_only": True,
        },
    }
    return StructuredRequest(
        use_case=FAMILY_PROBLEM_UNDERSTANDING_USE_CASE,
        prompt_version=FAMILY_PROBLEM_UNDERSTANDING_PROMPT_VERSION,
        schema_version=FAMILY_PROBLEM_UNDERSTANDING_SCHEMA_VERSION,
        data_class=data_class,
        payload=payload,
        output_schema=family_problem_understanding_output_schema(),
        context_snapshot_ref=context_snapshot_ref,
        input_refs=evidence_refs,
        media_inputs=media_inputs,
        request_id=run_id,
    )


__all__ = [
    "FAMILY_PROBLEM_UNDERSTANDING_INSTRUCTIONS",
    "FAMILY_PROBLEM_UNDERSTANDING_PROMPT_VERSION",
    "FAMILY_PROBLEM_UNDERSTANDING_SCHEMA_VERSION",
    "FAMILY_PROBLEM_UNDERSTANDING_USE_CASE",
    "FamilyConversationTurn",
    "ReviewedKnowledgeExcerpt",
    "build_family_problem_understanding_request",
    "family_problem_understanding_output_schema",
]
