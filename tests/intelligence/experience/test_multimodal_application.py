from __future__ import annotations

from dataclasses import replace

import pytest

from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceCommand,
    MultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
    MultimodalRouteRequest,
)
from backend.intelligence.model_gateway.attempts import InMemoryAttemptSink
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import (
    InMemoryModelDraftRegistry,
    ModelDraftScope,
)
from backend.intelligence.model_gateway.provider_registry import ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.model_gateway.test_fail_closed import build, fake_record


def _command(**overrides: object) -> MultimodalExperienceCommand:
    values: dict[str, object] = {
        "run_id": "run-routed-001",
        "provider_id": "placeholder",
        "use_case": "family-image-summary",
        "prompt_version": "prompt.v1",
        "schema_version": "schema.v1",
        "data_class": "SYNTHETIC",
        "context_snapshot_ref": "ctx:routed-001",
        "payload": {"media_ref": "fixture:image-001"},
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
    }
    values.update(overrides)
    return MultimodalExperienceCommand(**values)  # type: ignore[arg-type]


def _route_request(**overrides: object) -> MultimodalRouteRequest:
    values: dict[str, object] = {
        "use_case": "family-image-summary",
        "data_class": "SYNTHETIC",
        "modalities": ("TEXT", "IMAGE"),
        "environment": "test",
        "estimated_input_tokens": 1000,
    }
    values.update(overrides)
    return MultimodalRouteRequest(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_service_routes_by_capability_then_uses_model_gateway() -> None:
    provider = FakeProvider({"family-image-summary": {"summary": "已完成结构化理解"}})
    generation = MultimodalExperienceService(build(provider))
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id="fake-deterministic",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
    )
    service = RoutedMultimodalExperienceService(
        router=MultimodalRouter((profile,)), generation=generation
    )

    result = await service.generate_draft(_command(), _route_request())

    assert result.route.selected.provider_id == "fake-deterministic"
    assert result.output["summary"] == "已完成结构化理解"
    assert result.requires_human_confirmation is True
    assert result.experience.draft.may_mutate_business_state is False
    assert provider.invocations[0].request_id == "run-routed-001"


@pytest.mark.asyncio
async def test_service_refuses_command_route_mismatch_before_model_call() -> None:
    provider = FakeProvider({"family-image-summary": {"summary": "不会调用"}})
    generation = MultimodalExperienceService(build(provider))
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id="fake-deterministic",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
    )
    service = RoutedMultimodalExperienceService(
        router=MultimodalRouter((profile,)), generation=generation
    )

    with pytest.raises(ValueError, match="use_case"):
        await service.generate_draft(_command(), _route_request(use_case="different-use-case"))
    assert provider.invocations == []


def _fallback_service(
    first: FakeProvider,
    second: FakeProvider,
    *,
    registry: InMemoryModelDraftRegistry | None = None,
    sink: InMemoryAttemptSink | None = None,
) -> RoutedMultimodalExperienceService:
    first_profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id=first.provider_id,
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
        estimated_input_cost_microusd_per_1k_tokens=1,
    )
    second_profile = replace(
        first_profile,
        provider_id=second.provider_id,
        estimated_input_cost_microusd_per_1k_tokens=2,
    )
    gateway = ModelGateway(
        {first.provider_id: first, second.provider_id: second},
        environment="test",
        registry=ProviderRegistry(
            (
                fake_record(
                    first.provider_id,
                ),
                fake_record(
                    second.provider_id,
                ),
            )
        ),
        attempt_sink=sink,
    )
    return RoutedMultimodalExperienceService(
        router=MultimodalRouter((first_profile, second_profile)),
        generation=MultimodalExperienceService(gateway, registry=registry),
    )


@pytest.mark.asyncio
async def test_service_executes_governed_fallback_only_for_infrastructure_failure() -> None:
    attempts = InMemoryAttemptSink()
    first = FakeProvider(fail_with="PROVIDER_5XX", provider_id="provider-first")
    second = FakeProvider(
        {"family-image-summary": {"summary": "备用模型完成"}},
        provider_id="provider-second",
    )
    service = _fallback_service(first, second, sink=attempts)

    result = await service.generate_draft(_command(), _route_request(strategy="cost"))

    assert result.route.selected.provider_id == "provider-first"
    assert result.route.fallback_provider_ids == ("provider-second",)
    assert result.experience.draft.provenance.provider_id == "provider-second"
    assert result.output == {"summary": "备用模型完成"}
    assert [(item.provider_id, item.route_sequence) for item in attempts.all_attempts()] == [
        ("provider-first", 0),
        ("provider-second", 1),
    ]


@pytest.mark.asyncio
async def test_service_does_not_fallback_for_invalid_model_output() -> None:
    first = FakeProvider(
        raw_text_by_use_case={"family-image-summary": "not-json"},
        provider_id="provider-first",
    )
    second = FakeProvider(
        {"family-image-summary": {"summary": "不应调用"}},
        provider_id="provider-second",
    )
    service = _fallback_service(first, second)

    with pytest.raises(ModelGatewayError, match="INVALID_JSON"):
        await service.generate_draft(_command(), _route_request(strategy="cost"))
    assert second.invocations == []


@pytest.mark.asyncio
async def test_fallback_draft_replay_uses_registry_without_another_provider_call() -> None:
    registry = InMemoryModelDraftRegistry()
    first = FakeProvider(fail_with="TIMEOUT", provider_id="provider-first")
    second = FakeProvider(
        {"family-image-summary": {"summary": "已持久化备用草案"}},
        provider_id="provider-second",
    )
    command = _command(
        model_draft_scope=ModelDraftScope(
            tenant_id="tenant-a",
            family_id="family-a",
            subject_person_id="child-a",
            purpose="family-image-summary",
            correlation_id="correlation-a",
        )
    )
    service = _fallback_service(first, second, registry=registry)

    created = await service.generate_draft(command, _route_request(strategy="cost"))
    first_invocations = len(first.invocations)
    second_invocations = len(second.invocations)
    replayed = await service.generate_draft(command, _route_request(strategy="cost"))

    assert replayed.experience.draft == created.experience.draft
    assert replayed.experience.draft.provenance.provider_id == "provider-second"
    assert len(first.invocations) == first_invocations
    assert len(second.invocations) == second_invocations
