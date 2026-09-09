from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.intelligence.agi_vertical_durable import (
    DurableVerticalGrowthRuntime,
    DurableVerticalLedgerAdapter,
)
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
        assert replay.draft_payload["input_refs"] == []

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

    async with postgres_session_factory() as deleted_reader:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(deleted_reader))
        deleted_replay = await adapter.replay(run_id="run-pg-1", scope=scope)
        assert deleted_replay.deletion_state == "deleted"
        assert deleted_replay.draft_payload is None
        assert not deleted_replay.artifact_refs
        with pytest.raises(RunHttpError):
            await adapter.replay(run_id="run-pg-1", scope=foreign_scope)

    async with postgres_session_factory() as repeated_deleter:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(repeated_deleter))
        async with repeated_deleter.begin():
            repeated_delete = await adapter.delete(run_id="run-pg-1", scope=scope)
        assert repeated_delete.deletion_state == "deleted"
        assert repeated_delete.draft_payload is None


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
async def test_vertical_postgres_readback_after_engine_dispose_reconnects(
    postgres_session_factory,
):
    """A fresh physical connection recovers the durable vertical draft."""

    scope = RunScope("tenant-pg-reconnect", "family-pg-reconnect", ("child-pg",))
    async with postgres_session_factory() as writer:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(writer))
        async with writer.begin():
            await adapter.save_entry(_entry(), scope=scope)

    engine = postgres_session_factory.kw["bind"]
    await engine.dispose()

    async with postgres_session_factory() as process_b_reader:
        adapter = DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(process_b_reader))
        replay = await adapter.replay(run_id="run-pg-1", scope=scope)

    assert replay.run_id == "run-pg-1"
    assert replay.draft_payload["family_need_id"] == "need-pg-1"


