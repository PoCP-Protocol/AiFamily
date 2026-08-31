from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.intelligence.human_gate import GateStatus
from backend.intelligence.human_gate.persistence import HumanGateBase, HumanTaskRow
from backend.platform.audit import AuditBase, AuditEventRow, read_all_events

from ..application.context import ActorContext
from ..application.product_definition_adoption import ProductDefinitionAdoptionArguments
from ..application.product_package_submission import (
    PRODUCT_PACKAGE_SUBMIT_PERMISSION,
    ProductPackageSubmissionConflictError,
    ProductPackageSubmissionError,
    ProductPackageSubmissionForbiddenError,
    ProductPackageSubmissionInput,
    ProductPackageSubmissionRepository,
    submit_product_package_draft,
)
from ..domain.entities import ProductConcept
from ..domain.errors import (
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from ..domain.evidence_verification import (
    EvidenceVerificationReceipt,
    EvidenceVerificationReceiptContent,
    evidence_verification_receipt_hash,
)
from ..domain.product_package_draft import (
    EvidenceAdmissionSnapshot,
    ProductPackageEvidenceRequirement,
)
from ..domain.zone_entities import DimensionAssessment, ProductZoneAssessment
from ..infrastructure.evidence_verification_repository import (
    SqlAlchemyEvidenceVerificationReceiptRepository,
)
from ..infrastructure.product_package_submission_repository import (
    ProductPackageDraftRow,
    SqlAlchemyProductPackageSubmissionRepository,
)
from ..infrastructure.sqlalchemy_models import Base as ProductBase
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository
from ..infrastructure.zone_sqlalchemy_models import Base as ZoneBase
from ..infrastructure.zone_sqlalchemy_repository import SqlAlchemyZoneAssessmentRepository

NOW = datetime(2026, 8, 31, 18, 0, tzinfo=UTC)
DIMENSIONS = (
    "customer_scarcity",
    "replaceability",
    "data_advantage",
    "network_effect",
    "learning_effect",
    "switching_cost",
)


def _evidence(kind: str, *, tenant: str = "tenant-a"):
    from ..domain.entities import Evidence

    return Evidence(
        id=f"evidence:{kind}:one",
        version=1,
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=1),
        created_by="human:researcher",
        tenant_scope=tenant,
        description=f"redacted {kind} evidence",
        evidence_ref=f"source:{kind}:one",
    )


def _receipt(kind: str, *, tenant: str = "tenant-a") -> EvidenceVerificationReceipt:
    from ..application.evidence_verification import evidence_record_hash

    evidence = _evidence(kind, tenant=tenant)
    claim_ref = f"claim:{kind}"
    content = EvidenceVerificationReceiptContent(
        receipt_id=f"verification-receipt:{kind}",
        tenant_scope=tenant,
        evidence_id=evidence.id,
        evidence_version=evidence.version,
        evidence_record_hash=evidence_record_hash(evidence),
        evidence_ref=evidence.evidence_ref,
        claim_scope=(claim_ref,),
        verification_methods=("SOURCE_OPENED", "EVIDENCE_RECORD_HASH_MATCHED"),
        applicability_scope=(
            "role:PARENT_GUARDIAN",
            "age:AGE_9_12",
            "scenario:HOME_ROUTINE",
            "region:CN",
            "language:zh-CN",
        ),
        criteria_refs=("evidence-policy:source-integrity:v1",),
        verification_purpose="product_package_admission",
        verification_policy_version="product-evidence-verification:v1",
        task_id=f"task:{kind}",
        proposal_id=f"proposal:{kind}",
        decision_id=f"decision:{kind}",
        request_id=f"request:{kind}",
        verifier_actor_id="operator:evidence-reviewer",
        decision_reason="source and scope reviewed",
        verified_at=NOW - timedelta(hours=1),
        valid_until=NOW + timedelta(days=30),
        recorded_at=NOW - timedelta(minutes=50),
        request_hash=("a" if kind == "market" else "b") * 64,
    )
    return EvidenceVerificationReceipt(
        **content.model_dump(mode="python"),
        receipt_hash=evidence_verification_receipt_hash(content),
    )


