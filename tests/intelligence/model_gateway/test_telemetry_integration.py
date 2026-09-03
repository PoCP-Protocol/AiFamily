from __future__ import annotations

import pytest

from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.observability import InMemoryTelemetrySink
from backend.intelligence.safety.runtime import SafetyRuntime


def _record(provider_id: str) -> ProviderRecord:
    return ProviderRecord(
        provider_id=provider_id,
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


def _request(*, use_case: str = "assessment_interpretation") -> StructuredRequest:
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
        request_id="request:test",
        session_id="session:test",
    )


@pytest.mark.asyncio
async def test_gateway_records_successful_trace_without_raw_content() -> None:
    provider = FakeProvider({"assessment_interpretation": {"headline": "ok"}})
    telemetry = InMemoryTelemetrySink()
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((_record(provider.provider_id),)),
        safety_runtime=SafetyRuntime(),
        telemetry_sink=telemetry,
    )

    await gateway.generate_structured(_request(), provider_id=provider.provider_id)

    assert len(telemetry.spans) == 1
    span = telemetry.spans[0]
    assert span["status"] == "OK"
    assert span["trace_id"] == "request:test"
    assert span["attributes"]["draft_status"] == "DRAFT"
    assert "payload" not in span
    assert "output" not in span


@pytest.mark.asyncio
async def test_gateway_records_policy_failure_trace() -> None:
    provider = FakeProvider({"family_total_score": {"headline": "blocked"}})
    telemetry = InMemoryTelemetrySink()
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((_record(provider.provider_id),)),
        safety_runtime=SafetyRuntime(),
        telemetry_sink=telemetry,
    )

    with pytest.raises(ModelGatewayError):
        await gateway.generate_structured(
            _request(use_case="family_total_score"), provider_id=provider.provider_id
        )

    assert telemetry.spans[0]["status"] == "ERROR"
    assert telemetry.spans[0]["error_code"] == "POLICY_REJECTED"
    assert provider.invocations == []
