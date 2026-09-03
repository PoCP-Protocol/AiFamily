from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.intelligence.observability import (
    CompositeTelemetrySink,
    InMemoryTelemetrySink,
    OpenTelemetrySpanSink,
    TelemetryContext,
)


def _context() -> TelemetryContext:
    return TelemetryContext(
        trace_id="trace-otel-1",
        request_id="request-otel-1",
        tenant_id="tenant-otel-1",
        family_id="family-otel-1",
        use_case="assessment_interpretation",
        data_class="SYNTHETIC",
        operation_id="operation-otel-1",
    )


@pytest.mark.asyncio
async def test_opentelemetry_sink_exports_only_allowlisted_metadata() -> None:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    sink = OpenTelemetrySpanSink(provider.get_tracer("aifamily-test"))

    handle = await sink.start_span(
        name="ai.model_gateway.generate_structured",
        context=_context(),
        attributes={"provider_id": "internal", "route_sequence": 0},
    )
    await sink.finish_span(
        handle,
        status="ERROR",
        error_code="POLICY_REJECTED",
        attributes={"draft_status": "DRAFT"},
    )

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "ai.model_gateway.generate_structured"
    assert span.attributes["aifamily.provider_id"] == "internal"
    assert span.attributes["aifamily.error_code"] == "POLICY_REJECTED"
    assert "aifamily.tenant_ref" in span.attributes
    assert "tenant-otel-1" not in span.attributes.values()
    assert "payload" not in span.attributes


@pytest.mark.asyncio
async def test_composite_sink_keeps_sql_and_exporter_in_one_lifecycle() -> None:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    durable = InMemoryTelemetrySink()
    exported = OpenTelemetrySpanSink(provider.get_tracer("aifamily-test"))
    sink = CompositeTelemetrySink((durable, exported))

    handle = await sink.start_span(
        name="ai.agent_runtime.execute",
        context=_context(),
        attributes={"stage": "agent"},
    )
    await sink.finish_span(handle, status="OK")

    assert durable.spans[0]["status"] == "OK"
    assert len(exporter.get_finished_spans()) == 1
