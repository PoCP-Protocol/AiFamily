from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    GateScope,
    NamedActionRequest,
)
from backend.intelligence.human_gate.persistence import HumanGateBase, SqlAlchemyHumanGate
from backend.platform.audit import AuditBase, AuditEventRow, AuditRecorder, read_all_events

from ..application.evidence_verification import (
    EVIDENCE_VERIFICATION_MAX_VALIDITY,
    EVIDENCE_VERIFICATION_POLICY_VERSION,
    EVIDENCE_VERIFICATION_PROCESSING_BASIS,
    EVIDENCE_VERIFICATION_PURPOSE,
    VERIFY_PRODUCT_EVIDENCE_ACTION,
    VERIFY_PRODUCT_EVIDENCE_PERMISSION,
    EvidenceVerificationArguments,
    evidence_record_hash,
    execute_evidence_verification_named_action,
)
from ..domain.entities import Evidence
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceForbiddenError,
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from ..infrastructure.evidence_verification_repository import (
    EvidenceVerificationReceiptRow,
    SqlAlchemyEvidenceVerificationReceiptRepository,
)
from ..infrastructure.sqlalchemy_models import Base as ProductBase
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


class _Authorizer:
    def __init__(self, allowed: bool = True):
        self.allowed = allowed

    async def is_allowed(self, *, actor_id: str, tenant_scope: str, permission: str) -> bool:
        assert actor_id == "operator:evidence-reviewer"
        assert tenant_scope == "tenant-a"
        assert permission == VERIFY_PRODUCT_EVIDENCE_PERMISSION
        return self.allowed


def _evidence(*, created_by: str = "human:researcher", status: str = "ACTIVE") -> Evidence:
    return Evidence(
        id="evidence:one",
        version=3,
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=1),
        created_by=created_by,
        tenant_scope="tenant-a",
        status=status,
        description="匿名访谈记录显示家长理解方法后仍难以持续行动",
        evidence_ref="source:interview:redacted:one",
    )


def _arguments(evidence: Evidence, **changes: object) -> EvidenceVerificationArguments:
    values: dict[str, object] = {
        "evidence_id": evidence.id,
        "evidence_version": evidence.version,
        "evidence_record_hash": evidence_record_hash(evidence),
        "evidence_ref": evidence.evidence_ref,
        "claim_scope": ("访谈仅支持行动持续性困难这一主张",),
        "verification_methods": (
            "SOURCE_OPENED",
            "IDENTITY_CONFIRMED",
            "EVIDENCE_RECORD_HASH_MATCHED",
        ),
        "applicability_scope": ("匿名家长访谈", "家庭行动支持产品研究"),
        "criteria_refs": ("evidence-policy:source-integrity:v1",),
        "verification_purpose": "product_package_admission",
        "verification_policy_version": EVIDENCE_VERIFICATION_POLICY_VERSION,
        "integrity_check": "PASS",
        "relevance": "RELEVANT",
        "valid_until": NOW + timedelta(days=30),
    }
    values.update(changes)
    return EvidenceVerificationArguments.model_validate(values)


async def _factory() -> tuple[object, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ProductBase.metadata.create_all)
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_evidence(session: AsyncSession, evidence: Evidence) -> None:
    await SqlAlchemyProductIntelligenceRepository(session).save_evidence(evidence)
    await session.commit()


async def _accepted_request(
    session: AsyncSession,
    evidence: Evidence,
    *,
    reason: str = "已核对脱敏来源、身份和内容哈希；结论仅适用于所列主张",
    argument_changes: dict[str, object] | None = None,
) -> NamedActionRequest:
    arguments = _arguments(evidence, **(argument_changes or {}))
    proposal = ActionProposal(
        proposal_id="proposal:evidence-verification:one",
        draft_id="draft:evidence-verification:one",
        draft_status="DRAFT",
        action_name=VERIFY_PRODUCT_EVIDENCE_ACTION,
        action_arguments=arguments.model_dump(mode="json"),
        scope=GateScope(
            tenant_id="tenant-a",
            family_id=None,
            subject_ids=(evidence.id,),
            purpose=EVIDENCE_VERIFICATION_PURPOSE,
            consent_version=EVIDENCE_VERIFICATION_PROCESSING_BASIS,
            correlation_id="trace:evidence-verification:one",
        ),
        allowed_actor_types=(ActorType.OPERATOR,),
        risk_level="MEDIUM",
        provenance_ref=(
            f"evidence-record-snapshot:{evidence.id}:{arguments.evidence_record_hash}"
        ),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )
    gate = SqlAlchemyHumanGate(session)
    recorder = AuditRecorder()
    task = await gate.submit(
        proposal,
        recorder=recorder,
        task_id="human-task:evidence-verification:one",
    )
    decided, request = await gate.decide(
        task.task_id,
        actor_id="operator:evidence-reviewer",
        actor_type=ActorType.OPERATOR,
        outcome="ACCEPT",
        reason=reason,
        decision_id="decision:evidence-verification:one",
        now=NOW + timedelta(hours=1),
        recorder=recorder,
    )
    assert decided.action_request is not None
    assert request is not None
    await recorder.flush(session)
    await session.commit()
    return request