def _admission(kind: str, *, tenant: str = "tenant-a") -> EvidenceAdmissionSnapshot:
    receipt = _receipt(kind, tenant=tenant)
    return EvidenceAdmissionSnapshot(
        claim_type="MARKET_EXISTENCE" if kind == "market" else "DELIVERY_FEASIBILITY",
        required_claim_refs=(f"claim:{kind}",),
        required_applicability_refs=("role:PARENT_GUARDIAN", "age:AGE_9_12"),
        receipt_id=receipt.receipt_id,
        receipt_hash=receipt.receipt_hash,
        evidence_id=receipt.evidence_id,
        evidence_version=receipt.evidence_version,
        evidence_record_hash=receipt.evidence_record_hash,
        evidence_ref=receipt.evidence_ref,
        claim_scope=receipt.claim_scope,
        applicability_scope=receipt.applicability_scope,
        criteria_refs=receipt.criteria_refs,
        verification_methods=receipt.verification_methods,
        verification_purpose=receipt.verification_purpose,
        verification_policy_version=receipt.verification_policy_version,
        receipt_outcome=receipt.outcome,
        integrity_check=receipt.integrity_check,
        relevance=receipt.relevance,
        task_id=receipt.task_id,
        proposal_id=receipt.proposal_id,
        decision_id=receipt.decision_id,
        verified_at=receipt.verified_at,
        valid_until=receipt.valid_until,
        admission_policy_version="family-education-evidence-admission:v1",
        admitted_at=NOW,
    )


def _requirement(kind: str) -> ProductPackageEvidenceRequirement:
    return ProductPackageEvidenceRequirement(
        receipt_locator=f"verification-receipt:{kind}",
        claim_type="MARKET_EXISTENCE" if kind == "market" else "DELIVERY_FEASIBILITY",
        required_claim_refs=(f"claim:{kind}",),
        required_applicability_refs=("role:PARENT_GUARDIAN", "age:AGE_9_12"),
    )


def _context(*, tenant: str = "tenant-a", allowed: bool = True) -> ActorContext:
    return ActorContext(
        actor_id="human:product-owner",
        actor_type="HUMAN",
        tenant_scope=tenant,
        permissions=(frozenset({PRODUCT_PACKAGE_SUBMIT_PERMISSION}) if allowed else frozenset()),
        trace_id="trace:package:one",
    )


def _source(**changes: object) -> ProductPackageSubmissionInput:
    values: dict[str, object] = {
        "concept_id": "concept:one",
        "zone_assessment_id": "assessment:one",
        "upstream_decision_draft_ref": "decision-draft:one",
        "product_kind": "MICRO_CAMP",
        "duration_days": 21,
        "primary_contradiction": "理解与行动之间存在断点",
        "demand_ref": "demand:one",
        "market_insight_refs": ("insight:one",),
        "competitor_evidence_refs": ("competitor-evidence:one",),
        "component_ids": ("component:understand:v1", "component:action:v1"),
        "skill_ids": ("skill:compose:v1",),
        "success_metric_ids": ("metric:action-adoption",),
        "guardrail_ids": ("guardrail:consent",),
        "stop_conditions": ("stop:safety",),
        "pause_policy": "家长可随时暂停",
        "human_gate_policy": "敏感建议需人工复核",
        "evidence_refs": ("verification-receipt:market", "verification-receipt:pilot"),
        "evidence_requirements": (_requirement("market"), _requirement("pilot")),
        "evidence_admissions": (_admission("market"), _admission("pilot")),
        "assumptions": ("需要小批家庭验证",),
        "unknowns": ("不同年龄段的节奏差异",),
        "next_validation": "完成五个家庭的匿名试点",
        "expires_at": NOW + timedelta(days=7),
        "source_provenance_ref": "model-draft:product-package:one",
        "model_ref": "model:test@1",
        "prompt_use_case_version": "service-product-composition@1",
        "confidence": 0.82,
    }
    values.update(changes)
    return ProductPackageSubmissionInput(**values)


def _concept(*, tenant: str = "tenant-a") -> ProductConcept:
    return ProductConcept(
        id="concept:one",
        created_at=NOW,
        updated_at=NOW,
        created_by="human:research-owner",
        tenant_scope=tenant,
        strategy_id="strategy:one",
        title="家庭行动支持",
    )


