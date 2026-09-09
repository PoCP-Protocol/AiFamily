from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.intelligence.agi_vertical_durable import DurableVerticalLedgerAdapter
from backend.intelligence.agi_vertical_runtime import EvaluationLedgerEntry, GuardianDecision
from backend.intelligence.experience.run_http import RunHttpError, RunScope
from backend.intelligence.experience.run_store import ExperienceRunPersistenceBase
from backend.intelligence.experience.sql_run_ledger import SqlAlchemyExperienceRunLedger
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


@pytest_asyncio.fixture
async def postgres_session_factory():
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    async with postgres_schema_engine(ExperienceRunPersistenceBase.metadata) as engine:
        yield async_sessionmaker(engine, expire_on_commit=False)


def _entry() -> EvaluationLedgerEntry:
    return EvaluationLedgerEntry(
        "need-pg-1",
        "path-pg-1",
        "run-pg-1",
        "ctx-pg-1",
        ModelDraft(
            {"understanding": "启动阻力", "next_step": "开始仪式", "path": ["拆解任务"]},
            AiProvenance("fake", "model", "v1", "p1", "s1", "ctx-pg-1", 1, "SYNTHETIC", "vertical"),
        ),
        (),
    )


@pytest.mark.asyncio
async def test_vertical_adapter_postgres_restart_decision_delete_and_scope(
    postgres_session_factory,
):
    scope = RunScope("tenant-pg", "family-pg", ("child-pg",))
    foreign_scope = RunScope("tenant-pg", "family-other", ("child-other",))

    async with postgres_session_factory() as writer:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(writer))
        async with writer.begin():
            await adapter.save_entry(_entry(), scope=scope)

    async with postgres_session_factory() as reader:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(reader))
        replay = await adapter.replay(run_id="run-pg-1", scope=scope)
        assert replay.draft_payload["family_need_id"] == "need-pg-1"
        assert replay.draft_payload["guardian_calibration"] is None

    decision = GuardianDecision("decision:pg-edit", "need-pg-1", "run-pg-1", "path-pg-1", "EDIT")
    async with postgres_session_factory() as decision_writer:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(decision_writer))
        async with decision_writer.begin():
            await adapter.record_guardian_decision(decision, scope=scope)

    async with postgres_session_factory() as verifier:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(verifier))
        replay = await adapter.replay(run_id="run-pg-1", scope=scope)
        assert replay.interactions[-1].payload["decision_ref"] == "decision:pg-edit"
        with pytest.raises(RunHttpError):
            await adapter.replay(run_id="run-pg-1", scope=foreign_scope)

    async with postgres_session_factory() as deleter:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(deleter))
        async with deleter.begin():
            deleted = await adapter.delete(run_id="run-pg-1", scope=scope)
        assert deleted.deletion_state == "deleted"
        assert deleted.draft_payload is None
        assert not deleted.artifact_refs


@pytest.mark.asyncio
async def test_vertical_adapter_postgres_repeated_create_and_decision_are_idempotent(
    postgres_session_factory,
):
    """A retry after a client timeout must replay, not append another event."""

    scope = RunScope("tenant-pg-retry", "family-pg-retry", ("child-pg-retry",))
    async with postgres_session_factory() as writer:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(writer))
        async with writer.begin():
            saved_entry = _entry()
            first = await adapter.save_entry(saved_entry, scope=scope)
            replay = await adapter.save_entry(saved_entry, scope=scope)
        assert replay.snapshot.event_sequence == first.snapshot.event_sequence

    decision = GuardianDecision(
        "decision:pg-retry", "need-pg-1", "run-pg-1", "path-pg-1", "EDIT"
    )
    async with postgres_session_factory() as writer:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(writer))
        async with writer.begin():
            await adapter.record_guardian_decision(decision, scope=scope)
            await adapter.record_guardian_decision(decision, scope=scope)

    async with postgres_session_factory() as reader:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(reader))
        replay = await adapter.replay(run_id="run-pg-1", scope=scope)
        decisions = [
            item
            for item in replay.interactions
            if item.payload.get("decision_ref") == "decision:pg-retry"
        ]
        assert len(decisions) == 1
