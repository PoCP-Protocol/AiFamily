from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.intelligence.experience.contract_binding import (
    MultimodalContractBindingError,
    MultimodalContractRegistryBinding,
    ReleaseContractExpectation,
)
from backend.intelligence.experience.execution_materials import (
    InMemoryExecutionMaterialRegistry,
    SystemPolicyMaterial,
)
from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.registry import SchemaRegistry


def _binding() -> MultimodalContractRegistryBinding:
    effective_at = datetime(2026, 1, 1, tzinfo=UTC)
    prompt = PromptBundle(
        prompt_ref="experience.prompt",
        version="v1",
        use_case="family-image-summary",
        agent_id="family-experience",
        template="请基于已授权证据给出结构化家庭陪伴草稿。",
        system_policy_ref="policy:experience.v1",
        knowledge_refs=(),
        input_contract_ref="input:experience.v1",
        output_schema_ref="experience.schema",
        safety_policy_version="safety.v1",
        locale="zh-CN",
        author="test",
        reviewer="reviewer",
        status="PUBLISHED",
        effective_at=effective_at,
    )
    output_schema = {
        "type": "object",
        "required": ["headline"],
        "properties": {"headline": {"type": "string"}},
    }
    schema = SchemaDefinition(
        schema_ref="experience.schema",
        version="v1",
        use_case="family-image-summary",
        agent_id="family-experience",
        object_type="ExperienceDraft",
        required_fields=("headline",),
        json_schema=output_schema,
        author="test",
        reviewer="reviewer",
        status="PUBLISHED",
        effective_at=effective_at,
    )
    return MultimodalContractRegistryBinding(
        prompt_registry=PromptRegistry(bundles=(prompt,)),
        schema_registry=SchemaRegistry(definitions=(schema,)),
        agent_id="family-experience",
        prompt_ref="experience.prompt",
        schema_ref="experience.schema",
        material_resolver=InMemoryExecutionMaterialRegistry(
            policies=(
                SystemPolicyMaterial.build(
                    policy_ref="policy:experience.v1",
                    use_case="family-image-summary",
                    agent_id="family-experience",
                    content="只生成待人工确认的草稿。",
                    locale="zh-CN",
                    status="PUBLISHED",
                    reviewer="reviewer",
                    effective_at=effective_at,
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_binding_resolves_reviewed_prompt_and_schema_as_one_pair() -> None:
    binding = _binding()
    resolved = await binding.resolve(
        use_case="family-image-summary",
        prompt_version="v1",
        schema_version="v1",
        output_schema={
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
    )

    assert resolved.prompt_ref == "experience.prompt"
    assert resolved.schema_ref == "experience.schema"
    assert resolved.agent_id == "family-experience"
    assert resolved.output_schema["required"] == ["headline"]
    assert resolved.prompt_execution_plan.template == "请基于已授权证据给出结构化家庭陪伴草稿。"
    assert resolved.prompt_execution_plan.prompt_ref == resolved.prompt_ref
    assert resolved.prompt_execution_plan.asset_digest == resolved.asset_digest


@pytest.mark.asyncio
async def test_binding_rejects_client_schema_drift() -> None:
    with pytest.raises(
        MultimodalContractBindingError, match="CLIENT_SCHEMA_DOES_NOT_MATCH_REGISTRY"
    ):
        await _binding().resolve(
            use_case="family-image-summary",
            prompt_version="v1",
            schema_version="v1",
            output_schema={"type": "object", "properties": {"forged": {"type": "string"}}},
        )


@pytest.mark.asyncio
async def test_binding_rejects_use_case_or_version_mismatch() -> None:
    with pytest.raises(MultimodalContractBindingError, match="PROMPT_OR_SCHEMA_NOT_FOUND"):
        await _binding().resolve(
            use_case="other-use-case",
            prompt_version="v1",
            schema_version="v1",
            output_schema={"type": "object"},
        )


@pytest.mark.asyncio
async def test_active_release_rejects_same_version_prompt_content_drift() -> None:
    binding = _binding()
    schema = {
        "type": "object",
        "required": ["headline"],
        "properties": {"headline": {"type": "string"}},
    }
    resolved = await binding.resolve(
        use_case="family-image-summary",
        prompt_version="v1",
        schema_version="v1",
        output_schema=schema,
    )
    release_bound = replace(
        binding,
        release_expectation=ReleaseContractExpectation(
            agent_id=resolved.agent_id,
            prompt_ref=resolved.prompt_ref,
            prompt_version=resolved.prompt_version,
            schema_ref=resolved.schema_ref,
            schema_version=resolved.schema_version,
            safety_policy_version=resolved.safety_policy_version,
            knowledge_refs=resolved.knowledge_refs,
            asset_digest="0" * 64,
        ),
    )
    with pytest.raises(
        MultimodalContractBindingError,
        match="ACTIVE_RELEASE_CONTRACT_MISMATCH",
    ):
        await release_bound.resolve(
            use_case="family-image-summary",
            prompt_version="v1",
            schema_version="v1",
            output_schema=schema,
        )


@pytest.mark.asyncio
async def test_active_release_rejects_missing_execution_material_before_call() -> None:
    binding = _binding()
    schema = {
        "type": "object",
        "required": ["headline"],
        "properties": {"headline": {"type": "string"}},
    }
    resolved = await binding.resolve(
        use_case="family-image-summary",
        prompt_version="v1",
        schema_version="v1",
        output_schema=schema,
    )
    release_bound = replace(
        binding,
        material_resolver=InMemoryExecutionMaterialRegistry(),
        release_expectation=ReleaseContractExpectation(
            agent_id=resolved.agent_id,
            prompt_ref=resolved.prompt_ref,
            prompt_version=resolved.prompt_version,
            schema_ref=resolved.schema_ref,
            schema_version=resolved.schema_version,
            safety_policy_version=resolved.safety_policy_version,
            knowledge_refs=resolved.knowledge_refs,
            asset_digest=resolved.asset_digest,
        ),
    )

    with pytest.raises(
        MultimodalContractBindingError,
        match="EXECUTION_MATERIAL_NOT_ELIGIBLE",
    ):
        await release_bound.resolve(
            use_case="family-image-summary",
            prompt_version="v1",
            schema_version="v1",
            output_schema=schema,
        )
