from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.intelligence.agi_vertical_durable import DurableVerticalLedgerAdapter
from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedger,
    EvaluationLedgerEntry,
    GuardianDecision,
    PublishedKnowledge,
    VerticalFamilyGrowthRuntime,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass, StateObservation
from backend.intelligence.context_engine.family_growth_port import SqlFamilyGrowthContextPort
from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextPersistenceBase,
)
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


@pytest_asyncio.fixture
async def postgres_context_session_factory():
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    async with postgres_schema_engine(ContextPersistenceBase.metadata) as engine:
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
        assert replay.draft_payload["knowledge_ref"] == ""
        assert replay.draft_payload["provenance"]["provider_id"] == "fake"
        assert replay.draft_payload["provenance"]["prompt_version"] == "p1"
        assert replay.draft_payload["provenance"]["schema_version"] == "s1"
        assert replay.draft_payload.get("parent_run_id", "") == ""

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


@pytest.mark.asyncio
async def test_structured_understanding_survives_postgres_restart_readback(
    postgres_session_factory,
):
    scope = RunScope("tenant-pg-structured", "family-pg-structured", ("child-pg",))
    structured = EvaluationLedgerEntry(
        "need-structured",
        "path-structured",
        "run-structured",
        "context:structured",
        ModelDraft(
            {
                "understanding": "证据存在分歧",
                "next_step": "补充一次观察",
                "path": [],
                "dimensions": [{"name": "沟通", "state": "UNKNOWN"}],
                "evidence_refs": ["obs:1", "obs:2"],
                "unknowns": [{"dimension": "沟通", "reason": "证据不足"}],
                "contradictions": [{"refs": ["obs:1", "obs:2"]}],
            },
            AiProvenance(
                "fake",
                "model",
                "v1",
                "p1",
                "s1",
                "context:structured",
                1,
                "SYNTHETIC",
                "vertical",
            ),
        ),
        (),
        lineage_ref="lineage:structured-evidence",
    )
    async with postgres_session_factory() as writer:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(writer))
        async with writer.begin():
            await adapter.save_entry(structured, scope=scope)

    async with postgres_session_factory() as restarted_reader:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(restarted_reader))
        replay = await adapter.replay(run_id="run-structured", scope=scope)
        payload = replay.draft_payload
        assert payload["output"]["unknowns"][0]["dimension"] == "沟通"
        assert payload["output"]["contradictions"][0]["refs"] == ["obs:1", "obs:2"]
        assert payload["lineage_ref"] == "lineage:structured-evidence"


@pytest.mark.asyncio
async def test_revision_child_parent_lineage_survives_new_session(postgres_session_factory):
    scope = RunScope("tenant-pg-revision", "family-pg-revision", ("child-pg",))
    base = _entry()
    parent = EvaluationLedgerEntry(
        base.family_need_id, base.path_id, "run-pg-parent", base.context_snapshot_ref,
        base.draft, base.feedback_refs, lineage_ref="lineage:parent",
    )
    child = EvaluationLedgerEntry(
        base.family_need_id, base.path_id, "run-pg-child", base.context_snapshot_ref,
        base.draft, base.feedback_refs, lineage_ref="lineage:child", parent_run_id="run-pg-parent",
    )
    async with postgres_session_factory() as writer:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(writer))
        async with writer.begin():
            await adapter.save_entry(parent, scope=scope)
            await adapter.record_guardian_decision(
                GuardianDecision(
                    "decision:pg-parent",
                    "need-pg-1",
                    "run-pg-parent",
                    "path-pg-1",
                    "EDIT",
                    {"next_step": "共同观察"},
                ),
                scope=scope,
            )
            await adapter.save_entry(child, scope=scope)
    async with postgres_session_factory() as reader:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(reader))
        parent_replay = await adapter.replay(run_id="run-pg-parent", scope=scope)
        replay = await adapter.replay(run_id="run-pg-child", scope=scope)
        assert parent_replay.interactions[-1].payload["decision_ref"] == "decision:pg-parent"
        assert replay.draft_payload["parent_run_id"] == "run-pg-parent"


