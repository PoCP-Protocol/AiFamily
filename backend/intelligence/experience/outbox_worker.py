"""Provider-neutral worker for the durable experience outbox.

The worker deliberately knows nothing about Family/Journey/Commerce and never
imports a model SDK.  It pulls opaque :class:`StoredExperienceMessage` values
from the SQL outbox, hands them to an injected consumer, and marks the row only
after the consumer acknowledges success.  A consumer must be idempotent by
``message_id`` because a process crash can happen between consume and
``mark_published``.

Failures are at-least-once by default: a retry leaves the outbox row pending.
After ``max_attempts`` a dead-letter sink receives the original envelope.  The
row is marked terminal only after the sink acknowledges it, so a sink outage
cannot silently lose an event.  The default in-memory sink is intentionally a
test/dev adapter; production composition roots must inject a durable sink.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from backend.intelligence.experience.persistence import StoredExperienceMessage


class ExperienceOutboxStore(Protocol):
    """Minimal storage port implemented by ``SqlAlchemyExperienceOutbox``."""

    async def pending(self, *, limit: int = 100) -> tuple[StoredExperienceMessage, ...]:
        """Return at most ``limit`` unacknowledged envelopes."""
        ...

    async def mark_published(
        self,
        message_id: str,
        *,
        published_at: datetime | None = None,
    ) -> StoredExperienceMessage:
        """Idempotently acknowledge one envelope."""
        ...


class ExperienceOutboxConsumer(Protocol):
    """Provider-neutral acknowledgement port for one outbox envelope."""

    async def consume(self, message: StoredExperienceMessage) -> None:
        """Apply a projection/side effect, or raise a delivery error."""
        ...


class ExperienceDeadLetterSink(Protocol):
    """Terminal-failure port; implementations must be idempotent by message."""

    async def publish(
        self,
        message: StoredExperienceMessage,
        *,
        attempts: int,
        error: str,
    ) -> None:
        """Persist a dead-letter envelope and acknowledge the write."""
        ...


class ExperienceDeliveryAttemptStore(Protocol):
    """Optional durable attempt/terminal-state port."""

    async def begin_attempt(self, message_id: str) -> int:
        """Atomically increment and return the durable attempt number."""
        ...

    async def claim_attempt(
        self,
        message_id: str,
        *,
        worker_id: str,
        lease_ttl: timedelta,
        now: datetime | None = None,
    ) -> int | None:
        """Claim a message, returning ``None`` when another lease is active."""
        ...

    async def mark_published(self, message_id: str) -> object:
        """Mark one message terminal after outbox acknowledgement."""
        ...

    async def mark_dead_lettered(self, message_id: str, *, error: str) -> object:
        """Record terminal dead-letter metadata."""
        ...


class PermanentExperienceDeliveryError(RuntimeError):
    """Consumer error that should skip transient retries and go to the DLQ."""


class DeliveryStatus(StrEnum):
    """Outcome for one message in a worker pass."""

    PUBLISHED = "published"
    RETRY = "retry"
    DEAD_LETTERED = "dead_lettered"
    LEASED = "leased"


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Auditable outcome without exposing ORM rows or mutable state."""

    message_id: str
    status: DeliveryStatus
    attempts: int
    error: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class OutboxWorkerReport:
    """Summary of one bounded pull; suitable for metrics/audit adapters."""

    results: tuple[DeliveryResult, ...]

    @property
    def pulled(self) -> int:
        return len(self.results)

    @property
    def published(self) -> int:
        return sum(item.status is DeliveryStatus.PUBLISHED for item in self.results)

    @property
    def retried(self) -> int:
        return sum(item.status is DeliveryStatus.RETRY for item in self.results)

    @property
    def dead_lettered(self) -> int:
        return sum(item.status is DeliveryStatus.DEAD_LETTERED for item in self.results)

    @property
    def leased(self) -> int:
        return sum(item.status is DeliveryStatus.LEASED for item in self.results)


@dataclass(frozen=True, slots=True)
class DeadLetterEnvelope:
    """Opaque dead-letter representation used by the dev/test sink."""

    message: StoredExperienceMessage
    attempts: int
    error: str
    occurred_at: datetime


class InMemoryExperienceDeadLetterSink:
    """Idempotent test adapter; production must provide a durable sink."""

    def __init__(self) -> None:
        self._messages: dict[str, DeadLetterEnvelope] = {}

    async def publish(
        self,
        message: StoredExperienceMessage,
        *,
        attempts: int,
        error: str,
    ) -> None:
        prior = self._messages.get(message.message_id)
        envelope = DeadLetterEnvelope(
            message=message,
            attempts=attempts,
            error=error,
            occurred_at=datetime.now(UTC),
        )
        if prior is not None:
            # A repeated acknowledgement must be byte-for-byte equivalent in
            # its stable fields; changing the failure reason under one key is
            # an idempotency violation rather than a second DLQ message.
            if prior.message != message or prior.attempts != attempts or prior.error != error:
                raise ValueError("DEAD_LETTER_IDEMPOTENCY_REPLAY_MISMATCH")
            return
        self._messages[message.message_id] = envelope

    def messages(self) -> tuple[DeadLetterEnvelope, ...]:
        """Return envelopes in deterministic message-id order for assertions."""

        return tuple(self._messages[key] for key in sorted(self._messages))


