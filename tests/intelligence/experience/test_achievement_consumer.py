from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.achievement import AchievementEngine, AchievementKey
from backend.intelligence.experience.achievement_consumer import (
    ExperienceAchievementConsumer,
    ExperienceAchievementEnvelopeError,
    decode_experience_event,
)
from backend.intelligence.experience.achievement_persistence import (
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.contracts import ExperienceEventType
from backend.intelligence.experience.outbox_worker import (
    DeliveryStatus,
    ExperienceOutboxWorker,
    InMemoryExperienceDeadLetterSink,
)
from backend.intelligence.experience.persistence import (
    ExperienceOutboxRow,
    ExperiencePersistenceBase,
    SqlAlchemyExperienceOutbox,
)
from backend.intelligence.experience.pipeline import ExperienceOutboxMessage
from backend.intelligence.experience.projections import (
    SqlAlchemyAchievementNotificationProjection,
    SqlAlchemyExperienceAnalyticsProjection,
)

from .test_gateway import _event


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


@pytest.mark.asyncio
async def test_event_outbox_worker_projects_evidence_bound_achievement(session_factory) -> None:
    event = _event(
        event_id="event-achievement-consumer",
        event_type=ExperienceEventType.ACTION_COMPLETED,
        occurred_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        async with session.begin():
            await outbox.append(_outbox_message(event))

        engine = AchievementEngine()
        consumer = ExperienceAchievementConsumer(engine)
        sink = InMemoryExperienceDeadLetterSink()
        worker = ExperienceOutboxWorker(outbox, consumer, dead_letter_sink=sink)
        async with session.begin():
            report = await worker.run_once()

        assert report.results[0].status is DeliveryStatus.PUBLISHED
        assert report.published == 1
        achievements = engine.projection.earned(event.scope)
        assert tuple(item.key for item in achievements) == (AchievementKey.FIRST_STEP,)
        assert achievements[0].evidence_refs == ("experience-event:event-achievement-consumer",)
        assert achievements[0].provenance == event.provenance
        assert await outbox.pending() == ()
    assert sink.messages() == ()


@pytest.mark.asyncio
async def test_consumer_replay_is_idempotent_after_projection_before_ack(session_factory) -> None:
    event = _event(
        event_id="event-achievement-replay",
        event_type=ExperienceEventType.ACTION_COMPLETED,
    )
    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        async with session.begin():
            stored = await outbox.append(_outbox_message(event))

        engine = AchievementEngine()
        consumer = ExperienceAchievementConsumer(engine)
        await consumer.consume(stored)
        await consumer.consume(stored)

        assert len(engine.projection.earned(event.scope)) == 1
        assert consumer.achievements_for(stored.message_id)[0].key is AchievementKey.FIRST_STEP


@pytest.mark.asyncio
async def test_consumer_updates_achievement_notification_and_analytics_in_same_relay(
    session_factory,
) -> None:
    event = _event(
        event_id="event-feedback-projections",
        event_type=ExperienceEventType.ACTION_COMPLETED,
    )
    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        async with session.begin():
            await outbox.append(_outbox_message(event))

        consumer = ExperienceAchievementConsumer(
            projection=SqlAlchemyAchievementProjection(session),
            notifications=SqlAlchemyAchievementNotificationProjection(session),
            analytics=SqlAlchemyExperienceAnalyticsProjection(session),
        )
        worker = ExperienceOutboxWorker(
            outbox,
            consumer,
            dead_letter_sink=InMemoryExperienceDeadLetterSink(),
        )
        async with session.begin():
            report = await worker.run_once()
        assert report.published == 1

        notifications = SqlAlchemyAchievementNotificationProjection(session)
        analytics = SqlAlchemyExperienceAnalyticsProjection(session)
        assert len(await notifications.unread(event.scope)) == 1
        assert dict(await analytics.counts(event.scope)) == {
            "achievement:first_step": 1,
            "event:action_completed": 1,
        }


@pytest.mark.asyncio
async def test_non_event_envelope_is_permanent_and_worker_dead_letters(session_factory) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                ExperienceOutboxRow(
                    message_id="message-non-event",
                    event_type="experience.recommendation_decision",
                    tenant_id="tenant-achievement",
                    region_id="CN",
                    family_id="family-achievement",
                    subject_ids=["child-achievement"],
                    purpose="growth_support",
                    consent_version="consent.v1",
                    idempotency_key="5:tenant-achievement:non-event",
                    schema_version="experience.v1",
                    payload={"record": {"status": "PROPOSED"}},
                    enqueued_at=datetime(2026, 8, 30, tzinfo=UTC),
                )
            )
        outbox = SqlAlchemyExperienceOutbox(session)
        sink = InMemoryExperienceDeadLetterSink()
        worker = ExperienceOutboxWorker(
            outbox,
            ExperienceAchievementConsumer(),
            dead_letter_sink=sink,
            max_attempts=3,
        )
        async with session.begin():
            report = await worker.run_once()
        assert report.results[0].status is DeliveryStatus.DEAD_LETTERED
        assert report.results[0].attempts == 1
        assert await outbox.pending() == ()
    assert (
        sink.messages()[0].error == "ACHIEVEMENT_EVENT_TYPE_MISMATCH"
        or sink.messages()[0].error == "ACHIEVEMENT_EVENT_TYPE_UNSUPPORTED"
    )


def test_decoder_rejects_malformed_record_without_synthesizing_scope() -> None:
    from backend.intelligence.experience.persistence import StoredExperienceMessage

    message = StoredExperienceMessage(
        message_id="message-malformed",
        event_type="experience.action_completed",
        tenant_id="tenant-a",
        region_id="CN",
        family_id="family-a",
        subject_ids=("child-a",),
        purpose="growth_support",
        consent_version="consent.v1",
        idempotency_key="5:tenant-a:event-a",
        schema_version="experience.v1",
        payload={"record": {"event_id": "event-a"}},
        enqueued_at=datetime(2026, 8, 30, tzinfo=UTC),
        published_at=None,
    )
    with pytest.raises(ExperienceAchievementEnvelopeError, match="EVENT_TYPE_REQUIRED"):
        decode_experience_event(message)


def _outbox_message(event) -> ExperienceOutboxMessage:
    return ExperienceOutboxMessage(
        message_id=f"outbox:{event.event_id}",
        event_type=f"experience.{event.event_type.value}",
        record=event,
        scope=event.scope,
    )
