"""Durable attempt ledger for accepted Named Action delivery.

Human Gate owns the review decision and its claim lease.  This adapter owns
only post-gate delivery metadata (attempt count, terminal state and opaque
result reference), so a worker restart can distinguish a completed action from
an action that still needs replay.  It never stores action arguments or model
output and never commits a transaction on behalf of its caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.human_gate.contracts import NamedActionRequest
from backend.intelligence.tool_runtime.accepted_dispatch import ActionExecutionReceipt


class AcceptedActionDeliveryError(ValueError):
    """Base error for invalid or conflicting delivery records."""


class AcceptedActionDeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    DEAD_LETTERED = "DEAD_LETTERED"


@dataclass(frozen=True, slots=True)
class AcceptedActionDelivery:
    request_id: str
    task_id: str
    action_name: str
    tenant_id: str
    family_id: str | None
    attempts: int
    status: AcceptedActionDeliveryStatus
    last_error: str | None
    result_ref: str | None
    created_at: datetime
    updated_at: datetime
    dead_lettered_at: datetime | None = None


class AcceptedActionDeliveryBase(DeclarativeBase):
    """Metadata-only SQL model for post-gate delivery state."""


class AcceptedActionDeliveryRow(AcceptedActionDeliveryBase):
    __tablename__ = "ai_accepted_action_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "task_id", name="uq_ai_accepted_action_delivery_task"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_ai_accepted_action_delivery_attempts"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SUCCEEDED', 'DEAD_LETTERED')",
            name="ck_ai_accepted_action_delivery_status",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    action_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AcceptedActionDeliveryStore(Protocol):
    async def get(self, request_id: str) -> AcceptedActionDelivery | None: ...

    async def begin_attempt(
        self, request: NamedActionRequest, *, now: datetime | None = None
    ) -> AcceptedActionDelivery: ...

    async def mark_succeeded(
        self,
        request: NamedActionRequest,
        receipt: ActionExecutionReceipt,
        *,
        now: datetime | None = None,
    ) -> AcceptedActionDelivery: ...

    async def mark_dead_lettered(
        self, request: NamedActionRequest, *, error: str, now: datetime | None = None
    ) -> AcceptedActionDelivery: ...

    async def list_dead_letters(
        self, *, limit: int = 100
    ) -> tuple[AcceptedActionDelivery, ...]: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class SqlAlchemyAcceptedActionDeliveryStore:
    """Async SQL adapter; transaction ownership remains with the worker root."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, request_id: str) -> AcceptedActionDelivery | None:
        row = await self._session.get(AcceptedActionDeliveryRow, request_id)
        return None if row is None else _stored(row)

    async def begin_attempt(
        self, request: NamedActionRequest, *, now: datetime | None = None
    ) -> AcceptedActionDelivery:
        current = _aware(now or datetime.now(UTC), "now")
        row = await self._session.get(AcceptedActionDeliveryRow, request.request_id)
        if row is not None:
            _assert_identity(row, request)
            status = AcceptedActionDeliveryStatus(row.status)
            if status is not AcceptedActionDeliveryStatus.PENDING:
                return _stored(row)
            row.attempts += 1
            row.updated_at = current
            await self._session.flush()
            return _stored(row)

        row = AcceptedActionDeliveryRow(
            request_id=request.request_id,
            task_id=request.task_id,
            action_name=request.action_name,
            tenant_id=request.scope.tenant_id,
            family_id=request.scope.family_id,
            attempts=1,
            status=AcceptedActionDeliveryStatus.PENDING.value,
            last_error=None,
            result_ref=None,
            created_at=current,
            updated_at=current,
        )
        self._session.add(row)
        await self._session.flush()
        return _stored(row)

    async def mark_succeeded(
        self,
        request: NamedActionRequest,
        receipt: ActionExecutionReceipt,
        *,
        now: datetime | None = None,
    ) -> AcceptedActionDelivery:
        if receipt.request_id != request.request_id or receipt.action_name != request.action_name:
            raise AcceptedActionDeliveryError("DELIVERY_RECEIPT_REQUEST_MISMATCH")
        row = await self._require(request)
        current = _aware(now or datetime.now(UTC), "now")
        status = AcceptedActionDeliveryStatus(row.status)
        if status is AcceptedActionDeliveryStatus.DEAD_LETTERED:
            raise AcceptedActionDeliveryError("DELIVERY_ALREADY_DEAD_LETTERED")
        if status is AcceptedActionDeliveryStatus.SUCCEEDED:
            if row.result_ref != receipt.result_ref:
                raise AcceptedActionDeliveryError("DELIVERY_SUCCESS_REPLAY_MISMATCH")
            return _stored(row)
        row.status = AcceptedActionDeliveryStatus.SUCCEEDED.value
        row.result_ref = receipt.result_ref
        row.last_error = None
        row.updated_at = current
        await self._session.flush()
        return _stored(row)

    async def mark_dead_lettered(
        self, request: NamedActionRequest, *, error: str, now: datetime | None = None
    ) -> AcceptedActionDelivery:
        if not isinstance(error, str) or not error.strip():
            raise AcceptedActionDeliveryError("DELIVERY_ERROR_REQUIRED")
        row = await self._require(request)
        current = _aware(now or datetime.now(UTC), "now")
        status = AcceptedActionDeliveryStatus(row.status)
        if status is AcceptedActionDeliveryStatus.SUCCEEDED:
            raise AcceptedActionDeliveryError("DELIVERY_ALREADY_SUCCEEDED")
        if status is AcceptedActionDeliveryStatus.DEAD_LETTERED:
            if row.last_error != error.strip():
                raise AcceptedActionDeliveryError("DELIVERY_DEAD_LETTER_REPLAY_MISMATCH")
            return _stored(row)
        row.status = AcceptedActionDeliveryStatus.DEAD_LETTERED.value
        row.last_error = error.strip()
        row.dead_lettered_at = current
        row.updated_at = current
        await self._session.flush()
        return _stored(row)

    async def list_dead_letters(self, *, limit: int = 100) -> tuple[AcceptedActionDelivery, ...]:
        if limit < 0:
            raise AcceptedActionDeliveryError("DELIVERY_LIMIT_INVALID")
        rows = await self._session.scalars(
            select(AcceptedActionDeliveryRow)
            .where(
                AcceptedActionDeliveryRow.status
                == AcceptedActionDeliveryStatus.DEAD_LETTERED.value
            )
            .order_by(
                AcceptedActionDeliveryRow.dead_lettered_at,
                AcceptedActionDeliveryRow.request_id,
            )
            .limit(limit)
        )
        return tuple(_stored(row) for row in rows)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def _require(self, request: NamedActionRequest) -> AcceptedActionDeliveryRow:
        row = await self._session.get(AcceptedActionDeliveryRow, request.request_id)
        if row is None:
            raise AcceptedActionDeliveryError("DELIVERY_ATTEMPT_NOT_STARTED")
        _assert_identity(row, request)
        return row


