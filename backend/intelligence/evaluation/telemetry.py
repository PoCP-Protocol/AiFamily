"""Provider-neutral, redacted telemetry seam for AI runtime evidence.

This module provides a common event shape that a composition root can project
from Gateway attempts, AgentRun/Trace and ReleaseGate decisions without copying
prompts, model output, media, credentials or family-authored text. It is an
append-only recording boundary: no provider SDK, network call or domain write
lives here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Protocol


class TelemetryError(ValueError):
    """Raised when an event is malformed or an idempotency key conflicts."""


class TelemetryConflictError(TelemetryError):
    """The same idempotency key was reused for different event content."""


_SENSITIVE_KEY_TOKENS = frozenset(
    {
        "token", "secret", "password", "credential", "authorization", "cookie",
        "api_key", "apikey", "prompt", "payload", "output", "input", "media",
        "content", "message", "text", "embedding", "email", "phone", "address",
    }
)
_SAFE_STRING_KEYS = frozenset(
    {
        "event_type", "status", "failure_kind", "provider_id", "model", "model_version",
        "environment", "data_class", "use_case", "schema_version", "prompt_version",
        "report_ref", "gate_status", "risk_level",
    }
)
_MAX_STRING_LENGTH = 256


@dataclass(frozen=True, slots=True)
class AiTelemetryEvent:
    """Minimal event with immutable scope and redacted attributes."""

    event_id: str
    idempotency_key: str
    trace_id: str
    event_type: str
    tenant_id: str
    family_id: str | None = None
    subject_ids: tuple[str, ...] = ()
    attributes: Mapping[str, Any] | None = None
    occurred_at: datetime = datetime.min.replace(tzinfo=UTC)

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id),
            ("idempotency_key", self.idempotency_key),
            ("trace_id", self.trace_id),
            ("event_type", self.event_type),
            ("tenant_id", self.tenant_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise TelemetryError(f"{name.upper()}_REQUIRED")
        if self.family_id is not None and (
            not isinstance(self.family_id, str) or not self.family_id.strip()
        ):
            raise TelemetryError("FAMILY_ID_INVALID")
        if not isinstance(self.subject_ids, tuple) or any(
            not isinstance(value, str) or not value.strip() for value in self.subject_ids
        ):
            raise TelemetryError("SUBJECT_IDS_INVALID")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise TelemetryError("SUBJECT_IDS_MUST_BE_UNIQUE")
        if self.occurred_at.tzinfo is None:
            raise TelemetryError("OCCURRED_AT_MUST_BE_TIMEZONE_AWARE")
        if not isinstance(self.attributes, Mapping):
            raise TelemetryError("ATTRIBUTES_REQUIRED")
        object.__setattr__(self, "attributes", MappingProxyType(_redact_mapping(self.attributes)))
        object.__setattr__(self, "tenant_id", _opaque_ref(self.tenant_id))
        if self.family_id is not None:
            object.__setattr__(self, "family_id", _opaque_ref(self.family_id))
        object.__setattr__(
            self,
            "subject_ids",
            tuple(_opaque_ref(value) for value in self.subject_ids),
        )

    @property
    def fingerprint(self) -> str:
        """Stable content fingerprint used for idempotency conflict checks."""

        payload = {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "event_type": self.event_type,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "subject_ids": self.subject_ids,
            "attributes": self.attributes,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()


class TelemetrySink(Protocol):
    """Sync or async append-only event sink."""

    def append(self, event: AiTelemetryEvent) -> None | Awaitable[None]: ...


class InMemoryTelemetrySink:
    """Deterministic sink for tests and local diagnostics; never production durable."""

    def __init__(self) -> None:
        self._events: dict[str, AiTelemetryEvent] = {}
        self._fingerprints: dict[str, str] = {}

    def append(self, event: AiTelemetryEvent) -> None:
        if not isinstance(event, AiTelemetryEvent):
            raise TelemetryError("TELEMETRY_EVENT_REQUIRED")
        existing = self._events.get(event.idempotency_key)
        if existing is not None:
            if self._fingerprints[event.idempotency_key] != event.fingerprint:
                raise TelemetryConflictError("TELEMETRY_IDEMPOTENCY_CONFLICT")
            return
        self._events[event.idempotency_key] = event
        self._fingerprints[event.idempotency_key] = event.fingerprint

    def events(self) -> tuple[AiTelemetryEvent, ...]:
        return tuple(self._events.values())


async def append_telemetry(sink: TelemetrySink, event: AiTelemetryEvent) -> None:
    """Append through either a synchronous test sink or an async durable sink."""

    result = sink.append(event)
    if hasattr(result, "__await__"):
        await result  # type: ignore[misc]


def _redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _redact_value(str(key), nested) for key, nested in value.items()}


def _redact_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if key_lower in _SAFE_STRING_KEYS and isinstance(value, str):
        return value[:_MAX_STRING_LENGTH]
    if any(token in key_lower for token in _SENSITIVE_KEY_TOKENS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_redact_value(key, nested) for nested in value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "[REDACTED]"
    if isinstance(value, str):
        return "ref:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return "[REDACTED]"


def _opaque_ref(value: str) -> str:
    return "ref:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


__all__ = [
    "AiTelemetryEvent",
    "InMemoryTelemetrySink",
    "TelemetryConflictError",
    "TelemetryError",
    "TelemetrySink",
    "append_telemetry",
]
