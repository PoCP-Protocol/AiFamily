from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.production_experience_outbox_wiring import (
    ExperienceOutboxSchedule,
    ProductionExperienceOutboxRuntime,
)
from backend.intelligence.experience.dead_letter import (
    ExperienceDeadLetterRow,
    SqlAlchemyExperienceDeadLetterSink,
)
from backend.intelligence.experience.outbox_worker import (
    DeliveryStatus,
    OutboxWorkerReport,
)
from backend.intelligence.experience.persistence import (
    ExperienceDeliveryAttemptRow,
    ExperienceDeliveryAttemptStatus,
    ExperienceOutboxRow,
    ExperiencePersistenceBase,
    SqlAlchemyExperienceDeliveryAttemptStore,
    SqlAlchemyExperienceOutbox,
    StoredExperienceMessage,
)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperiencePersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed(session_factory, message_id: str = "outbox-runtime-1") -> None:
    async with session_factory() as session, session.begin():
        session.add(
            ExperienceOutboxRow(
                message_id=message_id,
                event_type="experience.feedback_signal",
                tenant_id="tenant-runtime",
                region_id="cn-east-1",
                family_id="family-runtime",
                subject_ids=["guardian-runtime"],
                purpose="ux_optimization",
                consent_version="consent-v1",
                idempotency_key=f"key-{message_id}",
                schema_version="experience.v1",
                payload={"record": {"status": "DRAFT"}},
                enqueued_at=datetime(2026, 8, 30, tzinfo=UTC),
            )
        )


class FlakyConsumer:
    def __init__(self, *, fail: bool) -> None:
        self.fail = fail
        self.seen: list[str] = []

    async def consume(self, message) -> None:
        self.seen.append(message.message_id)
        if self.fail:
            raise RuntimeError("projection unavailable")


class Sink:
    async def publish(self, _message, *, attempts: int, error: str) -> None:
        self.attempts = attempts
        self.error = error


class AlertSink:
    def __init__(self) -> None:
        self.reports = []

    async def __call__(self, report) -> None:
        self.reports.append(report)


@pytest.mark.asyncio
async def test_runtime_persists_attempts_across_new_worker_instances(session_factory) -> None:
    await _seed(session_factory)
    first = FlakyConsumer(fail=True)
    runtime = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: first,
        lambda _session: Sink(),
        environment="staging",
        worker_id="worker-a",
    )
    report = await runtime.run_once()
    assert report.results[0].status is DeliveryStatus.RETRY
    assert report.results[0].attempts == 1

    second = FlakyConsumer(fail=False)
    restarted = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: second,
        lambda _session: Sink(),
        environment="production",
        worker_id="worker-a",
    )
    report = await restarted.run_once()
    assert report.results[0].status is DeliveryStatus.PUBLISHED
    assert report.results[0].attempts == 2
    state = await restarted.delivery_attempt("outbox-runtime-1")
    assert state is not None
    assert state.status.value == "PUBLISHED"
    assert state.attempts == 2


@pytest.mark.asyncio
async def test_runtime_scheduled_tick_uses_explicit_bounded_schedule(session_factory) -> None:
    await _seed(session_factory)
    runtime = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: FlakyConsumer(fail=False),
        lambda _session: Sink(),
        environment="production",
        worker_id="worker-schedule",
        schedule=ExperienceOutboxSchedule(
            interval=timedelta(seconds=15), batch_limit=1, max_polls=2
        ),
    )

    reports = await runtime.run_scheduled_tick()

    assert reports[0].published == 1
    assert reports[-1].pulled == 0


@pytest.mark.asyncio
async def test_runtime_exposes_bounded_metadata_only_attempt_query(session_factory) -> None:
    await _seed(session_factory)
    runtime = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: FlakyConsumer(fail=False),
        lambda _session: Sink(),
        environment="production",
        worker_id="worker-query",
    )
    await runtime.run_once()

    attempts = await runtime.delivery_attempts(
        limit=10, status=ExperienceDeliveryAttemptStatus.PUBLISHED
    )

    assert len(attempts) == 1
    assert attempts[0].message_id == "outbox-runtime-1"
    assert attempts[0].status is ExperienceDeliveryAttemptStatus.PUBLISHED
    assert not hasattr(attempts[0], "payload")
    with pytest.raises(ValueError, match="non-negative integer"):
        await runtime.delivery_attempts(limit=-1)


