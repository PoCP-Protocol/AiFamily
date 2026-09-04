"""AI Coach — a Socratic, provider-neutral perspective generator.

This module is the generic, business-agnostic half of the AI Coach capability
(R10/R7: AI Runtime is collapsed into `backend/intelligence/`, and does not
import any domain repository). It knows how to build a `StructuredRequest` for
the coaching use case, call the real `ModelGateway`, and hand back a
schema-validated `CoachPerspective` — nothing about *which* family need
produced the context passes through here as a hardcoded rule.

## Why this is not a template engine

The content of `guiding_question` / `reflection` is produced by whatever the
gateway's provider returns. This module writes only:

1. the system prompt (instructions on *how* to behave, never a canned answer);
2. the call into `ModelGateway.generate_structured`;
3. structural validation of the shape the model returned (already enforced by
   the gateway's schema check, restated here as a narrow post-condition so a
   caller does not have to re-derive the schema to know what it got back).

There is no `if urgency == "HIGH": return ...` branch anywhere in this file,
and there must never be one — see `docs/05_ai/AI_USE_CASES/family-ai-coach.md`.

## Governance boundary (R9)

`CoachPerspective` is a Perspective, not a Fact. It is shown to a parent for
their own reflection; nothing here writes to any domain aggregate, and
`ModelDraft.may_mutate_business_state` is enforced upstream by the gateway
itself. The HTTP boundary must label the response with
`AI_PERSPECTIVE_NOT_FAMILY_FACT_GUIDANCE_NOT_ANSWER` — see the family_need
routes wiring, not this module, because a labelling convention belongs at the
HTTP surface, not buried in the generic runtime helper.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceProvenance,
    ExperienceScope,
    MemoryLevel,
    MemoryRef,
    MemoryScope,
    ProvenanceKind,
)
from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    DataClass,
    ModelDraft,
    PolicyContext,
    PromptExecutionPlan,
    StructuredRequest,
)
from backend.intelligence.model_gateway.gateway import ModelGateway

COACH_USE_CASE = "FAMILY_AI_COACH_SOCRATIC_PERSPECTIVE"
COACH_PROMPT_VERSION = "family-ai-coach-prompt-v2"
COACH_SCHEMA_VERSION = "family-ai-coach-schema-v1"

COACH_SYSTEM_PROMPT = (
    "你是一名家长自我成长教练，服务对象是家长本人——这个平台的核心定位是"
    "家长的第二次成长，孩子遇到的具体状况只是家长成长路上出现的一个真实场景，"
    "不是唯一焦点。采用苏格拉底式引导方式与家长对话。\n"
    "严格遵守以下规则：\n"
    "1. 不要直接给出解决方案、结论或诊断——你的任务是通过提问帮助家长自己想清楚，"
    "而不是替家长做决定。\n"
    "2. 视角落在家长自己身上：多问'你希望自己在这件事上做出什么样的改变/成长'，"
    "少问'孩子该怎么办'——把家长当作正在成长的主角，而不是只负责解决孩子问题的执行者。\n"
    "3. 先用一两句话反映你理解到的家长处境（体现你认真听到了家长在说什么），"
    "再提出一个具体的、能推进家长思考的问题。这个问题必须是真正的疑问句，"
    "不能是换个说法的建议或陈述。\n"
    "4. 全程使用中文回复。\n"
    "5. 不做任何临床诊断、不给医学或心理治疗建议、不评判家长或孩子的对错。\n"
    "6. 如果提供的上下文里已经匹配过课程或服务，可以在反馈中提及它的存在，"
    "但不要把它当作现成答案塞给家长，仍要留出家长自己思考的空间。\n"
    "7. 你的回复只是你对家长处境的理解和一个引导性问题，不是家庭的事实记录，"
    "也不是最终答案。"
)

COACH_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reflection": {
            "type": "string",
            "minLength": 1,
            "description": "对家长当前处境的理解性反馈，不含建议或诊断。",
        },
        "guiding_question": {
            "type": "string",
            "minLength": 1,
            "description": "一个具体的、能推进家长自己思考的苏格拉底式提问。",
        },
        "boundary_note": {
            "type": "string",
            "description": "可选：对本次回复边界的补充说明，例如提示家长这只是引导不是诊断。",
        },
    },
    "required": ["reflection", "guiding_question"],
}


@dataclass(frozen=True, slots=True)
class CoachProvenance:
    """A narrowed, coach-facing view of `AiProvenance`.

    Carries exactly the identifiers a caller needs to explain "why did the
    coach say this" (PIPL 第24条) without re-exporting the full gateway
    contract type into every consumer.
    """

    provider_id: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str
    context_snapshot_ref: str
    latency_ms: int
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class CoachPerspective:
    """The AI Coach's Perspective — never a Fact, never auto-actionable.

    `boundary_note` always carries the governance label even when the model
    did not supply one, so a caller cannot forward a response that forgets to
    say what kind of artifact this is.
    """

    reflection: str
    guiding_question: str
    boundary_note: str
    provenance: CoachProvenance


BOUNDARY_LABEL = "AI_PERSPECTIVE_NOT_FAMILY_FACT_GUIDANCE_NOT_ANSWER"

COACH_PROMPT_REF = "family-ai-coach/socratic-perspective"
COACH_SYSTEM_POLICY_REF = "family-ai-coach/system-policy"
COACH_SAFETY_POLICY_VERSION = "family-ai-coach-safety-v1"


def _build_prompt_execution_plan() -> PromptExecutionPlan:
    """The reviewed prompt content the OpenAI-compatible adapter requires.

    `FakeProvider` never reads this (it echoes canned/computed output without
    inspecting the request), so it is optional for gateway-agnostic tests, but
    the real adapter's `_system_prompt` raises without one — so this module
    always builds one rather than making callers remember to.
    """

    digest = hashlib.sha256(
        f"{COACH_PROMPT_REF}:{COACH_PROMPT_VERSION}:{COACH_SYSTEM_PROMPT}".encode()
    ).hexdigest()
    return PromptExecutionPlan(
        prompt_ref=COACH_PROMPT_REF,
        prompt_version=COACH_PROMPT_VERSION,
        template=COACH_SYSTEM_PROMPT,
        system_policy_ref=COACH_SYSTEM_POLICY_REF,
        safety_policy_version=COACH_SAFETY_POLICY_VERSION,
        knowledge_refs=(),
        asset_digest=digest,
    )


def _validate_output_shape(output: dict) -> None:
    """Narrow post-condition check on top of the gateway's own schema validation.

    The gateway already fails closed on a malformed response before this
    function ever runs (`generate_structured` raises `ModelGatewayError` for a
    schema-invalid draft). This is a second, cheap check against accidental
    empty-string content slipping through a schema that only checks presence
    and `minLength` — defence in depth, not a replacement for the gateway's
    fail-closed contract.
    """

    reflection = output.get("reflection")
    guiding_question = output.get("guiding_question")
    if not isinstance(reflection, str) or not reflection.strip():
        raise ValueError("AI_COACH_REFLECTION_MISSING_OR_EMPTY")
    if not isinstance(guiding_question, str) or not guiding_question.strip():
        raise ValueError("AI_COACH_GUIDING_QUESTION_MISSING_OR_EMPTY")


def _to_perspective(draft: ModelDraft) -> CoachPerspective:
    _validate_output_shape(draft.output)
    provenance: AiProvenance = draft.provenance
    boundary_note = str(draft.output.get("boundary_note") or "").strip()
    return CoachPerspective(
        reflection=draft.output["reflection"],
        guiding_question=draft.output["guiding_question"],
        boundary_note=boundary_note or BOUNDARY_LABEL,
        provenance=CoachProvenance(
            provider_id=provenance.provider_id,
            model=provenance.model,
            model_version=provenance.model_version,
            prompt_version=provenance.prompt_version,
            schema_version=provenance.schema_version,
            context_snapshot_ref=provenance.context_snapshot_ref,
            latency_ms=provenance.latency_ms,
            confidence=provenance.confidence,
        ),
    )


class CoachMemoryStore(Protocol):
    """The narrow slice of `SqlAlchemyMemoryStore` the coach's memory helpers
    need. A `Protocol`, not the concrete class, so this generic-runtime module
    stays testable against any store shape (including a fake) without
    importing the SQLAlchemy adapter (R7/R10: keep the generic layer
    infrastructure-agnostic)."""

    async def put(self, memory: MemoryRef) -> MemoryRef: ...

    async def list_recent_by_source_prefix(
        self,
        source_ref_prefix: str,
        scope: ExperienceScope,
        *,
        purpose: str,
        limit: int = 3,
        moment: datetime | None = None,
    ) -> list[MemoryRef]: ...


COACH_MEMORY_PURPOSE = "family_ai_coach_conversation_continuity"
COACH_MEMORY_RETENTION_POLICY = "family-ai-coach-session-memory.v1"
COACH_MEMORY_SESSION_TTL = timedelta(days=30)
_COACH_MEMORY_SOURCE_PREFIX = "family-ai-coach-turn:"


def _coach_memory_source_ref(*, tenant_id: str, family_id: str, need_id: str) -> str:
    """A stable, honest key: one memory "thread" per (tenant, family, need).

    Used both as `source_ref` on write and as the prefix scanned on read, so
    a later audit can see exactly why a given memory row was written for this
    need without any separate lookup table.
    """

    return f"{_COACH_MEMORY_SOURCE_PREFIX}{tenant_id}:{family_id}:{need_id}:"


def _coach_memory_scope(
    *, tenant_id: str, family_id: str, subject_ids: tuple[str, ...], consent_version: str
) -> ExperienceScope:
    return ExperienceScope(
        global_id=f"family-ai-coach:{tenant_id}:{family_id}",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subject_ids,
        purpose=COACH_MEMORY_PURPOSE,
        consent_version=consent_version,
        consent_granted=True,
        data_class="FAMILY_PRIVATE_TEXT",
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef(
            deletion_id=f"family-ai-coach-memory:{tenant_id}:{family_id}",
            retention_policy=COACH_MEMORY_RETENTION_POLICY,
        ),
        correlation_id=f"family-ai-coach-memory:{tenant_id}:{family_id}",
        causation_id=f"family-ai-coach-memory:{tenant_id}:{family_id}",
    )


async def retrieve_recent_coach_turns(
    memory_store: CoachMemoryStore,
    *,
    tenant_id: str,
    family_id: str,
    need_id: str,
    subject_ids: tuple[str, ...] = (),
    consent_version: str = "family-ai-coach-memory-consent.v1",
    limit: int = 3,
) -> list[dict]:
    """Most-recent-first prior turns for this need, as plain dicts.

    Returns `[]` on any scope/consent/expiry rejection or when no memory
    exists yet — a brand-new conversation is not an error, it is turn one.
    Each dict carries exactly what was stored: `parent_message`, `reflection`,
    `guiding_question`, and `recorded_at` (ISO 8601) — enough for a caller to
    render "what was said before" without reconstructing it from provenance.
    """

    scope = _coach_memory_scope(
        tenant_id=tenant_id,
        family_id=family_id,
        subject_ids=subject_ids,
        consent_version=consent_version,
    )
    prefix = _coach_memory_source_ref(tenant_id=tenant_id, family_id=family_id, need_id=need_id)
    memories = await memory_store.list_recent_by_source_prefix(
        prefix, scope, purpose=COACH_MEMORY_PURPOSE, limit=limit
    )
    return [_decode_turn_payload(memory) for memory in memories]


def _encode_turn_payload(
    *, parent_message: str, reflection: str, guiding_question: str, recorded_at: datetime
) -> str:
    return json.dumps(
        {
            "parent_message": parent_message,
            "reflection": reflection,
            "guiding_question": guiding_question,
            "recorded_at": recorded_at.isoformat(),
        },
        ensure_ascii=False,
    )


def _decode_turn_payload(memory: MemoryRef) -> dict:
    try:
        decoded = json.loads(memory.provenance.model_attempt_ref or "{}")
    except (TypeError, ValueError):
        decoded = {}
    return {
        "parent_message": str(decoded.get("parent_message", "")),
        "reflection": str(decoded.get("reflection", "")),
        "guiding_question": str(decoded.get("guiding_question", "")),
        "recorded_at": str(decoded.get("recorded_at", "")),
    }


async def store_coach_turn(
    memory_store: CoachMemoryStore,
    *,
    tenant_id: str,
    family_id: str,
    need_id: str,
    parent_message: str,
    perspective: CoachPerspective,
    subject_ids: tuple[str, ...] = (),
    consent_version: str = "family-ai-coach-memory-consent.v1",
    now: datetime | None = None,
) -> MemoryRef:
    """Persist one conversational turn (parent question + coach perspective)
    as an `M1_SESSION` memory so the next call can see it.

    `M1_SESSION` (not `M3_DURABLE`): this is conversational continuity within
    an active coaching thread, not a durable fact about the family — it still
    expires (`COACH_MEMORY_SESSION_TTL`) like every memory level must
    (`MemoryRef`'s own docstring: "there is no unlimited-memory mode").
    """

    moment = now or datetime.now(UTC)
    memory_id = f"family-ai-coach-turn:{tenant_id}:{family_id}:{need_id}:{uuid4().hex}"
    source_ref = (
        f"{_coach_memory_source_ref(tenant_id=tenant_id, family_id=family_id, need_id=need_id)}"
        f"{memory_id}"
    )
    turn_payload = _encode_turn_payload(
        parent_message=parent_message,
        reflection=perspective.reflection,
        guiding_question=perspective.guiding_question,
        recorded_at=moment,
    )
    provenance = ExperienceProvenance(
        provenance_ref=f"family-ai-coach-turn-provenance:{memory_id}",
        source_refs=(perspective.provenance.context_snapshot_ref,),
        kind=ProvenanceKind.AI_DRAFT,
        policy_version=COACH_PROMPT_VERSION,
        context_snapshot_ref=perspective.provenance.context_snapshot_ref,
        model_attempt_ref=turn_payload,
        captured_at=moment,
    )
    memory = MemoryRef(
        memory_id=memory_id,
        memory_ref=f"family-ai-coach-turn-ref:{memory_id}",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subject_ids,
        memory_scope=MemoryScope.FAMILY_RELATIONSHIP
        if len(subject_ids) >= 2
        else (MemoryScope.CHILD if subject_ids else MemoryScope.GUARDIAN),
        level=MemoryLevel.M1_SESSION,
        purpose=COACH_MEMORY_PURPOSE,
        consent_version=consent_version,
        consent_granted=True,
        data_class="FAMILY_PRIVATE_TEXT",
        locale="zh-CN",
        provenance=provenance,
        deletion_ref=DeletionRef(
            deletion_id=f"family-ai-coach-memory:{tenant_id}:{family_id}",
            retention_policy=COACH_MEMORY_RETENTION_POLICY,
        ),
        source_ref=source_ref,
        correlation_id=f"family-ai-coach-memory:{tenant_id}:{family_id}",
        causation_id=memory_id,
        created_at=moment,
        expires_at=moment + COACH_MEMORY_SESSION_TTL,
    )
    return await memory_store.put(memory)


def _format_history_for_prompt(history: list[dict]) -> str:
    """Render prior turns oldest-first as readable Chinese conversation log
    text for injection into the model payload — never structured JSON dumped
    raw into a prompt, so the model reads it the way a transcript reads."""

    if not history:
        return ""
    lines = ["以下是这次对话之前的往来（按时间顺序）："]
    for turn in reversed(history):
        if turn.get("parent_message"):
            lines.append(f"家长：{turn['parent_message']}")
        if turn.get("reflection") or turn.get("guiding_question"):
            coach_line = " ".join(
                part for part in (turn.get("reflection"), turn.get("guiding_question")) if part
            )
            lines.append(f"教练：{coach_line}")
    return "\n".join(lines)


async def coach_reply(
    gateway: ModelGateway,
    *,
    provider_id: str,
    family_context: dict,
    parent_message: str,
    tenant_id: str,
    family_id: str,
    context_snapshot_ref: str,
    data_class: DataClass,
    request_id: str | None = None,
    memory_store: CoachMemoryStore | None = None,
    need_id: str | None = None,
    subject_ids: tuple[str, ...] = (),
    consent_version: str = "family-ai-coach-memory-consent.v1",
    memory_history_limit: int = 3,
) -> CoachPerspective:
    """Call the real model to produce one Socratic-guidance Perspective.

    `data_class` has no default on purpose: this content is genuinely
    family-private (or minor-personal, depending on the need's subjects), and
    every registered provider's §16 admission rights are data-class specific
    (see `ai_coach_wiring.py`). A silent default here would let a caller pick
    whichever class happens to be admissible instead of the one the content
    actually is — the same reasoning `StructuredRequest.output_schema` uses
    for having no default.

    `family_context` must already be a real, non-fabricated payload assembled
    by the caller from the family_need domain (statement/desired_outcome/
    intervention_tier/matched supply, when present) — this function does not
    reach into any repository itself (R7/R10: the generic AI Runtime layer
    does not import a domain).

    `memory_store`/`need_id` are optional: when both are supplied, this
    function reads the last `memory_history_limit` turns for this need before
    calling the model (so the reply can actually reference what was said
    before) and writes this turn back after a successful call. Omitting them
    keeps the previous single-turn behaviour — the AI Native Principles §4
    "gets better with use" property is additive, not a hard requirement of the
    minimal signature every caller (including the real-model livecheck test,
    which does not have a memory store wired) must supply.
    """

    if not parent_message.strip():
        raise ValueError("AI_COACH_PARENT_MESSAGE_REQUIRED")
    if not tenant_id.strip() or not family_id.strip():
        raise ValueError("AI_COACH_TENANT_FAMILY_SCOPE_REQUIRED")
    if not context_snapshot_ref.strip():
        raise ValueError("AI_COACH_CONTEXT_SNAPSHOT_REF_REQUIRED")

    conversation_history: list[dict] = []
    if memory_store is not None and need_id is not None:
        conversation_history = await retrieve_recent_coach_turns(
            memory_store,
            tenant_id=tenant_id,
            family_id=family_id,
            need_id=need_id,
            subject_ids=subject_ids,
            consent_version=consent_version,
            limit=memory_history_limit,
        )

    payload = {
        "system_instructions": COACH_SYSTEM_PROMPT,
        "family_context": family_context,
        "parent_message": parent_message,
    }
    history_text = _format_history_for_prompt(conversation_history)
    if history_text:
        payload["conversation_history"] = history_text
    request = StructuredRequest(
        use_case=COACH_USE_CASE,
        prompt_version=COACH_PROMPT_VERSION,
        schema_version=COACH_SCHEMA_VERSION,
        data_class=data_class,
        payload=payload,
        output_schema=COACH_OUTPUT_SCHEMA,
        context_snapshot_ref=context_snapshot_ref,
        request_id=request_id,
        policy_context=PolicyContext(),
        tenant_id=tenant_id,
        family_id=family_id,
        prompt_execution_plan=_build_prompt_execution_plan(),
    )
    draft = await gateway.generate_structured(request, provider_id=provider_id)
    perspective = _to_perspective(draft)

    # `subject_ids` empty is a legitimate need (not every family need names a
    # specific child subject) — `MemoryRef.__post_init__` hard-requires at
    # least one subject to scope a *write* to (memory must always be scoped
    # to a real subject for consent/deletion), so a need with no subject
    # simply has no cross-turn memory to write. This is the same
    # "gracefully skip, do not fail the reply" posture omitting
    # `memory_store`/`need_id` already has — an empty `subject_ids` must not
    # turn a reply that otherwise succeeded into a 502.
    if memory_store is not None and need_id is not None and subject_ids:
        await store_coach_turn(
            memory_store,
            tenant_id=tenant_id,
            family_id=family_id,
            need_id=need_id,
            parent_message=parent_message,
            perspective=perspective,
            subject_ids=subject_ids,
            consent_version=consent_version,
        )

    return perspective
