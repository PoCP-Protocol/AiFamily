from __future__ import annotations

import httpx
import pytest

from backend.intelligence.context_engine.contracts import DataClass
from backend.intelligence.experience import synthetic_runtime
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
)
from backend.intelligence.experience.multimodal_routing import MultimodalRouteRequest
from backend.intelligence.experience.standard_assets import (
    FAMILY_EXPERIENCE_PROMPT_VERSION,
    FAMILY_EXPERIENCE_SCHEMA_VERSION,
    family_experience_output_schema,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import build_gateway
from backend.intelligence.model_gateway.ibm_ica_wiring import IBM_ICA_PROVIDER_ID
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.model_gateway.providers.openai_compatible import (
    OpenAICompatibleProvider,
)


def _command(runtime, *, run_id: str = "run-ibm-ica") -> ContextBoundMultimodalCommand:
    return ContextBoundMultimodalCommand(
        run_id=run_id,
        route_request=MultimodalRouteRequest(
            use_case=runtime.scope.purpose,
            data_class=runtime.scope.data_class.value,
            modalities=("TEXT", "IMAGE"),
            environment=runtime.environment,
            estimated_input_tokens=100,
        ),
        scope=runtime.scope,
        prompt_version=FAMILY_EXPERIENCE_PROMPT_VERSION,
        schema_version=FAMILY_EXPERIENCE_SCHEMA_VERSION,
        payload={"media_ref": "fixture:image-001"},
        output_schema=family_experience_output_schema(),
    )


def test_default_provider_remains_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFAMILY_SYNTHETIC_RUNTIME_PROVIDER", raising=False)
    monkeypatch.setattr(
        synthetic_runtime,
        "build_livecheck_ibm_ica_gateway",
        lambda: pytest.fail("IBM ICA must not be selected by default"),
    )

    runtime = synthetic_runtime.build_synthetic_runtime(
        tenant_id="tenant-ibm-ica",
        family_id="family-ibm-ica",
        subject_ids=("child-ibm-ica",),
    )

    assert runtime.scope.data_class is DataClass.SYNTHETIC


def test_ibm_ica_switch_constructs_livecheck_gateway_with_fake_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_SYNTHETIC_RUNTIME_PROVIDER", "ibm_ica")
    provider = FakeProvider(
        {
            "family_assistant_conversation": {
                "understanding": "IBM ICA synthetic draft",
                "next_step": "confirm",
                "limitations": ["synthetic"],
            }
        },
        provider_id=IBM_ICA_PROVIDER_ID,
    )
    livecheck_gateway = build_gateway(
        environment="internal_livecheck",
        providers={IBM_ICA_PROVIDER_ID: provider},
        registry=ProviderRegistry((ProviderRecord(
            provider_id=IBM_ICA_PROVIDER_ID,
            vendor="ibm-ica",
            model="gpt-5.6-sol",
            model_version="gpt-5.6-sol",
            status="INTERNAL_APPROVED",
            approved_environments=("internal_livecheck",),
            sub_delegates=None,
        ),)),
    )
    called = False

    def fake_builder():
        nonlocal called
        called = True
        return livecheck_gateway

    monkeypatch.setattr(synthetic_runtime, "build_livecheck_ibm_ica_gateway", fake_builder)
    runtime = synthetic_runtime.build_synthetic_runtime(
        tenant_id="tenant-ibm-ica",
        family_id="family-ibm-ica",
        subject_ids=("child-ibm-ica",),
        environment="test",
    )

    assert called is True
    assert runtime.scope.data_class is DataClass.SYNTHETIC


@pytest.mark.asyncio
async def test_ibm_ica_http_503_is_diagnostic_and_payload_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_SYNTHETIC_RUNTIME_PROVIDER", "ibm_ica")
    payload_marker = "family-secret-payload-marker"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": {"message": f"upstream leaked {payload_marker}"}},
        )

    provider = OpenAICompatibleProvider(
        provider_id=IBM_ICA_PROVIDER_ID,
        base_url="https://ica.invalid/v1",
        api_key="test-key",
        model="gpt-5.6-sol",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    record = ProviderRecord(
        provider_id=IBM_ICA_PROVIDER_ID,
        vendor="ibm-ica",
        model="gpt-5.6-sol",
        model_version="gpt-5.6-sol",
        status="INTERNAL_APPROVED",
        approved_environments=("internal_livecheck",),
        sub_delegates=None,
        minor_data_allowed=False,
        private_text_allowed=False,
        security_assessment_ref="ica-livecheck-assessment",
        processing_agreement_ref="ica-livecheck-agreement",
        deletion_on_termination_committed=False,
        processing_region="unspecified",
    )
    livecheck_gateway = build_gateway(
        environment="internal_livecheck",
        providers={IBM_ICA_PROVIDER_ID: provider},
        registry=ProviderRegistry((record,)),
    )
    monkeypatch.setattr(
        synthetic_runtime,
        "build_livecheck_ibm_ica_gateway",
        lambda: livecheck_gateway,
    )

    runtime = synthetic_runtime.build_synthetic_runtime(
        tenant_id="tenant-ibm-ica",
        family_id="family-ibm-ica",
        subject_ids=("child-ibm-ica",),
        environment="test",
    )

    with pytest.raises(ModelGatewayError) as captured:
        await runtime.application.generate_draft(_command(runtime))

    error = captured.value
    assert error.kind == "PROVIDER_5XX"
    assert error.status_code == 503
    assert error.provider_id == IBM_ICA_PROVIDER_ID
    assert payload_marker not in str(error)
    await provider._client.aclose()


@pytest.mark.parametrize("environment", ["production", "internal_livecheck"])
def test_ibm_ica_switch_remains_fail_closed_outside_development_test(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("AIFAMILY_SYNTHETIC_RUNTIME_PROVIDER", "ibm_ica")

    with pytest.raises(ValueError, match="only supports development or test"):
        synthetic_runtime.build_synthetic_runtime(
            tenant_id="tenant-ibm-ica",
            family_id="family-ibm-ica",
            subject_ids=("child-ibm-ica",),
            environment=environment,
        )


async def _generate(runtime):
    return await runtime.application.generate_draft(_command(runtime))
