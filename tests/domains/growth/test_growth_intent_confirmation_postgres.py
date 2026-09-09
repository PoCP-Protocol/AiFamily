"""Real-Postgres contract for canonical GrowthIntent confirmation."""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, func, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.types import Uuid

from backend.domains.assessment.application.growth_intent_handoff import (
    ConfirmGrowthIntentInput,
)
from backend.domains.growth.application.growth_intent_confirmation import (
    GrowthConfirmationConflictError,
    GrowthConfirmationValidationError,
)
from backend.domains.growth.infrastructure.sqlalchemy_growth_intent_confirmation import (
    SqlAlchemyGrowthIntentConfirmationAdapter,
)
from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceScope,
)
from backend.intelligence.growth_graph.store import (
    GrowthGraphPersistenceBase,
    SqlAlchemyGrowthGraphProjection,
)
from backend.platform.audit import AuditBase
from backend.platform.outbox import OutboxMetadata, SqlAlchemyOutboxWriter
from backend.platform.persistence import SqlAlchemyUnitOfWork
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

metadata = MetaData()
growth_intents = Table(
    "growth_intents",
    metadata,
    Column("intent_id", Uuid(as_uuid=True), primary_key=True),
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("subject_person_id", Uuid(as_uuid=True), nullable=False),
    Column("signal_ref", Uuid(as_uuid=True), nullable=True),
    Column("need_type", String(64), nullable=False),
    Column("goal_text", String, nullable=False),
    Column("required_capability_keys", ARRAY(String), nullable=False),
    Column("status", String(16), nullable=False),
    Column("close_reason", String(48), nullable=True),
    Column("confirmed_by", Uuid(as_uuid=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=False),
    Column("source_type", String(48), nullable=False),
    Column("source_ref", String(256), nullable=True),
    Column("evidence_refs", ARRAY(Uuid(as_uuid=True)), nullable=False),
    Column("boundary", String(96), nullable=False),
)
idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    Column("idempotency_key", String(128), primary_key=True),
    Column("action_name", String(128), nullable=False),
    Column("request_hash", String(128), nullable=False),
    Column("response_code", Integer, nullable=True),
    Column("response_body", JSON().with_variant(JSONB(), "postgresql"), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)
AuditBase.metadata.tables["platform_audit_events"].to_metadata(metadata)
OutboxMetadata.tables["outbox_events"].to_metadata(metadata)
GrowthGraphPersistenceBase.metadata.tables["ai_growth_graph_edges"].to_metadata(metadata)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    async with postgres_schema_engine(metadata) as engine:
        yield async_sessionmaker(engine, expire_on_commit=False)


def command(*, key: str = "confirm-1") -> ConfirmGrowthIntentInput:
    tenant_id = str(uuid.UUID("10000000-0000-4000-8000-000000000001"))
    family_id = str(uuid.UUID("20000000-0000-4000-8000-000000000001"))
    return ConfirmGrowthIntentInput(
        tenant_id=tenant_id,
        family_id=family_id,
        actor_id=str(uuid.UUID("30000000-0000-4000-8000-000000000001")),
        subject_person_id=str(uuid.UUID("40000000-0000-4000-8000-000000000001")),
        signal_ref="ASSESSMENT:session-1:FAMILY_SUPPORT_NEEDS:v2:H1",
        signal_version=2,
        scope_ref=f"family://{tenant_id}/{family_id}/assessment",
        reviewed_draft_ref="draft-1",
        draft_version=3,
        provenance_ref="provenance-1",
        human_gate_receipt_ref="human-gate-1",
        need_type="PARENT_CHILD_COMMUNICATION",
        goal_text="希望晚饭后的沟通少一点争吵",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=(str(uuid.UUID("50000000-0000-4000-8000-000000000001")),),
        correlation_id="correlation-1",
        idempotency_key=key,
    )


async def count_rows(session: AsyncSession, table: Table) -> int:
    value = await session.scalar(select(func.count()).select_from(table))
    return int(value or 0)


async def test_confirm_commits_intent_audit_outbox_receipt_and_replays(
    session_factory,
) -> None:
    original = command()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        receipt = await SqlAlchemyGrowthIntentConfirmationAdapter(
            uow.session
        ).confirm_growth_intent(original)
        await uow.commit()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        replay = await SqlAlchemyGrowthIntentConfirmationAdapter(uow.session).confirm_growth_intent(
            original
        )

    assert replay == replace(receipt, replayed=True)
    assert receipt.signal_ref == original.signal_ref
    assert receipt.signal_version == original.signal_version
    assert receipt.reviewed_draft_ref == original.reviewed_draft_ref
    assert receipt.draft_version == original.draft_version
    assert receipt.provenance_ref == original.provenance_ref
    assert receipt.human_gate_receipt_ref == original.human_gate_receipt_ref

    async with session_factory() as verify:
        assert await count_rows(verify, growth_intents) == 1
        assert await count_rows(verify, idempotency_keys) == 1
        assert await count_rows(verify, metadata.tables["platform_audit_events"]) == 1
        assert await count_rows(verify, metadata.tables["outbox_events"]) == 1
        envelope = await verify.scalar(select(metadata.tables["outbox_events"].c.payload))
    assert envelope["event"]["human_gate_receipt_ref"] == original.human_gate_receipt_ref
    assert envelope["event"]["reviewed_draft_ref"] == original.reviewed_draft_ref


async def test_same_key_changed_payload_and_existing_intent_mismatch_fail_closed(
    session_factory,
) -> None:
    original = command()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await SqlAlchemyGrowthIntentConfirmationAdapter(uow.session).confirm_growth_intent(original)
        await uow.commit()

    with pytest.raises(GrowthConfirmationConflictError, match="idempotency_key_payload_mismatch"):
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            await SqlAlchemyGrowthIntentConfirmationAdapter(uow.session).confirm_growth_intent(
                replace(original, goal_text="changed")
            )

    with pytest.raises(GrowthConfirmationConflictError, match="existing_growth_intent_mismatch"):
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            await SqlAlchemyGrowthIntentConfirmationAdapter(uow.session).confirm_growth_intent(
                replace(original, goal_text="changed", idempotency_key="confirm-2")
            )

    async with session_factory() as verify:
        assert await count_rows(verify, growth_intents) == 1
        assert await count_rows(verify, idempotency_keys) == 1


@pytest.mark.parametrize(
    ("invalid_command", "message"),
    [
        (
            replace(command(), scope_ref="family://other/other/assessment"),
            "confirmation_scope_mismatch",
        ),
        (replace(command(), reviewed_draft_ref=""), "confirmation_required_reference_missing"),
    ],
)
async def test_invalid_binding_is_rejected_before_any_write(
    session_factory, invalid_command, message
) -> None:
    with pytest.raises(GrowthConfirmationValidationError, match=message):
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            await SqlAlchemyGrowthIntentConfirmationAdapter(uow.session).confirm_growth_intent(
                invalid_command
            )

    async with session_factory() as verify:
        assert await count_rows(verify, growth_intents) == 0
        assert await count_rows(verify, idempotency_keys) == 0


class FailingOutboxWriter(SqlAlchemyOutboxWriter):
    async def append(self, session, event):
        raise RuntimeError("injected canonical outbox failure")


class FailingAuditAdapter(SqlAlchemyGrowthIntentConfirmationAdapter):
    async def _flush_audit(self, binding, receipt, envelope):
        raise RuntimeError("injected canonical audit failure")


class FailingReceiptAdapter(SqlAlchemyGrowthIntentConfirmationAdapter):
    async def _persist_receipt(self, storage_key, receipt):
        raise RuntimeError("injected receipt failure")


@pytest.mark.parametrize(
    ("adapter_type", "message"),
    [
        (FailingAuditAdapter, "injected canonical audit failure"),
        (FailingReceiptAdapter, "injected receipt failure"),
    ],
)
async def test_audit_or_receipt_failure_rolls_every_write_back(
    session_factory, adapter_type, message
) -> None:
    with pytest.raises(RuntimeError, match=message):
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            await adapter_type(uow.session).confirm_growth_intent(command())

    async with session_factory() as verify:
        assert await count_rows(verify, growth_intents) == 0
        assert await count_rows(verify, idempotency_keys) == 0
        assert await count_rows(verify, metadata.tables["platform_audit_events"]) == 0
        assert await count_rows(verify, metadata.tables["outbox_events"]) == 0


async def test_outbox_failure_rolls_intent_audit_and_receipt_back_then_retry_succeeds(
    session_factory,
) -> None:
    original = command()
    with pytest.raises(RuntimeError, match="injected canonical outbox failure"):
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            adapter = SqlAlchemyGrowthIntentConfirmationAdapter(
                uow.session, outbox_writer=FailingOutboxWriter()
            )
            await adapter.confirm_growth_intent(original)

    async with session_factory() as verify:
        assert await count_rows(verify, growth_intents) == 0
        assert await count_rows(verify, idempotency_keys) == 0
        assert await count_rows(verify, metadata.tables["platform_audit_events"]) == 0
        assert await count_rows(verify, metadata.tables["outbox_events"]) == 0

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        await SqlAlchemyGrowthIntentConfirmationAdapter(uow.session).confirm_growth_intent(original)
        await uow.commit()

    async with session_factory() as verify:
        assert await count_rows(verify, growth_intents) == 1
        assert await count_rows(verify, idempotency_keys) == 1


async def test_confirmation_projects_a_queryable_growth_graph_edge(
    session_factory,
) -> None:
    """The real hypothesis-confirmation write path feeds the Growth Graph.

    Runs the exact same adapter used in production
    (`ProductionGrowthConfirmationWiring`) with a real `growth_graph` port
    bound to the same `AsyncSession`, then queries
    `SqlAlchemyGrowthGraphProjection` on a fresh session/scope to prove the
    edge this confirmation produced is durable and independently readable —
    not just constructed in memory.
    """

    original = command()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        adapter = SqlAlchemyGrowthIntentConfirmationAdapter(
            uow.session,
            growth_graph=SqlAlchemyGrowthGraphProjection(uow.session),
        )
        receipt = await adapter.confirm_growth_intent(original)
        await uow.commit()

    async with session_factory() as verify:
        assert await count_rows(verify, metadata.tables["ai_growth_graph_edges"]) == 1
        scope = ExperienceScope(
            global_id=f"family://{original.tenant_id}/{original.family_id}",
            tenant_id=original.tenant_id,
            region_id="CN",
            family_id=original.family_id,
            subject_ids=(original.subject_person_id,),
            purpose="growth_support",
            consent_version=f"signal:{original.signal_version}",
            consent_granted=True,
            data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
            locale="zh-CN",
            content_locale="zh-CN",
            model_locale="zh-CN",
            policy_locale="zh-CN",
            deletion_ref=DeletionRef(
                deletion_id=f"growth-intent:{receipt.intent_id}",
                retention_policy="growth_graph.default_v1",
            ),
            correlation_id=original.correlation_id,
            causation_id=original.human_gate_receipt_ref,
        )
        projection = SqlAlchemyGrowthGraphProjection(verify)
        edges = await projection.query(scope, subject_id=original.subject_person_id)
    assert len(edges) == 1
    edge = edges[0]
    assert edge.relation == "growth_hypothesis.confirmed"
    assert edge.target_node == f"growth_intent:{receipt.intent_id}"
    assert edge.source_node == f"hypothesis:{original.signal_ref}"
    assert edge.event_ref == receipt.receipt_ref
    assert edge.evidence_refs == original.evidence_refs
    assert edge.provenance.provenance_ref == original.provenance_ref

    # A replayed confirmation is idempotent and does not duplicate the edge.
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        adapter = SqlAlchemyGrowthIntentConfirmationAdapter(
            uow.session,
            growth_graph=SqlAlchemyGrowthGraphProjection(uow.session),
        )
        replay = await adapter.confirm_growth_intent(original)
    assert replay.replayed is True
    async with session_factory() as verify:
        assert await count_rows(verify, metadata.tables["ai_growth_graph_edges"]) == 1