def _assessment(*, tenant: str = "tenant-a", status: str = "APPROVED") -> ProductZoneAssessment:
    dimensions = [
        DimensionAssessment(
            dimension=dimension,
            score=82,
            rationale="evidence-backed",
            evidence_refs=[f"evidence:{dimension}"],
            evidence_strength=0.8,
            assessed_by="human:research-owner",
            assessed_at=NOW,
        )
        for dimension in DIMENSIONS
    ]
    return ProductZoneAssessment(
        id="assessment:one",
        version=3,
        created_at=NOW,
        updated_at=NOW,
        created_by="human:research-owner",
        tenant_scope=tenant,
        status=status,
        subject_ref="concept:one",
        zone_policy_version_id="zone-policy:v2",
        dimension_assessments=dimensions,
        differentiation_index=76,
        defensibility_index=84,
        commodity_score=12,
        advantage_score=70,
        unique_score=82,
        recommended_zone="UNIQUE",
        approved_zone="UNIQUE" if status == "APPROVED" else None,
        reviewed_by="human:portfolio-owner" if status == "APPROVED" else None,
        reviewed_at=NOW if status == "APPROVED" else None,
        review_reason="证据足以进入产品设计" if status == "APPROVED" else None,
    )


async def _factory() -> tuple[object, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ProductBase.metadata.create_all)
        await connection.run_sync(ZoneBase.metadata.create_all)
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed(
    session: AsyncSession,
    *,
    assessment_status: str = "APPROVED",
    tenant: str = "tenant-a",
) -> None:
    await SqlAlchemyProductIntelligenceRepository(session).save_product_concept(
        _concept(tenant=tenant)
    )
    await SqlAlchemyZoneAssessmentRepository(session).save_zone_assessment(
        _assessment(status=assessment_status, tenant=tenant)
    )
    product_repo = SqlAlchemyProductIntelligenceRepository(session)
    receipt_repo = SqlAlchemyEvidenceVerificationReceiptRepository(session)
    for kind in ("market", "pilot"):
        await product_repo.save_evidence(_evidence(kind, tenant=tenant))
        await receipt_repo.create_receipt_if_absent(_receipt(kind, tenant=tenant))
    await session.commit()


@pytest.mark.asyncio
async def test_submission_persists_immutable_draft_and_open_action_proposal() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        result = await submit_product_package_draft(
            SqlAlchemyProductPackageSubmissionRepository(session),
            _context(),
            _source(),
            idempotency_key="package-key-one",
            now=NOW,
        )

    async with factory() as session:
        persisted = await SqlAlchemyProductPackageSubmissionRepository(session).get(
            draft_id=result.draft.draft_id,
            tenant_scope="tenant-a",
        )
        events = await read_all_events(session)
    await engine.dispose()

    assert persisted.draft == result.draft
    assert persisted.draft.status == "DRAFT"
    assert persisted.draft.zone_assessment_version == 3
    assert persisted.draft.approved_zone == "UNIQUE"
    assert persisted.task.status is GateStatus.OPEN
    assert persisted.task.proposal.draft_id == persisted.draft.draft_id
    assert persisted.task.proposal.provenance_ref.endswith(persisted.draft.content_hash)
    arguments = ProductDefinitionAdoptionArguments.model_validate(
        persisted.task.proposal.action_arguments
    )
    assert arguments.source_decision_draft_ref == persisted.draft.draft_id
    assert "zone" not in persisted.task.proposal.action_arguments
    assert [event.action for event in events] == [
        "CREATE_PRODUCT_PACKAGE_DRAFT",
        "CREATE_HUMAN_TASK",
    ]


@pytest.mark.asyncio
async def test_exact_replay_returns_original_snapshot_and_changed_payload_conflicts() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        repo = SqlAlchemyProductPackageSubmissionRepository(session)
        first = await submit_product_package_draft(
            repo,
            _context(),
            _source(),
            idempotency_key="package-key-one",
            now=NOW,
        )
        await SqlAlchemyZoneAssessmentRepository(session).save_zone_assessment(
            _assessment(status="RETIRED")
        )
        await session.commit()
        replay = await submit_product_package_draft(
            repo,
            _context(),
            _source(),
            idempotency_key="package-key-one",
            now=NOW + timedelta(hours=1),
        )
        with pytest.raises(
            ProductPackageSubmissionConflictError,
            match="INTENT_REPLAY_MISMATCH",
        ):
            await submit_product_package_draft(
                repo,
                _context(),
                _source(duration_days=90, product_kind="SCALE_PLAN"),
                idempotency_key="package-key-one",
                now=NOW,
            )
        events = await read_all_events(session)
    await engine.dispose()

    assert replay.replayed is True
    assert replay.draft == first.draft
    assert replay.task == first.task
    assert len(events) == 2


