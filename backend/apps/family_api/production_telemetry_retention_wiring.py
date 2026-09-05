"""Production composition root for metadata-only telemetry retention.

The runtime is intentionally bounded: deployment supplies the recurring
schedule, while this module owns one transactional SQL purge pass.  The audit
sink is explicit so production cannot accidentally delete spans without a
durable deletion proof.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.observability.retention import (
    SqlAlchemyTelemetryRetentionStore,
    TelemetryDeletionAuditSink,
    TelemetryRetentionRun,
    TelemetryRetentionWorker,
)

TELEMETRY_RETENTION_ENVIRONMENTS = frozenset({"staging", "production"})
TelemetryAuditFactory = Callable[[AsyncSession], TelemetryDeletionAuditSink]


@dataclass(frozen=True, slots=True)
class ProductionTelemetryRetentionRuntime:
    """One restart-safe, caller-scheduled telemetry retention invocation."""

    session_factory: async_sessionmaker[AsyncSession]
    audit_factory: TelemetryAuditFactory
    environment: str
    ttl: timedelta
    batch_limit: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not callable(self.audit_factory):
            raise TypeError("audit_factory must be callable")
        if self.environment not in TELEMETRY_RETENTION_ENVIRONMENTS:
            raise ValueError("telemetry retention runtime requires staging or production")
        if self.ttl <= timedelta(0):
            raise ValueError("telemetry retention ttl must be positive")
        if not isinstance(self.batch_limit, int) or isinstance(self.batch_limit, bool):
            raise ValueError("telemetry retention batch_limit must be an integer")
        if self.batch_limit < 1:
            raise ValueError("telemetry retention batch_limit must be positive")

    async def run_once(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> TelemetryRetentionRun:
        """Delete one bounded batch and atomically record its audit receipts."""

        effective_limit = self.batch_limit if limit is None else limit
        if not isinstance(effective_limit, int) or isinstance(effective_limit, bool):
            raise ValueError("telemetry retention limit must be an integer")
        if effective_limit < 0:
            raise ValueError("telemetry retention limit must not be negative")
        async with self.session_factory() as session, session.begin():
            audit = self.audit_factory(session)
            if not callable(getattr(audit, "record", None)):
                raise TypeError("audit_factory must return a TelemetryDeletionAuditSink")
            worker = TelemetryRetentionWorker(
                SqlAlchemyTelemetryRetentionStore(session),
                audit=audit,
            )
            return await worker.run_once(ttl=self.ttl, limit=effective_limit, now=now)


__all__ = ["ProductionTelemetryRetentionRuntime", "TELEMETRY_RETENTION_ENVIRONMENTS"]
