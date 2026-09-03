"""Unified metadata-only telemetry boundary for AI runtime components."""

from .contracts import (
    AttributeValue,
    SpanStatus,
    TelemetryContext,
    TelemetrySink,
    TelemetrySpanHandle,
    new_span_handle,
    validate_attributes,
)
from .opentelemetry import CompositeTelemetrySink, OpenTelemetrySpanSink
from .persistence import (
    InMemoryTelemetrySink,
    SessionPerCallTelemetrySink,
    SqlAlchemyTelemetrySink,
    TelemetryPersistenceBase,
    TelemetrySpanRow,
)
from .retention import (
    InMemoryTelemetryDeletionAudit,
    InMemoryTelemetryRetentionStore,
    SqlAlchemyTelemetryRetentionStore,
    TelemetryDeletionAuditSink,
    TelemetryDeletionReceipt,
    TelemetryRetentionRun,
    TelemetryRetentionStore,
    TelemetryRetentionWorker,
    TelemetrySpanRecord,
)

__all__ = [
    "AttributeValue",
    "InMemoryTelemetrySink",
    "CompositeTelemetrySink",
    "OpenTelemetrySpanSink",
    "SessionPerCallTelemetrySink",
    "SpanStatus",
    "SqlAlchemyTelemetrySink",
    "TelemetryContext",
    "TelemetryPersistenceBase",
    "TelemetrySink",
    "TelemetrySpanHandle",
    "TelemetrySpanRow",
    "InMemoryTelemetryDeletionAudit",
    "InMemoryTelemetryRetentionStore",
    "SqlAlchemyTelemetryRetentionStore",
    "TelemetryDeletionAuditSink",
    "TelemetryDeletionReceipt",
    "TelemetryRetentionRun",
    "TelemetryRetentionStore",
    "TelemetryRetentionWorker",
    "TelemetrySpanRecord",
    "new_span_handle",
    "validate_attributes",
]
