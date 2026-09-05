from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.human_gate_bridge import (
    EXPERIENCE_RUN_REF_ARGUMENT,
    RUN_ID_ARGUMENT,
    AsyncExperienceRunHumanGateBridge,
    ExperienceRunHumanGateBridge,
    experience_run_ref,
)
from backend.intelligence.experience.runs import DurableExperienceRun, RunState
from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    GateScope,
    HumanGateBase,
    HumanGateError,
    SqlAlchemyHumanGate,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.platform.audit import AuditBase, AuditRecorder

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)


def _run(*, state: RunState = RunState.SUCCEEDED) -> DurableExperienceRun:
    run = DurableExperienceRun(
        run_id="run-bridge-001",
        tenant_id="tenant-bridge",
        family_id="family-bridge",
        subject_ids=("guardian-bridge", "child-bridge"),
        request_ref="request:bridge-001",
    )
    if state is not RunState.QUEUED:
        run.transition(RunState.RUNNING, event_id="run-bridge-001:started")
        if state is RunState.SUCCEEDED:
            run.checkpoint(checkpoint_id="run-bridge-001:draft", draft_payload={"action": "start"})
            run.transition(RunState.SUCCEEDED, event_id="run-bridge-001:succeeded")
        elif state is RunState.FAILED:
            run.transition(RunState.FAILED, event_id="run-bridge-001:failed")
    return run


def _draft(*, output: dict[str, object] | None = None) -> ModelDraft:
    return ModelDraft(
        output=output or {"action": "start"},
        provenance=AiProvenance(
            provider_id="fake-deterministic",
            model="fake-model",
            model_version="v1",
            prompt_version="prompt.v1",
            schema_version="schema.v1",
            context_snapshot_ref="ctx:bridge-001",
            latency_ms=1,
            data_class="SYNTHETIC",
            use_case="growth_action",
        ),
    )


def _scope() -> GateScope:
    return GateScope(
        tenant_id="tenant-bridge",
        family_id="family-bridge",
        subject_ids=("guardian-bridge", "child-bridge"),
        purpose="growth_action",
        consent_version="consent.v1",
        correlation_id="request:bridge-001",
    )


def _submit(bridge: ExperienceRunHumanGateBridge, run: DurableExperienceRun, **kwargs: object):
    defaults = {
        "draft_id": "draft:bridge-001",
        "proposal_id": "proposal:bridge-001",
        "action_name": "START_GROWTH_ACTION",
        "action_arguments": {"action": "start"},
        "scope": _scope(),
        "allowed_actor_types": (ActorType.GUARDIAN,),
        "risk_level": "LOW",
        "provenance_ref": "model-draft:bridge-001",
        "now": NOW,
    }
    defaults.update(kwargs)
    return bridge.submit_model_draft(run, _draft(), **defaults)


def test_accept_binds_run_ref_and_replay_is_idempotent():
    run = _run()
    bridge = ExperienceRunHumanGateBridge()
    task = _submit(bridge, run)

    decided, request = bridge.decide(
        run,
        task.task_id,
        actor_id="guardian-bridge",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        now=NOW,
    )
    assert decided.action_request is request
    assert request is not None
    assert request.action_arguments[RUN_ID_ARGUMENT] == run.run_id
    assert request.action_arguments[EXPERIENCE_RUN_REF_ARGUMENT] == experience_run_ref(run)

    replay, replay_request = bridge.decide(
        run,
        task.task_id,
        actor_id="guardian-bridge",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        now=NOW,
    )
    assert replay == decided
    assert replay_request == request


@pytest.mark.parametrize(
    "mutator, error",
    [
        (lambda run, draft: {"scope": GateScope(
            tenant_id="tenant-other", family_id=run.family_id,
            subject_ids=run.subject_ids, purpose="growth_action",
            consent_version="consent.v1", correlation_id=run.snapshot.request_ref,
        )}, "EXPERIENCE_SCOPE_MISMATCH"),
        (
            lambda run, draft: {"action_arguments": {"run_id": "forged"}},
            "EXPERIENCE_RUN_REF_MISMATCH",
        ),
        (
            lambda run, draft: {"draft": _draft(output={"action": "different"})},
            "EXPERIENCE_DRAFT_MISMATCH",
        ),
    ],
)
def test_binding_drift_fails_closed(mutator, error):
    run = _run()
    bridge = ExperienceRunHumanGateBridge()
    with pytest.raises(HumanGateError, match=error):
        values = mutator(run, _draft())
        if "draft" in values:
            bridge.submit_model_draft(run, values.pop("draft"), **{
                "draft_id": "draft:bridge-001", "proposal_id": "proposal:bridge-001",
                "action_name": "START_GROWTH_ACTION", "action_arguments": {"action": "start"},
                "scope": _scope(), "allowed_actor_types": (ActorType.GUARDIAN,),
                "risk_level": "LOW", "provenance_ref": "model-draft:bridge-001", "now": NOW,
            })
        else:
            _submit(bridge, run, **values)


