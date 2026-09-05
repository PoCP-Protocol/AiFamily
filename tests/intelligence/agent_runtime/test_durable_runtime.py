from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.agent_runtime.authorization import AgentAuthorizationError
from backend.intelligence.agent_runtime.context_bound import ContextBoundAgentRuntime
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AgentTask,
    AuthorizationBudget,
)
from backend.intelligence.agent_runtime.durable_runtime import (
    DurableAgentRuntime,
    DurableAgentRuntimeError,
)
from backend.intelligence.agent_runtime.persistence import (
    AgentRunPersistenceBase,
    AgentRunScope,
    SqlAlchemyAgentRunStore,
)
from backend.intelligence.agent_runtime.runtime import AgentRuntime
from backend.intelligence.context_engine.contracts import (
    ContextScope,
    ContextScopeError,
    DataClass,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft

NOW = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)


class _GenerationPort:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_structured(self, request):
        self.calls += 1
        return ModelDraft(
            output={"explanation": "draft"},
            provenance=AiProvenance(
                provider_id="fake",
                model="fake",
                model_version="v1",
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                context_snapshot_ref=request.context_snapshot_ref,
                latency_ms=1,
                data_class=request.data_class,
                use_case=request.use_case,
            ),
        )


def _runtime(port: _GenerationPort) -> AgentRuntime:
    definition = AgentDefinition(
        agent_id="parent_advisor",
        name="家长顾问",
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        context_policy="minimum",
        safety_policy="family-safety-v1",
        human_handoff_policy="review",
        budget_policy="one-step",
    )
    return AgentRuntime(port, [definition], clock=lambda: NOW)


def _task() -> AgentTask:
    return AgentTask(
        request_id="request-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="assessment_interpretation",
        context_snapshot_ref="snapshot-1",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        data_class="SYNTHETIC",
        payload={"evidence_refs": ["e-1"]},
        output_schema={"type": "object"},
    )


def _authorization() -> AgentAuthorization:
    return AgentAuthorization(
        authorization_id="auth-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        allowed_tools=frozenset(),
        issued_by="guardian-1",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        revoked_at=None,
        budget=AuthorizationBudget(),
        policy_version="v1",
        reason="assessment",
        audit_ref="audit-1",
    )


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(AgentRunPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_durable_runtime_replays_success_without_second_generation(session_factory) -> None:
    port = _GenerationPort()
    async with session_factory() as session:
        durable = DurableAgentRuntime(
            _runtime(port), SqlAlchemyAgentRunStore(session), clock=lambda: NOW
        )
        first = await durable.execute(_task(), _authorization(), idempotency_key="idem-1")
        await session.commit()
        replay = await durable.execute(_task(), _authorization(), idempotency_key="idem-1")
        snapshot = await SqlAlchemyAgentRunStore(session).replay(
            first.run_id, scope=AgentRunScope("tenant-1", "family-1")
        )

    assert first.run_id == replay.run_id
    assert first.draft.output == replay.draft.output
    assert port.calls == 1
    assert snapshot is not None
    assert [event.event_type for event in snapshot.traces] == ["run.started", "run.succeeded"]


@pytest.mark.asyncio
async def test_durable_runtime_rejects_changed_evidence_on_replay(session_factory) -> None:
    port = _GenerationPort()
    async with session_factory() as session:
        durable = DurableAgentRuntime(
            _runtime(port), SqlAlchemyAgentRunStore(session), clock=lambda: NOW
        )
        await durable.execute(_task(), _authorization(), idempotency_key="idem-1")
        await session.commit()
        changed = replace(
            _task(),
            input_refs=("assessment-evidence:e-2",),
            payload={"evidence_refs": ["e-2"]},
        )
        with pytest.raises(DurableAgentRuntimeError, match="REPLAY_MISMATCH"):
            await durable.execute(changed, _authorization(), idempotency_key="idem-1")

    assert port.calls == 1


@pytest.mark.asyncio
async def test_durable_runtime_records_failed_authorization_and_blocks_replay(
    session_factory,
) -> None:
    port = _GenerationPort()
    async with session_factory() as session:
        durable = DurableAgentRuntime(
            _runtime(port), SqlAlchemyAgentRunStore(session), clock=lambda: NOW
        )
        with pytest.raises(AgentAuthorizationError):
            await durable.execute(_task(), None, idempotency_key="idem-failed")
        await session.commit()
        with pytest.raises(DurableAgentRuntimeError, match="REPLAY_FAILED"):
            await durable.execute(_task(), None, idempotency_key="idem-failed")

    assert port.calls == 0


@pytest.mark.asyncio
async def test_context_bound_runtime_rejects_cross_family_task(session_factory) -> None:
    port = _GenerationPort()
    other_scope = ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id="family-2",
        subject_ids=("subject-1",),
        purpose="assessment",
        consent_version="consent-v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete-2",
        correlation_id="corr-2",
        causation_id="cause-2",
    )
    async with session_factory() as session:
        bound = ContextBoundAgentRuntime(
            DurableAgentRuntime(
                _runtime(port), SqlAlchemyAgentRunStore(session), clock=lambda: NOW
            )
        )
        with pytest.raises(ContextScopeError, match="AGENT_TASK_SCOPE_MISMATCH"):
            await bound.execute(
                _task(),
                _authorization(),
                scope=other_scope,
                idempotency_key="scope-mismatch",
            )
    assert port.calls == 0


@pytest.mark.asyncio
async def test_durable_runtime_does_not_reexecute_in_progress_run(session_factory) -> None:
    port = _GenerationPort()
    idempotency_key = "idem-progress"
    digest = hashlib.sha256(f"tenant-1:family-1:{idempotency_key}".encode()).hexdigest()
    async with session_factory() as session:
        store = SqlAlchemyAgentRunStore(session)
        await store.start(
            _task(),
            run_id=f"agent-run-{digest}",
            trace_id=f"trace-{digest}",
            idempotency_key=idempotency_key,
            started_at=NOW,
        )
        durable = DurableAgentRuntime(_runtime(port), store, clock=lambda: NOW)
        with pytest.raises(DurableAgentRuntimeError, match="IN_PROGRESS"):
            await durable.execute(_task(), _authorization(), idempotency_key=idempotency_key)
    assert port.calls == 0
