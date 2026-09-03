import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.agent_runtime.contracts import AgentRun, AgentTask
from backend.intelligence.agent_runtime.persistence import (
    AgentRunConflict,
    AgentRunPersistenceBase,
    AgentRunRow,
    AgentRunScope,
    AgentRunStatus,
    AgentTraceEvent,
    SqlAlchemyAgentRunStore,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft

NOW = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(AgentRunPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def task(
    *,
    tenant_id: str = "tenant-1",
    family_id: str = "family-1",
    evidence_ref: str = "e-1",
    input_refs: tuple[str, ...] | None = None,
) -> AgentTask:
    return AgentTask(
        request_id="request-1",
        agent_id="parent_advisor",
        tenant_id=tenant_id,
        family_id=family_id,
        use_case="assessment_interpretation",
        context_snapshot_ref="snapshot-1",
        prompt_version="assessment-v1",
        schema_version="growth-v1",
        data_class="SYNTHETIC",
        payload={"evidence_refs": [evidence_ref]},
        output_schema={"type": "object"},
        input_refs=input_refs or (f"assessment-evidence:{evidence_ref}",),
    )


def draft(*, text: str = "draft") -> ModelDraft:
    return ModelDraft(
        output={"explanation": text},
        provenance=AiProvenance(
            provider_id="fake",
            model="fake-model",
            model_version="v1",
            prompt_version="assessment-v1",
            schema_version="growth-v1",
            context_snapshot_ref="snapshot-1",
            latency_ms=3,
            data_class="SYNTHETIC",
            use_case="assessment_interpretation",
            generated_at=NOW,
        ),
    )


def run(*, run_id: str = "run-1", text: str = "draft") -> AgentRun:
    return AgentRun(
        run_id=run_id,
        request_id="request-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="assessment_interpretation",
        draft=draft(text=text),
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=2),
    )


@pytest.mark.asyncio
async def test_start_is_idempotent_and_conflicts_on_changed_task(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyAgentRunStore(session)
        first = await store.start(
            task(), run_id="run-1", trace_id="trace-1", idempotency_key="idem-1", started_at=NOW
        )
        retry = await store.start(
            task(),
            run_id="different-run",
            trace_id="different-trace",
            idempotency_key="idem-1",
            started_at=NOW,
        )
        assert retry.run_id == first.run_id
        assert retry.status is AgentRunStatus.STARTED
        with pytest.raises(AgentRunConflict, match="IDEMPOTENCY_REPLAY_MISMATCH"):
            await store.start(
                task(evidence_ref="e-2"),
                run_id="run-2",
                trace_id="trace-2",
                idempotency_key="idem-1",
                started_at=NOW,
            )


@pytest.mark.asyncio
async def test_safe_replay_redacts_legacy_raw_task_fingerprint(session_factory) -> None:
    current_task = task()
    raw_fingerprint = json.dumps(
        {
            "request_id": current_task.request_id,
            "agent_id": current_task.agent_id,
            "tenant_id": current_task.tenant_id,
            "family_id": current_task.family_id,
            "use_case": current_task.use_case,
            "context_snapshot_ref": current_task.context_snapshot_ref,
            "prompt_version": current_task.prompt_version,
            "schema_version": current_task.schema_version,
            "data_class": current_task.data_class,
            "input_refs": list(current_task.input_refs),
            "payload": current_task.payload,
            "output_schema": current_task.output_schema,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    async with session_factory() as session:
        store = SqlAlchemyAgentRunStore(session)
        await store.start(
            current_task,
            run_id="run-1",
            trace_id="trace-1",
            idempotency_key="idem-1",
            started_at=NOW,
        )
        row = await session.scalar(select(AgentRunRow))
        assert row is not None
        row.idempotency_fingerprint = raw_fingerprint
        await session.flush()

        await store.start(
            current_task,
            run_id="run-1",
            trace_id="trace-1",
            idempotency_key="idem-1",
            started_at=NOW,
        )

        assert row.idempotency_fingerprint != raw_fingerprint
        assert len(row.idempotency_fingerprint) == 64
        with pytest.raises(AgentRunConflict, match="IDEMPOTENCY_REPLAY_MISMATCH"):
            await store.start(
                task(input_refs=("assessment-evidence:other",)),
                run_id="run-3",
                trace_id="trace-3",
                idempotency_key="idem-1",
                started_at=NOW,
            )


@pytest.mark.asyncio
async def test_success_persists_draft_and_replay_round_trips(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyAgentRunStore(session)
        await store.create(
            task(), run_id="run-1", trace_id="trace-1", idempotency_key="idem-1", started_at=NOW
        )
        completed = await store.succeed(run(), scope=AgentRunScope("tenant-1", "family-1"))
        assert completed.status is AgentRunStatus.SUCCEEDED
        assert completed.draft is not None
        await store.append_trace(
            AgentTraceEvent(
                trace_id="trace-1",
                run_id="run-1",
                scope=AgentRunScope("tenant-1", "family-1"),
                event_type="model.completed",
                payload={"status": "DRAFT"},
                idempotency_key="trace-idem-1",
                occurred_at=NOW,
            )
        )
        replay = await store.replay("run-1", scope=AgentRunScope("tenant-1", "family-1"))
        replay_by_request = await store.replay_by_request_id(
            "request-1", scope=AgentRunScope("tenant-1", "family-1")
        )
        assert replay is not None
        assert replay_by_request is not None
        assert replay_by_request.run.run_id == replay.run.run_id
        assert replay.run.draft == completed.draft
        assert [event.event_type for event in replay.traces] == [
            "run.started",
            "run.succeeded",
            "model.completed",
        ]

        # A second completion is a safe replay, not a duplicate transition.
        assert (
            await store.succeed(run(), scope=AgentRunScope("tenant-1", "family-1"))
        ).status is AgentRunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_request_replay_is_scope_local_and_rejects_ambiguous_identity(
    session_factory,
) -> None:
    async with session_factory() as session:
        store = SqlAlchemyAgentRunStore(session)
        await store.start(
            task(), run_id="run-1", trace_id="trace-1", idempotency_key="idem-1", started_at=NOW
        )
        assert (
            await store.replay_by_request_id(
                "request-1", scope=AgentRunScope("tenant-1", "other-family")
            )
            is None
        )
        await store.start(
            task(), run_id="run-2", trace_id="trace-2", idempotency_key="idem-2", started_at=NOW
        )
        with pytest.raises(AgentRunConflict, match="REQUEST_ID_AMBIGUOUS"):
            await store.replay_by_request_id(
                "request-1", scope=AgentRunScope("tenant-1", "family-1")
            )


@pytest.mark.asyncio
async def test_failure_and_scope_isolation(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyAgentRunStore(session)
        await store.start(
            task(), run_id="run-1", trace_id="trace-1", idempotency_key="idem-1", started_at=NOW
        )
        failed = await store.fail(
            "run-1",
            scope=AgentRunScope("tenant-1", "family-1"),
            error_code="PROVIDER_TIMEOUT",
            completed_at=NOW + timedelta(seconds=1),
        )
        assert failed.status is AgentRunStatus.FAILED
        assert failed.error_code == "PROVIDER_TIMEOUT"
        assert await store.replay("run-1", scope=AgentRunScope("tenant-1", "family-2")) is None
        assert await store.replay("run-1", scope=AgentRunScope("tenant-2", "family-1")) is None


@pytest.mark.asyncio
async def test_trace_idempotency_sequence_and_forbidden_fact_guard(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyAgentRunStore(session)
        await store.start(
            task(), run_id="run-1", trace_id="trace-1", idempotency_key="idem-1", started_at=NOW
        )
        event = AgentTraceEvent(
            trace_id="trace-1",
            run_id="run-1",
            scope=AgentRunScope("tenant-1", "family-1"),
            event_type="run.started",
            payload={"step": 1},
            idempotency_key="trace-idem-1",
            occurred_at=NOW,
        )
        assert (await store.append_trace(event)).payload == {"step": 1}
        assert (await store.append_trace(event)).payload == {"step": 1}
        with pytest.raises(AgentRunConflict):
            await store.append_trace(
                AgentTraceEvent(
                    trace_id="trace-1",
                    run_id="run-1",
                    scope=AgentRunScope("tenant-1", "family-1"),
                    event_type="run.started",
                    payload={"step": 2},
                    idempotency_key="trace-idem-1",
                    occurred_at=NOW,
                )
            )
        with pytest.raises(Exception, match="cannot become a business fact"):
            AgentTraceEvent(
                trace_id="trace-1",
                run_id="run-1",
                scope=AgentRunScope("tenant-1", "family-1"),
                event_type="unsafe",
                payload={"family_score": 100},
                idempotency_key="unsafe-1",
                occurred_at=NOW,
            )
