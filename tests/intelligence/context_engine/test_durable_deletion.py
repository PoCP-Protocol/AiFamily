from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.context_engine.deletion import SubjectDeletionCommand
from backend.intelligence.context_engine.durable_deletion import (
    DurableDeletionError,
    DurableDeletionEventType,
    DurableDeletionStatus,
    DurableDeletionWorker,
    InMemoryDurableDeletionStore,
    ProjectionDeletionReceipt,
    ProjectionKind,
)


def make_command(
    *, tenant_id: str = "tenant-1", idempotency_key: str = "delete-1"
) -> SubjectDeletionCommand:
    return SubjectDeletionCommand(
        command_id=f"command:{tenant_id}:{idempotency_key}",
        tenant_id=tenant_id,
        family_id="family-1",
        subject_id="child-1",
        deletion_ref=f"deletion:{tenant_id}:child-1",
        requested_by="guardian-1",
        idempotency_key=idempotency_key,
        correlation_id=f"correlation:{tenant_id}:{idempotency_key}",
        causation_id=f"causation:{tenant_id}:{idempotency_key}",
    )


class ReceiptPort:
    def __init__(self, projection: ProjectionKind, *, deleted_count: int = 1) -> None:
        self.projection = projection
        self.deleted_count = deleted_count
        self.calls = 0

    def delete_subject(self, command: SubjectDeletionCommand) -> ProjectionDeletionReceipt:
        self.calls += 1
        return ProjectionDeletionReceipt(
            receipt_id=f"receipt:{self.projection.value}:{self.calls}",
            projection=self.projection,
            tenant_id=command.tenant_id,
            subject_id=command.subject_id,
            command_id=command.command_id,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            deleted_count=self.deleted_count,
            confirmed=True,
        )


def all_ports() -> list[ReceiptPort]:
    return [ReceiptPort(kind) for kind in ProjectionKind]


def test_same_store_recovers_jobs_after_worker_restart() -> None:
    store = InMemoryDurableDeletionStore()
    first = DurableDeletionWorker(store, all_ports())
    first.submit(make_command())

    restarted = DurableDeletionWorker(store, all_ports())
    completed = restarted.run_once("worker-after-restart")

    assert completed is not None
    assert completed.status is DurableDeletionStatus.COMPLETED
    assert {receipt.projection for receipt in completed.receipts} == set(ProjectionKind)
    assert len(store.audits()) == 8  # request + claim + 5 receipts + completion
    assert all(event.correlation_id == make_command().correlation_id for event in store.audits())


def test_expired_lease_can_be_reclaimed_by_another_worker() -> None:
    store = InMemoryDurableDeletionStore()
    now = datetime(2026, 8, 30, tzinfo=UTC)
    store.enqueue(make_command(), now=now)
    claimed = store.claim(
        worker_id="worker-that-crashed",
        now=now,
        lease_ttl=timedelta(minutes=1),
    )
    assert claimed is not None

    worker = DurableDeletionWorker(
        store,
        all_ports(),
        clock=lambda: now + timedelta(minutes=2),
    )
    completed = worker.run_once("replacement-worker")

    assert completed is not None
    assert completed.status is DurableDeletionStatus.COMPLETED
    assert completed.attempts == 1


def test_retry_then_dead_letters_without_claiming_completion() -> None:
    class AlwaysFailPort(ReceiptPort):
        def delete_subject(self, command: SubjectDeletionCommand) -> ProjectionDeletionReceipt:
            self.calls += 1
            raise RuntimeError("provider detail must not enter audit")

    ports = [
        AlwaysFailPort(ProjectionKind.TEXT),
        *(ReceiptPort(kind) for kind in ProjectionKind if kind is not ProjectionKind.TEXT),
    ]
    store = InMemoryDurableDeletionStore()
    clock = [datetime(2026, 8, 30, tzinfo=UTC)]
    worker = DurableDeletionWorker(
        store,
        ports,
        clock=lambda: clock[0],
        retry_delay=timedelta(0),
        max_attempts=2,
    )
    worker.submit(make_command())

    first = worker.run_once()
    second = worker.run_once()

    assert first is not None and first.status is DurableDeletionStatus.RETRYABLE
    assert second is not None and second.status is DurableDeletionStatus.DEAD_LETTER
    assert len(store.dead_letters()) == 1
    assert all(
        event.error_code != "provider detail must not enter audit" for event in store.audits()
    )
    assert store.audits()[-1].event_type is DurableDeletionEventType.DEAD_LETTERED


def test_constructor_requires_all_projection_kinds_by_default() -> None:
    with pytest.raises(DurableDeletionError, match="REQUIRED_PROJECTION_PORTS_MISSING"):
        DurableDeletionWorker(
            InMemoryDurableDeletionStore(),
            [ReceiptPort(ProjectionKind.TEXT)],
        )


def test_unconfirmed_receipt_cannot_complete_a_job() -> None:
    class UnconfirmedPort(ReceiptPort):
        def delete_subject(self, command: SubjectDeletionCommand) -> ProjectionDeletionReceipt:
            return ProjectionDeletionReceipt(
                receipt_id="receipt:unconfirmed",
                projection=self.projection,
                tenant_id=command.tenant_id,
                subject_id=command.subject_id,
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
                deleted_count=0,
                confirmed=False,
            )

    ports = [
        UnconfirmedPort(ProjectionKind.TEXT),
        *(ReceiptPort(kind) for kind in ProjectionKind if kind is not ProjectionKind.TEXT),
    ]
    store = InMemoryDurableDeletionStore()
    worker = DurableDeletionWorker(store, ports, retry_delay=timedelta(0), max_attempts=1)
    worker.submit(make_command())

    result = worker.run_once()

    assert result is not None
    assert result.status is DurableDeletionStatus.DEAD_LETTER
    assert result.deleted_count == 0
    assert result.last_error_code == "PROJECTION_DELETE_FAILED"


def test_tenant_scoped_idempotency_cannot_cross_read() -> None:
    store = InMemoryDurableDeletionStore()
    worker = DurableDeletionWorker(store, all_ports())
    worker.submit(make_command(tenant_id="tenant-a", idempotency_key="same"))
    worker.submit(make_command(tenant_id="tenant-b", idempotency_key="same"))
    with pytest.raises(DurableDeletionError, match="DELETION_JOB_NOT_FOUND"):
        worker.get(tenant_id="tenant-c", idempotency_key="same")
    with pytest.raises(DurableDeletionError, match="IDEMPOTENCY_CONFLICT"):
        worker.submit(
            replace(
                make_command(tenant_id="tenant-a", idempotency_key="same"),
                command_id="different-command",
            )
        )
