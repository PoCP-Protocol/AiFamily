from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.outbox_worker import (
    DeliveryStatus,
    ExperienceOutboxWorker,
    InMemoryExperienceDeadLetterSink,
    PermanentExperienceDeliveryError,
)
from backend.intelligence.experience.persistence import (
    ExperienceOutboxRow,
    ExperiencePersistenceBase,
    SqlAlchemyExperienceOutbox,
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


async def _seed(session_factory, *, message_id: str = "message-1") -> None:
    async with session_factory() as session, session.begin():
        session.add(
            ExperienceOutboxRow(
                message_id=message_id,
                event_type="experience.feedback_signal",
                tenant_id="tenant-worker",
                region_id="cn-east-1",
                family_id="family-worker",
                subject_ids=["guardian-worker", "child-worker"],
                purpose="ux_optimization",
                consent_version="consent-v1",
                idempotency_key=f"idempotency-{message_id}",
                schema_version="experience.v1",
                payload={"record": {"status": "DRAFT"}},
                enqueued_at=datetime(2026, 8, 30, tzinfo=UTC),
            )
        )


class RecordingConsumer:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def consume(self, message) -> None:
        self.messages.append(message.message_id)


class FlakyConsumer(RecordingConsumer):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    async def consume(self, message) -> None:
        self.messages.append(message.message_id)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("projection unavailable")


@pytest.mark.asyncio
async def test_worker_publishes_after_consume_and_mark_is_idempotent(session_factory) -> None:
    await _seed(session_factory)
    consumer = RecordingConsumer()
    sink = InMemoryExperienceDeadLetterSink()

    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        worker = ExperienceOutboxWorker(outbox, consumer, dead_letter_sink=sink, max_attempts=2)
        async with session.begin():
            report = await worker.run_once(limit=10)
        assert report.published == 1
        assert report.results[0].status is DeliveryStatus.PUBLISHED

        # A second pass sees no pending row.  Calling mark_published directly
        # proves the adapter's acknowledgement is also replay-safe.
        assert await outbox.pending() == ()
        await session.rollback()
        async with session.begin():
            marked = await outbox.mark_published("message-1")
        assert marked.published
    assert consumer.messages == ["message-1"]
    assert sink.messages() == ()


@pytest.mark.asyncio
async def test_worker_leaves_transient_failure_pending_then_retries(session_factory) -> None:
    await _seed(session_factory)
    consumer = FlakyConsumer(failures=1)
    sink = InMemoryExperienceDeadLetterSink()

    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        worker = ExperienceOutboxWorker(outbox, consumer, dead_letter_sink=sink, max_attempts=3)
        async with session.begin():
            first = await worker.run_once()
        assert first.results[0].status is DeliveryStatus.RETRY
        assert first.results[0].attempts == 1
        assert len(await outbox.pending()) == 1
        await session.rollback()

        async with session.begin():
            second = await worker.run_once()
        assert second.results[0].status is DeliveryStatus.PUBLISHED
        assert second.results[0].attempts == 2
        assert await outbox.pending() == ()
    assert consumer.messages == ["message-1", "message-1"]


@pytest.mark.asyncio
async def test_worker_dead_letters_permanent_failure_only_after_sink_ack(
    session_factory,
) -> None:
    await _seed(session_factory)

    class PermanentConsumer:
        async def consume(self, _message) -> None:
            raise PermanentExperienceDeliveryError("invalid envelope")

    sink = InMemoryExperienceDeadLetterSink()
    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        worker = ExperienceOutboxWorker(
            outbox,
            PermanentConsumer(),
            dead_letter_sink=sink,
            max_attempts=5,
        )
        async with session.begin():
            report = await worker.run_once()
        assert report.results[0].status is DeliveryStatus.DEAD_LETTERED
        assert report.results[0].attempts == 1
        assert await outbox.pending() == ()

    dead_letters = sink.messages()
    assert len(dead_letters) == 1
    assert dead_letters[0].message.message_id == "message-1"
    assert dead_letters[0].error == "invalid envelope"


@pytest.mark.asyncio
async def test_worker_keeps_pending_when_dead_letter_sink_fails(session_factory) -> None:
    await _seed(session_factory)

    class PermanentConsumer:
        async def consume(self, _message) -> None:
            raise PermanentExperienceDeliveryError("invalid envelope")

    class BrokenSink:
        async def publish(self, _message, *, attempts: int, error: str) -> None:
            raise RuntimeError("dlq unavailable")

    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        worker = ExperienceOutboxWorker(
            outbox,
            PermanentConsumer(),
            dead_letter_sink=BrokenSink(),
            max_attempts=1,
        )
        async with session.begin():
            report = await worker.run_once()
        assert report.results[0].status is DeliveryStatus.RETRY
        assert "dlq unavailable" in (report.results[0].error or "")
        assert len(await outbox.pending()) == 1


@pytest.mark.asyncio
async def test_worker_respects_pull_limit_and_scope_opaque_payload(session_factory) -> None:
    await _seed(session_factory, message_id="message-a")
    await _seed(session_factory, message_id="message-b")
    consumer = RecordingConsumer()

    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        worker = ExperienceOutboxWorker(
            outbox,
            consumer,
            dead_letter_sink=InMemoryExperienceDeadLetterSink(),
        )
        async with session.begin():
            report = await worker.run_once(limit=1)
        assert report.pulled == 1
        assert len(await outbox.pending()) == 1
    assert consumer.messages == ["message-a"]
