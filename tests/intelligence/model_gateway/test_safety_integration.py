from __future__ import annotations

import pytest

from backend.intelligence.model_gateway.attempts import InMemoryAttemptSink
from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway, build_gateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
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


def _request(*, use_case: str = "assessment_interpretation", payload=None, schema=None):
    return StructuredRequest(
        use_case=use_case,
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        data_class="SYNTHETIC",
        payload=payload or {"answers": [1]},
        output_schema=schema
        or {
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        context_snapshot_ref="ctx:test",
        request_id="req:test",
    )


class _BrokenSafety:
    def __init__(self, *, output_only: bool = False) -> None:
        self.output_only = output_only

    def evaluate_input(self, context, payload):
        if self.output_only:
            return type("Decision", (), {"status": "ALLOW"})()
        raise RuntimeError("policy implementation failure")

    def evaluate_output(self, context, draft):
        raise RuntimeError("policy implementation failure")


@pytest.mark.asyncio
async def test_gateway_blocks_prohibited_input_before_provider_call() -> None:
    provider = FakeProvider({"family_total_score": {"headline": "never"}})
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((_record(provider.provider_id),)),
        safety_runtime=SafetyRuntime(),
    )

    with pytest.raises(ModelGatewayError, match="safety policy blocked"):
        await gateway.generate_structured(
            _request(use_case="family_total_score"), provider_id=provider.provider_id
        )

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_gateway_blocks_forbidden_output_and_records_failed_attempt() -> None:
    provider = FakeProvider(
        {"assessment_interpretation": {"headline": "draft", "family_score": 99}}
    )
    sink = InMemoryAttemptSink()
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((_record(provider.provider_id),)),
        attempt_sink=sink,
        safety_runtime=SafetyRuntime(),
    )

    with pytest.raises(ModelGatewayError, match="safety policy blocked"):
        await gateway.generate_structured(
            _request(
                schema={
                    "type": "object",
                    "required": ["headline", "family_score"],
                    "properties": {
                        "headline": {"type": "string"},
                        "family_score": {"type": "integer"},
                    },
                }
            ),
            provider_id=provider.provider_id,
        )

    attempt = sink.all_attempts()[-1]
    assert attempt.status == "FAILURE"
    assert attempt.failure_kind == "POLICY_REJECTED"


def test_supported_gateway_factory_wires_safety_by_default() -> None:
    provider = FakeProvider({"assessment_interpretation": {"headline": "ok"}})
    gateway = build_gateway(
        environment="test",
        providers={provider.provider_id: provider},
        registry=ProviderRegistry((_record(provider.provider_id),)),
    )

    assert isinstance(gateway.safety_runtime, SafetyRuntime)


@pytest.mark.asyncio
async def test_broken_input_policy_fails_closed_without_provider_call() -> None:
    provider = FakeProvider({"assessment_interpretation": {"headline": "never"}})
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((_record(provider.provider_id),)),
        safety_runtime=_BrokenSafety(),  # type: ignore[arg-type]
    )

    with pytest.raises(ModelGatewayError, match="evaluation failed closed"):
        await gateway.generate_structured(_request(), provider_id=provider.provider_id)
    assert provider.invocations == []


@pytest.mark.asyncio
async def test_broken_output_policy_fails_closed_and_closes_attempt() -> None:
    provider = FakeProvider({"assessment_interpretation": {"headline": "draft"}})
    sink = InMemoryAttemptSink()
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((_record(provider.provider_id),)),
        attempt_sink=sink,
        safety_runtime=_BrokenSafety(output_only=True),  # type: ignore[arg-type]
    )

    with pytest.raises(ModelGatewayError, match="evaluation failed closed"):
        await gateway.generate_structured(_request(), provider_id=provider.provider_id)
    assert sink.all_attempts()[-1].failure_kind == "POLICY_REJECTED"
