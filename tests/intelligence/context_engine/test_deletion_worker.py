from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.deletion import (
    DeletionContractError,
    DeletionEventType,
    DeletionStatus,
    SubjectDeletionCommand,
    SubjectDeletionWorker,
)
from backend.intelligence.context_engine.store import ContextBroker


def command(
    *,
    tenant_id: str = "tenant-1",
    family_id: str = "family-1",
    subject_id: str = "child-1",
    command_id: str = "delete-command-1",
    idempotency_key: str = "delete-key-1",
) -> SubjectDeletionCommand:
    return SubjectDeletionCommand(
        command_id=command_id,
        tenant_id=tenant_id,
        family_id=family_id,
        subject_id=subject_id,
        deletion_ref=f"deletion:{tenant_id}:{subject_id}",
        requested_by="guardian-1",
        idempotency_key=idempotency_key,
        correlation_id=f"correlation:{command_id}",
        causation_id=f"causation:{command_id}",
    )


def scope(*, tenant_id: str = "tenant-1") -> ContextScope:
    return ContextScope(
        tenant_id=tenant_id,
        region_id="CN",
        family_id="family-1",
        subject_ids=("child-1",),
        purpose="family_growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.FAMILY_PRIVATE_TEXT,
        locale="zh-CN",
        deletion_ref=f"deletion:{tenant_id}:child-1",
        correlation_id="correlation:delete-command-1",
        causation_id="causation:delete-command-1",
    )


def append_observation(broker: ContextBroker, *, context_scope: ContextScope) -> None:
    now = datetime.now(UTC)
    broker.append(
        StateObservation(
            observation_id=f"observation:{context_scope.tenant_id}",
            tenant_id=context_scope.tenant_id,
            family_id=context_scope.family_id,
            subject_id=context_scope.subject_ids[0],
            dimension="rhythm",
            observed_value="a bounded family observation",
            evidence_refs=("evidence:1",),
            provenance="guardian-report",
            observed_at=now - timedelta(minutes=1),
            data_class=context_scope.data_class,
            purpose=context_scope.purpose,
            consent_version=context_scope.consent_version,
            consent_granted=True,
            region_id=context_scope.region_id,
            locale=context_scope.locale,
            deletion_ref=context_scope.deletion_ref,
            correlation_id=context_scope.correlation_id,
            causation_id=context_scope.causation_id,
            expires_at=now + timedelta(hours=1),
            retention_policy="context.v1",
        )
    )


def test_submit_is_pending_and_audited_once() -> None:
    worker = SubjectDeletionWorker(ContextBroker())

    job = worker.submit(command())
    replay = worker.submit(command())

    assert job.status is DeletionStatus.PENDING
    assert job == replay
    assert [event.event_type for event in worker.audit_events] == [DeletionEventType.REQUESTED]
    assert worker.audit_events[0].tenant_id == "tenant-1"
    assert worker.audit_events[0].deletion_ref == "deletion:tenant-1:child-1"


def test_completed_deletion_removes_context_observation_and_snapshot() -> None:
    broker = ContextBroker()
    context_scope = scope()
    append_observation(broker, context_scope=context_scope)
    snapshot = broker.snapshot(scope=context_scope)
    worker = SubjectDeletionWorker(broker)
    worker.submit(command())

    completed = worker.execute(tenant_id="tenant-1", idempotency_key="delete-key-1")

    assert completed.status is DeletionStatus.COMPLETED
    assert completed.attempts == 1
    assert completed.deleted_count == 1
    assert broker.snapshot(scope=context_scope).observations == ()
    with pytest.raises(ContextContractError, match="CONTEXT_SNAPSHOT_NOT_FOUND"):
        broker.read(snapshot.snapshot_ref, context_scope)
    assert [event.event_type for event in worker.audit_events] == [
        DeletionEventType.REQUESTED,
        DeletionEventType.ATTEMPTED,
        DeletionEventType.COMPLETED,
    ]


def test_completed_replay_is_idempotent_and_does_not_call_storage_again() -> None:
    class RecordingStorage:
        calls = 0

        def delete_subject(self, tenant_id: str, subject_id: str) -> int:
            self.calls += 1
            return 2

    storage = RecordingStorage()
    worker = SubjectDeletionWorker(storage)
    worker.submit(command())
    first = worker.execute(tenant_id="tenant-1", idempotency_key="delete-key-1")
    replay = worker.execute(tenant_id="tenant-1", idempotency_key="delete-key-1")

    assert first == replay
    assert storage.calls == 1
    assert len(worker.audit_events) == 3


def test_failed_deletion_is_not_reported_as_external_completion_and_can_retry() -> None:
    class FlakyStorage:
        calls = 0

        def delete_subject(self, tenant_id: str, subject_id: str) -> int:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("provider response must not enter audit")
            return 1

    storage = FlakyStorage()
    worker = SubjectDeletionWorker(storage)
    worker.submit(command())

    failed = worker.execute(tenant_id="tenant-1", idempotency_key="delete-key-1")
    completed = worker.execute(tenant_id="tenant-1", idempotency_key="delete-key-1")

    assert failed.status is DeletionStatus.FAILED
    assert failed.error_code == "STORAGE_DELETE_FAILED"
    assert completed.status is DeletionStatus.COMPLETED
    assert completed.attempts == 2
    assert completed.deleted_count == 1
    assert all(
        event.error_code != "provider response must not enter audit"
        for event in worker.audit_events
    )
    assert worker.audit_events[-1].event_type is DeletionEventType.COMPLETED


def test_tenant_isolation_scopes_idempotency_and_storage_calls() -> None:
    class RecordingStorage:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def delete_subject(self, tenant_id: str, subject_id: str) -> int:
            self.calls.append((tenant_id, subject_id))
            return 0

    storage = RecordingStorage()
    worker = SubjectDeletionWorker(storage)
    worker.submit(command(tenant_id="tenant-1", idempotency_key="same-key"))
    worker.submit(command(tenant_id="tenant-2", idempotency_key="same-key"))

    with pytest.raises(DeletionContractError, match="DELETION_JOB_NOT_FOUND"):
        worker.execute(tenant_id="tenant-2", idempotency_key="delete-key-1")
    worker.execute(tenant_id="tenant-1", idempotency_key="same-key")
    worker.execute(tenant_id="tenant-2", idempotency_key="same-key")

    assert storage.calls == [("tenant-1", "child-1"), ("tenant-2", "child-1")]
    completed_tenants = [
        event.tenant_id
        for event in worker.audit_events
        if event.event_type is DeletionEventType.COMPLETED
    ]
    assert completed_tenants == ["tenant-1", "tenant-2"]


def test_idempotency_conflict_cannot_replace_an_existing_command() -> None:
    worker = SubjectDeletionWorker(ContextBroker())
    worker.submit(command())

    with pytest.raises(DeletionContractError, match="IDEMPOTENCY_CONFLICT"):
        worker.submit(command(command_id="other-command"))


def test_worker_rejects_invalid_port_and_invalid_clock() -> None:
    with pytest.raises(DeletionContractError, match="SUBJECT_DELETION_PORT_REQUIRED"):
        SubjectDeletionWorker(object())  # type: ignore[arg-type]

    worker = SubjectDeletionWorker(ContextBroker(), clock=lambda: datetime(2026, 1, 1))
    with pytest.raises(DeletionContractError, match="worker clock"):
        worker.submit(command())
