"""OpenTelemetry SDK adapters for the canonical metadata-only span contract."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer

from .contracts import (
    AttributeValue,
    SpanStatus,
    TelemetryContext,
    TelemetrySink,
    TelemetrySpanHandle,
    new_span_handle,
    validate_attributes,
)


class OpenTelemetrySpanSink:
    """Bridge canonical spans to an injected OpenTelemetry tracer.

    The adapter never sends payloads to the SDK.  Every attribute is validated
    by the canonical allowlist first, then namespaced under ``aifamily.``.
    Exporter choice and sampling remain deployment concerns owned by the tracer
    provider.
    """

    def __init__(self, tracer: Tracer | None = None, *, tracer_name: str = "aifamily.ai-runtime"):
        self._tracer = tracer or trace.get_tracer(tracer_name)
        self._spans: dict[str, Span] = {}

    async def start_span(
        self,
        *,
        name: str,
        context: TelemetryContext,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> TelemetrySpanHandle:
        clean = validate_attributes(attributes or {})
        span = self._tracer.start_span(
            name,
            attributes=_otel_attributes(context, clean),
        )
        handle = new_span_handle(name=name, context=context)
        self._spans[handle.span_id] = span
        return handle

    async def finish_span(
        self,
        handle: TelemetrySpanHandle,
        *,
        status: SpanStatus,
        ended_at: datetime | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        error_code: str | None = None,
    ) -> None:
        if status not in {"OK", "ERROR"}:
            raise ValueError("TELEMETRY_FINAL_STATUS_REQUIRED")
        if error_code is not None and (not error_code.strip() or len(error_code) > 128):
            raise ValueError("TELEMETRY_ERROR_CODE_INVALID")
        span = self._spans.pop(handle.span_id, None)
        if span is None:
            raise ValueError("TELEMETRY_SPAN_NOT_FOUND")
        clean = validate_attributes(attributes or {})
        for key, value in _otel_attributes(handle.context, clean).items():
            span.set_attribute(key, value)
        if error_code is not None:
            span.set_attribute("aifamily.error_code", error_code)
        from opentelemetry.trace import Status, StatusCode

        span.set_status(Status(StatusCode.OK if status == "OK" else StatusCode.ERROR))
        ended = ended_at or datetime.now(UTC)
        if ended.tzinfo is None:
            raise ValueError("TELEMETRY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        span.end(end_time=int(ended.timestamp() * 1_000_000_000))


class CompositeTelemetrySink:
    """Fan out one canonical span to durable and exported sinks.

    ``strict=False`` keeps an exporter outage from changing a model/policy
    result; the durable SQL sink remains the source of audit truth.  A future
    deployment may choose ``strict=True`` for an operational fail-closed mode.
    """

    def __init__(self, sinks: tuple[TelemetrySink, ...], *, strict: bool = False) -> None:
        if not sinks or any(sink is None for sink in sinks):
            raise ValueError("at least one telemetry sink is required")
        self._sinks = sinks
        self._strict = strict
        self._children: dict[
            str, tuple[tuple[TelemetrySink, TelemetrySpanHandle], ...]
        ] = {}

    async def start_span(
        self,
        *,
        name: str,
        context: TelemetryContext,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> TelemetrySpanHandle:
        clean = validate_attributes(attributes or {})
        parent = new_span_handle(name=name, context=context)
        children: list[tuple[TelemetrySink, TelemetrySpanHandle]] = []
        errors: list[Exception] = []
        for sink in self._sinks:
            try:
                child = await sink.start_span(name=name, context=context, attributes=clean)
            except Exception as exc:
                errors.append(exc)
            else:
                children.append((sink, child))
        if errors and self._strict:
            raise errors[0]
        self._children[parent.span_id] = tuple(children)
        return parent

    async def finish_span(
        self,
        handle: TelemetrySpanHandle,
        *,
        status: SpanStatus,
        ended_at: datetime | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        error_code: str | None = None,
    ) -> None:
        children = self._children.pop(handle.span_id, ())
        errors: list[Exception] = []
        for sink, child in children:
            try:
                await sink.finish_span(
                    child,
                    status=status,
                    ended_at=ended_at,
                    attributes=attributes,
                    error_code=error_code,
                )
            except Exception as exc:
                errors.append(exc)
        if errors and self._strict:
            raise errors[0]


def _otel_attributes(
    context: TelemetryContext,
    attributes: Mapping[str, AttributeValue],
) -> dict[str, AttributeValue]:
    clean = validate_attributes(attributes)
    result: dict[str, AttributeValue] = {
        "aifamily.trace_id": context.trace_id,
        "aifamily.operation_id": context.operation_id or context.trace_id,
        "aifamily.use_case": context.use_case,
        "aifamily.data_class": context.data_class,
    }
    if context.request_id is not None:
        result["aifamily.request_ref"] = context.request_id
    if context.session_id is not None:
        result["aifamily.session_ref"] = context.session_id
    if context.tenant_id is not None:
        result["aifamily.tenant_ref"] = context.tenant_id
    if context.family_id is not None:
        result["aifamily.family_ref"] = context.family_id
    result.update({f"aifamily.{key}": value for key, value in clean.items()})
    return result


__all__ = ["CompositeTelemetrySink", "OpenTelemetrySpanSink"]
