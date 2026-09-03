"""SQLAlchemy adapter for the adult contribution ledger.

The tables are intentionally isolated from the existing points models.  This
module supplies the production-shaped adapter and ORM metadata; a governed
Alembic migration is still required before deployment to the canonical
database.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base

from ..domain.contribution import (
    ContributionAuditEvent,
    ContributionNotFoundError,
    ContributionOperation,
    ContributionOutboxEvent,
    ContributionRecord,
    PlatformPoint,
)

ContributionBase = declarative_base()


class ContributionRecordRow(ContributionBase):
    __tablename__ = "family_contribution_records"

    contribution_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    contributor_family_id = Column(String(64), nullable=False)
    contributor_person_id = Column(String(64), nullable=False)
    contributor_is_adult = Column(Boolean, nullable=False)
    adult_verification_ref = Column(String(255), nullable=False)
    consumer_family_id = Column(String(64), nullable=False)
    content_ref = Column(String(255), nullable=False)
    content_type = Column(String(32), nullable=False)
    content_version = Column(Integer, nullable=False)
    purpose = Column(String(128), nullable=False)
    copyright_attestation_ref = Column(String(255), nullable=False)
    privacy_redaction_ref = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    review_ref = Column(String(255), nullable=True)
    reviewed_by = Column(String(64), nullable=True)
    use_confirmation_ref = Column(String(255), nullable=True)
    use_confirmed_by = Column(String(64), nullable=True)
    hold_reason = Column(Text, nullable=True)
    release_ref = Column(String(255), nullable=True)
    platform_point_entry_id = Column(String(64), nullable=True)
    appeal_ref = Column(String(255), nullable=True)
    appeal_reason = Column(Text, nullable=True)
    reversal_ref = Column(String(255), nullable=True)
    decision_code = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "contribution_id",
            name="uq_contribution_record_tenant_id",
        ),
    )


class ContributionOperationRow(ContributionBase):
    __tablename__ = "family_contribution_operations"

    operation_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    family_id = Column(String(64), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    action = Column(String(64), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "family_id",
            "idempotency_key",
            name="uq_contribution_operation_scope_key",
        ),
    )


class ContributionAuditEventRow(ContributionBase):
    __tablename__ = "family_contribution_audit_events"

    event_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    family_id = Column(String(64), nullable=False)
    actor_person_id = Column(String(64), nullable=False)
    actor = Column(String(128), nullable=False)
    action = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=False)
    before_status = Column(String(32), nullable=True)
    after_status = Column(String(32), nullable=False)
    reason_code = Column(String(128), nullable=False)
    correlation_id = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class ContributionOutboxEventRow(ContributionBase):
    __tablename__ = "family_contribution_outbox"

    event_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    family_id = Column(String(64), nullable=False)
    aggregate_id = Column(String(64), nullable=False)
    event_type = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    correlation_id = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class PlatformPointRow(ContributionBase):
    __tablename__ = "family_contribution_platform_points"

    entry_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    family_id = Column(String(64), nullable=False)
    contribution_id = Column(String(64), nullable=False)
    points_delta = Column(Integer, nullable=False)
    reward_basis = Column(String(64), nullable=False)
    reversal_of_entry_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


def _record_to_row(record: ContributionRecord) -> ContributionRecordRow:
    values = record.model_dump(mode="python")
    return ContributionRecordRow(**values)


def _row_to_record(row: ContributionRecordRow) -> ContributionRecord:
    values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    return ContributionRecord.model_validate(values)


class SqlAlchemyContributionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def checkpoint(self) -> None:
        # SQLAlchemy's session transaction is opened by the first write/query.
        # Commands call rollback on failure; no nested begin is introduced here.
        return None

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def save_record(self, record: ContributionRecord) -> None:
        await self._session.merge(_record_to_row(record))

    async def get_record(self, tenant_id: str, contribution_id: str) -> ContributionRecord:
        row = await self._session.get(ContributionRecordRow, contribution_id)
        if row is None or row.tenant_id != tenant_id:
            raise ContributionNotFoundError("contribution_not_found")
        return _row_to_record(row)

    async def find_operation(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> ContributionOperation | None:
        result = await self._session.execute(
            select(ContributionOperationRow).where(
                ContributionOperationRow.tenant_id == tenant_id,
                ContributionOperationRow.family_id == family_id,
                ContributionOperationRow.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return ContributionOperation.model_validate(
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
        )

    async def save_operation(self, operation: ContributionOperation) -> None:
        await self._session.merge(ContributionOperationRow(**operation.model_dump(mode="python")))

    async def append_audit(self, event: ContributionAuditEvent) -> None:
        values = event.model_dump(mode="python")
        values["before_status"] = (
            event.before_status.value if event.before_status is not None else None
        )
        values["after_status"] = event.after_status.value
        self._session.add(ContributionAuditEventRow(**values))

    async def append_outbox(self, event: ContributionOutboxEvent) -> None:
        self._session.add(ContributionOutboxEventRow(**event.model_dump(mode="python")))

    async def append_platform_point(self, entry: PlatformPoint) -> None:
        self._session.add(PlatformPointRow(**entry.model_dump(mode="python")))

    async def list_audits(
        self, tenant_id: str, contribution_id: str
    ) -> list[ContributionAuditEvent]:
        result = await self._session.execute(
            select(ContributionAuditEventRow)
            .where(
                ContributionAuditEventRow.tenant_id == tenant_id,
                ContributionAuditEventRow.resource_id == contribution_id,
            )
            .order_by(ContributionAuditEventRow.created_at)
        )
        return [
            ContributionAuditEvent.model_validate(
                {
                    **{column.name: getattr(row, column.name) for column in row.__table__.columns},
                    "before_status": row.before_status,
                    "after_status": row.after_status,
                }
            )
            for row in result.scalars()
        ]

    async def list_outbox(
        self, tenant_id: str, contribution_id: str
    ) -> list[ContributionOutboxEvent]:
        result = await self._session.execute(
            select(ContributionOutboxEventRow)
            .where(
                ContributionOutboxEventRow.tenant_id == tenant_id,
                ContributionOutboxEventRow.aggregate_id == contribution_id,
            )
            .order_by(ContributionOutboxEventRow.created_at)
        )
        return [
            ContributionOutboxEvent.model_validate(
                {column.name: getattr(row, column.name) for column in row.__table__.columns}
            )
            for row in result.scalars()
        ]

    async def list_platform_points(self, tenant_id: str, family_id: str) -> list[PlatformPoint]:
        result = await self._session.execute(
            select(PlatformPointRow)
            .where(
                PlatformPointRow.tenant_id == tenant_id,
                PlatformPointRow.family_id == family_id,
            )
            .order_by(PlatformPointRow.created_at)
        )
        return [
            PlatformPoint.model_validate(
                {column.name: getattr(row, column.name) for column in row.__table__.columns}
            )
            for row in result.scalars()
        ]
