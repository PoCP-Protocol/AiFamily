"""Metadata-only telemetry retention and deletion worker.

The telemetry schema calls its creation timestamp ``started_at``; this module
uses that column as the ``created_at``/TTL source and deletes spans only after
the configured cutoff.  No span payload is read, reconstructed, or sent to a
provider.  Both stores own only the telemetry table and flush through a
caller-owned transaction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .persistence import TelemetrySpanRow


@dataclass(frozen=True, slots=True)
class TelemetrySpanRecord:
    """Minimal metadata required by an in-memory retention adapter."""

    span_id: str
    started_at: datetime
    tenant_id: str | None = None
    family_id: str | None = None

    def __post_init__(self) -> None:
        if not self.span_id:
            raise ValueError("TELEMETRY_SPAN_ID_REQUIRED")
        if self.started_at.tzinfo is None:
            raise ValueError("TELEMETRY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")


@dataclass(frozen=True, slots=True)
class TelemetryDeletionReceipt:
    """Auditable result for one metadata-only span deletion."""

    receipt_id: str
    span_id: str
    started_at: datetime
    cutoff: datetime
    deleted_at: datetime
    tenant_id: str | None = None
    family_id: str | None = None


@dataclass(frozen=True, slots=True)
class TelemetryRetentionRun:
    """Bounded retention pass result; receipts contain no sensitive payload."""

    cutoff: datetime
    limit: int
    receipts: tuple[TelemetryDeletionReceipt, ...]
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def scanned(self) -> int:
        """Number of rows selected in this bounded pass."""

        return len(self.receipts)

    @property
    def deleted(self) -> int:
        """Alias used by metrics/reporting consumers."""

        return len(self.receipts)


class TelemetryRetentionStore(Protocol):
    """Provider-neutral, telemetry-table-only deletion port."""

    async def purge_before(
        self,
        cutoff: datetime,
        *,
        limit: int,
        deleted_at: datetime | None = None,
    ) -> tuple[TelemetryDeletionReceipt, ...]:
        """Delete at most ``limit`` spans older than ``cutoff``."""
        ...


class TelemetryDeletionAuditSink(Protocol):
    """Optional audit projection for deletion receipts."""

    async def record(self, receipts: tuple[TelemetryDeletionReceipt, ...]) -> None:
        """Persist receipts idempotently in the caller's transaction."""
        ...


