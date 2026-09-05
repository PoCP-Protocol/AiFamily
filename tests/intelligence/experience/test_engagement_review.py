from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.engagement import EngagementDraft, EngagementDraftService
from backend.intelligence.experience.engagement_review import (
    AcceptedAchievementDraftVerifier,
    AchievementCandidateSubmissionService,
    EngagementDraftReviewError,
    EngagementDraftReviewNotFound,
    EngagementDraftReviewRow,
    InMemoryEngagementDraftReviewStore,
    SqlAlchemyEngagementDraftReviewStore,
    engagement_draft_id,
)
from backend.intelligence.experience.persistence import ExperiencePersistenceBase
from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    HumanGateBase,
    SqlAlchemyHumanGate,
)
from backend.intelligence.model_gateway.contracts import ModelDraft
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.platform.audit import AuditBase, AuditRecorder, read_all_events
from tests.intelligence.experience.test_engagement import _command, _output
from tests.intelligence.experience.test_gateway import _event, _scope
from tests.intelligence.model_gateway.test_fail_closed import build

NOW = datetime(2026, 9, 1, 9, tzinfo=UTC)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperiencePersistenceBase.metadata.create_all)
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _draft(*, event_id: str = "review-event") -> EngagementDraft:
    event = _event(event_id=event_id)
    service = EngagementDraftService(
        build(
            FakeProvider(
                {"family-engagement-draft": _output(evidence_refs=[event.event_id])}
            )
        )
    )
    return await service.generate_draft(_command(events=(event,)))


def test_draft_id_is_opaque_and_retry_stable() -> None:
    first = engagement_draft_id(
        tenant_id="tenant-a", family_id="family-a", request_id="request-a"
    )
    second = engagement_draft_id(
        tenant_id="tenant-a", family_id="family-a", request_id="request-a"
    )
    assert first == second
    assert first.startswith("engagement-draft:")
    assert "family-a" not in first


@pytest.mark.asyncio
async def test_in_memory_store_replays_and_authorizes_fresh_request_scope() -> None:
    draft = await _draft()
    assert draft.scope is not None
    store = InMemoryEngagementDraftReviewStore()
    saved = await store.save(draft, created_at=NOW)
    replayed = await store.save(draft, created_at=NOW + timedelta(minutes=2))
    assert replayed == saved

    fresh_scope = replace(
        draft.scope,
        correlation_id="correlation:fresh-request",
        causation_id="causation:fresh-request",
    )
    loaded = await store.resolve(saved.draft_id, scope=fresh_scope, now=NOW)
    assert loaded == saved


@pytest.mark.asyncio
async def test_store_hides_cross_scope_records_and_rejects_expired_or_deleted_scope() -> None:
    draft = await _draft()
    assert draft.scope is not None
    store = InMemoryEngagementDraftReviewStore()
    saved = await store.save(draft, created_at=NOW, ttl=timedelta(minutes=5))

    with pytest.raises(EngagementDraftReviewNotFound):
        await store.resolve(
            saved.draft_id,
            scope=_scope(family_id="family-other"),
            now=NOW,
        )
    with pytest.raises(EngagementDraftReviewError, match="EXPIRED"):
        await store.resolve(
            saved.draft_id,
            scope=draft.scope,
            now=NOW + timedelta(minutes=5),
        )
    deleted = replace(
        draft.scope,
        deletion_ref=replace(draft.scope.deletion_ref, requested_at=NOW),
    )
    with pytest.raises(EngagementDraftReviewError, match="SCOPE_DELETED"):
        await store.resolve(saved.draft_id, scope=deleted, now=NOW)


@pytest.mark.asyncio
async def test_sql_store_round_trips_complete_scope_evidence_and_provenance(
    session_factory,
) -> None:
    draft = await _draft(event_id="sql-review-event")
    assert draft.scope is not None
    async with session_factory() as session:
        saved = await SqlAlchemyEngagementDraftReviewStore(session).save(
            draft, created_at=NOW
        )
        await session.commit()

    async with session_factory() as session:
        loaded = await SqlAlchemyEngagementDraftReviewStore(session).resolve(
            saved.draft_id,
            scope=replace(
                draft.scope,
                correlation_id="correlation:second-request",
                causation_id="causation:second-request",
            ),
            now=NOW,
        )
    assert loaded.draft.scope == draft.scope
    assert loaded.draft.evidence_event_ids == ("sql-review-event",)
    assert loaded.draft.draft.provenance == draft.draft.provenance


@pytest.mark.asyncio
async def test_sql_store_rejects_replay_with_changed_model_output(session_factory) -> None:
    draft = await _draft(event_id="replay-event")
    changed_output = dict(draft.output)
    changed_output["achievement_candidates"] = [
        {
            "candidate_id": "achievement-1",
            "text": "changed candidate",
            "evidence_refs": ["replay-event"],
        }
    ]
    changed = replace(
        draft,
        draft=ModelDraft(output=changed_output, provenance=draft.draft.provenance),
    )
    async with session_factory() as session:
        store = SqlAlchemyEngagementDraftReviewStore(session)
        await store.save(draft, created_at=NOW)
        await session.commit()
    async with session_factory() as session:
        with pytest.raises(EngagementDraftReviewError, match="REPLAY_MISMATCH"):
            await SqlAlchemyEngagementDraftReviewStore(session).save(
                changed, created_at=NOW
            )


