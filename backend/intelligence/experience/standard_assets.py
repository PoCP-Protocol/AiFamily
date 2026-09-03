"""Reviewed-asset factory for the canonical family experience contract.

The selector in :mod:`standard_contracts` owns stable names.  This module
owns the content-addressed Prompt/Schema fixture used by dev/test composition
roots and by the review workflow.  The default bundle is deliberately DRAFT;
callers must provide an explicit reviewer and effective time before creating a
PUBLISHED snapshot.  No provider SDK or business-domain repository is
imported here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.schema_registry.contracts import SchemaDefinition

from .execution_materials import KnowledgeExecutionMaterial, SystemPolicyMaterial
from .standard_contracts import (
    FAMILY_EXPERIENCE_AGENT_ID,
    FAMILY_EXPERIENCE_PROMPT_REF,
    FAMILY_EXPERIENCE_SCHEMA_REF,
    FAMILY_EXPERIENCE_USE_CASE,
)

FAMILY_EXPERIENCE_PROMPT_VERSION = "family-companion.v1"
FAMILY_EXPERIENCE_SCHEMA_VERSION = "family-experience-draft.v1"
FAMILY_EXPERIENCE_SYSTEM_POLICY_REF = "family-safety.v1"
FAMILY_EXPERIENCE_SAFETY_POLICY_VERSION = "family-safety.v1"
FAMILY_EXPERIENCE_INPUT_CONTRACT_REF = "multimodal-experience-input.v1"
FAMILY_EXPERIENCE_KNOWLEDGE_REF = "family_assistant_knowledge_v1"

_FAMILY_EXPERIENCE_TEMPLATE = """你是 AiFamily 的家庭助手，只能生成供家庭成员理解和人工确认的
结构化草稿。

请基于请求中明确提供的上下文和证据，输出 JSON 对象，字段为：
- understanding：用温和、简短的语言说明你理解到的情况；不把推测写成事实。
- next_step：只给一个可选择的小步骤，由家长或指定人工角色确认后执行。
- limitations：列出不确定性、缺失信息和需要人工判断的边界，至少保留一条。