class SqlAlchemyTelemetryRetentionStore:
    """SQL adapter that deletes only ``ai_telemetry_spans`` rows.

    ``purge_before`` flushes but never commits or closes the supplied session;
    callers can therefore atomically combine deletion and a durable audit
    receipt, or roll the whole batch back on failure.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def purge_before(
        self,
        cutoff: datetime,
        *,
        limit: int,
        deleted_at: datetime | None = None,
    ) -> tuple[TelemetryDeletionReceipt, ...]:
        _validate_cutoff(cutoff)
        _validate_limit(limit)
        if limit == 0:
            return ()
        result = await self._session.execute(
            select(TelemetrySpanRow)
            .where(TelemetrySpanRow.started_at < cutoff)
            .order_by(TelemetrySpanRow.started_at, TelemetrySpanRow.span_id)
            .limit(limit)
        )
        rows = tuple(result.scalars())
        deleted = deleted_at or datetime.now(UTC)
        _validate_cutoff(deleted)
        receipts = tuple(_receipt(row, cutoff=cutoff, deleted_at=deleted) for row in rows)
        for row in rows:
            await self._session.delete(row)
        if rows:
            await self._session.flush()
        return receipts


class InMemoryTelemetryRetentionStore:
    """Deterministic contract adapter; production uses the SQL implementation."""

    def __init__(self, spans: Iterable[TelemetrySpanRecord] = ()) -> None:
        self._spans: dict[str, TelemetrySpanRecord] = {}
        for span in spans:
            self.add(span)

    def add(self, span: TelemetrySpanRecord) -> None:
        if span.span_id in self._spans:
            raise ValueError("TELEMETRY_SPAN_ID_CONFLICT")
        self._spans[span.span_id] = span

    async def purge_before(
        self,
        cutoff: datetime,
        *,
        limit: int,
        deleted_at: datetime | None = None,
    ) -> tuple[TelemetryDeletionReceipt, ...]:
        _validate_cutoff(cutoff)
        _validate_limit(limit)
        if limit == 0:
            return ()
        deleted = deleted_at or datetime.now(UTC)
        _validate_cutoff(deleted)
        candidates = sorted(
            (span for span in self._spans.values() if span.started_at < cutoff),
            key=lambda span: (span.started_at, span.span_id),
        )[:limit]
        receipts = tuple(
            TelemetryDeletionReceipt(
                receipt_id=_receipt_id(span.span_id),
                span_id=span.span_id,
                started_at=span.started_at,
                cutoff=cutoff,
                deleted_at=deleted,
                tenant_id=span.tenant_id,
                family_id=span.family_id,
            )
            for span in candidates
        )
        for span in candidates:
            del self._spans[span.span_id]
        return receipts

    def remaining(self) -> tuple[TelemetrySpanRecord, ...]:
        """Return rows in deterministic order for tests/diagnostics."""

        return tuple(sorted(self._spans.values(), key=lambda span: span.span_id))


class InMemoryTelemetryDeletionAudit:
    """Idempotent audit sink for dev/test retention runs."""

    def __init__(self) -> None:
        self.receipts: dict[str, TelemetryDeletionReceipt] = {}

    async def record(self, receipts: tuple[TelemetryDeletionReceipt, ...]) -> None:
        for receipt in receipts:
            existing = self.receipts.get(receipt.receipt_id)
            if existing is not None and existing != receipt:
                raise ValueError("TELEMETRY_DELETION_AUDIT_IDEMPOTENCY_CONFLICT")
            self.receipts[receipt.receipt_id] = receipt


class TelemetryRetentionWorker:
    """Run a bounded metadata-only TTL deletion pass."""

    def __init__(
        self,
        store: TelemetryRetentionStore,
        *,
        audit: TelemetryDeletionAuditSink | None = None,
    ) -> None:
        self._store = store
        self._audit = audit

    async def run_once(
        self,
        *,
        ttl: timedelta,
        limit: int = 100,
        now: datetime | None = None,
    ) -> TelemetryRetentionRun:
        if ttl <= timedelta(0):
            raise ValueError("TELEMETRY_TTL_MUST_BE_POSITIVE")
        _validate_limit(limit)
        reference = now or datetime.now(UTC)
        _validate_cutoff(reference)
        cutoff = reference - ttl
        receipts = await self._store.purge_before(
            cutoff,
            limit=limit,
            deleted_at=reference,
        )
        if self._audit is not None and receipts:
            await self._audit.record(receipts)
        return TelemetryRetentionRun(
            cutoff=cutoff,
            limit=limit,
            receipts=receipts,
            completed_at=reference,
        )


def _receipt(
    row: TelemetrySpanRow,
    *,
    cutoff: datetime,
    deleted_at: datetime,
) -> TelemetryDeletionReceipt:
    started = _aware(row.started_at)
    return TelemetryDeletionReceipt(
        receipt_id=_receipt_id(row.span_id),
        span_id=row.span_id,
        started_at=started,
        cutoff=cutoff,
        deleted_at=deleted_at,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
    )


def _receipt_id(span_id: str) -> str:
    return f"telemetry-retention:{span_id}"


def _validate_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("TELEMETRY_RETENTION_LIMIT_INVALID")


def _validate_cutoff(moment: datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError("TELEMETRY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


__all__ = [
    "InMemoryTelemetryDeletionAudit",
    "InMemoryTelemetryRetentionStore",
    "SqlAlchemyTelemetryRetentionStore",
    "TelemetryDeletionAuditSink",
    "TelemetryDeletionReceipt",
    "TelemetryRetentionRun",
    "TelemetryRetentionStore",
    "TelemetryRetentionWorker",
    "TelemetrySpanRecord",
]
