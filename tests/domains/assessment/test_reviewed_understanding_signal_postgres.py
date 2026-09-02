"""Real-PostgreSQL contract for a guardian-reviewed understanding signal."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.types import Uuid

from backend.domains.assessment.application.growth_intent_handoff import (
    AssessmentGrowthIntentHandoff,
    DecideViewedUnderstandingInput,
    GrowthIntentReceipt,
)
from backend.domains.assessment.application.reviewed_understanding_signals import (
    RecordReviewedUnderstandingInput,
    RecordReviewedUnderstandingService,
)
from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
    AssessmentNotFoundError,
    AssessmentValidationError,
)
from backend.domains.assessment.infrastructure.deterministic_interpretation import (
    DeterministicInterpretationAdapter,
)
from backend.domains.assessment.infrastructure.sqlalchemy_reviewed_understanding_signals import (
    SqlAlchemyReviewedUnderstandingSignals,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

metadata = MetaData()
reviewed_signals = Table(
    "assessment_reviewed_understanding_signals",
    metadata,
    Column("reviewed_signal_id", Uuid(as_uuid=True), primary_key=True),
    Column("tenant_id", Uuid(as_uuid=True), nullable=False),
    Column("family_id", Uuid(as_uuid=True), nullable=False),
    Column("assessment_session_id", Uuid(as_uuid=True), nullable=True),
    Column("understanding_run_ref", String(256), nullable=True),
    Column("signal_ref", String(256), nullable=False),
    Column("signal_version", Integer, nullable=False),
    Column("scope_ref", String(256), nullable=False),
    Column("reviewed_draft_ref", String(256), nullable=False),
    Column("draft_version", Integer, nullable=False),
    Column("provenance_ref", String(256), nullable=False),
    Column("draft_source", String(32), nullable=False),
    Column("output_schema_ref", String(256), nullable=False),
    Column("view_event_ref", String(256), nullable=False),
    Column("human_gate_receipt_ref", String(256), nullable=False),
    Column("effective_status", String(16), nullable=False),
    Column("reviewed_by_actor_id", Uuid(as_uuid=True), nullable=False),
    Column("reviewed_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("revocation_ref", String(256), nullable=True),
    Column("subject_person_id", Uuid(as_uuid=True), nullable=False),
    Column("need_type", String(64), nullable=False),
    Column("goal_text", Text, nullable=False),
    Column("required_capability_keys", ARRAY(String), nullable=False),
    Column("evidence_refs", ARRAY(String), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint(
        "tenant_id",
        "family_id",
        "human_gate_receipt_ref",
        name="uq_reviewed_understanding_gate_receipt",
    ),
    CheckConstraint("signal_version > 0", name="ck_reviewed_understanding_signal_version"),
    CheckConstraint("draft_version > 0", name="ck_reviewed_understanding_draft_version"),
    CheckConstraint(
        "effective_status IN ('EFFECTIVE', 'REVOKED', 'EXPIRED')",
        name="ck_reviewed_understanding_effective_status",
    ),
    CheckConstraint(
        "draft_source = 'MODEL_GATEWAY'",
        name="ck_reviewed_understanding_model_gateway_source",
    ),
)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    async with postgres_schema_engine(metadata) as engine:
        yield async_sessionmaker(engine, expire_on_commit=False)


def reviewed_command() -> RecordReviewedUnderstandingInput:
    tenant_id = "10000000-0000-4000-8000-000000000001"
    family_id = "20000000-0000-4000-8000-000000000001"
    reviewed_at = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    return RecordReviewedUnderstandingInput(
        tenant_id=tenant_id,
        family_id=family_id,
        assessment_session_id="60000000-0000-4000-8000-000000000001",
        signal_ref=("ASSESSMENT:60000000-0000-4000-8000-000000000001:FAMILY_SUPPORT_NEEDS:v2:H1"),
        signal_version=2,
        scope_ref=f"family://{tenant_id}/{family_id}/assessment",
        reviewed_draft_ref="draft-3",
        draft_version=3,
        provenance_ref="provenance-3",
        draft_source="MODEL_GATEWAY",
        output_schema_ref="FAMILY_UNDERSTANDING_OUTPUT_V1",
        view_event_ref="view-event-3",
        human_gate_receipt_ref="gate-receipt-3",
        human_gate_effective_status="EFFECTIVE",
        reviewed_by_actor_id="30000000-0000-4000-8000-000000000001",
        reviewed_by_actor_type="FAMILY_GUARDIAN",
        reviewed_at=reviewed_at,
        expires_at=reviewed_at + timedelta(days=100),
        subject_person_id="40000000-0000-4000-8000-000000000001",
        need_type="PARENT_CHILD_COMMUNICATION",
        goal_text="希望晚饭后的沟通少一点争吵",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=("50000000-0000-4000-8000-000000000001",),
    )


def evidence() -> GrowthHypothesisEvidence:
    return GrowthHypothesisEvidence(
        assessment_session_id="60000000-0000-4000-8000-000000000001",
        subject_person_id="40000000-0000-4000-8000-000000000001",
        subject_display_name="孩子",
        submitted_at=datetime(2026, 9, 1, tzinfo=UTC),
        tool_ref="FAMILY_SUPPORT_NEEDS",
        tool_version=2,
        assessment_response_id="response-1",
        focus_ref="COMMUNICATION",
        assessment_evidence_id="50000000-0000-4000-8000-000000000001",
        need_type_ref="PARENT_CHILD_COMMUNICATION",
        need_type_version=1,
        title="沟通",
        description="先理解彼此的触发点",
        required_capability_keys=["FAMILY_COMMUNICATION"],
        response_set=[],
    )


async def row_count(session_factory) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(reviewed_signals)) or 0)


async def test_draft_generation_does_not_create_reviewed_fact(session_factory) -> None:
    await DeterministicInterpretationAdapter().interpret("family-1", evidence())
    assert await row_count(session_factory) == 0


async def test_guardian_view_is_durable_and_idempotent_across_sessions(session_factory) -> None:
    command = reviewed_command()
    async with session_factory() as session:
        service = RecordReviewedUnderstandingService(
            SqlAlchemyReviewedUnderstandingSignals(session)
        )
        first = await service.record_viewed(command)
        replay = await service.record_viewed(command)
        await session.commit()

    assert first == replay
    assert await row_count(session_factory) == 1

    async with session_factory() as restarted_session:
        loaded = await SqlAlchemyReviewedUnderstandingSignals(restarted_session).load_viewed_signal(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            assessment_session_id=command.assessment_session_id,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
        )
    assert loaded == first


async def test_same_gate_receipt_cannot_bind_a_different_version(session_factory) -> None:
    command = reviewed_command()
    async with session_factory() as session:
        service = RecordReviewedUnderstandingService(
            SqlAlchemyReviewedUnderstandingSignals(session)
        )
        await service.record_viewed(command)
        with pytest.raises(
            AssessmentConflictError, match="reviewed_understanding_idempotency_conflict"
        ):
            await service.record_viewed(replace(command, draft_version=4))


@pytest.mark.parametrize(
    "changed",
    [
        {"reviewed_by_actor_type": "AI"},
        {"human_gate_effective_status": "REVOKED"},
        {"scope_ref": "family://other/other/assessment"},
        {"draft_source": "SYNTHETIC"},
        {"draft_source": "FIXED_TEMPLATE"},
    ],
)
async def test_invalid_view_never_writes(session_factory, changed) -> None:
    command = replace(reviewed_command(), **changed)
    async with session_factory() as session:
        service = RecordReviewedUnderstandingService(
            SqlAlchemyReviewedUnderstandingSignals(session)
        )
        with pytest.raises(AssessmentForbiddenError):
            await service.record_viewed(command)
    assert await row_count(session_factory) == 0


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        ({"provenance_ref": ""}, "viewed_understanding_signal_required"),
        ({"evidence_refs": ()}, "understanding_signal_evidence_required"),
        ({"output_schema_ref": ""}, "reviewed_draft_verification_required"),
        ({"view_event_ref": ""}, "reviewed_draft_verification_required"),
        (
            {"expires_at": datetime(2026, 9, 1, 7, 59, tzinfo=UTC)},
            "reviewed_understanding_expiry_invalid",
        ),
    ],
)
async def test_invalid_binding_is_rejected_before_writer(session_factory, changed, message) -> None:
    command = replace(reviewed_command(), **changed)
    async with session_factory() as session:
        service = RecordReviewedUnderstandingService(
            SqlAlchemyReviewedUnderstandingSignals(session)
        )
        with pytest.raises(AssessmentValidationError, match=message):
            await service.record_viewed(command)
    assert await row_count(session_factory) == 0


class GrowthIntentStub:
    calls = 0

    async def confirm_growth_intent(self, command) -> GrowthIntentReceipt:
        self.calls += 1
        return GrowthIntentReceipt(
            intent_id=str(uuid.uuid4()),
            signal_ref=command.signal_ref,
            signal_version=command.signal_version,
            scope_ref=command.scope_ref,
            reviewed_draft_ref=command.reviewed_draft_ref,
            draft_version=command.draft_version,
            provenance_ref=command.provenance_ref,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
            receipt_ref="growth-receipt-1",
        )


def decision(command: RecordReviewedUnderstandingInput) -> DecideViewedUnderstandingInput:
    return DecideViewedUnderstandingInput(
        tenant_id=command.tenant_id,
        family_id=command.family_id,
        actor_id=command.reviewed_by_actor_id,
        actor_type="FAMILY_GUARDIAN",
        assessment_session_id=command.assessment_session_id,
        signal_ref=command.signal_ref,
        signal_version=command.signal_version,
        scope_ref=command.scope_ref,
        reviewed_draft_ref=command.reviewed_draft_ref,
        draft_version=command.draft_version,
        provenance_ref=command.provenance_ref,
        human_gate_receipt_ref=command.human_gate_receipt_ref,
        decision_type="CONFIRM",
        correlation_id="correlation-1",
        idempotency_key="decision-1",
        understanding_run_ref=command.understanding_run_ref,
    )


async def test_problem_understanding_signal_survives_restart_and_handoffs(
    session_factory,
) -> None:
    assessment = reviewed_command()
    command = replace(
        assessment,
        assessment_session_id=None,
        understanding_run_ref="understanding-run-1",
        scope_ref=(f"family://{assessment.tenant_id}/{assessment.family_id}/problem-understanding"),
        signal_ref="understanding-signal:v1:sha256:one",
        signal_version=1,
        reviewed_draft_ref="artifact-v1",
        draft_version=1,
        provenance_ref="air-provenance:v1:sha256:one",
        human_gate_receipt_ref="review-receipt:v1:sha256:one",
    )
    async with session_factory() as session:
        adapter = SqlAlchemyReviewedUnderstandingSignals(session)
        first = await RecordReviewedUnderstandingService(adapter).record_viewed(command)
        replay = await RecordReviewedUnderstandingService(adapter).record_viewed(command)
        await session.commit()
    assert replay == first

    growth = GrowthIntentStub()
    async with session_factory() as restarted_session:
        adapter = SqlAlchemyReviewedUnderstandingSignals(restarted_session)
        loaded = await adapter.load_viewed_signal(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            assessment_session_id=None,
            understanding_run_ref=command.understanding_run_ref,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
        )
        assert loaded == first
        receipt = await AssessmentGrowthIntentHandoff(adapter, growth).decide(decision(command))

    assert receipt.outcome == "INTENT_CREATED"
    assert growth.calls == 1


async def test_confirm_uses_exact_durable_binding_and_rejects_stale_version(
    session_factory,
) -> None:
    command = reviewed_command()
    growth = GrowthIntentStub()
    async with session_factory() as session:
        adapter = SqlAlchemyReviewedUnderstandingSignals(session)
        await RecordReviewedUnderstandingService(adapter).record_viewed(command)
        await session.commit()

    async with session_factory() as restarted_session:
        handoff = AssessmentGrowthIntentHandoff(
            SqlAlchemyReviewedUnderstandingSignals(restarted_session), growth
        )
        receipt = await handoff.decide(decision(command))
        assert receipt.outcome == "INTENT_CREATED"
        with pytest.raises(AssessmentConflictError, match="understanding_signal_version_conflict"):
            await handoff.decide(replace(decision(command), signal_version=1))
    assert growth.calls == 1


async def test_revoked_expired_and_cross_scope_signals_fail_closed(session_factory) -> None:
    command = reviewed_command()
    async with session_factory() as session:
        adapter = SqlAlchemyReviewedUnderstandingSignals(session)
        await RecordReviewedUnderstandingService(adapter).record_viewed(command)
        await session.commit()

    async with session_factory() as session:
        adapter = SqlAlchemyReviewedUnderstandingSignals(session)
        assert (
            await adapter.load_viewed_signal(
                tenant_id="90000000-0000-4000-8000-000000000009",
                family_id=command.family_id,
                assessment_session_id=command.assessment_session_id,
                human_gate_receipt_ref=command.human_gate_receipt_ref,
            )
            is None
        )
        assert (
            await adapter.load_viewed_signal(
                tenant_id=command.tenant_id,
                family_id="90000000-0000-4000-8000-000000000009",
                assessment_session_id=command.assessment_session_id,
                human_gate_receipt_ref=command.human_gate_receipt_ref,
            )
            is None
        )
        await session.execute(
            text(
                "update assessment_reviewed_understanding_signals "
                "set effective_status='REVOKED',revoked_at=now(),"
                "revocation_ref='revocation-1'"
            )
        )
        await session.commit()

    async with session_factory() as session:
        handoff = AssessmentGrowthIntentHandoff(
            SqlAlchemyReviewedUnderstandingSignals(session), GrowthIntentStub()
        )
        with pytest.raises(AssessmentForbiddenError, match="human_gate_receipt_not_effective"):
            await handoff.decide(decision(command))

        await session.execute(
            text(
                "update assessment_reviewed_understanding_signals "
                "set effective_status='EXPIRED',revoked_at=null,revocation_ref=null,"
                "expires_at=now() - interval '1 day'"
            )
        )
        await session.commit()

    async with session_factory() as session:
        handoff = AssessmentGrowthIntentHandoff(
            SqlAlchemyReviewedUnderstandingSignals(session), GrowthIntentStub()
        )
        with pytest.raises(AssessmentForbiddenError, match="human_gate_receipt_not_effective"):
            await handoff.decide(decision(command))


async def test_missing_or_deleted_signal_cannot_be_confirmed(session_factory) -> None:
    command = reviewed_command()
    async with session_factory() as session:
        handoff = AssessmentGrowthIntentHandoff(
            SqlAlchemyReviewedUnderstandingSignals(session), GrowthIntentStub()
        )
        with pytest.raises(AssessmentNotFoundError, match="understanding_signal_not_found"):
            await handoff.decide(decision(command))
