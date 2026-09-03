from __future__ import annotations

from datetime import datetime

import pytest

from backend.intelligence.evaluation.telemetry import (
    AiTelemetryEvent,
    InMemoryTelemetrySink,
    TelemetryConflictError,
    TelemetryError,
    append_telemetry,
)


def _event(*, text: str = "family private message", event_id: str = "event-1") -> AiTelemetryEvent:
    return AiTelemetryEvent(
        event_id=event_id,
        idempotency_key="idem-1",
        trace_id="trace-1",
        event_type="gateway.attempt.finished",
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("subject-1",),
        attributes={
            "status": "SUCCESS",
            "latency_ms": 42,
            "prompt_version": "experience.v1",
            "prompt": text,
            "nested": {"message": text, "provider_id": "fake-deterministic"},
            "opaque_note": text,
        },
    )


def test_event_redacts_sensitive_values_and_hashes_scope_refs() -> None:
    event = _event()

    assert event.tenant_id.startswith("ref:")
    assert event.family_id and event.family_id.startswith("ref:")
    assert event.subject_ids[0].startswith("ref:")
    assert event.attributes["status"] == "SUCCESS"
    assert event.attributes["prompt_version"] == "experience.v1"
    assert event.attributes["prompt"] == "[REDACTED]"
    assert event.attributes["nested"]["message"] == "[REDACTED]"
    assert event.attributes["nested"]["provider_id"] == "fake-deterministic"
    assert event.attributes["opaque_note"].startswith("ref:")
    assert "family private message" not in repr(event)


def test_sink_is_idempotent_and_rejects_conflicting_replay() -> None:
    sink = InMemoryTelemetrySink()
    sink.append(_event())
    sink.append(_event())
    assert len(sink.events()) == 1

    with pytest.raises(TelemetryConflictError, match="IDEMPOTENCY_CONFLICT"):
        sink.append(_event(event_id="different-event"))


@pytest.mark.asyncio
async def test_async_bridge_accepts_an_async_sink() -> None:
    class AsyncSink:
        def __init__(self) -> None:
            self.events: list[AiTelemetryEvent] = []

        async def append(self, event: AiTelemetryEvent) -> None:
            self.events.append(event)

    sink = AsyncSink()
    await append_telemetry(sink, _event())
    assert len(sink.events) == 1


def test_event_rejects_naive_timestamp_and_duplicate_subjects() -> None:
    with pytest.raises(TelemetryError, match="OCCURRED_AT"):
        AiTelemetryEvent(
            event_id="event-1",
            idempotency_key="idem-1",
            trace_id="trace-1",
            event_type="gateway.attempt.started",
            tenant_id="tenant-1",
            subject_ids=("subject-1",),
            attributes={},
            occurred_at=datetime.now(),
        )
    with pytest.raises(TelemetryError, match="SUBJECT_IDS_MUST_BE_UNIQUE"):
        AiTelemetryEvent(
            event_id="event-1",
            idempotency_key="idem-1",
            trace_id="trace-1",
            event_type="gateway.attempt.started",
            tenant_id="tenant-1",
            subject_ids=("subject-1", "subject-1"),
            attributes={},
        )
