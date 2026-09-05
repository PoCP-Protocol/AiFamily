"""One transaction boundary for an idempotent audited domain mutation.

This module coordinates existing persistence seams; it does not own domain
facts, audit storage, outbox schema, or receipt schema.  Callers inject the
database-only stages and every stage receives the same ``AsyncSession``.
External providers must run before or after this function, never inside it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork

ResultT = TypeVar("ResultT")

DatabaseStage = Callable[[AsyncSession], Awaitable[None]]
BusinessStage = Callable[[AsyncSession], Awaitable[ResultT]]
ResultStage = Callable[[AsyncSession, ResultT], Awaitable[None]]
IdempotencyStage = Callable[[AsyncSession], Awaitable[ResultT | None]]


@dataclass(frozen=True, slots=True)
class AtomicMutationResult[ResultT]:
    """Committed result or an already-committed idempotent replay."""

    value: ResultT
    replayed: bool


async def execute_atomic_mutation[ResultT](
    *,
    unit_of_work: SqlAlchemyUnitOfWork,
    load_replay_or_reserve: IdempotencyStage[ResultT],
    apply_business_change: BusinessStage[ResultT],
    flush_audit: DatabaseStage,
    append_outbox: ResultStage[ResultT],
    persist_receipt: ResultStage[ResultT],
) -> AtomicMutationResult[ResultT]:
    """Execute all first-attempt writes through one caller-owned transaction.

    ``load_replay_or_reserve`` returns a prior committed result for a replay,
    or returns ``None`` after staging a reservation in the current session.
    All remaining callbacks must only stage database work; none may commit.
    Any exception propagates and ``SqlAlchemyUnitOfWork`` rolls every staged
    write back, including the idempotency reservation.
    """

    async with unit_of_work:
        session = unit_of_work.session
        assert session is not None

        replay = await load_replay_or_reserve(session)
        if replay is not None:
            return AtomicMutationResult(value=replay, replayed=True)

        value = await apply_business_change(session)
        await flush_audit(session)
        await append_outbox(session, value)
        await persist_receipt(session, value)
        await unit_of_work.commit()
        return AtomicMutationResult(value=value, replayed=False)


__all__ = ["AtomicMutationResult", "execute_atomic_mutation"]
