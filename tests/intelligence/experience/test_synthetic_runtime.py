from __future__ import annotations

from dataclasses import replace

import pytest

from backend.intelligence.context_engine.contracts import ContextScopeError, DataClass
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
)
from backend.intelligence.experience.multimodal_routing import MultimodalRouteRequest
from backend.intelligence.experience.standard_assets import (
    FAMILY_EXPERIENCE_PROMPT_VERSION,
    FAMILY_EXPERIENCE_SCHEMA_VERSION,
)
from backend.intelligence.experience.synthetic_runtime import (
    SyntheticRuntimeResolver,
    build_synthetic_runtime,
)


def _runtime():
    return build_synthetic_runtime(
        tenant_id="tenant-synthetic",
        family_id="family-synthetic",
        subject_ids=("guardian-synthetic", "child-synthetic"),
    )


def _command(runtime, *, scope=None) -> ContextBoundMultimodalCommand:
    active_scope = scope or runtime.scope
    return ContextBoundMultimodalCommand(
        run_id="run-synthetic-001",
        route_request=MultimodalRouteRequest(
            use_case=active_scope.purpose,
            data_class=active_scope.data_class.value,
            modalities=("TEXT", "IMAGE"),
            environment=runtime.environment,
            estimated_input_tokens=100,
        ),
        scope=active_scope,
        prompt_version=FAMILY_EXPERIENCE_PROMPT_VERSION,
        schema_version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
        payload={"media_ref": "fixture:image-001"},
        output_schema={
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
        },
    )


def test_factory_requires_explicit_scope_and_has_no_global_defaults() -> None:
    with pytest.raises(ValueError, match="tenant_id must be explicit"):
        build_synthetic_runtime(family_id="family-only", subject_ids=("child",))
    with pytest.raises(ValueError, match="subject_ids must be explicit"):
        build_synthetic_runtime(family_id="family-only", tenant_id="tenant-only")


def test_factory_rejects_production_environment() -> None:
    with pytest.raises(ValueError, match="only supports development or test"):
        build_synthetic_runtime(
            tenant_id="tenant-synthetic",
            family_id="family-synthetic",
            subject_ids=("child-synthetic",),
            environment="production",
        )


def test_factory_preserves_development_environment_identity() -> None:
    runtime = build_synthetic_runtime(
        tenant_id="tenant-development",
        family_id="family-development",
        subject_ids=("child-development",),
        environment="development",
    )

    assert runtime.environment == "development"


@pytest.mark.asyncio
async def test_synthetic_runtime_generates_a_draft_through_gateway() -> None:
    runtime = _runtime()

    result = await runtime.application.generate_draft(_command(runtime))

    assert result.output["understanding"] == "这是由生产同构测试链路生成的合成草案"
    assert result.requires_human_confirmation is True
    assert result.routed.experience.draft.status == "DRAFT"
    assert result.snapshot.scope.data_class is DataClass.SYNTHETIC
    assert result.snapshot.family_id == "family-synthetic"
    provenance = result.routed.experience.draft.provenance
    assert provenance.release_set_id
    assert provenance.bundle_id
    assert provenance.deployment_receipt_id
    assert provenance.runtime_config_digest


@pytest.mark.asyncio
async def test_synthetic_runtime_cannot_mix_a_different_family_scope() -> None:
    runtime = _runtime()
    other = build_synthetic_runtime(
        tenant_id="tenant-synthetic",
        family_id="family-other",
        subject_ids=("guardian-other", "child-other"),
    )

    with pytest.raises(ContextScopeError, match="SYNTHETIC_RUNTIME_SCOPE_MISMATCH"):
        await runtime.application.generate_draft(_command(runtime, scope=other.scope))


@pytest.mark.asyncio
async def test_synthetic_runtime_resolver_uses_request_family_path() -> None:
    resolver = SyntheticRuntimeResolver(
        tenant_id="tenant-synthetic",
        subject_ids=("guardian-synthetic", "child-synthetic"),
    )

    first = await resolver.resolve("family-path-a")
    second = await resolver.resolve("family-path-b")

    assert first.scope.family_id == "family-path-a"
    assert second.scope.family_id == "family-path-b"
    assert first.scope.family_id != second.scope.family_id
    assert first.scope.tenant_id == second.scope.tenant_id == "tenant-synthetic"


def test_synthetic_runtime_resolver_rejects_production_environment() -> None:
    with pytest.raises(ValueError, match="only supports development or test"):
        SyntheticRuntimeResolver(
            tenant_id="tenant-synthetic",
            subject_ids=("child-synthetic",),
            environment="production",
        )


@pytest.mark.asyncio
async def test_resolver_reuses_budget_ledger_across_request_runtimes() -> None:
    resolver = SyntheticRuntimeResolver(
        tenant_id="tenant-synthetic",
        subject_ids=("guardian-synthetic", "child-synthetic"),
    )
    first = await resolver.resolve("family-path-a")
    second = await resolver.resolve("family-path-b")

    await first.application.generate_draft(_command(first))
    second_command = _command(second)
    second_command = replace(second_command, run_id="run-synthetic-002")
    await second.application.generate_draft(second_command)

    assert resolver.budget_store is not None
    assert len(resolver.budget_store.reservations) == 2
