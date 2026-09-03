from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.contracts import ExperienceContractError, ExperienceEventType
from backend.intelligence.experience.engagement_persistence import (
    SqlAlchemyEngagementEventReader,
)
from backend.intelligence.experience.persistence import (
    ExperienceOutboxRow,
    ExperiencePersistenceBase,
    SqlAlchemyExperienceOutbox,
)
from backend.intelligence.experience.pipeline import ExperienceOutboxMessage
from tests.intelligence.experience.test_gateway import _event, _scope


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
async def test_reader_returns_scope_bound_events_in_requested_order(session_factory) -> None:
    first = _event(event_id="reader-first", event_type=ExperienceEventType.ACTION_COMPLETED)
    second = _event(event_id="reader-second", event_type=ExperienceEventType.ACTION_STARTED)
    async with session_factory() as session, session.begin():
        outbox = SqlAlchemyExperienceOutbox(session)
        await outbox.append(
            ExperienceOutboxMessage(
                message_id="outbox:first",
                event_type=f"experience.{first.event_type.value}",
                record=first,
                scope=first.scope,
            )
        )
        await outbox.append(
            ExperienceOutboxMessage(
                message_id="outbox:second",
                event_type=f"experience.{second.event_type.value}",
                record=second,
                scope=second.scope,
            )
        )

        events = await SqlAlchemyEngagementEventReader(session).read(
            scope=first.scope,
            event_ids=(second.event_id, first.event_id),
        )

    assert tuple(event.event_id for event in events) == (second.event_id, first.event_id)


@pytest.mark.asyncio
async def test_reader_rejects_missing_or_cross_scope_events(session_factory) -> None:
    event = _event(event_id="reader-missing", event_type=ExperienceEventType.ACTION_COMPLETED)
    async with session_factory() as session, session.begin():
        reader = SqlAlchemyEngagementEventReader(session)
        with pytest.raises(ExperienceContractError, match="EVENTS_NOT_FOUND"):
            await reader.read(scope=event.scope, event_ids=(event.event_id,))

    async with session_factory() as session, session.begin():
        outbox = SqlAlchemyExperienceOutbox(session)
        await outbox.append(
            ExperienceOutboxMessage(
                message_id="outbox:cross-scope",
                event_type=f"experience.{event.event_type.value}",
                record=event,
                scope=event.scope,
            )
        )
        with pytest.raises(ExperienceContractError, match="EVENTS_NOT_FOUND"):
            await SqlAlchemyEngagementEventReader(session).read(
                scope=_scope(family_id="other-family"), event_ids=(event.event_id,)
            )


@pytest.mark.asyncio
async def test_reader_rejects_deleted_scope(session_factory) -> None:
    event = _event(event_id="reader-deleted", event_type=ExperienceEventType.ACTION_COMPLETED)
    deleted_scope = replace(
        event.scope,
        deletion_ref=replace(event.scope.deletion_ref, requested_at=event.occurred_at),
    )
    async with session_factory() as session, session.begin():
        with pytest.raises(ExperienceContractError, match="SCOPE_DELETED"):
            await SqlAlchemyEngagementEventReader(session).read(
                scope=deleted_scope, event_ids=(event.event_id,)
            )


@pytest.mark.asyncio
async def test_reader_maps_corrupt_persisted_envelope_to_stable_error(session_factory) -> None:
    event = _event(event_id="reader-corrupt", event_type=ExperienceEventType.ACTION_COMPLETED)
    async with session_factory() as session, session.begin():
        outbox = SqlAlchemyExperienceOutbox(session)
        await outbox.append(
            ExperienceOutboxMessage(
                message_id="outbox:corrupt",
                event_type=f"experience.{event.event_type.value}",
                record=event,
                scope=event.scope,
            )
        )
        row = await session.get(ExperienceOutboxRow, "outbox:corrupt")
        assert row is not None
        row.payload = {"record": {"event_id": event.event_id}}
        with pytest.raises(ExperienceContractError, match="EVENT_READER_INVALID"):
            await SqlAlchemyEngagementEventReader(session).read(
                scope=event.scope, event_ids=(event.event_id,)
            )
