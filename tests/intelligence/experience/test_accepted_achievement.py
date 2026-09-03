from dataclasses import replace
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.accepted_achievement import (
    ACHIEVEMENT_ACTION_NAME,
    AcceptedAchievementError,
    ExperienceAchievementActionHandler,
    build_achievement_action_proposal,
)
from backend.intelligence.experience.achievement import (
    AchievementKey,
    InMemoryAchievementProjection,
)
from backend.intelligence.experience.achievement_persistence import SqlAlchemyAchievementProjection
from backend.intelligence.experience.contracts import ExperienceEventType
from backend.intelligence.experience.engagement import EngagementDraftService
from backend.intelligence.experience.persistence import ExperiencePersistenceBase
from backend.intelligence.human_gate import ActorType, DecisionOutcome, InMemoryHumanGate
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.platform.audit import AuditRecorder
from tests.intelligence.experience.test_engagement import _command, _output
from tests.intelligence.experience.test_gateway import _event
from tests.intelligence.model_gateway.test_fail_closed import build


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperiencePersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_ai_candidate_becomes_human_reviewable_named_action() -> None:
    event = _event(event_id="achievement-event", event_type=ExperienceEventType.ACTION_COMPLETED)
    draft = await EngagementDraftService(
        build(FakeProvider({"family-engagement-draft": _output(evidence_refs=[event.event_id])}))
    ).generate_draft(_command(events=(event,)))
    proposal = build_achievement_action_proposal(
        draft,
        candidate_id="achievement-1",
        scope=event.scope,
        draft_id="draft:engagement-001",
        proposal_id="proposal:achievement-001",
        now=datetime(2026, 8, 30, tzinfo=UTC),
    )
    assert proposal.action_name == ACHIEVEMENT_ACTION_NAME
    assert proposal.draft_status == "DRAFT"
    assert proposal.action_arguments["evidence_refs"] == [
        "experience-event:achievement-event"
    ]

    gate = InMemoryHumanGate()
    task = gate.submit(proposal)
    _, request = gate.decide(
        task.task_id,
        actor_id="guardian-a",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        now=datetime(2026, 8, 30, 1, tzinfo=UTC),
    )
    assert request is not None
    projection = InMemoryAchievementProjection()
    receipt = await ExperienceAchievementActionHandler(
        projection, recorder=AuditRecorder()
    )(request)
    earned = projection.earned(event.scope)
    assert receipt.result_ref == earned[0].achievement_id
    assert earned[0].key is AchievementKey.AI_EVIDENCE_MOMENT
    assert earned[0].evidence_refs == ("experience-event:achievement-event",)


@pytest.mark.asyncio
async def test_handler_rejects_scope_tampering() -> None:
    event = _event(event_id="achievement-scope")
    draft = await EngagementDraftService(
        build(FakeProvider({"family-engagement-draft": _output(evidence_refs=[event.event_id])}))
    ).generate_draft(_command(events=(event,)))
    proposal = build_achievement_action_proposal(
        draft,
        candidate_id="achievement-1",
        scope=event.scope,
        draft_id="draft:scope",
        proposal_id="proposal:scope",
    )
    arguments = dict(proposal.action_arguments)
    tampered_scope = dict(arguments["experience_scope"])
    tampered_scope["family_id"] = "family-other"
    arguments["experience_scope"] = tampered_scope
    gate = InMemoryHumanGate()
    task = gate.submit(replace(proposal, action_arguments=arguments))
    _, request = gate.decide(
        task.task_id,
        actor_id="guardian-a",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
    )
    assert request is not None
    with pytest.raises(Exception, match="scope mismatch"):
        await ExperienceAchievementActionHandler(
            InMemoryAchievementProjection(), recorder=AuditRecorder()
        )(request)


@pytest.mark.asyncio
async def test_sql_projection_persists_human_accepted_candidate(session_factory) -> None:
    event = _event(event_id="achievement-sql", event_type=ExperienceEventType.ACTION_COMPLETED)
    draft = await EngagementDraftService(
        build(FakeProvider({"family-engagement-draft": _output(evidence_refs=[event.event_id])}))
    ).generate_draft(_command(events=(event,)))
    proposal = build_achievement_action_proposal(
        draft,
        candidate_id="achievement-1",
        scope=event.scope,
        draft_id="draft:sql",
        proposal_id="proposal:sql",
    )
    gate = InMemoryHumanGate()
    task = gate.submit(proposal)
    _, request = gate.decide(
        task.task_id,
        actor_id="guardian-a",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
    )
    assert request is not None
    async with session_factory() as session:
        projection = SqlAlchemyAchievementProjection(session)
        receipt = await ExperienceAchievementActionHandler(
            projection, recorder=AuditRecorder()
        )(request)
        assert receipt.result_ref is not None
    async with session_factory() as session:
        earned = await SqlAlchemyAchievementProjection(session).earned(event.scope)
        assert len(earned) == 1
        assert earned[0].key is AchievementKey.AI_EVIDENCE_MOMENT


@pytest.mark.asyncio
async def test_bridge_rejects_missing_draft_scope() -> None:
    event = _event(event_id="achievement-no-scope")
    # EngagementDraft returned by the service always carries the resolved scope;
    # this guard protects hand-built test objects and future adapters.
    generated = await EngagementDraftService(
        build(FakeProvider({"family-engagement-draft": _output(evidence_refs=[event.event_id])}))
    ).generate_draft(_command(events=(event,)))
    draft = replace(generated, scope=None)
    with pytest.raises(AcceptedAchievementError, match="ENGAGEMENT_SCOPE_REQUIRED"):
        build_achievement_action_proposal(
            draft,
            candidate_id="achievement-1",
            scope=event.scope,
            draft_id="draft:no-scope",
            proposal_id="proposal:no-scope",
        )


@pytest.mark.asyncio
async def test_distinct_evidence_events_create_repeatable_ai_moments() -> None:
    first = _event(event_id="achievement-repeat-1")
    second = _event(event_id="achievement-repeat-2")
    projection = InMemoryAchievementProjection()
    handler = ExperienceAchievementActionHandler(projection, recorder=AuditRecorder())

    for index, event in enumerate((first, second), start=1):
        draft = await EngagementDraftService(
            build(
                FakeProvider(
                    {"family-engagement-draft": _output(evidence_refs=[event.event_id])}
                )
            )
        ).generate_draft(_command(events=(event,)))
        proposal = build_achievement_action_proposal(
            draft,
            candidate_id="achievement-1",
            scope=event.scope,
            draft_id=f"draft:repeat-{index}",
            proposal_id=f"proposal:repeat-{index}",
        )
        gate = InMemoryHumanGate()
        task = gate.submit(proposal)
        _, request = gate.decide(
            task.task_id,
            actor_id="guardian-a",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
        )
        assert request is not None
        await handler(request)

    earned = projection.earned(first.scope)
    assert len(earned) == 2
    assert len({item.occurrence_id for item in earned}) == 2
