from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.platform.notification.contracts import (
    NotificationChannel,
    NotificationIntent,
    NotificationPolicy,
    NotificationScope,
)
from backend.platform.notification.orchestrator import NotificationOrchestrator
from backend.platform.notification.persistence import (
    NotificationPersistenceBase,
    NotificationPersistenceError,
    SqlAlchemyNotificationStore,
)
from backend.platform.outbox import OutboxEvent


@pytest.fixture
async def session_factory() -> async_sessionmaker:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(NotificationPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _intent(body: str = "请查看今日行动") -> NotificationIntent:
    return NotificationIntent.create(
        scope=NotificationScope("tenant-a", "family-a", "person-a", "growth_tracking", "c-1"),
        channel=NotificationChannel.PUSH,
        template_key="task.reminder",
        idempotency_key="task-1",
        correlation_id="corr-1",
        body=body,
        created_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
    )


def _event() -> OutboxEvent:
    return OutboxEvent.create(
        tenant_id="tenant-a",
        family_id="family-a",
        aggregate_type="GrowthTask",
        aggregate_id="task-1",
        event_name="GrowthTaskDue",
        event_version=1,
        idempotency_key="task-1",
        request_hash="hash-1",
        correlation_id="corr-1",
        payload={"task_ref": "task-1"},
        occurred_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
    )


async def test_intent_replay_is_idempotent_and_payload_conflict_fails(session_factory) -> None:
    async with session_factory() as session, session.begin():
        store = SqlAlchemyNotificationStore(session)
        first = await store.create_intent(_intent())
        replay = await store.create_intent(_intent())
        assert first.intent_id == replay.intent_id
        with pytest.raises(NotificationPersistenceError, match="payload_conflict"):
            await store.create_intent(_intent("changed"))


async def test_claim_failure_retries_then_dead_letters(session_factory) -> None:
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        store = SqlAlchemyNotificationStore(session)
        intent = _intent()
        await store.create_intent(intent)
        attempt = await store.enqueue_attempt(intent_id=intent.intent_id, now=now)
        claimed = await store.claim_due(owner="worker-a", now=now, lease=timedelta(minutes=5))
        assert claimed is attempt
        await store.record_failure(
            attempt,
            now=now,
            error_code="PROVIDER_TIMEOUT",
            retry_at=now + timedelta(minutes=1),
            max_attempts=2,
        )
        assert attempt.status == "retry"
        claimed = await store.claim_due(
            owner="worker-a", now=now + timedelta(minutes=1), lease=timedelta(minutes=5)
        )
        assert claimed is attempt
        await store.record_failure(
            attempt,
            now=now + timedelta(minutes=1),
            error_code="PROVIDER_TIMEOUT",
            retry_at=None,
            max_attempts=2,
        )
        assert attempt.status == "dead_letter"


async def test_success_lease_recovery_and_dead_letter_replay(session_factory) -> None:
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        store = SqlAlchemyNotificationStore(session)
        intent = _intent()
        await store.create_intent(intent)
        attempt = await store.enqueue_attempt(intent_id=intent.intent_id, now=now)
        assert await store.recover_expired_leases(now=now) == 0
        await store.claim_due(owner="worker-a", now=now, lease=timedelta(minutes=1))
        attempt.lease_until = now - timedelta(seconds=1)
        assert await store.recover_expired_leases(now=now) == 1
        claimed = await store.claim_due(owner="worker-b", now=now, lease=timedelta(minutes=1))
        assert claimed is attempt
        await store.record_success(attempt, now=now, provider_reference="provider-1")
        assert attempt.status == "delivered"


async def test_outbox_orchestration_is_idempotent_and_fail_closed(session_factory) -> None:
    now = datetime(2026, 9, 10, 23, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        store = SqlAlchemyNotificationStore(session)
        orchestrator = NotificationOrchestrator(
            store,
            lambda *_: NotificationPolicy(
                True, quiet_hours_start=time(22), quiet_hours_end=time(7)
            ),
        )
        first = await orchestrator.enqueue(
            _event(),
            subject_id="person-a",
            purpose="growth_tracking",
            consent_version="c-1",
            channel=NotificationChannel.PUSH,
            template_key="task.reminder",
            body="请查看今日行动",
            now=now,
        )
        replay = await orchestrator.enqueue(
            _event(),
            subject_id="person-a",
            purpose="growth_tracking",
            consent_version="c-1",
            channel=NotificationChannel.PUSH,
            template_key="task.reminder",
            body="请查看今日行动",
            now=now,
        )
        assert first.attempt_id == replay.attempt_id
        assert first.status == "retry"
        assert first.next_attempt_at == datetime(2026, 9, 11, 7, tzinfo=UTC)