@pytest.mark.asyncio
async def test_sql_store_detects_persisted_output_tampering(session_factory) -> None:
    draft = await _draft(event_id="tamper-event")
    assert draft.scope is not None
    async with session_factory() as session:
        saved = await SqlAlchemyEngagementDraftReviewStore(session).save(
            draft, created_at=NOW
        )
        await session.commit()
    async with session_factory() as session:
        row = await session.get(
            EngagementDraftReviewRow,
            (draft.scope.tenant_id, saved.draft_id),
        )
        assert row is not None
        row.output_payload = {**row.output_payload, "achievement_candidates": []}
        await session.commit()
    async with session_factory() as session:
        with pytest.raises(EngagementDraftReviewError, match="DIGEST_MISMATCH"):
            await SqlAlchemyEngagementDraftReviewStore(session).resolve(
                saved.draft_id, scope=draft.scope, now=NOW
            )


class _ExactEventReader:
    def __init__(self, events=()) -> None:
        self.events = tuple(events)

    async def read(self, *, scope, event_ids):
        by_id = {event.event_id: event for event in self.events}
        return tuple(by_id[item] for item in event_ids if item in by_id)


@pytest.mark.asyncio
async def test_candidate_submission_rechecks_evidence_and_opens_audited_human_task(
    session_factory,
) -> None:
    event = _event(event_id="submit-review-event")
    draft = await _draft(event_id=event.event_id)
    assert draft.scope is not None
    recorder = AuditRecorder()
    async with session_factory() as session:
        store = SqlAlchemyEngagementDraftReviewStore(session)
        saved = await store.save(draft, created_at=NOW)
        gate = SqlAlchemyHumanGate(session)
        service = AchievementCandidateSubmissionService(
            store,
            _ExactEventReader((event,)),
            gate,
            recorder,
        )
        task = await service.submit(
            draft_id=saved.draft_id,
            candidate_id="achievement-1",
            scope=draft.scope,
            actor_id="guardian-reviewer",
            approval_ref="guardian-consent:active",
            idempotency_key="submit-achievement-1",
            now=NOW + timedelta(minutes=1),
        )
        replay = await service.submit(
            draft_id=saved.draft_id,
            candidate_id="achievement-1",
            scope=draft.scope,
            actor_id="guardian-reviewer",
            approval_ref="guardian-consent:active",
            idempotency_key="submit-achievement-1",
            now=NOW + timedelta(minutes=1),
        )
        await recorder.flush(session)
        await session.commit()

    assert replay == task
    assert task.proposal.draft_id == saved.draft_id
    assert task.proposal.action_arguments["message"] == "记录这次尝试"
    assert task.proposal.action_arguments["evidence_refs"] == [
        "experience-event:submit-review-event"
    ]
    async with session_factory() as session:
        events = await read_all_events(session, tenant_id=draft.scope.tenant_id)
    assert any(item.action == "READ_ENGAGEMENT_DRAFT_EVIDENCE_FOR_REVIEW" for item in events)
    assert any(item.action == "CREATE_HUMAN_TASK" for item in events)


@pytest.mark.asyncio
async def test_candidate_submission_fails_before_human_gate_when_evidence_is_stale(
    session_factory,
) -> None:
    draft = await _draft(event_id="missing-review-event")
    assert draft.scope is not None
    recorder = AuditRecorder()
    async with session_factory() as session:
        store = SqlAlchemyEngagementDraftReviewStore(session)
        saved = await store.save(draft, created_at=NOW)
        service = AchievementCandidateSubmissionService(
            store,
            _ExactEventReader(),
            SqlAlchemyHumanGate(session),
            recorder,
        )
        with pytest.raises(EngagementDraftReviewError, match="EVIDENCE_STALE"):
            await service.submit(
                draft_id=saved.draft_id,
                candidate_id="achievement-1",
                scope=draft.scope,
                actor_id="guardian-reviewer",
                approval_ref="guardian-consent:active",
                idempotency_key="submit-missing-evidence",
                now=NOW + timedelta(minutes=1),
            )
    assert recorder.all_events() == ()


@pytest.mark.asyncio
async def test_accepted_achievement_verifier_rejects_tampered_action_arguments(
    session_factory,
) -> None:
    event = _event(event_id="execution-binding-event")
    draft = await _draft(event_id=event.event_id)
    assert draft.scope is not None
    recorder = AuditRecorder()
    async with session_factory() as session:
        store = SqlAlchemyEngagementDraftReviewStore(session)
        saved = await store.save(draft, created_at=NOW)
        gate = SqlAlchemyHumanGate(session)
        task = await AchievementCandidateSubmissionService(
            store,
            _ExactEventReader((event,)),
            gate,
            recorder,
        ).submit(
            draft_id=saved.draft_id,
            candidate_id="achievement-1",
            scope=draft.scope,
            actor_id="guardian-reviewer",
            approval_ref="guardian-consent:active",
            idempotency_key="submit-execution-binding",
            now=NOW + timedelta(minutes=1),
        )
        _, request = await gate.decide(
            task.task_id,
            actor_id="guardian-reviewer",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=recorder,
            now=NOW + timedelta(minutes=2),
        )
        assert request is not None
        verifier = AcceptedAchievementDraftVerifier(
            store,
            _ExactEventReader((event,)),
        )
        await verifier.verify(request)
        tampered = replace(
            request,
            action_arguments={**request.action_arguments, "message": "forged achievement"},
        )
        with pytest.raises(EngagementDraftReviewError, match="BINDING_MISMATCH"):
            await verifier.verify(tampered)