@pytest.mark.asyncio
async def test_runtime_exposes_cursor_pages_and_status_summary(session_factory) -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        session.add_all(
            [
                ExperienceDeliveryAttemptRow(
                    message_id="attempt-a",
                    attempts=2,
                    status=ExperienceDeliveryAttemptStatus.PENDING,
                    last_error="temporary",
                    updated_at=now,
                ),
                ExperienceDeliveryAttemptRow(
                    message_id="attempt-b",
                    attempts=1,
                    status=ExperienceDeliveryAttemptStatus.PUBLISHED,
                    updated_at=now,
                ),
            ]
        )
    runtime = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: object(),
        lambda _session: object(),
        environment="production",
        worker_id="worker-query",
    )

    first = await runtime.delivery_attempts_page(limit=1)
    assert [item.message_id for item in first.items] == ["attempt-a"]
    assert first.next_cursor is not None
    second = await runtime.delivery_attempts_page(limit=1, after=first.next_cursor)
    assert [item.message_id for item in second.items] == ["attempt-b"]
    assert second.next_cursor is None
    summary = await runtime.delivery_attempt_summary()
    assert summary.count(ExperienceDeliveryAttemptStatus.PENDING) == 1
    assert summary.count(ExperienceDeliveryAttemptStatus.PUBLISHED) == 1


def test_runtime_schedule_rejects_unbounded_values() -> None:
    with pytest.raises(ValueError, match="interval must be positive"):
        ExperienceOutboxSchedule(interval=timedelta(0))
    with pytest.raises(ValueError, match="max_polls must be positive"):
        ExperienceOutboxSchedule(max_polls=0)


@pytest.mark.asyncio
async def test_runtime_dead_letter_state_is_metadata_only(session_factory) -> None:
    await _seed(session_factory)
    sink = Sink()

    class PermanentConsumer:
        async def consume(self, _message) -> None:
            from backend.intelligence.experience.outbox_worker import (
                PermanentExperienceDeliveryError,
            )

            raise PermanentExperienceDeliveryError("invalid envelope")

    runtime = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: PermanentConsumer(),
        lambda _session: sink,
        environment="production",
        worker_id="worker-a",
    )
    report = await runtime.run_once()
    assert report.results[0].status is DeliveryStatus.DEAD_LETTERED
    state = await runtime.delivery_attempt("outbox-runtime-1")
    assert state is not None
    assert state.status.value == "DEAD_LETTERED"
    assert state.last_error == "invalid envelope"


@pytest.mark.asyncio
async def test_runtime_alerts_only_on_retry_or_dead_letter_after_commit(session_factory) -> None:
    await _seed(session_factory)
    alert = AlertSink()
    runtime = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: FlakyConsumer(fail=True),
        lambda _session: Sink(),
        environment="production",
        worker_id="worker-alert",
        max_attempts=2,
        alert_sink=alert,
    )

    retry = await runtime.run_once()
    assert retry.retried == 1
    assert len(alert.reports) == 1

    recovery = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: FlakyConsumer(fail=False),
        lambda _session: Sink(),
        environment="production",
        worker_id="worker-alert",
    )
    assert (await recovery.run_once()).published == 1

    # The alert is invoked after the transaction commits; a sink failure must
    # not make the acknowledged outbox row visible again on a later pass.
    await _seed(session_factory, "outbox-runtime-alert-failure")
    async def fail_alert(_report) -> None:
        raise RuntimeError("alert transport unavailable")

    class PermanentConsumer:
        async def consume(self, _message) -> None:
            from backend.intelligence.experience.outbox_worker import (
                PermanentExperienceDeliveryError,
            )

            raise PermanentExperienceDeliveryError("invalid envelope")

    failing_alert_runtime = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: PermanentConsumer(),
        lambda _session: Sink(),
        environment="production",
        worker_id="worker-alert-2",
        max_attempts=1,
        alert_sink=fail_alert,
    )
    with pytest.raises(RuntimeError, match="alert transport unavailable"):
        await failing_alert_runtime.run_once()
    assert await failing_alert_runtime.run_once() == OutboxWorkerReport(results=())


