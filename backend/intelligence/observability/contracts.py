"""Provider-neutral, metadata-only tracing contracts for AI runtime calls."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

SpanStatus = Literal["IN_PROGRESS", "OK", "ERROR"]
AttributeValue = str | int | float | bool

# Only stable, low-cardinality metadata is allowed in telemetry.  In
# particular, raw payload, prompt, model output and exception text are not an
# attribute type and therefore cannot accidentally enter the ledger.
_ALLOWED_ATTRIBUTE_KEYS = frozenset(
    {
        "provider_id",
        "model",
        "model_version",
        "environment",
        "route_sequence",
        "attempt_id",
        "stage",
        "safety_status",
        "risk_level",
        "draft_status",
        "has_media",
        "media_count",
    }
)


@dataclass(frozen=True, slots=True)
class TelemetryContext:
    """Trusted correlation and scope metadata for one AI trace."""

    trace_id: str
    request_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    family_id: str | None = None
    use_case: str = ""
    data_class: str = ""
    operation_id: str | None = None
    parent_span_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.trace_id, str) or not self.trace_id.strip():
            raise ValueError("TELEMETRY_TRACE_ID_REQUIRED")
        if (self.tenant_id is None) != (self.family_id is None):
            raise ValueError("TELEMETRY_SCOPE_MUST_INCLUDE_TENANT_AND_FAMILY")
        for name in (
            "request_id",
            "session_id",
            "tenant_id",
            "family_id",
            "use_case",
            "data_class",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"TELEMETRY_{name.upper()}_INVALID")
        operation_id = self.operation_id or self.trace_id
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("TELEMETRY_OPERATION_ID_INVALID")
        # Scope and request identifiers are references, not business data.  A
        # one-way digest keeps correlation possible without putting tenant,
        # family, session or causation identifiers into telemetry storage.
        for name in (
            "request_id",
            "session_id",
            "tenant_id",
            "family_id",
            "correlation_id",
            "causation_id",
            "operation_id",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _opaque_ref(value))


@dataclass(frozen=True, slots=True)
class TelemetrySpanHandle:
    """Opaque handle returned when a span is started."""

    span_id: str
    name: str
    context: TelemetryContext
    started_at: datetime

    def __post_init__(self) -> None:
        if not self.span_id or not self.name:
            raise ValueError("TELEMETRY_SPAN_IDENTITY_REQUIRED")
        if self.started_at.tzinfo is None:
            raise ValueError("TELEMETRY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")


class TelemetrySink(Protocol):
    """A sink for metadata-only span lifecycle records."""

    async def start_span(
        self,
        *,
        name: str,
        context: TelemetryContext,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> TelemetrySpanHandle: ...

    async def finish_span(
        self,
        handle: TelemetrySpanHandle,
        *,
        status: SpanStatus,
        ended_at: datetime | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        error_code: str | None = None,
    ) -> None: ...


def new_span_handle(
    *, name: str, context: TelemetryContext, started_at: datetime | None = None
) -> TelemetrySpanHandle:
    """Create a validated handle without touching a provider or database."""

    return TelemetrySpanHandle(
        span_id=f"span-{uuid4().hex}",
        name=name,
        context=context,
        started_at=started_at or datetime.now(UTC),
    )


def validate_attributes(attributes: Mapping[str, AttributeValue]) -> dict[str, AttributeValue]:
    """Allowlist low-cardinality fields and reject unsafe telemetry values."""

    if not isinstance(attributes, Mapping):
        raise ValueError("TELEMETRY_ATTRIBUTES_REQUIRED")
    unknown = set(attributes) - _ALLOWED_ATTRIBUTE_KEYS
    if unknown:
        raise ValueError(f"TELEMETRY_ATTRIBUTE_NOT_ALLOWED:{sorted(unknown)}")
    clean: dict[str, AttributeValue] = {}
    for key, value in attributes.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("TELEMETRY_ATTRIBUTE_KEY_INVALID")
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("TELEMETRY_ATTRIBUTE_VALUE_TOO_LONG")
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError("TELEMETRY_ATTRIBUTE_VALUE_INVALID")
        clean[key] = value
    return clean


def _opaque_ref(value: str) -> str:
    import hashlib

    # ``dataclasses.replace`` re-runs ``__post_init__``.  Keep already-redacted
    # references stable so replaying/rebinding a context does not double-hash
    # the operation or scope and accidentally bypass idempotency lookup.
    if len(value) == 28 and value.startswith("ref:") and all(
        character in "0123456789abcdef" for character in value[4:]
    ):
        return value
    return "ref:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


__all__ = [
    "AttributeValue",
    "SpanStatus",
    "TelemetryContext",
    "TelemetrySink",
    "TelemetrySpanHandle",
    "new_span_handle",
    "validate_attributes",
]
