"""Single-pass scheduler adapter for FamilyNeed outcome reflections.

This module deliberately does not own a clock, thread, queue, or retry loop.
The workflow worker supplies invocation cadence and a fully authorized scope;
the adapter performs one bounded pass and returns its count.  That keeps
retries safe and prevents an in-memory scheduler from being mistaken for a
production durable worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import ContextScope
from .family_need_outcome_consumer import (
    ConfirmedOutcomeReader,
    FamilyNeedOutcomeReflectionConsumer,
)
from .outcome_reflection import OutcomeReflectionContextWriter


@dataclass(frozen=True, slots=True)
class OutcomeReflectionPollResult:
    inspected: int
    projected: int

    @property
    def empty(self) -> bool:
        """Whether this bounded pass found no durable events."""

        return self.inspected == 0

    @property
    def has_unprojected(self) -> bool:
        """Whether at least one inspected event did not produce a projection."""

        return self.projected < self.inspected


class OutcomeReflectionScopeResolver(Protocol):
    async def resolve(self, *, tenant_id: str, family_id: str) -> ContextScope: ...


class FamilyNeedOutcomeReflectionPoller:
    """Run one authorized, bounded FamilyNeed reflection pass."""

    def __init__(
        self,
        reader: ConfirmedOutcomeReader,
        writer: OutcomeReflectionContextWriter,
        scope_resolver: OutcomeReflectionScopeResolver,
    ) -> None:
        self._reader = reader
        self._consumer = FamilyNeedOutcomeReflectionConsumer(reader, writer)
        self._scope_resolver = scope_resolver

    async def poll_once(
        self, *, tenant_id: str, family_id: str, limit: int = 100
    ) -> OutcomeReflectionPollResult:
        if not tenant_id.strip() or not family_id.strip():
            raise ValueError("tenant and family are required")
        if limit <= 0 or limit > 1000:
            raise ValueError("event limit must be between 1 and 1000")
        scope = await self._scope_resolver.resolve(
            tenant_id=tenant_id, family_id=family_id
        )
        if not isinstance(scope, ContextScope):
            raise TypeError("scope resolver must return ContextScope")
        if scope.tenant_id != tenant_id or scope.family_id != family_id:
            raise ValueError("resolved scope does not match requested family")
        events = await self._reader.list_events(
            tenant_id=tenant_id,
            family_id=family_id,
            event_name="family_need.outcome_confirmed",
            limit=limit,
        )
        projected = 0
        for event in events:
            if await self._consumer.consume(event, scope=scope):
                projected += 1
        return OutcomeReflectionPollResult(inspected=len(events), projected=projected)


__all__ = [
    "FamilyNeedOutcomeReflectionPoller",
    "OutcomeReflectionPollResult",
    "OutcomeReflectionScopeResolver",
]