class ExperienceOutboxWorker:
    """Bounded, retry-safe worker over :class:`SqlAlchemyExperienceOutbox`.

    The worker owns attempt counters only for the current process.  Durable
    delivery state is the outbox itself: until a consumer or dead-letter sink
    acknowledges successfully, ``published_at`` remains null and a restart
    will pull the envelope again.  A production scheduler may replace the
    counter policy with a durable lease/attempt store without changing this
    consumer port.
    """

    def __init__(
        self,
        outbox: ExperienceOutboxStore,
        consumer: ExperienceOutboxConsumer,
        *,
        dead_letter_sink: ExperienceDeadLetterSink,
        max_attempts: int = 3,
        attempt_store: ExperienceDeliveryAttemptStore | None = None,
        worker_id: str | None = None,
        lease_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._outbox = outbox
        self._consumer = consumer
        self._dead_letter_sink = dead_letter_sink
        self._max_attempts = max_attempts
        self._attempt_store = attempt_store
        if worker_id is not None and (not isinstance(worker_id, str) or not worker_id.strip()):
            raise ValueError("worker_id must be non-empty when provided")
        if lease_ttl.total_seconds() <= 0:
            raise ValueError("lease_ttl must be positive")
        self._worker_id = worker_id
        self._lease_ttl = lease_ttl
        self._attempts: dict[str, int] = {}

    async def run_once(self, *, limit: int = 100) -> OutboxWorkerReport:
        """Pull at most ``limit`` pending rows and process them in order."""

        if limit < 0:
            raise ValueError("limit must be non-negative")
        pending = await self._outbox.pending(limit=limit)
        results = tuple([await self._deliver(message) for message in pending])
        return OutboxWorkerReport(results=results)

    async def _deliver(self, message: StoredExperienceMessage) -> DeliveryResult:
        if self._attempt_store is not None and self._worker_id is not None:
            attempts = await self._attempt_store.claim_attempt(
                message.message_id,
                worker_id=self._worker_id,
                lease_ttl=self._lease_ttl,
            )
            if attempts is None:
                return DeliveryResult(
                    message_id=message.message_id,
                    status=DeliveryStatus.LEASED,
                    attempts=0,
                )
        elif self._attempt_store is None:
            attempts = self._attempts.get(message.message_id, 0) + 1
        else:
            attempts = await self._attempt_store.begin_attempt(message.message_id)
        try:
            await self._consumer.consume(message)
        except Exception as error:  # noqa: BLE001 - worker must classify all failures
            reason = _error_text(error)
            self._attempts[message.message_id] = attempts
            permanent = isinstance(error, PermanentExperienceDeliveryError)
            if not permanent and attempts < self._max_attempts:
                return DeliveryResult(
                    message_id=message.message_id,
                    status=DeliveryStatus.RETRY,
                    attempts=attempts,
                    error=reason,
                )
            try:
                await self._dead_letter_sink.publish(message, attempts=attempts, error=reason)
                await self._outbox.mark_published(message.message_id)
                if self._attempt_store is not None:
                    await self._attempt_store.mark_dead_lettered(message.message_id, error=reason)
            except Exception as terminal_error:  # noqa: BLE001
                # Keep the row pending if either DLQ or terminal marking fails.
                # The original error remains visible while the terminal error
                # explains why this pass did not acknowledge the row.
                return DeliveryResult(
                    message_id=message.message_id,
                    status=DeliveryStatus.RETRY,
                    attempts=attempts,
                    error=f"{reason}; terminal={_error_text(terminal_error)}",
                )
            self._attempts.pop(message.message_id, None)
            return DeliveryResult(
                message_id=message.message_id,
                status=DeliveryStatus.DEAD_LETTERED,
                attempts=attempts,
                error=reason,
            )

        try:
            await self._outbox.mark_published(message.message_id)
            if self._attempt_store is not None:
                await self._attempt_store.mark_published(message.message_id)
        except Exception as error:  # noqa: BLE001 - leave pending for replay
            self._attempts[message.message_id] = attempts
            return DeliveryResult(
                message_id=message.message_id,
                status=DeliveryStatus.RETRY,
                attempts=attempts,
                error=f"MARK_PUBLISHED_FAILED: {_error_text(error)}",
            )
        self._attempts.pop(message.message_id, None)
        return DeliveryResult(
            message_id=message.message_id,
            status=DeliveryStatus.PUBLISHED,
            attempts=attempts,
        )


def _error_text(error: BaseException) -> str:
    text = str(error).strip()
    return text or type(error).__name__


__all__ = [
    "DeadLetterEnvelope",
    "DeliveryResult",
    "DeliveryStatus",
    "ExperienceDeadLetterSink",
    "ExperienceDeliveryAttemptStore",
    "ExperienceOutboxStore",
    "ExperienceOutboxConsumer",
    "ExperienceOutboxWorker",
    "InMemoryExperienceDeadLetterSink",
    "OutboxWorkerReport",
    "PermanentExperienceDeliveryError",
]
