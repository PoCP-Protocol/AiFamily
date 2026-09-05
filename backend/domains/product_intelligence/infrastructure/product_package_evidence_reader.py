"""SQL reader for receipt-backed ProductPackage evidence admission."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.product_package_evidence_admission import ProductPackageEvidenceReader
from ..domain.entities import Evidence
from ..domain.errors import ProductIntelligenceNotFoundError
from ..domain.evidence_verification import EvidenceVerificationReceipt
from . import sqlalchemy_models as product_models
from .evidence_verification_repository import (
    SqlAlchemyEvidenceVerificationReceiptRepository,
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqlAlchemyProductPackageEvidenceReader(ProductPackageEvidenceReader):
    def __init__(self, session: AsyncSession, *, lock_evidence: bool = False) -> None:
        self._session = session
        self._lock_evidence = lock_evidence
        self._receipts = SqlAlchemyEvidenceVerificationReceiptRepository(session)

    async def load_receipt(
        self,
        receipt_id: str,
        tenant_scope: str,
    ) -> EvidenceVerificationReceipt:
        return await self._receipts.load_receipt(receipt_id, tenant_scope)

    async def load_evidence(self, entity_id: str, tenant_scope: str) -> Evidence:
        statement = select(product_models.EvidenceRow).where(
            product_models.EvidenceRow.id == entity_id,
            product_models.EvidenceRow.tenant_scope == tenant_scope,
        )
        if self._lock_evidence:
            statement = statement.with_for_update()
        row = await self._session.scalar(statement)
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


__all__ = ["SqlAlchemyProductPackageEvidenceReader"]
