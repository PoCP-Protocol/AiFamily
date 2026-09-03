"""Production composition root for the Experience Outbox relay.

The relay is deliberately separate from HTTP request handling.  Each bounded
poll opens a fresh SQL session, composes the durable outbox, metadata-only
attempt ledger, consumer and dead-letter sink, and commits only after the
consumer has acknowledged the envelope.  Staging and production therefore
share the same functional path; only explicitly supplied infrastructure
adapters differ.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.evaluation.operator_identity import OperatorIdentityPort
from backend.intelligence.experience.operations_query import (
    EXPERIENCE_OPERATIONS_READ_SCOPE,
    AuthorizedExperienceOperationsQueryService,
    ExperienceOperationsAuditSink,
)
from backend.intelligence.experience.outbox_worker import (
    ExperienceDeadLetterSink,
    ExperienceOutboxConsumer,
    ExperienceOutboxWorker,
    OutboxWorkerReport,
)
from backend.intelligence.experience.persistence import (
    ExperienceDeliveryAttemptCursor,
    ExperienceDeliveryAttemptPage,
    ExperienceDeliveryAttemptStatus,
    ExperienceDeliveryAttemptSummary,
    SqlAlchemyExperienceDeliveryAttemptStore,
    SqlAlchemyExperienceOutbox,
    StoredExperienceDeliveryAttempt,
)

EXPERIENCE_OUTBOX_ENVIRONMENTS = frozenset({"staging", "production"})
ConsumerFactory = Callable[[AsyncSession], ExperienceOutboxConsumer]
DeadLetterSinkFactory = Callable[[AsyncSession], ExperienceDeadLetterSink]
DeliveryAlertSink = Callable[[OutboxWorkerReport], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ExperienceOutboxSchedule:
    """Deployment-owned recurrence and bounded poll parameters."""

    interval: timedelta = timedelta(seconds=30)
    batch_limit: int = 100
    max_polls: int = 10

    def __post_init__(self) -> None:
        if self.interval <= timedelta(0):
            raise ValueError("experience outbox schedule interval must be positive")
        if not isinstance(self.batch_limit, int) or isinstance(self.batch_limit, bool):
            raise ValueError("experience outbox schedule batch_limit must be an integer")
        if self.batch_limit < 1:
            raise ValueError("experience outbox schedule batch_limit must be positive")
        if not isinstance(self.max_polls, int) or isinstance(self.max_polls, bool):
            raise ValueError("experience outbox schedule max_polls must be an integer")
        if self.max_polls < 1:
            raise ValueError("experience outbox schedule max_polls must be positive")


@dataclass(frozen=True, slots=True)
class ProductionExperienceOutboxRuntime:
    """One bounded, restart-safe relay invocation over the SQL outbox."""

    session_factory: async_sessionmaker[AsyncSession]
    consumer_factory: ConsumerFactory
    dead_letter_sink_factory: DeadLetterSinkFactory
    environment: str
    worker_id: str
    max_attempts: int = 3
    lease_ttl: timedelta = timedelta(minutes=5)
    alert_sink: DeliveryAlertSink | None = None
    schedule: ExperienceOutboxSchedule = field(default_factory=ExperienceOutboxSchedule)

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not callable(self.consumer_factory):
            raise TypeError("consumer_factory must be callable")
        if not callable(self.dead_letter_sink_factory):
            raise TypeError("dead_letter_sink_factory must be callable")
        if self.alert_sink is not None and not callable(self.alert_sink):
            raise TypeError("alert_sink must be callable when provided")
        if not isinstance(self.schedule, ExperienceOutboxSchedule):
            raise TypeError("schedule must be an ExperienceOutboxSchedule")
        if not isinstance(self.worker_id, str) or not self.worker_id.strip():
            raise ValueError("worker_id is required")
        if self.worker_id.lower().startswith("ai:"):
            raise ValueError("worker_id must identify an operational worker")
        if self.environment not in EXPERIENCE_OUTBOX_ENVIRONMENTS:
            raise ValueError("experience outbox runtime requires staging or production")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.lease_ttl.total_seconds() <= 0:
            raise ValueError("lease_ttl must be positive")

    async def run_once(self, *, limit: int = 100) -> OutboxWorkerReport:
        """Process at most ``limit`` messages in one caller-owned transaction."""

        if limit < 0:
            raise ValueError("limit must be non-negative")
        async with self.session_factory() as session:
            async with session.begin():
                worker = ExperienceOutboxWorker(
                    SqlAlchemyExperienceOutbox(session),
                    self.consumer_factory(session),
                    dead_letter_sink=self.dead_letter_sink_factory(session),
                    max_attempts=self.max_attempts,
                    attempt_store=SqlAlchemyExperienceDeliveryAttemptStore(session),
                    worker_id=self.worker_id,
                    lease_ttl=self.lease_ttl,
                )
                report = await worker.run_once(limit=limit)
            # Alerting is deliberately outside the DB transaction: a metrics or
            # paging outage must not roll back a successfully acknowledged
            # projection/outbox message.
            if self.alert_sink is not None and (report.retried or report.dead_lettered):
                result = self.alert_sink(report)
                if isinstance(result, Awaitable):
                    await result
            return report

    async def run_until_idle(
        self, *, limit: int = 100, max_polls: int = 10
    ) -> tuple[OutboxWorkerReport, ...]:
        """Bounded scheduler primitive; deployment owns the recurring trigger."""

        if max_polls < 1:
            raise ValueError("max_polls must be positive")
        reports: list[OutboxWorkerReport] = []
        for _ in range(max_polls):
            report = await self.run_once(limit=limit)
            reports.append(report)
            if report.pulled == 0:
                break
        return tuple(reports)

    async def run_scheduled_tick(self) -> tuple[OutboxWorkerReport, ...]:
        """Run one deployment-triggered bounded tick; never sleeps or daemonizes."""

        return await self.run_until_idle(
            limit=self.schedule.batch_limit,
            max_polls=self.schedule.max_polls,
        )

    async def delivery_attempt(
        self, message_id: str
    ) -> StoredExperienceDeliveryAttempt | None:
        """Read metadata-only delivery state for operations and audit views."""

        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("message_id is required")
        async with self.session_factory() as session:
            return await SqlAlchemyExperienceDeliveryAttemptStore(session).get(message_id)

    async def delivery_attempts(
        self,
        *,
        limit: int = 100,
        status: ExperienceDeliveryAttemptStatus | None = None,
    ) -> tuple[StoredExperienceDeliveryAttempt, ...]:
        """Read a bounded metadata-only attempt list for dashboards/operations."""

        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("delivery attempt limit must be a non-negative integer")
        async with self.session_factory() as session:
            return await SqlAlchemyExperienceDeliveryAttemptStore(session).list(
                limit=limit,
                status=status,
            )

    async def delivery_attempts_page(
        self,
        *,
        limit: int = 100,
        status: ExperienceDeliveryAttemptStatus | None = None,
        after: ExperienceDeliveryAttemptCursor | None = None,
    ) -> ExperienceDeliveryAttemptPage:
        """Read one bounded cursor page for dashboard polling."""

        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("delivery attempt limit must be a non-negative integer")
        async with self.session_factory() as session:
            return await SqlAlchemyExperienceDeliveryAttemptStore(session).list_page(
                limit=limit,
                status=status,
                after=after,
            )

    async def delivery_attempt_summary(self) -> ExperienceDeliveryAttemptSummary:
        """Read status counts without exposing message or family data."""

        async with self.session_factory() as session:
            return await SqlAlchemyExperienceDeliveryAttemptStore(session).summary()

    def operations_query(
        self,
        identity_port: OperatorIdentityPort,
        *,
        required_scope: str = EXPERIENCE_OPERATIONS_READ_SCOPE,
        audit_sink: ExperienceOperationsAuditSink | None = None,
    ) -> AuthorizedExperienceOperationsQueryService:
        """Compose the operator-authorized dashboard query facade."""

        return AuthorizedExperienceOperationsQueryService(
            environment=self.environment,
            identity_port=identity_port,
            runtime=self,
            required_scope=required_scope,
            audit_sink=audit_sink,
        )


__all__ = [
    "DeliveryAlertSink",
    "ExperienceOutboxSchedule",
    "ProductionExperienceOutboxRuntime",
]