@pytest.mark.asyncio
async def test_accepted_human_gate_action_creates_immutable_verification_receipt() -> None:
    engine, factory = await _factory()
    evidence = _evidence()
    async with factory() as session:
        await _seed_evidence(session, evidence)
        request = await _accepted_request(session, evidence)
        receipt, replayed = await execute_evidence_verification_named_action(
            SqlAlchemyEvidenceVerificationReceiptRepository(session),
            request,
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
            now=NOW + timedelta(hours=2),
        )

    async with factory() as session:
        persisted = await SqlAlchemyEvidenceVerificationReceiptRepository(
            session
        ).load_receipt(receipt.receipt_id, "tenant-a")
        events = await read_all_events(session)
    await engine.dispose()

    assert replayed is False
    assert persisted == receipt
    assert receipt.outcome == "VERIFIED"
    assert receipt.integrity_check == "PASS"
    assert receipt.relevance == "RELEVANT"
    assert receipt.evidence_version == 3
    assert receipt.verifier_actor_id == "operator:evidence-reviewer"
    assert receipt.verified_at == NOW + timedelta(hours=1)
    assert receipt.lifecycle_at(NOW + timedelta(days=29)) == "ACTIVE"
    assert receipt.lifecycle_at(NOW + timedelta(days=30)) == "EXPIRED"
    with pytest.raises(ValidationError):
        receipt.outcome = "REJECTED"
    assert [event.action for event in events] == [
        "CREATE_HUMAN_TASK",
        "DECIDE_HUMAN_TASK",
        "CREATE_EVIDENCE_VERIFICATION_RECEIPT",
    ]


@pytest.mark.asyncio
async def test_exact_replay_returns_receipt_after_source_changes_without_new_audit() -> None:
    engine, factory = await _factory()
    evidence = _evidence()
    async with factory() as session:
        await _seed_evidence(session, evidence)
        request = await _accepted_request(session, evidence)
        repo = SqlAlchemyEvidenceVerificationReceiptRepository(session)
        first, _ = await execute_evidence_verification_named_action(
            repo,
            request,
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
            now=NOW + timedelta(hours=2),
        )
        await SqlAlchemyProductIntelligenceRepository(session).save_evidence(
            evidence.model_copy(
                update={"status": "RETIRED", "version": 4, "updated_at": NOW + timedelta(days=1)}
            )
        )
        await session.commit()
        replay, replayed = await execute_evidence_verification_named_action(
            repo,
            request,
            human_actor_authorizer=_Authorizer(allowed=False),
            recorder=AuditRecorder(),
            now=NOW + timedelta(days=31),
        )
        events = await read_all_events(session)
    await engine.dispose()

    assert replayed is True
    assert replay == first
    assert len(events) == 3


