"""Project human-confirmed FamilyNeed outcomes into Context.

The consumer is intentionally an adapter: the FamilyNeed repository remains
the source of truth, while Context receives an append-only reflection after
the ``family_need.outcome_confirmed`` event is delivered.  No AI output can
enter this path because the repository outcome is already human-gated.
"""

from __future__ import annotations

from typing import Protocol

from .contracts import ContextScope
from .outcome_reflection import OutcomeReflectionContextWriter


class ConfirmedOutcomeReader(Protocol):
    async def get_outcome(
        self, *, tenant_id: str, family_id: str, outcome_id: str
    ) -> object | None: ...

    async def list_events(
        self, *, tenant_id: str, family_id: str, event_name: str, limit: int = 100
    ) -> tuple[OutcomeConfirmedEvent, ...]: ...


class OutcomeConfirmedEvent(Protocol):
    """Structural event contract owned by the AI runtime boundary.

    The producer may be a business domain, but the runtime must not import its
    application ports or repositories.  Keeping this protocol structural also
    allows the durable outbox adapter to evolve without coupling the runtime
    to a domain package.
    """

    event_name: str
    tenant_id: str
    family_id: str
    purpose: str
    consent_version: str | None
    data_class: str | None
    subject_person_ids: tuple[str, ...]
    idempotency_key: str | None
    aggregate_id: str
    version: int


class FamilyNeedOutcomeReflectionConsumer:
    """Handle one delivered outcome event with idempotent projection semantics."""

    def __init__(
        self,
        reader: ConfirmedOutcomeReader,
        writer: OutcomeReflectionContextWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._processed: set[str] = set()

    async def consume(self, event: OutcomeConfirmedEvent, *, scope: ContextScope) -> bool:
        if event.event_name != "family_need.outcome_confirmed":
            return False
        if event.tenant_id != scope.tenant_id or event.family_id != scope.family_id:
            raise ValueError("outcome reflection event scope mismatch")
        if event.purpose != scope.purpose:
            raise ValueError("outcome reflection event purpose mismatch")
        if event.consent_version and event.consent_version != scope.consent_version:
            raise ValueError("outcome reflection event consent mismatch")
        if event.data_class is not None and event.data_class != scope.data_class:
            raise ValueError("outcome reflection event data class mismatch")
        if event.subject_person_ids and not set(event.subject_person_ids).issubset(
            scope.subject_ids
        ):
            raise ValueError("outcome reflection event subject scope mismatch")
        event_key = event.idempotency_key or (
            f"{event.event_name}:{event.aggregate_id}:{event.version}"
        )
        if event_key in self._processed:
            return True
        outcome = await self._reader.get_outcome(
            tenant_id=event.tenant_id,
            family_id=event.family_id,
            outcome_id=event.aggregate_id,
        )
        if outcome is None:
            raise LookupError("confirmed outcome not found for event")
        if getattr(outcome, "outcome_id", None) != event.aggregate_id:
            raise ValueError("outcome reflection aggregate mismatch")
        await self._writer.record_family_need_outcome(outcome, scope=scope)
        self._processed.add(event_key)
        return True

    async def consume_pending(self, *, scope: ContextScope, limit: int = 100) -> int:
        """Consume a bounded batch from the durable FamilyNeed event stream."""

        if limit <= 0 or limit > 1000:
            raise ValueError("event limit must be between 1 and 1000")
        events = await self._reader.list_events(
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            event_name="family_need.outcome_confirmed",
            limit=limit,
        )
        processed = 0
        for event in events:
            if await self.consume(event, scope=scope):
                processed += 1
        return processed


__all__ = [
    "ConfirmedOutcomeReader",
    "FamilyNeedOutcomeReflectionConsumer",
    "OutcomeConfirmedEvent",
]
