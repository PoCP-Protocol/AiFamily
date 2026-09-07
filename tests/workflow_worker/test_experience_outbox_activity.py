"""The worker's Experience-outbox fanout activity actually drains the outbox.

Before ``ExperienceOutboxFanoutActivity`` existed, ``GrowthGraphOutboxConsumer``
and ``ExperienceAchievementConsumer`` were both exercised only in tests that
built the fan-out consumer by hand
(``tests/domains/action/test_daily_action_postgres.py``); nothing in the
running ``workflow_worker`` composition ever called
``SqlAlchemyExperienceOutbox.pending()``.  This test proves the wired-in
activity (as installed in ``backend.workflow_worker.main.build_runtime``)
actually publishes a pending message and projects a Growth Graph edge from
it, on a real database.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.achievement_persistence import (
    AchievementProjectionRow,
)
from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceNode,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.experience.persistence import (
    ExperienceOutboxRow,
    ExperiencePersistenceBase,
    SqlAlchemyExperienceOutbox,
)
from backend.intelligence.experience.pipeline import ExperienceOutboxMessage
from backend.intelligence.growth_graph.store import (
    GrowthGraphEdgeRow,
    GrowthGraphPersistenceBase,
    SqlAlchemyGrowthGraphProjection,
)
from backend.platform.idempotency.keys import IdempotencyKey
from backend.workflow_worker.experience_outbox_activity import (
    ExperienceOutboxFanoutActivity,
    ExperienceOutboxFanoutRunner,
)

_ = AchievementProjectionRow  # ensure the achievement table registers on the shared metadata


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


def _scope() -> ExperienceScope:
    return ExperienceScope(
        global_id="global-fanout-1",
        tenant_id="tenant-fanout",
        region_id="CN",
        family_id="family-fanout",
        subject_ids=("subject-fanout",),
        purpose="growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete-fanout-1", "fanout.v1"),
        correlation_id="corr-fanout-1",
        causation_id="cause-fanout-1",
    )


async def _seed_pending_message(session_factory) -> str:
    scope = _scope()
    event = ExperienceEvent(
        event_id="event-fanout-1",
        event_type=ExperienceEventType.ACTION_COMPLETED,
        node=ExperienceNode.N5,
        scope=scope,
        idempotency_key=IdempotencyKey(tenant_id=scope.tenant_id, value="event-fanout-1"),
        provenance=ExperienceProvenance(
            provenance_ref="prov:fanout-1",
            source_refs=("growth-action:fanout-1",),
            kind=ProvenanceKind.USER,
            policy_version="fanout-policy.v1",
        ),
        actor_id="actor-fanout-1",
        occurred_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    message = ExperienceOutboxMessage(
        message_id="outbox-fanout-1",
        event_type="experience.action_completed",
        record=event,
        scope=scope,
    )
    async with session_factory() as session, session.begin():
        await SqlAlchemyExperienceOutbox(session).append(message)
    return message.message_id


@pytest.mark.asyncio
async def test_fanout_activity_publishes_pending_message_and_projects_growth_graph_edge(
    session_factory,
) -> None:
    message_id = await _seed_pending_message(session_factory)

    runner = ExperienceOutboxFanoutRunner(session_factory)
    activity = ExperienceOutboxFanoutActivity(runner, limit=10)

    execution = await activity.run_once()

    assert execution.succeeded is True
    assert execution.error_type is None

    async with session_factory() as session:
        published_at = (
            await session.execute(
                ExperienceOutboxRow.__table__.select().where(
                    ExperienceOutboxRow.message_id == message_id
                )
            )
        ).mappings().first()["published_at"]
        assert published_at is not None

        projection = SqlAlchemyGrowthGraphProjection(session)
        edges = await projection.query(_scope(), subject_id="subject-fanout")
    assert len(edges) == 1
    edge = edges[0]
    assert edge.relation == "experience.action_completed"
    assert edge.event_ref == "event-fanout-1"

    async with session_factory() as session:
        edge_row_count = (
            await session.execute(GrowthGraphEdgeRow.__table__.select())
        ).mappings().all()
    assert len(edge_row_count) == 1


@pytest.mark.asyncio
async def test_fanout_activity_is_idle_when_outbox_is_empty(session_factory) -> None:
    runner = ExperienceOutboxFanoutRunner(session_factory)
    activity = ExperienceOutboxFanoutActivity(runner, limit=10)

    execution = await activity.run_once()

    assert execution.succeeded is True
    async with session_factory() as session:
        edges = (
            await session.execute(GrowthGraphEdgeRow.__table__.select())
        ).mappings().all()
    assert edges == []