@pytest.mark.asyncio
async def test_permission_four_eyes_snapshot_and_policy_window_fail_closed() -> None:
    engine, factory = await _factory()
    evidence = _evidence()
    async with factory() as session:
        await _seed_evidence(session, evidence)
        request = await _accepted_request(session, evidence)
        repo = SqlAlchemyEvidenceVerificationReceiptRepository(session)
        with pytest.raises(ProductIntelligenceForbiddenError, match="permission_required"):
            await execute_evidence_verification_named_action(
                repo,
                request,
                human_actor_authorizer=_Authorizer(allowed=False),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2),
            )

        await SqlAlchemyProductIntelligenceRepository(session).save_evidence(
            evidence.model_copy(update={"created_by": "operator:evidence-reviewer"})
        )
        await session.commit()
        with pytest.raises(ProductIntelligenceForbiddenError, match="four_eyes"):
            await execute_evidence_verification_named_action(
                repo,
                request,
                human_actor_authorizer=_Authorizer(),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2),
            )

        await SqlAlchemyProductIntelligenceRepository(session).save_evidence(
            evidence.model_copy(update={"description": "source changed", "updated_at": NOW})
        )
        await session.commit()
        with pytest.raises(ProductIntelligenceConflictError, match="snapshot_changed"):
            await execute_evidence_verification_named_action(
                repo,
                request,
                human_actor_authorizer=_Authorizer(),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2),
            )

        await SqlAlchemyProductIntelligenceRepository(session).save_evidence(evidence)
        await session.commit()
        with pytest.raises(ProductIntelligenceConflictError, match="policy_window_expired"):
            await execute_evidence_verification_named_action(
                repo,
                request,
                human_actor_authorizer=_Authorizer(),
                recorder=AuditRecorder(),
                now=NOW + timedelta(days=31),
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_named_action_must_match_persisted_accepted_task_and_reason() -> None:
    engine, factory = await _factory()
    evidence = _evidence()
    async with factory() as session:
        await _seed_evidence(session, evidence)
        request = await _accepted_request(session, evidence)
        forged = replace(request, proposal_id="proposal:forged")
        with pytest.raises(ProductIntelligenceConflictError, match="lineage_mismatch"):
            await execute_evidence_verification_named_action(
                SqlAlchemyEvidenceVerificationReceiptRepository(session),
                forged,
                human_actor_authorizer=_Authorizer(),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2),
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_receipt_read_is_tenant_scoped_and_detects_payload_tampering() -> None:
    engine, factory = await _factory()
    evidence = _evidence()
    async with factory() as session:
        await _seed_evidence(session, evidence)
        request = await _accepted_request(session, evidence)
        repo = SqlAlchemyEvidenceVerificationReceiptRepository(session)
        receipt, _ = await execute_evidence_verification_named_action(
            repo,
            request,
            human_actor_authorizer=_Authorizer(),
            recorder=AuditRecorder(),
            now=NOW + timedelta(hours=2),
        )
        with pytest.raises(ProductIntelligenceNotFoundError):
            await repo.load_receipt(receipt.receipt_id, "tenant-b")
        row = await session.get(EvidenceVerificationReceiptRow, receipt.receipt_id)
        assert row is not None
        payload = dict(row.payload)
        payload["claim_scope"] = ["tampered claim"]
        row.payload = payload
        await session.commit()

    async with factory() as session:
        with pytest.raises(
            ProductIntelligenceValidationError,
            match="receipt_hash_mismatch",
        ):
            await SqlAlchemyEvidenceVerificationReceiptRepository(session).load_receipt(
                receipt.receipt_id,
                "tenant-a",
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_receipt_and_its_audit() -> None:
    engine, factory = await _factory()
    evidence = _evidence()
    async with factory() as session:
        await _seed_evidence(session, evidence)
        request = await _accepted_request(session, evidence)
        repo = SqlAlchemyEvidenceVerificationReceiptRepository(session)
        repo.commit = AsyncMock(side_effect=RuntimeError("commit-down"))
        with pytest.raises(RuntimeError, match="commit-down"):
            await execute_evidence_verification_named_action(
                repo,
                request,
                human_actor_authorizer=_Authorizer(),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2),
            )

    async with factory() as session:
        receipt_count = await session.scalar(
            select(func.count()).select_from(EvidenceVerificationReceiptRow)
        )
        receipt_audits = await session.scalar(
            select(func.count())
            .select_from(AuditEventRow)
            .where(AuditEventRow.action == "CREATE_EVIDENCE_VERIFICATION_RECEIPT")
        )
    await engine.dispose()

    assert receipt_count == 0
    assert receipt_audits == 0


def test_verification_arguments_require_source_and_hash_checks() -> None:
    evidence = _evidence()
    with pytest.raises(ValidationError, match="missing_integrity_checks"):
        _arguments(evidence, verification_methods=("SOURCE_OPENED",))


def test_verification_arguments_reject_unimplemented_supersession() -> None:
    with pytest.raises(ValidationError, match="supersedes_receipt_id"):
        _arguments(_evidence(), supersedes_receipt_id="receipt:untrusted")


@pytest.mark.asyncio
async def test_server_policy_rejects_unrecognized_policy_and_excessive_validity() -> None:
    engine, factory = await _factory()
    evidence = _evidence()
    async with factory() as session:
        await _seed_evidence(session, evidence)
        wrong_policy = await _accepted_request(
            session,
            evidence,
            argument_changes={"verification_policy_version": "client-policy:v999"},
        )
        with pytest.raises(ProductIntelligenceForbiddenError, match="scope_invalid"):
            await execute_evidence_verification_named_action(
                SqlAlchemyEvidenceVerificationReceiptRepository(session),
                wrong_policy,
                human_actor_authorizer=_Authorizer(),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2),
            )

    engine2, factory2 = await _factory()
    async with factory2() as session:
        await _seed_evidence(session, evidence)
        overlong = await _accepted_request(
            session,
            evidence,
            argument_changes={
                "valid_until": NOW
                + timedelta(hours=1)
                + EVIDENCE_VERIFICATION_MAX_VALIDITY
                + timedelta(seconds=1)
            },
        )
        with pytest.raises(ProductIntelligenceConflictError, match="exceeds_maximum"):
            await execute_evidence_verification_named_action(
                SqlAlchemyEvidenceVerificationReceiptRepository(session),
                overlong,
                human_actor_authorizer=_Authorizer(),
                recorder=AuditRecorder(),
                now=NOW + timedelta(hours=2),
            )
    await engine.dispose()
    await engine2.dispose()
