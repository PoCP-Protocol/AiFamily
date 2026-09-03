from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.async_ledger_bridge import (
    AsyncExperienceRunLedgerBridge,
)
from backend.intelligence.experience.multimodal_eval import (
    MultimodalEvaluationReport,
    ProviderEvaluationSummary,
    persist_evaluation_projection,
)
from backend.intelligence.experience.run_http import (
    InteractionType,
    RunHttpConflictError,
    RunHttpError,
    RunScope,
)
from backend.intelligence.experience.run_store import (
    ExperienceRunCheckpointRow,
    ExperienceRunPersistenceBase,
    ExperienceRunRow,
)
from backend.intelligence.experience.sql_run_ledger import (
    CommittedExperienceRunLedger,
    ExperienceRunInteractionRow,
    SessionPerCallExperienceRunLedger,
    SqlAlchemyExperienceRunLedger,
)
from backend.intelligence.model_gateway.provenance import (
    ModelDraftRegistryBase,
    ModelDraftRow,
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


@pytest.fixture
async def session_factory_with_model_drafts():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperienceRunPersistenceBase.metadata.create_all)
        await connection.run_sync(ModelDraftRegistryBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _scope(
    *,
    tenant_id: str = "tenant-sql",
    family_id: str = "family-sql",
    subjects: tuple[str, ...] = ("guardian-sql", "child-sql"),
) -> RunScope:
    return RunScope(tenant_id=tenant_id, family_id=family_id, subject_ids=subjects)


async def _create(session, *, scope: RunScope | None = None):
    ledger = SqlAlchemyExperienceRunLedger(session)
    async with session.begin():
        return await ledger.create_draft(
            scope=scope or _scope(),
            run_id="run-sql-1",
            request_ref="request-sql-1",
            draft_payload={"status": "DRAFT", "headline": "可调整草稿"},
            artifact_refs=("media:sha256:" + "a" * 64,),
            idempotency_key="create-sql-1",
        )


def _model_draft_row(*, draft_id: str, run_id: str) -> ModelDraftRow:
    now = datetime.now(UTC)
    return ModelDraftRow(
        tenant_id="tenant-sql",
        draft_id=draft_id,
        provenance_ref=f"model-draft:{run_id}",
        family_id="family-sql",
        subject_person_id="child-sql",
        purpose="family_understanding",
        correlation_id=run_id,
        provider_id="provider-test",
        model="model-test",
        model_version="2026-09",
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        context_snapshot_ref=f"context:{run_id}",
        use_case="family_understanding",
        latency_ms=10,
        data_class="SYNTHETIC",
        confidence=0.8,
        generated_at=now,
        output_payload={"headline": "可调整草稿"},
        provenance_payload={"run_id": run_id},
        status="DRAFT",
        may_mutate_business_state=False,
        created_at=now,
    )


async def _create_with_model_draft(session, *, run_id: str, draft_id: str) -> None:
    ledger = SqlAlchemyExperienceRunLedger(session)
    reservation = await ledger.preflight_create(
        scope=_scope(),
        run_id=run_id,
        request_ref=f"request:{run_id}",
        request_fingerprint=f"fingerprint:{run_id}",
        idempotency_key=f"create:{run_id}",
    )
    await ledger.finalize_create(
        reservation,
        draft_payload={"status": "DRAFT", "headline": "可调整草稿"},
        response_payload={"run_id": run_id, "draft_id": draft_id, "status": "DRAFT"},
    )
    session.add(_model_draft_row(draft_id=draft_id, run_id=run_id))
    await session.flush()


@pytest.mark.asyncio
async def test_sql_ledger_round_trip_and_create_idempotency(session_factory) -> None:
    async with session_factory() as session:
        first = await _create(session)
        replay = await _create(session)

        assert replay == first
        assert first.status == "DRAFT"
        assert first.draft_payload == {"status": "DRAFT", "headline": "可调整草稿"}
        assert first.event_sequence == 3

        rows = await session.scalars(select(ExperienceRunInteractionRow))
        assert list(rows) == []

        reordered = await SqlAlchemyExperienceRunLedger(session).replay(
            scope=_scope(subjects=("child-sql", "guardian-sql")), run_id="run-sql-1"
        )
        assert reordered == first


@pytest.mark.asyncio
async def test_sql_ledger_interactions_are_append_only_and_replayable(session_factory) -> None:
    async with session_factory() as session:
        await _create(session)
        ledger = SqlAlchemyExperienceRunLedger(session)
        async with session.begin():
            decision = await ledger.append_interaction(
                scope=_scope(),
                run_id="run-sql-1",
                interaction_type=InteractionType.DECISION,
                payload={"decision": "rewrite"},
                idempotency_key="decision-sql-1",
            )
            feedback = await ledger.append_interaction(
                scope=_scope(),
                run_id="run-sql-1",
                interaction_type=InteractionType.FEEDBACK,
                payload={"signal": "not_helpful", "reason": "节奏太快"},
                idempotency_key="feedback-sql-1",
            )

        repeated = await ledger.append_interaction(
            scope=_scope(),
            run_id="run-sql-1",
            interaction_type=InteractionType.FEEDBACK,
            payload={"signal": "not_helpful", "reason": "节奏太快"},
            idempotency_key="feedback-sql-1",
        )
        assert decision.status == "recorded"
        assert feedback.interaction.sequence == 5
        assert repeated.status == "replayed"
        assert repeated.idempotency_replayed is True

        snapshot = await ledger.replay(scope=_scope(), run_id="run-sql-1")
        assert tuple(entry.sequence for entry in snapshot.entries) == (4, 5)
        assert snapshot.draft_payload is not None
        assert snapshot.deletion_state == "active"


@pytest.mark.asyncio
async def test_sql_feedback_references_use_the_shared_evaluation_contract(session_factory) -> None:
    async with session_factory() as session:
        await _create(session)
        ledger = SqlAlchemyExperienceRunLedger(session)
        async with session.begin():
            receipt = await ledger.append_interaction(
                scope=_scope(),
                run_id="run-sql-1",
                interaction_type=InteractionType.FEEDBACK,
                payload={
                    "signal": "helpful",
                    "benchmark_report_ref": "benchmark:multimodal:gold.v1:abc123",
                    "attempt_id": "attempt-sql-1",
                    "real_event_refs": ["event:experience:sql-1"],
                },
                idempotency_key="feedback-eval-sql-1",
            )
        assert receipt.status == "recorded"

        with pytest.raises(RunHttpError, match="BENCHMARK_REPORT_REF_INVALID"):
            async with session.begin():
                await ledger.append_interaction(
                    scope=_scope(),
                    run_id="run-sql-1",
                    interaction_type=InteractionType.FEEDBACK,
                    payload={"signal": "helpful", "benchmark_report_ref": "unscoped"},
                    idempotency_key="feedback-eval-sql-2",
                )


@pytest.mark.asyncio
async def test_sql_evaluation_projection_replays_after_a_new_session(session_factory) -> None:
    async with session_factory() as writer:
        await _create(writer)
        report_ledger = SessionPerCallExperienceRunLedger(session_factory)
        receipt = await report_ledger.record_evaluation(
            scope=_scope(),
            run_id="run-sql-1",
            report_ref="benchmark:multimodal:gold.v1:abc123",
            case_version="gold.v1",
            idempotency_key="evaluation-sql-1",
            payload={
                "summaries": [{"provider_id": "qwen", "quality_score": 0.9}],
                "release_gate": {"status": "ELIGIBLE", "reasons": []},
            },
        )
        assert receipt.status == "recorded"

    async with session_factory() as reader:
        snapshot = await SqlAlchemyExperienceRunLedger(reader).replay(
            scope=_scope(), run_id="run-sql-1"
        )
    assert snapshot.entries[-1].interaction_type is InteractionType.EVALUATION


@pytest.mark.asyncio
async def test_evaluation_coordinator_persists_through_session_per_call_ledger(
    session_factory,
) -> None:
    """The report coordinator must exercise the durable async ledger seam."""

    async with session_factory() as writer:
        await _create(writer)

    report = MultimodalEvaluationReport(
        case_version="gold.v1",
        total_cases=1,
        summaries=(
            ProviderEvaluationSummary(
                provider_id="qwen",
                model="qwen-omni",
                model_version="2026-08",
                total_cases=1,
                passed_cases=1,
                quality_score=1.0,
                schema_pass_rate=1.0,
                refusal_accuracy_rate=1.0,
                safety_pass_rate=1.0,
                provenance_pass_rate=1.0,
                latency_ms_p50=120,
                latency_ms_p95=120,
                cost_microusd_total=10,
            ),
        ),
    )
    ledger = SessionPerCallExperienceRunLedger(session_factory)
    receipt = await persist_evaluation_projection(
        ledger,
        scope=_scope(),
        run_id="run-sql-1",
        report=report,
        idempotency_key="evaluation-coordinator-sql-1",
    )

    assert receipt.status == "recorded"
    async with session_factory() as reader:
        snapshot = await SqlAlchemyExperienceRunLedger(reader).replay(
            scope=_scope(), run_id="run-sql-1"
        )
    projection = snapshot.entries[-1].payload
    assert projection["report_ref"] == report.report_ref
    assert projection["release_gate"] == {"status": "ELIGIBLE", "reasons": []}
    assert snapshot.entries[-1].payload["education_outcome_status"] == "NOT_MEASURED"


@pytest.mark.asyncio
async def test_sql_ledger_scope_and_idempotency_conflicts_fail_closed(session_factory) -> None:
    async with session_factory() as session:
        await _create(session)
        ledger = SqlAlchemyExperienceRunLedger(session)
        with pytest.raises(RunHttpConflictError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
            async with session.begin():
                await ledger.create_draft(
                    scope=_scope(),
                    run_id="run-sql-1",
                    request_ref="request-sql-1",
                    draft_payload={"status": "DRAFT", "headline": "tampered"},
                    artifact_refs=("media:sha256:" + "a" * 64,),
                    idempotency_key="create-sql-1",
                )

        with pytest.raises(RunHttpError, match="RUN_SCOPE_MISMATCH"):
            await ledger.replay(
                scope=_scope(tenant_id="tenant-other"), run_id="run-sql-1"
            )


@pytest.mark.asyncio
async def test_sql_delete_scrubs_derived_material_but_retains_event(session_factory) -> None:
    async with session_factory() as session:
        await _create(session)
        ledger = SqlAlchemyExperienceRunLedger(session)
        async with session.begin():
            receipt = await ledger.append_interaction(
                scope=_scope(),
                run_id="run-sql-1",
                interaction_type=InteractionType.DELETE,
                payload={"deletion_ref": "delete-sql-1", "status": "deleted"},
                idempotency_key="delete-sql-1",
            )
        assert receipt.status == "deleted"

        snapshot = await ledger.replay(scope=_scope(), run_id="run-sql-1")
        assert snapshot.deletion_state == "deleted"
        assert snapshot.draft_payload is None
        assert snapshot.artifact_refs == ()
        assert snapshot.entries == ()

        checkpoint = await session.scalar(select(ExperienceRunCheckpointRow))
        run = await session.get(
            ExperienceRunRow, {"tenant_id": "tenant-sql", "run_id": "run-sql-1"}
        )
        assert checkpoint is not None
        assert checkpoint.draft_payload is None
        assert checkpoint.artifact_refs == []
        assert run is not None and run.deletion_state == "deleted"

        await session.rollback()
        with pytest.raises(RunHttpError, match="RUN_DELETED"):
            async with session.begin():
                await ledger.append_interaction(
                    scope=_scope(),
                    run_id="run-sql-1",
                    interaction_type=InteractionType.FEEDBACK,
                    payload={"signal": "helpful"},
                    idempotency_key="after-delete",
                )


@pytest.mark.asyncio
async def test_sql_delete_removes_linked_model_draft_in_same_transaction(
    session_factory_with_model_drafts,
) -> None:
    run_id = "run-delete-model-draft"
    draft_id = f"draft:{run_id}"
    async with session_factory_with_model_drafts() as session:
        async with session.begin():
            await _create_with_model_draft(session, run_id=run_id, draft_id=draft_id)

        async with session.begin():
            receipt = await SqlAlchemyExperienceRunLedger(session).append_interaction(
                scope=_scope(),
                run_id=run_id,
                interaction_type=InteractionType.DELETE,
                payload={"deletion_ref": "delete-model-draft", "status": "deleted"},
                idempotency_key="delete-model-draft",
            )

        assert receipt.status == "deleted"
        assert (
            await session.get(
                ModelDraftRow,
                {"tenant_id": "tenant-sql", "draft_id": draft_id},
            )
            is None
        )
        snapshot = await SqlAlchemyExperienceRunLedger(session).replay(
            scope=_scope(), run_id=run_id
        )
        assert snapshot.deletion_state == "deleted"
        assert snapshot.draft_payload is None
        assert snapshot.entries == ()


@pytest.mark.asyncio
async def test_sql_delete_rolls_back_model_draft_and_run_scrub_together(
    session_factory_with_model_drafts,
) -> None:
    run_id = "run-delete-rollback"
    draft_id = f"draft:{run_id}"
    async with session_factory_with_model_drafts() as writer:
        async with writer.begin():
            await _create_with_model_draft(writer, run_id=run_id, draft_id=draft_id)

        with pytest.raises(RuntimeError, match="abort-delete"):
            async with writer.begin():
                await SqlAlchemyExperienceRunLedger(writer).append_interaction(
                    scope=_scope(),
                    run_id=run_id,
                    interaction_type=InteractionType.DELETE,
                    payload={"deletion_ref": "delete-rollback", "status": "deleted"},
                    idempotency_key="delete-rollback",
                )
                raise RuntimeError("abort-delete")

    async with session_factory_with_model_drafts() as reader:
        assert (
            await reader.get(
                ModelDraftRow,
                {"tenant_id": "tenant-sql", "draft_id": draft_id},
            )
            is not None
        )
        snapshot = await SqlAlchemyExperienceRunLedger(reader).replay(
            scope=_scope(), run_id=run_id
        )
        assert snapshot.deletion_state == "active"
        assert snapshot.draft_payload == {"status": "DRAFT", "headline": "可调整草稿"}
        assert snapshot.entries == ()


@pytest.mark.asyncio
async def test_sql_delete_fails_closed_for_cross_family_model_draft(
    session_factory_with_model_drafts,
) -> None:
    run_id = "run-delete-scope-mismatch"
    draft_id = f"draft:{run_id}"
    async with session_factory_with_model_drafts() as writer:
        async with writer.begin():
            await _create_with_model_draft(writer, run_id=run_id, draft_id=draft_id)
            model_draft = await writer.get(
                ModelDraftRow,
                {"tenant_id": "tenant-sql", "draft_id": draft_id},
            )
            assert model_draft is not None
            model_draft.family_id = "family-other"

        with pytest.raises(RunHttpError, match="MODEL_DRAFT_SCOPE_MISMATCH"):
            async with writer.begin():
                await SqlAlchemyExperienceRunLedger(writer).append_interaction(
                    scope=_scope(),
                    run_id=run_id,
                    interaction_type=InteractionType.DELETE,
                    payload={"deletion_ref": "delete-scope-mismatch", "status": "deleted"},
                    idempotency_key="delete-scope-mismatch",
                )

    async with session_factory_with_model_drafts() as reader:
        assert await reader.get(
            ModelDraftRow,
            {"tenant_id": "tenant-sql", "draft_id": draft_id},
        ) is not None
        snapshot = await SqlAlchemyExperienceRunLedger(reader).replay(
            scope=_scope(), run_id=run_id
        )
        assert snapshot.deletion_state == "active"
        assert snapshot.entries == ()


@pytest.mark.asyncio
async def test_transaction_context_is_explicit_and_rolls_back(session_factory) -> None:
    async with session_factory() as session:
        ledger = SqlAlchemyExperienceRunLedger(session)
        with pytest.raises(RuntimeError, match="abort"):
            async with ledger.transaction():
                await ledger.create_draft(
                    scope=_scope(),
                    run_id="run-rollback",
                    request_ref="request-rollback",
                    draft_payload={"status": "DRAFT"},
                    idempotency_key="create-rollback",
                )
                raise RuntimeError("abort")

        assert (
            await session.get(
                ExperienceRunRow,
                {"tenant_id": "tenant-sql", "run_id": "run-rollback"},
            )
            is None
        )


@pytest.mark.asyncio
async def test_sql_preflight_finalize_response_replays_after_session_restart(
    session_factory,
) -> None:
    scope = _scope()
    request_fingerprint = "request-fingerprint-v1"
    response_payload = {
        "run_id": "run-preflight-sql",
        "status": "DRAFT",
        "output": {"headline": "只读草稿"},
    }
    async with session_factory() as writer:
        ledger = SqlAlchemyExperienceRunLedger(writer)
        async with writer.begin():
            reservation = await ledger.preflight_create(
                scope=scope,
                run_id="run-preflight-sql",
                request_ref="request-preflight-sql",
                request_fingerprint=request_fingerprint,
                idempotency_key="idem-preflight-sql",
            )
        assert reservation.status == "reserved"
        async with writer.begin():
            snapshot = await ledger.finalize_create(
                reservation,
                draft_payload={"status": "DRAFT", "headline": "只读草稿"},
                response_payload=response_payload,
            )
        assert snapshot.status == "DRAFT"

    # A fresh session must be able to short-circuit the provider call and
    # return the exact HTTP projection persisted by finalize_create.
    async with session_factory() as reader:
        replay = await SqlAlchemyExperienceRunLedger(reader).preflight_create(
            scope=scope,
            run_id="run-preflight-sql",
            request_ref="request-preflight-sql",
            request_fingerprint=request_fingerprint,
            idempotency_key="idem-preflight-sql",
        )
    assert replay.status == "replay"
    assert replay.snapshot == snapshot
    assert replay.response_payload == response_payload


@pytest.mark.asyncio
async def test_sql_preflight_in_progress_and_release_are_durable(session_factory) -> None:
    scope = _scope()
    async with session_factory() as first_session:
        first = SqlAlchemyExperienceRunLedger(first_session)
        async with first_session.begin():
            reservation = await first.preflight_create(
                scope=scope,
                run_id="run-release-sql",
                request_ref="request-release-sql",
                request_fingerprint="fingerprint-release-sql",
                idempotency_key="idem-release-sql",
            )
    assert reservation.status == "reserved"

    async with session_factory() as second_session:
        second = SqlAlchemyExperienceRunLedger(second_session)
        async with second_session.begin():
            in_progress = await second.preflight_create(
                scope=scope,
                run_id="run-release-sql",
                request_ref="request-release-sql",
                request_fingerprint="fingerprint-release-sql",
                idempotency_key="idem-release-sql",
            )
        assert in_progress.status == "in_progress"
        with pytest.raises(RunHttpConflictError, match="DRAFT_CREATE_IN_PROGRESS"):
            async with second_session.begin():
                await second.preflight_create(
                    scope=scope,
                    run_id="run-release-sql",
                    request_ref="request-release-sql",
                    request_fingerprint="fingerprint-release-sql",
                    idempotency_key="another-idem-release-sql",
                )
        async with second_session.begin():
            await second.release_create(reservation)

    async with session_factory() as retry_session:
        retry = SqlAlchemyExperienceRunLedger(retry_session)
        async with retry_session.begin():
            retried = await retry.preflight_create(
                scope=scope,
                run_id="run-release-sql",
                request_ref="request-release-sql",
                request_fingerprint="fingerprint-release-sql",
                idempotency_key="idem-release-sql",
            )
        assert retried.status == "reserved"


@pytest.mark.asyncio
async def test_sql_finalize_validation_failure_releases_reservation(session_factory) -> None:
    scope = _scope()
    async with session_factory() as session:
        ledger = SqlAlchemyExperienceRunLedger(session)
        async with session.begin():
            reservation = await ledger.preflight_create(
                scope=scope,
                run_id="run-invalid-finalize",
                request_ref="request-invalid-finalize",
                request_fingerprint="fingerprint-invalid-finalize",
                idempotency_key="idem-invalid-finalize",
            )
        async with session.begin():
            with pytest.raises(RunHttpError, match="DRAFT_STATUS_MUST_REMAIN_DRAFT"):
                await ledger.finalize_create(
                    reservation,
                    draft_payload={"status": "APPROVED"},
                )
        async with session.begin():
            retried = await ledger.preflight_create(
                scope=scope,
                run_id="run-invalid-finalize",
                request_ref="request-invalid-finalize",
                request_fingerprint="fingerprint-invalid-finalize",
                idempotency_key="idem-invalid-finalize",
            )
        assert retried.status == "reserved"


@pytest.mark.asyncio
async def test_sql_adapter_through_async_bridge_replays_response_in_new_session(
    session_factory,
) -> None:
    scope = _scope()
    response_payload = {
        "run_id": "run-bridge-sql",
        "status": "DRAFT",
        "output": {"headline": "桥接后的草稿"},
    }
    async with session_factory() as writer:
        bridge = AsyncExperienceRunLedgerBridge(SqlAlchemyExperienceRunLedger(writer))
        async with writer.begin():
            reservation = await bridge.preflight_create(
                scope=scope,
                run_id="run-bridge-sql",
                request_ref="request-bridge-sql",
                request_fingerprint="fingerprint-bridge-sql",
                idempotency_key="idem-bridge-sql",
            )
        assert reservation.status == "reserved"
        async with writer.begin():
            snapshot = await bridge.finalize_create(
                reservation,
                draft_payload={"status": "DRAFT", "headline": "桥接后的草稿"},
                response_payload=response_payload,
            )
        assert snapshot.status == "DRAFT"

    async with session_factory() as reader:
        new_bridge = AsyncExperienceRunLedgerBridge(SqlAlchemyExperienceRunLedger(reader))
        replay = await new_bridge.preflight_create(
            scope=scope,
            run_id="run-bridge-sql",
            request_ref="request-bridge-sql",
            request_fingerprint="fingerprint-bridge-sql",
            idempotency_key="idem-bridge-sql",
        )
        assert replay.status == "replay"
        assert replay.snapshot == snapshot
        assert replay.response_payload == response_payload

        # The bridge must remain provider-free on replay; this is a pure SQL
        # read and returns the same immutable run projection.
        assert await new_bridge.replay(scope=scope, run_id="run-bridge-sql") == snapshot


@pytest.mark.asyncio
async def test_committed_adapter_persists_preflight_before_provider_boundary(
    session_factory,
) -> None:
    """The composition-root adapter makes reservations visible to new sessions."""

    scope = _scope()
    async with session_factory() as writer:
        ledger = CommittedExperienceRunLedger(
            SqlAlchemyExperienceRunLedger(writer), writer
        )
        reservation = await ledger.preflight_create(
            scope=scope,
            run_id="run-committed-boundary",
            request_ref="request-committed-boundary",
            request_fingerprint="fingerprint-committed-boundary",
            idempotency_key="idem-committed-boundary",
        )
        assert reservation.status == "reserved"
        assert writer.in_transaction() is False

    async with session_factory() as concurrent_reader:
        reader = CommittedExperienceRunLedger(
            SqlAlchemyExperienceRunLedger(concurrent_reader), concurrent_reader
        )
        in_progress = await reader.preflight_create(
            scope=scope,
            run_id="run-committed-boundary",
            request_ref="request-committed-boundary",
            request_fingerprint="fingerprint-committed-boundary",
            idempotency_key="idem-committed-boundary",
        )
        assert in_progress.status == "in_progress"
        await reader.release_create(reservation=reservation)
        assert concurrent_reader.in_transaction() is False

    async with session_factory() as retry:
        retry_ledger = CommittedExperienceRunLedger(
            SqlAlchemyExperienceRunLedger(retry), retry
        )
        retried = await retry_ledger.preflight_create(
            scope=scope,
            run_id="run-committed-boundary",
            request_ref="request-committed-boundary",
            request_fingerprint="fingerprint-committed-boundary",
            idempotency_key="idem-committed-boundary",
        )
        assert retried.status == "reserved"


@pytest.mark.asyncio
async def test_session_per_call_adapter_releases_sessions_and_replays_durably(
    session_factory,
) -> None:
    """A resolver can reuse the ledger without retaining request connections."""

    ledger = SessionPerCallExperienceRunLedger(session_factory)
    scope = _scope()
    reservation = await ledger.preflight_create(
        scope=scope,
        run_id="run-session-per-call",
        request_ref="request-session-per-call",
        request_fingerprint="fingerprint-session-per-call",
        idempotency_key="idem-session-per-call",
    )
    assert reservation.status == "reserved"

    in_progress = await ledger.preflight_create(
        scope=scope,
        run_id="run-session-per-call",
        request_ref="request-session-per-call",
        request_fingerprint="fingerprint-session-per-call",
        idempotency_key="idem-session-per-call",
    )
    assert in_progress.status == "in_progress"

    await ledger.release_create(reservation=reservation)
    retried = await ledger.preflight_create(
        scope=scope,
        run_id="run-session-per-call",
        request_ref="request-session-per-call",
        request_fingerprint="fingerprint-session-per-call",
        idempotency_key="idem-session-per-call",
    )
    assert retried.status == "reserved"
    await ledger.release_create(reservation=retried)
