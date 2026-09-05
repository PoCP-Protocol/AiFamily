"""Durable metadata-only audit sink for Experience operations access.

The operator query facade records an access decision before returning data.  This
adapter keeps that record durable without reusing the family/domain audit shape:
an operations query is platform metadata, has no family subject, and must never
persist an outbox payload, model output, token, or credential.  The caller owns
the transaction; ``record`` only adds and flushes the row.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.operations_query import (
    ExperienceOperationsAuditEvent,
)


class ExperienceOperationsAuditPersistenceError(ValueError):
    """Raised when an operations access event cannot be safely persisted."""


class ExperienceOperationsAuditPersistenceBase(DeclarativeBase):
    """Metadata boundary for the operations audit table."""


class ExperienceOperationsAuditRow(ExperienceOperationsAuditPersistenceBase):
    """Append-only operator access metadata; never stores query contents."""

    __tablename__ = "ai_experience_operations_audit"
    __table_args__ = (
        Index(
            "ix_ai_experience_operations_audit_environment_time",
            "environment",
            "occurred_at",
        ),
        Index(
            "ix_ai_experience_operations_audit_operator_time",
            "operator_id",
            "occurred_at",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    authorization_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _validate_event(event: ExperienceOperationsAuditEvent) -> None:
    if not isinstance(event, ExperienceOperationsAuditEvent):
        raise ExperienceOperationsAuditPersistenceError("OPERATIONS_AUDIT_EVENT_INVALID")
    required = {
        "operator_id": event.operator_id,
        "authorization_ref": event.authorization_ref,
        "environment": event.environment,
        "operation": event.operation,
        "outcome": event.outcome,
    }
    if any(not isinstance(value, str) or not value.strip() for value in required.values()):
        raise ExperienceOperationsAuditPersistenceError("OPERATIONS_AUDIT_METADATA_INVALID")
    if event.environment not in {"staging", "production"}:
        raise ExperienceOperationsAuditPersistenceError("OPERATIONS_AUDIT_ENVIRONMENT_INVALID")
    if event.outcome not in {"ALLOWED", "DENIED", "IDENTITY_ERROR"}:
        raise ExperienceOperationsAuditPersistenceError("OPERATIONS_AUDIT_OUTCOME_INVALID")
    if event.occurred_at.tzinfo is None:
        raise ExperienceOperationsAuditPersistenceError(
            "OPERATIONS_AUDIT_TIMESTAMP_TIMEZONE_REQUIRED"
        )


def _stored(row: ExperienceOperationsAuditRow) -> ExperienceOperationsAuditEvent:
    occurred_at = row.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return ExperienceOperationsAuditEvent(
        operator_id=row.operator_id,
        authorization_ref=row.authorization_ref,
        environment=row.environment,
        operation=row.operation,
        outcome=row.outcome,
        occurred_at=occurred_at,
    )


class SqlAlchemyExperienceOperationsAuditSink:
    """SQL sink that flushes into the caller-owned transaction and never commits."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        event_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._session = session
        self._event_id_factory = event_id_factory or (lambda: uuid4().hex)

    async def record(self, event: ExperienceOperationsAuditEvent) -> None:
        _validate_event(event)
        event_id = self._event_id_factory()
        if not isinstance(event_id, str) or not event_id.strip():
            raise ExperienceOperationsAuditPersistenceError("OPERATIONS_AUDIT_EVENT_ID_INVALID")
        self._session.add(
            ExperienceOperationsAuditRow(
                event_id=event_id,
                operator_id=event.operator_id,
                authorization_ref=event.authorization_ref,
                environment=event.environment,
                operation=event.operation,
                outcome=event.outcome,
                occurred_at=event.occurred_at,
            )
        )
        await self._session.flush()

    async def list_events(
        self,
        *,
        limit: int = 100,
        operator_id: str | None = None,
        environment: str | None = None,
    ) -> Sequence[ExperienceOperationsAuditEvent]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ExperienceOperationsAuditPersistenceError("OPERATIONS_AUDIT_LIMIT_INVALID")
        statement = (
            select(ExperienceOperationsAuditRow)
            .order_by(
                ExperienceOperationsAuditRow.occurred_at,
                ExperienceOperationsAuditRow.event_id,
            )
            .limit(limit)
        )
        if operator_id is not None:
            statement = statement.where(ExperienceOperationsAuditRow.operator_id == operator_id)
        if environment is not None:
            statement = statement.where(ExperienceOperationsAuditRow.environment == environment)
        result = await self._session.execute(statement)
        return tuple(_stored(row) for row in result.scalars())


class SqlAlchemyExperienceOperationsAuditSessionSink:
    """Request-independent sink that commits one audit transaction per event.

    Operator queries are read operations and do not share a business mutation
    transaction.  This adapter gives the authorization decision its own short
    transaction, committing it before the query facade can return metadata.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("experience operations audit session factory is required")
        self._session_factory = session_factory

    async def record(self, event: ExperienceOperationsAuditEvent) -> None:
        async with self._session_factory() as session, session.begin():
            await SqlAlchemyExperienceOperationsAuditSink(session).record(event)


__all__ = [
    "ExperienceOperationsAuditPersistenceBase",
    "ExperienceOperationsAuditPersistenceError",
    "ExperienceOperationsAuditRow",
    "SqlAlchemyExperienceOperationsAuditSink",
    "SqlAlchemyExperienceOperationsAuditSessionSink",
]