def _assert_identity(row: AcceptedActionDeliveryRow, request: NamedActionRequest) -> None:
    if (
        row.task_id != request.task_id
        or row.action_name != request.action_name
        or row.tenant_id != request.scope.tenant_id
        or row.family_id != request.scope.family_id
    ):
        raise AcceptedActionDeliveryError("DELIVERY_REQUEST_REPLAY_MISMATCH")


def _stored(row: AcceptedActionDeliveryRow) -> AcceptedActionDelivery:
    return AcceptedActionDelivery(
        request_id=row.request_id,
        task_id=row.task_id,
        action_name=row.action_name,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        attempts=row.attempts,
        status=AcceptedActionDeliveryStatus(row.status),
        last_error=row.last_error,
        result_ref=row.result_ref,
        created_at=_aware(row.created_at, "created_at"),
        updated_at=_aware(row.updated_at, "updated_at"),
        dead_lettered_at=(
            None
            if row.dead_lettered_at is None
            else _aware(row.dead_lettered_at, "dead_lettered_at")
        ),
    )


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        # SQLite strips tzinfo on round-trip; normalize it exactly as the
        # existing Human Gate persistence adapter does.
        return value.replace(tzinfo=UTC)
    return value


__all__ = [
    "AcceptedActionDelivery",
    "AcceptedActionDeliveryBase",
    "AcceptedActionDeliveryError",
    "AcceptedActionDeliveryRow",
    "AcceptedActionDeliveryStatus",
    "AcceptedActionDeliveryStore",
    "SqlAlchemyAcceptedActionDeliveryStore",
]