@pytest.mark.asyncio
async def test_vertical_postgres_provider_failure_is_retryable_without_stale_draft(
    postgres_session_factory,
):
    """A failed generation leaves no durable success; retry can commit once."""

    scope = RunScope("tenant-pg-failure", "family-pg-failure", ("child-pg",))
    calls = 0

    class Generator:
        async def run(self, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("provider unavailable")
            return _entry()

    async with postgres_session_factory() as session:
        runtime = DurableVerticalGrowthRuntime(
            runtime=Generator(),
            ledger=DurableVerticalLedgerAdapter(SqlAlchemyExperienceRunLedger(session)),
            scope_factory=lambda _family_id: scope,
        )
        request = {
            "family_id": "family-pg-failure",
            "family_need_id": "need-pg-1",
            "path_id": "path-pg-1",
            "run_id": "run-pg-failure",
        }
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await runtime.run(**request)

        with pytest.raises(RunHttpError):
            await runtime.replay(run_id="run-pg-failure", family_id="family-pg-failure")

        result = await runtime.run(**request)
        assert result.run_id == "run-pg-1"
        assert calls == 2


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


@pytest.mark.asyncio
async def test_same_family_counterfactual_changes_only_changed_context_input(
    postgres_context_session_factory,
):
    """Changing one durable observation changes only its dependent output."""

    family_id = "family-v10-counterfactual"
    subject_id = f"child:{family_id}"
    now = datetime.now(UTC)

    def scope() -> ContextScope:
        return ContextScope(
            tenant_id="tenant-v10",
            region_id="CN",
            family_id=family_id,
            subject_ids=(subject_id,),
            purpose="family-growth-understanding",
            consent_version="consent.v1",
            consent_granted=True,
            data_class=DataClass.OPERATIONAL_TEXT,
            locale="zh-CN",
            deletion_ref="delete:v10",
            correlation_id="corr:v10",
            causation_id="cause:v10",
        )

    class Gateway:
        async def generate_structured(self, request, *, provider_id=None):
            context = request.payload["context"]
            from backend.intelligence.model_gateway.contracts import AiProvenance

            provenance = AiProvenance(
                "test",
                "counterfactual",
                "v1",
                request.prompt_version,
                request.schema_version,
                request.context_snapshot_ref,
                1,
                request.data_class,
                request.use_case,
            )
            return ModelDraft(
                {
                    "understanding": f"观察到：{context['focus']}",
                    "next_step": "保持稳定支持节奏",
                    "path": [],
                    "dimensions": [
                        {"name": name, "state": "UNKNOWN"}
                        for name in request.payload["required_dimensions"]
                    ],
                    "evidence_refs": list(context["source_refs"]),
                    "unknowns": [
                        {"dimension": name, "reason": "counterfactual-test"}
                        for name in request.payload["required_dimensions"]
                    ],
                    "contradictions": [],
                },
                provenance,
            )

    class Knowledge:
        async def published(self, *, ref):
            return PublishedKnowledge(
                ref, "v1", "source:test", "family-growth", "digest", "guidance"
            )

    class Feedback:
        async def latest(self, *, family_need_id, family_id=None):
            return ()

    broker = AsyncSqlContextBroker(postgres_context_session_factory)
    current_scope = scope()
    stable = StateObservation(
        observation_id="observation:v10:stable",
        tenant_id="tenant-v10",
        family_id=family_id,
        subject_id=subject_id,
        dimension="support_rhythm",
        observed_value="每周一次",
        evidence_refs=("observation:v10:stable",),
        provenance="guardian-expression",
        observed_at=now,
        data_class=current_scope.data_class,
        purpose=current_scope.purpose,
        consent_version=current_scope.consent_version,
        consent_granted=True,
        region_id="CN",
        locale="zh-CN",
        deletion_ref=current_scope.deletion_ref,
        correlation_id=current_scope.correlation_id,
        causation_id=current_scope.causation_id,
        expires_at=now + timedelta(hours=1),
        retention_policy="v10-test",
    )

    await broker.append(stable)
    first_observation = StateObservation(
        observation_id="observation:v10:first",
        tenant_id=stable.tenant_id,
        family_id=stable.family_id,
        subject_id=stable.subject_id,
        dimension="focus",
        observed_value="作业启动",
        evidence_refs=("observation:v10:first",),
        provenance=stable.provenance,
        observed_at=stable.observed_at,
        data_class=stable.data_class,
        purpose=stable.purpose,
        consent_version=stable.consent_version,
        consent_granted=stable.consent_granted,
        region_id=stable.region_id,
        locale=stable.locale,
        deletion_ref=stable.deletion_ref,
        correlation_id=stable.correlation_id,
        causation_id=stable.causation_id,
        expires_at=stable.expires_at,
        retention_policy=stable.retention_policy,
    )
    await broker.append(first_observation)
    first_snapshot = await broker.snapshot(scope=current_scope, now=now)
    runtime = VerticalFamilyGrowthRuntime(
        gateway=Gateway(),
        context=SqlFamilyGrowthContextPort(broker, lambda _family_id: current_scope),
        knowledge=Knowledge(),
        feedback=Feedback(),
        ledger=EvaluationLedger(),
    )
    first = await runtime.run(
        family_need_id="need:v10",
        path_id="path:v10",
        run_id="run:v10:first",
        family_id=family_id,
        knowledge_ref="knowledge:v10",
        context_snapshot_ref=first_snapshot.snapshot_ref,
    )

    second_observation = StateObservation(
        observation_id="observation:v10:second",
        tenant_id=stable.tenant_id,
        family_id=stable.family_id,
        subject_id=stable.subject_id,
        dimension="focus",
        observed_value="亲子沟通",
        evidence_refs=("observation:v10:second",),
        provenance=stable.provenance,
        observed_at=stable.observed_at,
        data_class=stable.data_class,
        purpose=stable.purpose,
        consent_version=stable.consent_version,
        consent_granted=stable.consent_granted,
        region_id=stable.region_id,
        locale=stable.locale,
        deletion_ref=stable.deletion_ref,
        correlation_id=stable.correlation_id,
        causation_id=stable.causation_id,
        expires_at=stable.expires_at,
        retention_policy=stable.retention_policy,
    )
    await broker.append(second_observation)
    second_snapshot = await broker.snapshot(scope=current_scope, now=now)
    second = await runtime.run(
        family_need_id="need:v10",
        path_id="path:v10",
        run_id="run:v10:second",
        family_id=family_id,
        knowledge_ref="knowledge:v10",
        context_snapshot_ref=second_snapshot.snapshot_ref,
    )

    assert first.draft.output["next_step"] == second.draft.output["next_step"]
    assert first.draft.output["understanding"] != second.draft.output["understanding"]
    assert (
        first.draft.provenance.context_snapshot_ref
        != second.draft.provenance.context_snapshot_ref
    )
