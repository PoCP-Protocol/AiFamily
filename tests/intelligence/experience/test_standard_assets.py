from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.intelligence.experience.contract_binding import MultimodalContractRegistryBinding
from backend.intelligence.experience.execution_materials import (
    InMemoryExecutionMaterialRegistry,
)
from backend.intelligence.experience.standard_asset_registration import (
    FamilyExperienceAssetRegistrationError,
    register_family_experience_assets,
)
from backend.intelligence.experience.standard_assets import (
    FAMILY_EXPERIENCE_PROMPT_VERSION,
    FAMILY_EXPERIENCE_SCHEMA_VERSION,
    FamilyExperienceAssetBundle,
    build_family_experience_assets,
)
from backend.intelligence.experience.standard_contracts import (
    FAMILY_EXPERIENCE_AGENT_ID,
    FAMILY_EXPERIENCE_PROMPT_REF,
    FAMILY_EXPERIENCE_SCHEMA_REF,
    FAMILY_EXPERIENCE_USE_CASE,
)
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.schema_registry.registry import SchemaRegistry
from backend.intelligence.schema_registry.validator import (
    SchemaValidationError,
    SchemaValidator,
)

NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def test_family_experience_asset_factory_defaults_to_safe_draft() -> None:
    assets = build_family_experience_assets()

    assert isinstance(assets, FamilyExperienceAssetBundle)
    assert assets.status == "DRAFT"
    assert assets.prompt.version == FAMILY_EXPERIENCE_PROMPT_VERSION
    assert assets.schema.version == FAMILY_EXPERIENCE_SCHEMA_VERSION
    assert assets.prompt.prompt_ref == FAMILY_EXPERIENCE_PROMPT_REF
    assert assets.schema.schema_ref == FAMILY_EXPERIENCE_SCHEMA_REF
    assert assets.prompt.use_case == assets.schema.use_case == FAMILY_EXPERIENCE_USE_CASE
    assert assets.prompt.agent_id == assets.schema.agent_id == FAMILY_EXPERIENCE_AGENT_ID
    assert assets.prompt.output_schema_ref == assets.schema.schema_ref
    assert assets.schema.human_gate_rule == "REVIEW_REQUIRED"
    assert assets.schema.forbidden_fields >= {
        "diagnosis",
        "legal_or_medical_conclusion",
        "canonical_fact",
    }


@pytest.mark.asyncio
async def test_published_asset_pair_resolves_as_one_contract() -> None:
    assets = build_family_experience_assets(
        status="PUBLISHED",
        reviewer="reviewer-1",
        effective_at=NOW,
    )
    prompts = PromptRegistry(bundles=(assets.prompt,))
    schemas = SchemaRegistry(definitions=(assets.schema,))
    binding = MultimodalContractRegistryBinding(
        prompt_registry=prompts,
        schema_registry=schemas,
        agent_id=FAMILY_EXPERIENCE_AGENT_ID,
        prompt_ref=FAMILY_EXPERIENCE_PROMPT_REF,
        schema_ref=FAMILY_EXPERIENCE_SCHEMA_REF,
    )

    resolved = await binding.resolve(
        use_case=FAMILY_EXPERIENCE_USE_CASE,
        prompt_version=FAMILY_EXPERIENCE_PROMPT_VERSION,
        schema_version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
        output_schema=dict(assets.schema.json_schema),
    )

    assert resolved.prompt_ref == assets.prompt.prompt_ref
    assert resolved.schema_ref == assets.schema.schema_ref
    assert resolved.agent_id == assets.prompt.agent_id
    assert resolved.output_schema["type"] == "object"
    assert resolved.output_schema["required"] == [
        "understanding",
        "next_step",
        "limitations",
    ]
    assert resolved.output_schema["additionalProperties"] is False


def test_published_asset_requires_review_metadata() -> None:
    with pytest.raises(ValueError, match="reviewer"):
        build_family_experience_assets(status="PUBLISHED", effective_at=NOW)
    with pytest.raises(ValueError, match="effective_at"):
        build_family_experience_assets(status="PUBLISHED", reviewer="reviewer-1")


@pytest.mark.asyncio
async def test_registration_requires_published_pair_and_preflights_duplicates() -> None:
    prompts = PromptRegistry()
    schemas = SchemaRegistry()
    materials = InMemoryExecutionMaterialRegistry()
    draft = build_family_experience_assets()

    with pytest.raises(FamilyExperienceAssetRegistrationError, match="published"):
        await register_family_experience_assets(
            assets=draft,
            prompt_registry=prompts,
            schema_registry=schemas,
            material_registry=materials,
        )
    assert prompts.get(draft.prompt.prompt_ref, draft.prompt.version) is None
    assert schemas.get(draft.schema.schema_ref, draft.schema.version) is None

    published = build_family_experience_assets(
        status="PUBLISHED",
        reviewer="reviewer-1",
        effective_at=NOW,
    )
    registered = await register_family_experience_assets(
        assets=published,
        prompt_registry=prompts,
        schema_registry=schemas,
        material_registry=materials,
    )
    assert registered.prompt_version == published.prompt.version
    with pytest.raises(FamilyExperienceAssetRegistrationError, match="already registered"):
        await register_family_experience_assets(
            assets=published,
            prompt_registry=prompts,
            schema_registry=schemas,
            material_registry=materials,
        )


def test_schema_rejects_non_draft_fields_and_requires_limitations() -> None:
    schema = build_family_experience_assets().schema
    validator = SchemaValidator()

    with pytest.raises(SchemaValidationError, match="FORBIDDEN_FIELD"):
        validator.validate(
            schema,
            {
                "understanding": "ok",
                "next_step": "ask",
                "limitations": ["人工确认"],
                "diagnosis": "not allowed",
            },
        )
    with pytest.raises(SchemaValidationError, match="REQUIRED_FIELD_MISSING"):
        validator.validate(
            schema,
            {"understanding": "ok", "next_step": "ask"},
        )
