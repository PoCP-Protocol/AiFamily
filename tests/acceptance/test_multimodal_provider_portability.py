from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceCommand,
    MultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import (
    MultimodalRouteError,
    MultimodalRouter,
    MultimodalRouteRequest,
    ProviderCapabilityProfile,
)
from backend.intelligence.model_gateway.composition import (
    build_openai_compatible_gateway_from_registry,
)
from backend.intelligence.model_gateway.contracts import MediaInput
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from tests.intelligence.model_gateway.test_fail_closed import make_request


def _record(provider_id: str) -> ProviderRecord:
    env_prefix = provider_id.upper().replace("-", "_")
    return ProviderRecord(
        provider_id=provider_id,
        vendor=f"{provider_id}-vendor",
        model=f"{provider_id}-vision",
        model_version="2026-09",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        minor_data_allowed=False,
        private_text_allowed=False,
        credential_env_var=f"{env_prefix}_API_KEY",
        base_url_env_var=f"{env_prefix}_BASE_URL",
    )


def _profile(
    provider_id: str,
    *,
    latency_ms: int,
) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        provider_id=provider_id,
        vendor=f"{provider_id}-vendor",
        model=f"{provider_id}-vision",
        model_version="2026-09",
        modalities=frozenset({"TEXT", "IMAGE"}),
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
        supports_structured_output=True,
        estimated_input_cost_microusd_per_1k_tokens=10,
        estimated_latency_ms_p50=latency_ms,
    )


def _command(run_id: str) -> MultimodalExperienceCommand:
    reviewed_plan = make_request().prompt_execution_plan
    assert reviewed_plan is not None
    return MultimodalExperienceCommand(
        run_id=run_id,
        provider_id="selected-by-router",
        use_case="family-image-summary",
        prompt_version=reviewed_plan.prompt_version,
        schema_version="family-image-summary.v1",
        data_class="SYNTHETIC",
        context_snapshot_ref="ctx:synthetic-provider-portability",
        payload={"instruction": "Summarize the synthetic fixture."},
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
            "additionalProperties": False,
        },
        media_inputs=(
            MediaInput(
                media_type="IMAGE",
                uri="https://fixtures.example.invalid/synthetic-family-scene.png",
                mime_type="image/png",
                sha256="a" * 64,
            ),
        ),
        prompt_execution_plan=replace(
            reviewed_plan,
            prompt_ref="family-image-summary",
            template="Summarize the reviewed synthetic image fixture.",
        ),
    )


def _route_request(*, data_class: str = "SYNTHETIC") -> MultimodalRouteRequest:
    return MultimodalRouteRequest(
        use_case="family-image-summary",
        data_class=data_class,  # type: ignore[arg-type]
        modalities=("TEXT", "IMAGE"),
        environment="test",
        estimated_input_tokens=500,
        media_item_count=1,
        strategy="latency",
    )


@pytest.mark.asyncio
async def test_same_multimodal_contract_can_switch_between_two_providers() -> None:
    provider_ids = ("provider-alpha", "provider-beta")
    records = tuple(_record(provider_id) for provider_id in provider_ids)
    seen: dict[str, list[dict[str, object]]] = {provider_id: [] for provider_id in provider_ids}
    clients: dict[str, httpx.AsyncClient] = {}

    def client_factory(record: ProviderRecord) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            seen[record.provider_id].append(body)
            return httpx.Response(
                200,
                json={
                    "model": f"{record.provider_id}-served",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"summary": f"draft from {record.provider_id}"}
                                )
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 8,
                        "total_tokens": 28,
                    },
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients[record.provider_id] = client
        return client

    env = {
        "PROVIDER_ALPHA_API_KEY": "synthetic-alpha-key",
        "PROVIDER_ALPHA_BASE_URL": "https://alpha.example.invalid/v1",
        "PROVIDER_BETA_API_KEY": "synthetic-beta-key",
        "PROVIDER_BETA_BASE_URL": "https://beta.example.invalid/v1",
    }
    gateway = build_openai_compatible_gateway_from_registry(
        environment="test",
        provider_ids=provider_ids,
        registry=ProviderRegistry(records),
        env=env,
        client_factory=client_factory,
    )
    generation = MultimodalExperienceService(gateway)

    alpha_first = RoutedMultimodalExperienceService(
        router=MultimodalRouter(
            (
                _profile("provider-alpha", latency_ms=50),
                _profile("provider-beta", latency_ms=100),
            )
        ),
        generation=generation,
    )
    beta_first = RoutedMultimodalExperienceService(
        router=MultimodalRouter(
            (
                _profile("provider-alpha", latency_ms=100),
                _profile("provider-beta", latency_ms=50),
            )
        ),
        generation=generation,
    )

    try:
        alpha_draft = await alpha_first.generate_draft(
            _command("run-provider-alpha"), _route_request()
        )
        beta_draft = await beta_first.generate_draft(
            _command("run-provider-beta"), _route_request()
        )
    finally:
        for client in clients.values():
            await client.aclose()

    assert alpha_draft.route.selected.provider_id == "provider-alpha"
    assert beta_draft.route.selected.provider_id == "provider-beta"
    assert alpha_draft.experience.draft.provenance.provider_id == "provider-alpha"
    assert beta_draft.experience.draft.provenance.provider_id == "provider-beta"
    assert set(alpha_draft.output) == set(beta_draft.output) == {"summary"}
    assert alpha_draft.requires_human_confirmation is True
    assert beta_draft.requires_human_confirmation is True
    assert alpha_draft.experience.draft.may_mutate_business_state is False
    assert beta_draft.experience.draft.may_mutate_business_state is False
    assert len(seen["provider-alpha"]) == len(seen["provider-beta"]) == 1
    for provider_id in provider_ids:
        user_content = seen[provider_id][0]["messages"][1]["content"]  # type: ignore[index]
        assert isinstance(user_content, list)
        assert user_content[1] == {
            "type": "image_url",
            "image_url": {
                "url": "https://fixtures.example.invalid/synthetic-family-scene.png"
            },
        }


def test_provider_portability_does_not_bypass_minor_data_admission() -> None:
    router = MultimodalRouter(
        (
            _profile("provider-alpha", latency_ms=50),
            _profile("provider-beta", latency_ms=100),
        )
    )

    with pytest.raises(MultimodalRouteError) as excinfo:
        router.route(_route_request(data_class="MINOR_PERSONAL_DATA"))

    assert excinfo.value.reason == "NO_CAPABLE_PROVIDER"
