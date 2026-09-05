"""Canonical Prompt/Schema selectors for the family experience use case.

This module owns names only; the reviewed PromptBundle and SchemaDefinition
remain in the configured Prompt/Schema Registry.  Keeping selectors here
prevents each UI or composition root from inventing a second ref/agent mapping.
"""

from __future__ import annotations

from backend.intelligence.experience.contract_binding import (
    MultimodalContractRegistryBinding,
)

FAMILY_EXPERIENCE_USE_CASE = "family_assistant_conversation"
FAMILY_EXPERIENCE_AGENT_ID = "parent_advisor"
FAMILY_EXPERIENCE_PROMPT_REF = "family_assistant_v1"
FAMILY_EXPERIENCE_SCHEMA_REF = "assistant_response_v1"


def build_family_experience_contract_binding(
    *,
    prompt_registry: object,
    schema_registry: object,
    material_resolver: object | None = None,
) -> MultimodalContractRegistryBinding:
    """Build the reviewed family-assistant binding for an explicit registry."""

    return MultimodalContractRegistryBinding(
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        agent_id=FAMILY_EXPERIENCE_AGENT_ID,
        prompt_ref=FAMILY_EXPERIENCE_PROMPT_REF,
        schema_ref=FAMILY_EXPERIENCE_SCHEMA_REF,
        material_resolver=material_resolver,
    )


__all__ = [
    "FAMILY_EXPERIENCE_AGENT_ID",
    "FAMILY_EXPERIENCE_PROMPT_REF",
    "FAMILY_EXPERIENCE_SCHEMA_REF",
    "FAMILY_EXPERIENCE_USE_CASE",
    "build_family_experience_contract_binding",
]
