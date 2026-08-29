"""AuditRecorder.record / query semantics."""

from __future__ import annotations

import pytest

from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder


def _event(resource_id: str = "family-1", action: str = "create") -> AuditEvent:
    return AuditEvent(
        actor_id="actor-1",
        tenant_id="tenant-1",
        action=action,
        resource_type="family",
        resource_id=resource_id,
        reason="test",
        correlation_id="corr-1",
        before=None,
        after={"name": "Test Family"},
    )


def test_recorded_event_is_immediately_queryable() -> None:
    recorder = AuditRecorder()
    event = _event()

    recorder.record(event)

    assert event in recorder.all_events()


def test_events_for_resource_filters_by_type_and_id() -> None:
    recorder = AuditRecorder()
    matching = _event(resource_id="family-1")
    other_resource = _event(resource_id="family-2")

    recorder.record(matching)
    recorder.record(other_resource)

    results = recorder.events_for_resource("family", "family-1")
    assert results == (matching,)


async def test_flush_reports_buffered_event_count() -> None:
    recorder = AuditRecorder()
    recorder.record(_event())
    recorder.record(_event(resource_id="family-2"))

    flushed_count = await recorder.flush()

    assert flushed_count == 2


@pytest.mark.parametrize(
    "missing_field",
    ["actor_id", "tenant_id", "action", "resource_type", "resource_id", "reason", "correlation_id"],
)
def test_audit_event_rejects_missing_required_field(missing_field: str) -> None:
    kwargs = {
        "actor_id": "actor-1",
        "tenant_id": "tenant-1",
        "action": "create",
        "resource_type": "family",
        "resource_id": "family-1",
        "reason": "test",
        "correlation_id": "corr-1",
    }
    kwargs[missing_field] = ""

    with pytest.raises(ValueError):
        AuditEvent(**kwargs)
