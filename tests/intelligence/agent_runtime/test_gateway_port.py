from __future__ import annotations

import pytest

from backend.intelligence.agent_runtime.gateway_port import ModelGatewayExecutionPort
from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.safety.runtime import SafetyRuntime


def _request(use_case: str = "assessment_interpretation") -> StructuredRequest:
    return StructuredRequest(
        use_case=use_case,
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        data_class="SYNTHETIC",
        payload={"answers": [1]},
        output_schema={
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        context_snapshot_ref="ctx:test",
    )


def _gateway(provider: FakeProvider) -> ModelGateway:
    record = ProviderRecord(
        provider_id=provider.provider_id,
        vendor="aifamily-test",
        model="fake",
        model_version="1",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        security_assessment_ref="test",
        processing_agreement_ref="test",
        deletion_on_termination_committed=True,
    )
    return ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((record,)),
        safety_runtime=SafetyRuntime(),
    )


@pytest.mark.asyncio
async def test_adapter_binds_provider_and_preserves_gateway_safety() -> None:
    provider = FakeProvider({"assessment_interpretation": {"headline": "ok"}})
    port = ModelGatewayExecutionPort(_gateway(provider), provider.provider_id)

    draft = await port.generate_structured(_request())

    assert draft.status == "DRAFT"
    assert len(provider.invocations) == 1
    assert provider.invocations[0].use_case == "assessment_interpretation"


@pytest.mark.asyncio
async def test_adapter_does_not_bypass_input_safety() -> None:
    provider = FakeProvider({"family_total_score": {"headline": "blocked"}})
    port = ModelGatewayExecutionPort(_gateway(provider), provider.provider_id)

    with pytest.raises(ModelGatewayError, match="safety policy blocked"):
        await port.generate_structured(_request("family_total_score"))

    assert provider.invocations == []


def test_adapter_rejects_provider_not_wired() -> None:
    provider = FakeProvider({"assessment_interpretation": {"headline": "ok"}})
    gateway = _gateway(provider)

    with pytest.raises(ValueError, match="wired"):
        ModelGatewayExecutionPort(gateway, "missing-provider")