@pytest.mark.asyncio
async def test_same_resolved_source_cannot_replay_a_different_browser_intent() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        repo = SqlAlchemyProductPackageSubmissionRepository(session)
        await submit_product_package_draft(
            repo,
            _context(),
            _source(),
            idempotency_key="dual-hash-replay",
            intent_hash="a" * 64,
            source_draft_locator="source-locator:one",
            now=NOW,
        )
        with pytest.raises(
            ProductPackageSubmissionConflictError,
            match="PRODUCT_PACKAGE_INTENT_REPLAY_MISMATCH",
        ):
            await submit_product_package_draft(
                repo,
                _context(),
                _source(),
                idempotency_key="dual-hash-replay",
                intent_hash="b" * 64,
                source_draft_locator="source-locator:two",
                now=NOW,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_rejects_mismatched_resolved_hash_before_any_write() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        repo = SqlAlchemyProductPackageSubmissionRepository(session)
        result = await submit_product_package_draft(
            repo,
            _context(),
            _source(),
            idempotency_key="resolved-hash-lineage",
            intent_hash="a" * 64,
            source_draft_locator="source-locator:one",
            now=NOW,
        )
        before = (
            await session.scalar(select(func.count()).select_from(ProductPackageDraftRow)),
            await session.scalar(select(func.count()).select_from(HumanTaskRow)),
            await session.scalar(select(func.count()).select_from(AuditEventRow)),
        )
        with pytest.raises(
            ProductPackageSubmissionConflictError,
            match="PRODUCT_PACKAGE_INTENT_PERSISTENCE_LINEAGE_MISMATCH",
        ):
            await repo.persist_submission(
                draft=result.draft,
                proposal=result.task.proposal,
                task_id=result.task.task_id,
                actor_id="human:product-owner",
                idempotency_key="resolved-hash-lineage",
                request_hash="f" * 64,
                intent_hash=result.draft.intent_hash,
                source_draft_locator=result.draft.source_draft_locator,
            )
        after = (
            await session.scalar(select(func.count()).select_from(ProductPackageDraftRow)),
            await session.scalar(select(func.count()).select_from(HumanTaskRow)),
            await session.scalar(select(func.count()).select_from(AuditEventRow)),
        )
    await engine.dispose()

    assert before == after == (1, 1, 2)


@pytest.mark.asyncio
async def test_final_revalidation_blocks_source_drift_before_draft_task_or_audit() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        await SqlAlchemyProductIntelligenceRepository(session).save_evidence(
            _evidence("market").model_copy(
                update={
                    "description": "source changed after initial admission",
                    "updated_at": NOW + timedelta(minutes=1),
                }
            )
        )
        await session.commit()
        with pytest.raises(
            ProductPackageSubmissionConflictError,
            match="EVIDENCE_ADMISSION_REVALIDATION_FAILED",
        ):
            await submit_product_package_draft(
                SqlAlchemyProductPackageSubmissionRepository(session),
                _context(),
                _source(),
                idempotency_key="source-drift-before-write",
                now=NOW,
            )

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProductPackageDraftRow)) == 0
        assert await session.scalar(select(func.count()).select_from(HumanTaskRow)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEventRow)) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_final_revalidation_uses_commit_time_and_rolls_back_expired_receipts() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        repo = SqlAlchemyProductPackageSubmissionRepository(
            session,
            clock=lambda: NOW + timedelta(days=31),
        )
        with pytest.raises(
            ProductPackageSubmissionConflictError,
            match="EVIDENCE_ADMISSION_REVALIDATION_FAILED",
        ):
            await submit_product_package_draft(
                repo,
                _context(),
                _source(),
                idempotency_key="expired-at-commit",
                now=NOW,
            )

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProductPackageDraftRow)) == 0
        assert await session.scalar(select(func.count()).select_from(HumanTaskRow)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEventRow)) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_admission_evaluation_time_does_not_change_idempotency_identity() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        repo = SqlAlchemyProductPackageSubmissionRepository(session, clock=lambda: NOW)
        first = await submit_product_package_draft(
            repo,
            _context(),
            _source(),
            idempotency_key="admission-time-is-operational",
            now=NOW,
        )
        shifted = tuple(
            item.model_copy(update={"admitted_at": NOW + timedelta(minutes=1)})
            for item in _source().evidence_admissions
        )
        replay = await submit_product_package_draft(
            repo,
            _context(),
            _source(evidence_admissions=shifted),
            idempotency_key="admission-time-is-operational",
            now=NOW + timedelta(minutes=1),
        )

    await engine.dispose()
    assert replay.replayed is True
    assert replay.draft == first.draft


