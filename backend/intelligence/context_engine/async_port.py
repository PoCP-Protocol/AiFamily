"""Asynchronous port for the Context Engine.

The multimodal application is asynchronous, while the deterministic context
broker used by tests is deliberately synchronous.  This module keeps that
implementation detail at an adapter boundary.  A durable SQL broker can
implement :class:`AsyncContextBrokerPort` directly without changing the
application contract.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from .contracts import ContextScope, ContextSnapshot, StateObservation
from .store import ContextBroker


@runtime_checkable
class AsyncContextBrokerPort(Protocol):
    """Non-blocking Context Engine boundary used by async applications."""

    durability_mode: str

    async def append(self, observation: StateObservation) -> None:
        """Persist one append-only observation."""

    async def snapshot(
        self,
        tenant_id: str | None = None,
        subject_id: str | None = None,
        *,
        scope: ContextScope | None = None,
        now: datetime | None = None,
        snapshot_ttl: timedelta = timedelta(minutes=15),
    ) -> ContextSnapshot:
        """Create a scoped, bounded context projection."""

    async def read(
        self,
        snapshot_ref: str,
        scope: ContextScope,
        *,
        now: datetime | None = None,
    ) -> ContextSnapshot:
        """Read a prior snapshot inside its original scope."""

    async def delete_subject(self, tenant_id: str, subject_id: str) -> int:
        """Apply tenant-scoped subject deletion."""


class AsyncContextBrokerAdapter:
    """Bridge a synchronous broker without blocking the event loop.

    The adapter is intended for deterministic tests and local development.  A
    production resolver must inject a durable implementation of the async
    port; ``ContextBroker`` remains marked ``IN_MEMORY`` and is rejected by
    the production composition root.
    """

    def __init__(self, broker: ContextBroker) -> None:
        if not isinstance(broker, ContextBroker):
            raise TypeError("broker must be a ContextBroker")
        self._broker = broker

    @property
    def durability_mode(self) -> str:
        return getattr(self._broker, "durability_mode", "IN_MEMORY")

    async def append(self, observation: StateObservation) -> None:
        await asyncio.to_thread(self._broker.append, observation)

    async def snapshot(
        self,
        tenant_id: str | None = None,
        subject_id: str | None = None,
        *,
        scope: ContextScope | None = None,
        now: datetime | None = None,
        snapshot_ttl: timedelta = timedelta(minutes=15),
    ) -> ContextSnapshot:
        return await self._call(
            self._broker.snapshot,
            tenant_id,
            subject_id,
            scope=scope,
            now=now,
            snapshot_ttl=snapshot_ttl,
        )

    async def read(
        self,
        snapshot_ref: str,
        scope: ContextScope,
        *,
        now: datetime | None = None,
    ) -> ContextSnapshot:
        return await self._call(
            self._broker.read,
            snapshot_ref,
            scope,
            now=now,
        )

    async def delete_subject(self, tenant_id: str, subject_id: str) -> int:
        return await asyncio.to_thread(self._broker.delete_subject, tenant_id, subject_id)

    async def _call(
        self,
        operation: Callable[..., ContextSnapshot],
        *args: object,
        **kwargs: object,
    ) -> ContextSnapshot:
        return await asyncio.to_thread(operation, *args, **kwargs)


__all__ = ["AsyncContextBrokerAdapter", "AsyncContextBrokerPort"]