@pytest.mark.asyncio
async def test_two_families_differ_from_postgres_context_evidence_only(
    postgres_context_session_factory,
):
    class Gateway:
        def __init__(self):
            self.requests = []

        async def generate_structured(self, request, *, provider_id=None):
            self.requests.append(request)
            focus = request.payload["context"]["focus"]
            evidence = request.payload["context"]["source_refs"][0]
            return ModelDraft(
                {
                    "understanding": f"观察到：{focus}",
                    "next_step": f"围绕 {focus} 做一次共同观察",
                    "path": [],
                    "dimensions": [
                        {"name": name, "evidence_refs": [evidence]}
                        for name in request.payload["required_dimensions"]
                    ],
                    "evidence_refs": [evidence],
                    "unknowns": [],
                    "contradictions": [],
                },
                request_provenance(request),
            )

    def request_provenance(request):
        from backend.intelligence.model_gateway.contracts import AiProvenance

        return AiProvenance(
            "test", "evidence-grounded", "v1", request.prompt_version,
            request.schema_version, request.context_snapshot_ref, 1,
            request.data_class, request.use_case,
        )

    class Knowledge:
        async def published(self, *, ref):
            return PublishedKnowledge(
                ref, "v1", "source:test", "family-growth", "digest", "guidance"
            )

    class Feedback:
        async def latest(self, *, family_need_id, family_id=None):
            return ()

    def scope(family_id: str) -> ContextScope:
        return ContextScope(
            tenant_id="tenant-v06", region_id="CN", family_id=family_id,
            subject_ids=(f"child:{family_id}",), purpose="family-growth-understanding",
            consent_version="consent.v1", consent_granted=True,
            data_class=DataClass.OPERATIONAL_TEXT, locale="zh-CN",
            deletion_ref=f"delete:{family_id}", correlation_id=f"corr:{family_id}",
            causation_id=f"cause:{family_id}",
        )

    session_factory = postgres_context_session_factory
    broker = AsyncSqlContextBroker(session_factory)
    gateway = Gateway()
    now = datetime.now(UTC)
    for family_id, focus, evidence in (
        ("family-v06-a", "作业启动", "observation:v06:a"),
        ("family-v06-b", "亲子沟通", "observation:v06:b"),
    ):
        current_scope = scope(family_id)
        await broker.append(
            StateObservation(
                observation_id=evidence, tenant_id=current_scope.tenant_id,
                family_id=family_id, subject_id=current_scope.subject_ids[0],
                dimension="focus", observed_value=focus, evidence_refs=(evidence,),
                provenance="guardian-expression", observed_at=now,
                data_class=current_scope.data_class, purpose=current_scope.purpose,
                consent_version=current_scope.consent_version, consent_granted=True,
                region_id="CN", locale="zh-CN", deletion_ref=current_scope.deletion_ref,
                correlation_id=current_scope.correlation_id,
                causation_id=current_scope.causation_id,
                expires_at=now + timedelta(hours=1), retention_policy="v06-test",
            )
        )
        snapshot = await broker.snapshot(scope=current_scope, now=now)
        runtime = VerticalFamilyGrowthRuntime(
            gateway=gateway,
            context=SqlFamilyGrowthContextPort(broker, scope),
            knowledge=Knowledge(), feedback=Feedback(), ledger=EvaluationLedger(),
        )
        entry = await runtime.run(
            family_need_id=f"need:{family_id}", path_id=f"path:{family_id}",
            run_id=f"run:{family_id}", family_id=family_id,
            knowledge_ref="knowledge:v06", context_snapshot_ref=snapshot.snapshot_ref,
        )
        if family_id.endswith("a"):
            first = entry
        else:
            second = entry

    assert first.draft.output["next_step"] != second.draft.output["next_step"]
    assert gateway.requests[0].payload["context"]["source_refs"] == ("observation:v06:a",)
    assert gateway.requests[1].payload["context"]["source_refs"] == ("observation:v06:b",)
    assert gateway.requests[0].payload["context"]["focus"] != (
        gateway.requests[1].payload["context"]["focus"]
    )