必须遵守：不做诊断，不给出法律或医疗结论，不向未成年人做商业营销，不创建或改写家庭权威事实；
遇到高风险、无法确认或要求人工介入的情况，应在 limitations 中明确说明并建议人工处理。
"""

_FAMILY_EXPERIENCE_SYSTEM_POLICY = """你只能生成结构化 DRAFT，不能写入或改写家庭事实。
不得生成家庭总分、家庭排名、未成年人画像营销、医疗或法律结论。所有建议必须保留人工确认，
证据不足时明确说明限制，不得把推断表述为已验证事实。"""

_FAMILY_EXPERIENCE_KNOWLEDGE = """家庭成长支持应优先使用可选择、低压力的小步骤。
描述观察与建议时区分事实、解释和假设；当材料不足或涉及安全风险时，应建议由监护人或专业人员判断。
这是一条经审核的通用共享指导，不代表任何具体家庭事实。"""

_FAMILY_EXPERIENCE_JSON_SCHEMA = {
    "type": "object",
    "required": ["understanding", "next_step", "limitations"],
    "properties": {
        "understanding": {"type": "string", "minLength": 1},
        "next_step": {"type": "string", "minLength": 1},
        "limitations": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "additionalProperties": False,
}

_FORBIDDEN_OUTPUT_FIELDS = frozenset(
    {
        "diagnosis",
        "legal_or_medical_conclusion",
        "commercial_marketing_to_minor",
        "canonical_fact",
        "family_total_score",
        "family_ranking",
    }
)

AssetStatus = Literal["DRAFT", "REVIEW", "PUBLISHED", "RETIRED"]


@dataclass(frozen=True, slots=True)
class FamilyExperienceAssetBundle:
    """The Prompt and Schema that must move through review as one unit."""

    prompt: PromptBundle
    schema: SchemaDefinition
    system_policy: SystemPolicyMaterial
    knowledge: tuple[KnowledgeExecutionMaterial, ...]

    def __post_init__(self) -> None:
        if self.prompt.prompt_ref != FAMILY_EXPERIENCE_PROMPT_REF:
            raise ValueError("family experience prompt ref mismatch")
        if self.schema.schema_ref != FAMILY_EXPERIENCE_SCHEMA_REF:
            raise ValueError("family experience schema ref mismatch")
        if self.prompt.version != FAMILY_EXPERIENCE_PROMPT_VERSION:
            raise ValueError("family experience prompt version mismatch")
        if self.schema.version != FAMILY_EXPERIENCE_SCHEMA_VERSION:
            raise ValueError("family experience schema version mismatch")
        if self.prompt.use_case != FAMILY_EXPERIENCE_USE_CASE:
            raise ValueError("family experience prompt use-case mismatch")
        if self.schema.use_case != FAMILY_EXPERIENCE_USE_CASE:
            raise ValueError("family experience schema use-case mismatch")
        if self.prompt.agent_id != FAMILY_EXPERIENCE_AGENT_ID:
            raise ValueError("family experience prompt agent mismatch")
        if self.schema.agent_id != FAMILY_EXPERIENCE_AGENT_ID:
            raise ValueError("family experience schema agent mismatch")
        if self.prompt.output_schema_ref != self.schema.schema_ref:
            raise ValueError("family experience prompt/schema refs are not bound")
        if self.prompt.status != self.schema.status:
            raise ValueError("family experience prompt/schema lifecycle must match")
        if self.system_policy.policy_ref != self.prompt.system_policy_ref:
            raise ValueError("family experience system policy ref mismatch")
        if tuple(item.knowledge_ref for item in self.knowledge) != self.prompt.knowledge_refs:
            raise ValueError("family experience knowledge refs mismatch")
        if self.system_policy.status != self.prompt.status or any(
            item.status != self.prompt.status for item in self.knowledge
        ):
            raise ValueError("family experience material lifecycle must match")

    @property
    def status(self) -> AssetStatus:
        return self.prompt.status


def build_family_experience_assets(
    *,
    status: AssetStatus = "DRAFT",
    author: str = "family-experience",
    reviewer: str | None = None,
    effective_at: datetime | None = None,
    retired_at: datetime | None = None,
    change_reason: str = "",
) -> FamilyExperienceAssetBundle:
    """Build one immutable asset pair for explicit Registry registration.

    ``status='DRAFT'`` is the safe default.  Published assets are never
    implied by a test environment: the underlying value objects require both
    ``reviewer`` and ``effective_at`` and the caller owns that approval
    decision.
    """

    if status not in {"DRAFT", "REVIEW", "PUBLISHED", "RETIRED"}:
        raise ValueError(f"unknown family experience asset status: {status}")
    if not author or not author.strip():
        raise ValueError("family experience asset author is required")
    prompt = PromptBundle(
        prompt_ref=FAMILY_EXPERIENCE_PROMPT_REF,
        version=FAMILY_EXPERIENCE_PROMPT_VERSION,
        use_case=FAMILY_EXPERIENCE_USE_CASE,
        agent_id=FAMILY_EXPERIENCE_AGENT_ID,
        template=_FAMILY_EXPERIENCE_TEMPLATE,
        system_policy_ref=FAMILY_EXPERIENCE_SYSTEM_POLICY_REF,
        knowledge_refs=(FAMILY_EXPERIENCE_KNOWLEDGE_REF,),
        input_contract_ref=FAMILY_EXPERIENCE_INPUT_CONTRACT_REF,
        output_schema_ref=FAMILY_EXPERIENCE_SCHEMA_REF,
        safety_policy_version=FAMILY_EXPERIENCE_SAFETY_POLICY_VERSION,
        locale="zh-CN",
        author=author,
        reviewer=reviewer,
        status=status,
        effective_at=effective_at,
        retired_at=retired_at,
        change_reason=change_reason,
    )
    schema = SchemaDefinition(
        schema_ref=FAMILY_EXPERIENCE_SCHEMA_REF,
        version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
        use_case=FAMILY_EXPERIENCE_USE_CASE,
        agent_id=FAMILY_EXPERIENCE_AGENT_ID,
        object_type="FamilyExperienceDraft",
        required_fields=("understanding", "next_step", "limitations"),
        forbidden_fields=_FORBIDDEN_OUTPUT_FIELDS,
        allowed_fields=frozenset({"understanding", "next_step", "limitations"}),
        boundary_labels=("DRAFT_ONLY", "FAMILY_PRIVATE", "HUMAN_REVIEW_REQUIRED"),
        human_gate_rule="REVIEW_REQUIRED",
        json_schema=_FAMILY_EXPERIENCE_JSON_SCHEMA,
        status=status,
        effective_at=effective_at,
        retired_at=retired_at,
        author=author,
        reviewer=reviewer,
        change_reason=change_reason,
        visibility="FAMILY_PRIVATE",
        write_back_target="DERIVED_ARTIFACT",
    )
    system_policy = SystemPolicyMaterial.build(
        policy_ref=FAMILY_EXPERIENCE_SYSTEM_POLICY_REF,
        use_case=FAMILY_EXPERIENCE_USE_CASE,
        agent_id=FAMILY_EXPERIENCE_AGENT_ID,
        content=_FAMILY_EXPERIENCE_SYSTEM_POLICY,
        locale="zh-CN",
        status=status,
        reviewer=reviewer,
        effective_at=effective_at,
        retired_at=retired_at,
    )
    knowledge = (
        KnowledgeExecutionMaterial.build(
            knowledge_ref=FAMILY_EXPERIENCE_KNOWLEDGE_REF,
            use_case=FAMILY_EXPERIENCE_USE_CASE,
            content=_FAMILY_EXPERIENCE_KNOWLEDGE,
            source_ref="source:aifamily-reviewed-family-guidance:v1",
            license_ref="license:aifamily-internal-reviewed-content",
            evidence_level="E3",
            status=status,
            reviewer=reviewer,
            effective_at=effective_at,
            retired_at=retired_at,
        ),
    )
    return FamilyExperienceAssetBundle(
        prompt=prompt,
        schema=schema,
        system_policy=system_policy,
        knowledge=knowledge,
    )


def family_experience_output_schema() -> dict[str, object]:
    """Return a mutable transport copy of the reviewed output contract."""

    return deepcopy(_FAMILY_EXPERIENCE_JSON_SCHEMA)


__all__ = [
    "FAMILY_EXPERIENCE_INPUT_CONTRACT_REF",
    "FAMILY_EXPERIENCE_KNOWLEDGE_REF",
    "FAMILY_EXPERIENCE_PROMPT_VERSION",
    "FAMILY_EXPERIENCE_SAFETY_POLICY_VERSION",
    "FAMILY_EXPERIENCE_SCHEMA_VERSION",
    "FAMILY_EXPERIENCE_SYSTEM_POLICY_REF",
    "FamilyExperienceAssetBundle",
    "build_family_experience_assets",
    "family_experience_output_schema",
]