def test_reject_and_non_successful_run_do_not_create_action():
    bridge = ExperienceRunHumanGateBridge()
    run = _run()
    task = _submit(bridge, run)
    decided, request = bridge.decide(
        run, task.task_id, actor_id="guardian-bridge", actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.REJECT, reason="暂不执行", now=NOW,
    )
    assert decided.action_request is None
    assert request is None

    with pytest.raises(HumanGateError, match="EXPERIENCE_RUN_NOT_SUCCEEDED"):
        _submit(bridge, _run(state=RunState.RUNNING))


def test_successful_run_without_checkpoint_is_rejected():
    run = DurableExperienceRun(
        run_id="run-bridge-empty",
        tenant_id="tenant-bridge",
        family_id="family-bridge",
        subject_ids=("guardian-bridge", "child-bridge"),
        request_ref="request:bridge-empty",
    )
    run.transition(RunState.RUNNING, event_id="run-bridge-empty:started")
    run.transition(RunState.SUCCEEDED, event_id="run-bridge-empty:succeeded")
    bridge = ExperienceRunHumanGateBridge()
    with pytest.raises(HumanGateError, match="EXPERIENCE_DRAFT_CHECKPOINT_REQUIRED"):
        _submit(bridge, run)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _async_submit_kwargs(
    *, proposal_id: str = "proposal:async-001", now: datetime = NOW
) -> dict[str, object]:
    return {
        "draft_id": "draft:async-001",
        "proposal_id": proposal_id,
        "action_name": "START_GROWTH_ACTION",
        "action_arguments": {"action": "start"},
        "scope": _scope(),
        "allowed_actor_types": (ActorType.GUARDIAN,),
        "risk_level": "LOW",
        "provenance_ref": "model-draft:async-001",
        "now": now,
    }


@pytest.mark.asyncio
async def test_async_bridge_persists_replay_and_accept_binding(session_factory):
    run = _run()
    async with session_factory() as session:
        bridge = AsyncExperienceRunHumanGateBridge(SqlAlchemyHumanGate(session))
        recorder = AuditRecorder()
        task = await bridge.submit_model_draft(
            run,
            _draft(),
            recorder=recorder,
            **_async_submit_kwargs(),
        )
        assert await bridge.flush_audit(recorder) == 1
        await bridge.commit()

    async with session_factory() as session:
        bridge = AsyncExperienceRunHumanGateBridge(SqlAlchemyHumanGate(session))
        replay = await bridge.submit_model_draft(
            run,
            _draft(),
            recorder=AuditRecorder(),
            **_async_submit_kwargs(now=NOW + timedelta(hours=1)),
        )
        assert replay == task
        recorder = AuditRecorder()
        decided, request = await bridge.decide(
            run,
            task.task_id,
            actor_id="guardian-bridge",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            recorder=recorder,
            now=NOW + timedelta(hours=1),
        )
        assert request is not None
        assert request.action_arguments[RUN_ID_ARGUMENT] == run.run_id
        assert request.action_arguments[EXPERIENCE_RUN_REF_ARGUMENT] == experience_run_ref(run)
        assert await bridge.flush_audit(recorder) == 1
        await bridge.commit()

    async with session_factory() as session:
        loaded = await SqlAlchemyHumanGate(session).get(task.task_id)
        assert loaded == decided
        assert loaded.action_request is not None


@pytest.mark.asyncio
async def test_async_bridge_reject_has_no_action_request(session_factory):
    run = _run()
    async with session_factory() as session:
        bridge = AsyncExperienceRunHumanGateBridge(SqlAlchemyHumanGate(session))
        recorder = AuditRecorder()
        task = await bridge.submit_model_draft(
            run,
            _draft(),
            recorder=recorder,
            **_async_submit_kwargs(proposal_id="proposal:async-reject"),
        )
        await bridge.flush_audit(recorder)
        decided, request = await bridge.decide(
            run,
            task.task_id,
            actor_id="guardian-bridge",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.REJECT,
            reason="暂不执行",
            recorder=recorder,
            now=NOW,
        )
        assert decided.action_request is None
        assert request is None
        assert await bridge.flush_audit(recorder) == 1
        await bridge.commit()


@pytest.mark.asyncio
async def test_async_bridge_scope_mismatch_fails_before_persistence(session_factory):
    run = _run()
    wrong_scope = GateScope(
        tenant_id="tenant-other",
        family_id=run.family_id,
        subject_ids=run.subject_ids,
        purpose="growth_action",
        consent_version="consent.v1",
        correlation_id=run.snapshot.request_ref,
    )
    async with session_factory() as session:
        bridge = AsyncExperienceRunHumanGateBridge(SqlAlchemyHumanGate(session))
        with pytest.raises(HumanGateError, match="EXPERIENCE_SCOPE_MISMATCH"):
            await bridge.submit_model_draft(
                run,
                _draft(),
                recorder=AuditRecorder(),
                **{**_async_submit_kwargs(), "scope": wrong_scope},
            )
