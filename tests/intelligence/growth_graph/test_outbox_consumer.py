from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.outbox_worker import (
    DeliveryStatus,
    ExperienceOutboxWorker,
    InMemoryExperienceDeadLetterSink,
)
from backend.intelligence.experience.persistence import (
    ExperiencePersistenceBase,
    SqlAlchemyExperienceOutbox,
)
from backend.intelligence.growth_graph.outbox_consumer import GrowthGraphOutboxConsumer
from backend.intelligence.growth_graph.store import (
    GrowthGraphPersistenceBase,
    SqlAlchemyGrowthGraphProjection,
)
from tests.intelligence.experience.test_achievement_consumer import _outbox_message
from tests.intelligence.experience.test_gateway import _event


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperiencePersistenceBase.metadata.create_all)
        await connection.run_sync(GrowthGraphPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_worker_projects_event_into_graph_and_replays_safely(session_factory) -> None:
    event = _event(
        event_id="event-graph-outbox",
        occurred_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        projection = SqlAlchemyGrowthGraphProjection(session)
        async with session.begin():
            await outbox.append(_outbox_message(event))

        worker = ExperienceOutboxWorker(
            outbox,
            GrowthGraphOutboxConsumer(projection),
            dead_letter_sink=InMemoryExperienceDeadLetterSink(),
        )
        async with session.begin():
            report = await worker.run_once()
        assert report.results[0].status is DeliveryStatus.PUBLISHED
        assert len(await projection.query(event.scope)) == 1
        assert await outbox.pending() == ()


@pytest.mark.asyncio
async def test_invalid_non_event_envelope_is_dead_lettered(session_factory) -> None:
    async with session_factory() as session:
        outbox = SqlAlchemyExperienceOutbox(session)
        from backend.intelligence.experience.persistence import ExperienceOutboxRow

        async with session.begin():
            session.add(
                ExperienceOutboxRow(
                    message_id="message-graph-invalid",
                    event_type="experience.recommendation_decision",
                    tenant_id="tenant-a",
                    region_id="CN",
                    family_id="family-a",
                    subject_ids=["child-a"],
                    purpose="growth_support",
                    consent_version="consent.v1",
                    idempotency_key="idempotency-graph-invalid",
                    schema_version="experience.v1",
                    payload={"record": {}},
                    enqueued_at=datetime(2026, 8, 30, tzinfo=UTC),
                )
            )
        sink = InMemoryExperienceDeadLetterSink()
        worker = ExperienceOutboxWorker(
            outbox,
            GrowthGraphOutboxConsumer(SqlAlchemyGrowthGraphProjection(session)),
            dead_letter_sink=sink,
        )
        async with session.begin():
            report = await worker.run_once()
        assert report.results[0].status is DeliveryStatus.DEAD_LETTERED
        assert sink.messages()[0].error == "GRAPH_EVENT_INVALID"
