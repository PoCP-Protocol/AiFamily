"""Async composition-root bridge for the experience HTTP ledger.

The HTTP contract historically accepts a synchronous in-memory ledger, while
the durable SQL adapter is async and session-owned.  This module keeps those
contracts separate and provides two small seams:

* ``dispatch_ledger_call`` awaits an async implementation and returns a sync
  implementation unchanged; it never blocks the event loop with
  ``asyncio.run``.
* ``AsyncExperienceRunLedgerBridge`` adapts an async ledger to the HTTP
  preflight/finalize shape.  Its reservation map is process-local; durable
  idempotency remains the SQL adapter's responsibility.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, Protocol, TypeVar

from backend.intelligence.experience.run_http import (
    DraftPreflight,
    InteractionReceipt,
    InteractionType,
    RunHttpConflictError,
    RunHttpError,
    RunReplaySnapshot,
    RunScope,
)

T = TypeVar("T")


class AsyncExperienceRunLedgerPort(Protocol):
    async def create_draft(
        self,
        *,
        scope: RunScope,
        run_id: str,
        request_ref: str,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        idempotency_key: str,
    ) -> RunReplaySnapshot: ...

    async def append_interaction(
        self,
        *,
        scope: RunScope,
        run_id: str,
        interaction_type: InteractionType,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> InteractionReceipt: ...

    async def replay(self, *, scope: RunScope, run_id: str) -> RunReplaySnapshot: ...


async def dispatch_ledger_call(ledger: object, method_name: str, **kwargs: Any) -> Any:
    """Invoke a sync or async ledger method without changing the HTTP contract."""

    method = getattr(ledger, method_name, None)
    if method is None or not callable(method):
        raise RunHttpError("EXPERIENCE_RUN_LEDGER_METHOD_UNAVAILABLE")
    result = method(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


class AsyncExperienceRunLedgerBridge:
    """Expose the sync HTTP preflight shape over an async durable ledger.

    The bridge owns no session and never commits.  A reservation is only a
    local admission marker; ``finalize_create`` delegates to the durable
    adapter, whose transaction is owned by the composition root.
    """

    def __init__(self, ledger: AsyncExperienceRunLedgerPort) -> None:
        self._ledger = ledger
        self._pending: dict[tuple[tuple[str, str, tuple[str, ...]], str], DraftPreflight] = {}
        self._fingerprints: dict[tuple[tuple[str, str, tuple[str, ...]], str], str] = {}
        self._idempotency_keys: dict[tuple[tuple[str, str, tuple[str, ...]], str], str] = {}
        self._responses: dict[tuple[tuple[str, str, tuple[str, ...]], str], Mapping[str, Any]] = {}

    async def preflight_create(
        self,
        *,
        scope: RunScope,
        run_id: str,
        request_ref: str,
        request_fingerprint: str,
        idempotency_key: str,
    ) -> DraftPreflight:
        key = (scope.key, run_id)
        prior = self._fingerprints.get(key)
        if prior is not None:
            if self._idempotency_keys.get(key) != idempotency_key:
                raise RunHttpConflictError("RUN_ALREADY_EXISTS")
            if prior != request_fingerprint:
                raise RunHttpConflictError("IDEMPOTENCY_REPLAY_MISMATCH")
            snapshot = await self._ledger.replay(scope=scope, run_id=run_id)
            return DraftPreflight(
                scope=scope,
                run_id=run_id,
                request_ref=request_ref,
                request_fingerprint=request_fingerprint,
                idempotency_key=idempotency_key,
                status="replay",
                snapshot=snapshot,
                response_payload=self._responses.get(key),
            )

        if key in self._pending:
            pending = self._pending[key]
            if pending.request_fingerprint != request_fingerprint:
                raise RunHttpConflictError("IDEMPOTENCY_REPLAY_MISMATCH")
            return DraftPreflight(
                scope=scope,
                run_id=run_id,
                request_ref=request_ref,
                request_fingerprint=request_fingerprint,
                idempotency_key=idempotency_key,
                status="in_progress",
            )

        try:
            snapshot = await self._ledger.replay(scope=scope, run_id=run_id)
        except RunHttpError as error:
            if error.code != "RUN_NOT_FOUND":
                raise
            snapshot = None
        if snapshot is not None:
            # A durable row exists but this process has no response projection;
            # API will fail closed rather than inventing a response from a run.
            return DraftPreflight(
                scope=scope,
                run_id=run_id,
                request_ref=request_ref,
                request_fingerprint=request_fingerprint,
                idempotency_key=idempotency_key,
                status="replay",
                snapshot=snapshot,
                response_payload=self._responses.get(key),
            )

        reservation = DraftPreflight(
            scope=scope,
            run_id=run_id,
            request_ref=request_ref,
            request_fingerprint=request_fingerprint,
            idempotency_key=idempotency_key,
            status="reserved",
        )
        self._pending[key] = reservation
        return reservation

    async def finalize_create(
        self,
        reservation: DraftPreflight,
        *,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        response_payload: Mapping[str, Any] | None = None,
    ) -> RunReplaySnapshot:
        if reservation.status != "reserved":
            if reservation.snapshot is not None:
                return reservation.snapshot
            raise RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS")
        key = (reservation.scope.key, reservation.run_id)
        if self._pending.get(key) != reservation:
            raise RunHttpConflictError("DRAFT_RESERVATION_NOT_FOUND")
        try:
            snapshot = await self._ledger.create_draft(
                scope=reservation.scope,
                run_id=reservation.run_id,
                request_ref=reservation.request_ref,
                draft_payload=draft_payload,
                artifact_refs=artifact_refs,
                idempotency_key=reservation.idempotency_key,
            )
        finally:
            self._pending.pop(key, None)
        self._fingerprints[key] = reservation.request_fingerprint
        self._idempotency_keys[key] = reservation.idempotency_key
        if response_payload is not None:
            self._responses[key] = dict(response_payload)
        return snapshot

    async def release_create(self, reservation: DraftPreflight) -> None:
        key = (reservation.scope.key, reservation.run_id)
        if self._pending.get(key) == reservation:
            self._pending.pop(key, None)

    async def append_interaction(self, **kwargs: Any) -> InteractionReceipt:
        receipt = await self._ledger.append_interaction(**kwargs)
        if kwargs.get("interaction_type") is InteractionType.DELETE:
            scope = kwargs["scope"]
            run_id = kwargs["run_id"]
            self._responses.pop((scope.key, run_id), None)
        return receipt

    async def replay(self, *, scope: RunScope, run_id: str) -> RunReplaySnapshot:
        return await self._ledger.replay(scope=scope, run_id=run_id)


__all__ = [
    "AsyncExperienceRunLedgerBridge",
    "AsyncExperienceRunLedgerPort",
    "dispatch_ledger_call",
]
