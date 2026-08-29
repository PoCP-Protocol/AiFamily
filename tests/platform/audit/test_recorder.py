"""AuditRecorder.record / query semantics."""

from __future__ import annotations

import pytest

from backend.platform.audit.models import AuditActionKind, AuditEvent
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


async def test_flush_with_nothing_buffered_writes_nothing() -> None:
    """No events is not an error and must not need a live database.

    Superseded `test_flush_reports_buffered_event_count`, which asserted the
    old no-op behaviour ("report the count, keep the buffer, write nothing").
    That test locked in the defect: it passed precisely because flush did not
    persist. Real flush behaviour is covered in `test_store.py`.
    """
    recorder = AuditRecorder()

    assert await recorder.flush(session=None) == 0  # type: ignore[arg-type]


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


# ---------------------------------------------------------------------------
# Read access logging — 《未成年人网络保护条例》第36条
# ---------------------------------------------------------------------------


def _read_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "actor_id": "staff-1",
        "tenant_id": "tenant-1",
        "action": "child_profile.read",
        "resource_type": "ChildProfile",
        "resource_id": "child-1",
        "subject_person_id": "child-1",
        "accessed_fields": ["emotional_state", "conflict_type"],
        "access_purpose": "assessment",
        "reason": "guardian support ticket #42",
        "correlation_id": "corr-1",
    }
    kwargs.update(overrides)
    return kwargs


def test_record_read_produces_a_read_kind_event() -> None:
    recorder = AuditRecorder()

    event = recorder.record_read(**_read_kwargs())  # type: ignore[arg-type]

    assert event.action_kind is AuditActionKind.READ
    assert event.is_read and not event.is_mutation
    assert event.accessed_fields == ("emotional_state", "conflict_type")
    assert event in recorder.all_events()


def test_read_events_for_subject_filters_out_mutations_and_other_subjects() -> None:
    recorder = AuditRecorder()
    recorder.record(_event())  # a mutation on family-1
    mine = recorder.record_read(**_read_kwargs())  # type: ignore[arg-type]
    recorder.record_read(
        **_read_kwargs(subject_person_id="child-2", resource_id="child-2")  # type: ignore[arg-type]
    )

    assert recorder.read_events_for_subject("child-1") == (mine,)


def test_read_of_a_minor_without_approval_is_rejected() -> None:
    """第36条 requires 审批 before staff access a minor's information."""
    recorder = AuditRecorder()

    with pytest.raises(ValueError, match="approval_ref"):
        recorder.record_read(**_read_kwargs(subject_is_minor=True))  # type: ignore[arg-type]

    assert recorder.all_events() == (), "a rejected read must not be buffered"


def test_read_of_a_minor_with_approval_is_recorded() -> None:
    recorder = AuditRecorder()

    event = recorder.record_read(
        **_read_kwargs(subject_is_minor=True, approval_ref="approval-7")  # type: ignore[arg-type]
    )

    assert event.approval_ref == "approval-7"
    assert event.subject_is_minor is True


@pytest.mark.parametrize("blanked", ["subject_person_id", "access_purpose"])
def test_read_requires_subject_and_purpose(blanked: str) -> None:
    recorder = AuditRecorder()

    with pytest.raises(ValueError, match=blanked):
        recorder.record_read(**_read_kwargs(**{blanked: ""}))  # type: ignore[arg-type]


def test_read_with_no_accessed_fields_is_rejected() -> None:
    """"Someone read something" is not a record of access."""
    recorder = AuditRecorder()

    with pytest.raises(ValueError, match="accessed_fields"):
        recorder.record_read(**_read_kwargs(accessed_fields=[]))  # type: ignore[arg-type]


def test_mutation_may_not_carry_read_access_fields() -> None:
    """A write is not an access grant — the two shapes must stay separable."""
    with pytest.raises(ValueError, match="read-access field"):
        AuditEvent(
            actor_id="actor-1",
            tenant_id="tenant-1",
            action="update",
            resource_type="family",
            resource_id="family-1",
            reason="test",
            correlation_id="corr-1",
            after={"name": "New"},
            access_purpose="assessment",
        )


def test_existing_mutation_events_default_to_mutation_kind() -> None:
    """Backwards compatibility: every pre-T-07 R6 call site stays valid."""
    assert _event().action_kind is AuditActionKind.MUTATION
