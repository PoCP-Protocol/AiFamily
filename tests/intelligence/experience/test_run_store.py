from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.run_store import (
    ExperienceRunPersistenceBase,
    RunScope,
    SqlAlchemyExperienceRunStore,
)
from backend.intelligence.experience.runs import (
    DurableExperienceRun,
    RunContractError,
    RunState,
)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperienceRunPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _run(
    *,
    tenant_id: str = "tenant-run",
    family_id: str = "family-run",
    subjects: tuple[str, ...] = ("guardian-run", "child-run"),
    payload: dict[str, object] | None = None,
    checkpoint_payload: dict[str, object] | None = None,
    artifact_refs: tuple[str, ...] = ("media:sha256:" + "a" * 64,),
) -> DurableExperienceRun:
    run = DurableExperienceRun(
        run_id="run-001",
        tenant_id=tenant_id,
        family_id=family_id,
        subject_ids=subjects,
        request_ref="request:run-001",
    )
    run.transition(
        RunState.RUNNING,
        event_id="event-started",
        idempotency_key="idem-started",
        payload=payload or {"source": "api"},
    )
    run.checkpoint(
        checkpoint_id="checkpoint-draft",
        payload={"kind": "model-output"},
        artifact_refs=artifact_refs,
        draft_payload=checkpoint_payload or {"headline": "draft only"},
        idempotency_key="idem-checkpoint",
    )
    run.transition(
        RunState.SUCCEEDED,
        event_id="event-succeeded",
        idempotency_key="idem-succeeded",
        payload={"checkpoint_id": "checkpoint-draft"},
    )
    return run


def _scope(
    *,
    tenant_id: str = "tenant-run",
    family_id: str = "family-run",
    subjects: tuple[str, ...] = ("guardian-run", "child-run"),
) -> RunScope:
    return RunScope(tenant_id=tenant_id, family_id=family_id, subject_ids=subjects)


@pytest.mark.asyncio
async def test_save_and_replay_round_trip_preserves_append_only_run(session_factory) -> None:
    original = _run()
    async with session_factory() as session:
        async with session.begin():
            saved = await SqlAlchemyExperienceRunStore(session).save(original)
        replay = await SqlAlchemyExperienceRunStore(session).replay(
            scope=_scope(), run_id="run-001"
        )

    assert saved == original.snapshot
    assert replay.snapshot.state is RunState.SUCCEEDED
    assert replay.snapshot.version == 3
    assert replay.snapshot.latest_checkpoint_id == "checkpoint-draft"
    assert tuple(event.event_id for event in replay.events) == (
        "event-started",
        "checkpoint-draft",
        "event-succeeded",
    )
    assert replay.checkpoints[0].status == "DRAFT"
    assert replay.checkpoints[0].draft_payload == {"headline": "draft only"}
    assert replay.run.replay() == replay.snapshot


@pytest.mark.asyncio
async def test_save_is_idempotent_and_conflicting_event_replay_fails_closed(
    session_factory,
) -> None:
    original = _run()
    async with session_factory() as session:
        store = SqlAlchemyExperienceRunStore(session)
        async with session.begin():
            first = await store.save(original)
            second = await store.save(_run())
        assert second == first

        conflicting = _run(payload={"source": "tampered"})
        with pytest.raises(RunContractError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
            await store.save(conflicting)


@pytest.mark.asyncio
async def test_conflicting_checkpoint_replay_is_rejected(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyExperienceRunStore(session)
        async with session.begin():
            await store.save(_run())

        conflicting = _run(checkpoint_payload={"headline": "tampered"})
        with pytest.raises(RunContractError, match="CHECKPOINT_REPLAY_MISMATCH"):
            await store.save(conflicting)


@pytest.mark.asyncio
async def test_scope_isolation_applies_to_tenant_family_and_subjects(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyExperienceRunStore(session)
        async with session.begin():
            await store.save(_run())

        with pytest.raises(RunContractError, match="RUN_NOT_FOUND"):
            await store.load(scope=_scope(tenant_id="tenant-other"), run_id="run-001")
        with pytest.raises(RunContractError, match="RUN_SCOPE_MISMATCH"):
            await store.load(scope=_scope(family_id="family-other"), run_id="run-001")
        with pytest.raises(RunContractError, match="RUN_SCOPE_MISMATCH"):
            await store.load(
                scope=_scope(subjects=("guardian-other", "child-run")), run_id="run-001"
            )


@pytest.mark.asyncio
async def test_tenant_scoped_run_ids_do_not_collide(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyExperienceRunStore(session)
        async with session.begin():
            await store.save(_run(tenant_id="tenant-a"))
            await store.save(_run(tenant_id="tenant-b"))

        left = await store.load(scope=_scope(tenant_id="tenant-a"), run_id="run-001")
        right = await store.load(scope=_scope(tenant_id="tenant-b"), run_id="run-001")

    assert left.tenant_id == "tenant-a"
    assert right.tenant_id == "tenant-b"


def test_run_scope_rejects_empty_or_duplicate_subjects() -> None:
    with pytest.raises(RunContractError, match="SUBJECTS_REQUIRED"):
        RunScope(tenant_id="tenant", family_id="family", subject_ids=())
    with pytest.raises(RunContractError, match="SUBJECTS_MUST_BE_UNIQUE"):
        RunScope(tenant_id="tenant", family_id="family", subject_ids=("child", "child"))