@pytest.mark.asyncio
async def test_submission_fails_closed_for_permission_evidence_and_zone_status() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        repo = SqlAlchemyProductPackageSubmissionRepository(session)
        with pytest.raises(ProductPackageSubmissionForbiddenError):
            await submit_product_package_draft(
                repo,
                _context(allowed=False),
                _source(),
                idempotency_key="forbidden",
                now=NOW,
            )
        with pytest.raises(ProductPackageSubmissionError, match="ADMISSIONS_MUST_MATCH_REFS"):
            await submit_product_package_draft(
                repo,
                _context(),
                _source(
                    evidence_admissions=(_admission("market"),)
                ),
                idempotency_key="unverified",
                now=NOW,
            )
        await SqlAlchemyZoneAssessmentRepository(session).save_zone_assessment(
            _assessment(status="SCORED")
        )
        await session.commit()
        with pytest.raises(ProductPackageSubmissionError, match="APPROVED_ZONE"):
            await submit_product_package_draft(
                repo,
                _context(),
                _source(),
                idempotency_key="unapproved",
                now=NOW,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_draft_read_is_tenant_scoped() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        repo = SqlAlchemyProductPackageSubmissionRepository(session)
        result = await submit_product_package_draft(
            repo,
            _context(),
            _source(),
            idempotency_key="package-key-one",
            now=NOW,
        )
        with pytest.raises(ProductIntelligenceNotFoundError):
            await repo.get(draft_id=result.draft.draft_id, tenant_scope="tenant-b")
    await engine.dispose()


@pytest.mark.asyncio
async def test_task_id_is_bounded_for_maximum_tenant_length() -> None:
    engine, factory = await _factory()
    tenant = "t" * 128
    async with factory() as session:
        await _seed(session, tenant=tenant)
        result = await submit_product_package_draft(
            SqlAlchemyProductPackageSubmissionRepository(session),
            _context(tenant=tenant),
            _source(
                evidence_admissions=(
                    _admission("market", tenant=tenant),
                    _admission("pilot", tenant=tenant),
                )
            ),
            idempotency_key="bounded-task-id",
            now=NOW,
        )
    await engine.dispose()

    assert result.task.task_id.startswith("human-task:")
    assert len(result.task.task_id) <= 160


@pytest.mark.asyncio
async def test_content_hash_binds_normalized_snapshot_and_detects_tampering() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        repo = SqlAlchemyProductPackageSubmissionRepository(session)
        result = await submit_product_package_draft(
            repo,
            _context(),
            _source(
                primary_contradiction="  理解与行动之间存在断点  ",
                component_ids=(" component:understand:v1 ", "component:action:v1"),
            ),
            idempotency_key="normalized-hash",
            now=NOW,
        )
        assert result.draft.primary_contradiction == "理解与行动之间存在断点"
        assert result.draft.component_ids[0] == "component:understand:v1"

        row = await session.get(ProductPackageDraftRow, result.draft.draft_id)
        assert row is not None
        tampered = dict(row.payload)
        tampered["primary_contradiction"] = "tampered"
        row.payload = tampered
        await session.commit()

    async with factory() as session:
        with pytest.raises(ProductIntelligenceValidationError, match="content_hash_mismatch"):
            await SqlAlchemyProductPackageSubmissionRepository(session).get(
                draft_id=result.draft.draft_id,
                tenant_scope="tenant-a",
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_readback_rejects_tampered_adoption_arguments() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        result = await submit_product_package_draft(
            SqlAlchemyProductPackageSubmissionRepository(session),
            _context(),
            _source(),
            idempotency_key="tampered-adoption-arguments",
            now=NOW,
        )
        task_row = await session.get(HumanTaskRow, result.task.task_id)
        assert task_row is not None
        proposal_payload = dict(task_row.proposal_payload)
        action_arguments = dict(proposal_payload["action_arguments"])
        action_arguments["duration_days"] = 90
        proposal_payload["action_arguments"] = action_arguments
        task_row.proposal_payload = proposal_payload
        await session.commit()

    async with factory() as session:
        with pytest.raises(
            ProductPackageSubmissionConflictError,
            match="PRODUCT_PACKAGE_PERSISTED_LINEAGE_MISMATCH",
        ):
            await SqlAlchemyProductPackageSubmissionRepository(session).get(
                draft_id=result.draft.draft_id,
                tenant_scope="tenant-a",
            )
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        (
            "request_hash",
            "f" * 64,
            "PRODUCT_PACKAGE_PERSISTED_LINEAGE_MISMATCH",
        ),
        (
            "intent_hash",
            "e" * 64,
            "PRODUCT_PACKAGE_PERSISTED_LINEAGE_MISMATCH",
        ),
        (
            "source_draft_locator",
            "source-locator:tampered",
            "PRODUCT_PACKAGE_PERSISTED_LINEAGE_MISMATCH",
        ),
    ],
)
async def test_readback_rejects_tampered_intent_lineage(
    field: str,
    value: str,
    code: str,
) -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        result = await submit_product_package_draft(
            SqlAlchemyProductPackageSubmissionRepository(session),
            _context(),
            _source(),
            idempotency_key=f"tampered-{field}",
            intent_hash="a" * 64,
            source_draft_locator="source-locator:one",
            now=NOW,
        )
        row = await session.get(ProductPackageDraftRow, result.draft.draft_id)
        assert row is not None
        setattr(row, field, value)
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyProductPackageSubmissionRepository(session)
        with pytest.raises(ProductPackageSubmissionConflictError, match=code):
            await repo.get(
                draft_id=result.draft.draft_id,
                tenant_scope="tenant-a",
            )
        if field == "request_hash":
            with pytest.raises(ProductPackageSubmissionConflictError, match=code):
                await repo.find_intent_replay(
                    tenant_scope="tenant-a",
                    actor_id="human:product-owner",
                    idempotency_key=f"tampered-{field}",
                    intent_hash="a" * 64,
                )
    await engine.dispose()


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_draft_task_and_audit(monkeypatch) -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        monkeypatch.setattr(session, "commit", AsyncMock(side_effect=RuntimeError("commit-down")))
        with pytest.raises(RuntimeError, match="commit-down"):
            await submit_product_package_draft(
                SqlAlchemyProductPackageSubmissionRepository(session),
                _context(),
                _source(),
                idempotency_key="commit-failure",
                now=NOW,
            )

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProductPackageDraftRow)) == 0
        assert await session.scalar(select(func.count()).select_from(HumanTaskRow)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEventRow)) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_draft_and_nested_proposal_arguments_are_immutable() -> None:
    engine, factory = await _factory()
    async with factory() as session:
        await _seed(session)
        result = await submit_product_package_draft(
            SqlAlchemyProductPackageSubmissionRepository(session),
            _context(),
            _source(),
            idempotency_key="immutable",
            now=NOW,
        )
    await engine.dispose()

    with pytest.raises(ValidationError):
        result.draft.duration_days = 90
    with pytest.raises(ValidationError):
        result.draft.evidence_admissions[0].claim_type = "GROWTH_EFFECT"
    with pytest.raises(TypeError):
        result.task.proposal.action_arguments["duration_days"] = 90
    component_ids = result.task.proposal.action_arguments["component_ids"]
    assert isinstance(component_ids, tuple)
    with pytest.raises(TypeError):
        component_ids[0] = "component:forged"


def test_duplicate_refs_are_rejected() -> None:
    with pytest.raises(ProductPackageSubmissionError, match="MUST_BE_UNIQUE"):
        # Validation occurs before any repository call in the actual command.
        from ..application.product_package_submission import _refs

        _refs(("component:one", "component:one"), "COMPONENT_IDS_REQUIRED")


@pytest.mark.asyncio
async def test_identity_and_idempotency_lengths_fail_before_repository_access() -> None:
    context = _context()
    unreachable_repo = cast(ProductPackageSubmissionRepository, object())
    with pytest.raises(ProductPackageSubmissionError, match="ACTOR_ID_REQUIRED_TOO_LONG"):
        await submit_product_package_draft(
            unreachable_repo,
            replace(context, actor_id="a" * 129),
            _source(),
            idempotency_key="valid",
            now=NOW,
        )
    with pytest.raises(ProductPackageSubmissionError, match="IDEMPOTENCY_KEY_REQUIRED_TOO_LONG"):
        await submit_product_package_draft(
            unreachable_repo,
            context,
            _source(),
            idempotency_key="k" * 257,
            now=NOW,
        )