@pytest.mark.asyncio
async def test_delivery_lease_blocks_other_worker_and_allows_expiry_takeover(
    session_factory,
) -> None:
    await _seed(session_factory)
    first = FlakyConsumer(fail=True)
    runtime_a = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: first,
        lambda _session: Sink(),
        environment="production",
        worker_id="worker-a",
        lease_ttl=timedelta(hours=1),
    )
    first_report = await runtime_a.run_once()
    assert first_report.results[0].status is DeliveryStatus.RETRY

    runtime_b = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: FlakyConsumer(fail=False),
        lambda _session: Sink(),
        environment="production",
        worker_id="worker-b",
        lease_ttl=timedelta(minutes=5),
    )
    blocked = await runtime_b.run_once()
    assert blocked.results[0].status is DeliveryStatus.LEASED

    async with session_factory() as session, session.begin():
        attempts = SqlAlchemyExperienceDeliveryAttemptStore(session)
        takeover = await attempts.claim_attempt(
            "outbox-runtime-1",
            worker_id="worker-b",
            lease_ttl=timedelta(minutes=5),
            now=datetime.now(UTC) + timedelta(hours=2),
        )
        assert takeover == 2


@pytest.mark.asyncio
async def test_sql_dead_letter_sink_is_idempotent_and_payload_free(session_factory) -> None:
    await _seed(session_factory)

    class PermanentConsumer:
        async def consume(self, _message) -> None:
            from backend.intelligence.experience.outbox_worker import (
                PermanentExperienceDeliveryError,
            )

            raise PermanentExperienceDeliveryError("invalid envelope")

    runtime = ProductionExperienceOutboxRuntime(
        session_factory,
        lambda _session: PermanentConsumer(),
        lambda session: SqlAlchemyExperienceDeadLetterSink(session),
        environment="production",
        worker_id="worker-dlq",
    )
    report = await runtime.run_once()
    assert report.results[0].status is DeliveryStatus.DEAD_LETTERED

    async with session_factory() as session:
        sink = SqlAlchemyExperienceDeadLetterSink(session)
        async with session.begin():
            pending = await session.get(ExperienceOutboxRow, "outbox-runtime-1")
            assert pending is not None
            message = await SqlAlchemyExperienceOutbox(session).pending(limit=1)
            assert message == ()
            # Replaying the terminal write is a no-op, not a duplicate row.
            await sink.publish(
                StoredExperienceMessage(
                    message_id=pending.message_id,
                    event_type=pending.event_type,
                    tenant_id=pending.tenant_id,
                    region_id=pending.region_id,
                    family_id=pending.family_id,
                    subject_ids=tuple(pending.subject_ids),
                    purpose=pending.purpose,
                    consent_version=pending.consent_version,
                    idempotency_key=pending.idempotency_key,
                    schema_version=pending.schema_version,
                    payload=dict(pending.payload),
                    enqueued_at=pending.enqueued_at,
                    published_at=pending.published_at,
                ),
                attempts=1,
                error="invalid envelope",
            )
        dead_letters = await sink.list_dead_letters()
        assert len(dead_letters) == 1
        assert not hasattr(dead_letters[0], "payload")
        assert not hasattr(ExperienceDeadLetterRow, "payload")


def test_runtime_rejects_non_deployment_environment(session_factory) -> None:
    with pytest.raises(ValueError, match="staging or production"):
        ProductionExperienceOutboxRuntime(
            session_factory,
            lambda _session: object(),
            lambda _session: object(),
            environment="test",
            worker_id="worker-a",
        )

    with pytest.raises(TypeError, match="alert_sink"):
        ProductionExperienceOutboxRuntime(
            session_factory,
            lambda _session: object(),
            lambda _session: object(),
            environment="production",
            worker_id="worker-a",
            alert_sink=object(),
        )
