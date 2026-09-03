from __future__ import annotations

from backend.intelligence.experience.standard_contracts import (
    FAMILY_EXPERIENCE_AGENT_ID,
    FAMILY_EXPERIENCE_PROMPT_REF,
    FAMILY_EXPERIENCE_SCHEMA_REF,
    FAMILY_EXPERIENCE_USE_CASE,
    build_family_experience_contract_binding,
)
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.schema_registry.registry import SchemaRegistry


def test_family_experience_contract_selectors_are_canonical() -> None:
    binding = build_family_experience_contract_binding(
        prompt_registry=PromptRegistry(), schema_registry=SchemaRegistry()
    )

    assert FAMILY_EXPERIENCE_USE_CASE == "family_assistant_conversation"
    assert binding.agent_id == FAMILY_EXPERIENCE_AGENT_ID == "parent_advisor"
    assert binding.prompt_ref == FAMILY_EXPERIENCE_PROMPT_REF == "family_assistant_v1"
    assert binding.schema_ref == FAMILY_EXPERIENCE_SCHEMA_REF == "assistant_response_v1"
