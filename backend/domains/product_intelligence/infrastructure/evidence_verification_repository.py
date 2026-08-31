"""SQL persistence for immutable evidence-verification receipts."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Integer, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.intelligence.human_gate.errors import HumanGateError
from backend.intelligence.human_gate.persistence import SqlAlchemyHumanGate
from backend.platform.audit import AuditRecorder

from ..application.evidence_verification import EvidenceVerificationReceiptRepository
from ..domain.entities import Evidence
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceNotFoundError,
)
from ..domain.evidence_verification import EvidenceVerificationReceipt
from . import sqlalchemy_models as product_models
from .sqlalchemy_models import Base, DateTime


class EvidenceVerificationReceiptRow(Base):
    __tablename__ = "product_intelligence_evidence_verification_receipts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_scope",
            "decision_id",
            name="uq_evidence_verification_receipt_decision",
        ),
    )

    receipt_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    tenant_scope: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    evidence_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    task_id: Mapped[str] = mapped_column(String(160), nullable=False)
    proposal_id: Mapped[str] = mapped_column(String(160), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(160), nullable=False)
    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    verifier_actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _receipt(row: EvidenceVerificationReceiptRow) -> EvidenceVerificationReceipt:
    receipt = EvidenceVerificationReceipt.model_validate(row.payload)
    if (
        row.receipt_id != receipt.receipt_id
        or row.tenant_scope != receipt.tenant_scope
        or row.evidence_id != receipt.evidence_id
        or row.evidence_version != receipt.evidence_version
        or row.evidence_record_hash != receipt.evidence_record_hash
        or row.task_id != receipt.task_id
        or row.proposal_id != receipt.proposal_id
        or row.decision_id != receipt.decision_id
        or row.request_id != receipt.request_id
        or row.verifier_actor_id != receipt.verifier_actor_id
        or _utc(row.verified_at) != _utc(receipt.verified_at)
        or _utc(row.valid_until) != _utc(receipt.valid_until)
        or row.request_hash != receipt.request_hash
        or row.receipt_hash != receipt.receipt_hash
    ):
        raise ProductIntelligenceConflictError(
            "evidence_verification_persisted_lineage_mismatch"
        )
    return receipt


class SqlAlchemyEvidenceVerificationReceiptRepository(
    EvidenceVerificationReceiptRepository
):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._gate = SqlAlchemyHumanGate(session)

    async def load_evidence(self, entity_id: str, tenant_scope: str) -> Evidence:
        row = await self._session.scalar(
            select(product_models.EvidenceRow).where(
                product_models.EvidenceRow.id == entity_id,
                product_models.EvidenceRow.tenant_scope == tenant_scope,
            )
        )
        if row is None:
            raise ProductIntelligenceNotFoundError("evidence_not_found")
        return Evidence(
            id=row.id,
            version=row.version,
            created_at=_utc(row.created_at),
            updated_at=_utc(row.updated_at),
            created_by=row.created_by,
            tenant_scope=row.tenant_scope,
            status=row.status,
            description=row.description,
            evidence_ref=row.evidence_ref,
        )

    async def load_human_task(self, task_id: str):
        try:
            return await self._gate.get(task_id)
        except HumanGateError as exc:
            if exc.code == "TASK_NOT_FOUND":
                raise ProductIntelligenceNotFoundError(
                    "evidence_verification_task_not_found"
                ) from exc
            raise ProductIntelligenceConflictError(
                "evidence_verification_task_shape_invalid"
            ) from exc

    async def load_receipt(
        self, receipt_id: str, tenant_scope: str
    ) -> EvidenceVerificationReceipt:
        row = await self._session.scalar(
            select(EvidenceVerificationReceiptRow).where(
                EvidenceVerificationReceiptRow.receipt_id == receipt_id,
                EvidenceVerificationReceiptRow.tenant_scope == tenant_scope,
            )
        )
        if row is None:
            raise ProductIntelligenceNotFoundError(
                "evidence_verification_receipt_not_found"
            )
        return _receipt(row)

    async def _load_by_decision(
        self, *, tenant_scope: str, decision_id: str
    ) -> EvidenceVerificationReceipt | None:
        row = await self._session.scalar(
            select(EvidenceVerificationReceiptRow).where(
                EvidenceVerificationReceiptRow.tenant_scope == tenant_scope,
                EvidenceVerificationReceiptRow.decision_id == decision_id,
            )
        )
        return _receipt(row) if row is not None else None

    async def create_receipt_if_absent(
        self, receipt: EvidenceVerificationReceipt
    ) -> tuple[EvidenceVerificationReceipt, bool]:
        try:
            existing = await self.load_receipt(receipt.receipt_id, receipt.tenant_scope)
        except ProductIntelligenceNotFoundError:
            existing = None
        if existing is not None:
            return existing, False
        by_decision = await self._load_by_decision(
            tenant_scope=receipt.tenant_scope,
            decision_id=receipt.decision_id,
        )
        if by_decision is not None:
            return by_decision, False
        self._session.add(
            EvidenceVerificationReceiptRow(
                receipt_id=receipt.receipt_id,
                tenant_scope=receipt.tenant_scope,
                evidence_id=receipt.evidence_id,
                evidence_version=receipt.evidence_version,
                evidence_record_hash=receipt.evidence_record_hash,
                task_id=receipt.task_id,
                proposal_id=receipt.proposal_id,
                decision_id=receipt.decision_id,
                request_id=receipt.request_id,
                verifier_actor_id=receipt.verifier_actor_id,
                verified_at=receipt.verified_at,
                valid_until=receipt.valid_until,
                request_hash=receipt.request_hash,
                receipt_hash=receipt.receipt_hash,
                payload=receipt.model_dump(mode="json"),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            concurrent = await self._load_by_decision(
                tenant_scope=receipt.tenant_scope,
                decision_id=receipt.decision_id,
            )
            if concurrent is None:
                raise ProductIntelligenceConflictError(
                    "evidence_verification_concurrent_write_conflict"
                ) from exc
            return concurrent, False
        return receipt, True

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        return await recorder.flush(self._session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


__all__ = [
    "EvidenceVerificationReceiptRow",
    "SqlAlchemyEvidenceVerificationReceiptRepository",
]
