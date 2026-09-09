"""Session-per-operation FamilyNeed event reader for workflow workers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncEngine

from backend.domains.family_need.application.ports import NeedEvent
from backend.domains.family_need.domain.entities import FamilyConfirmedOutcome
from backend.domains.family_need.infrastructure.postgres_repository import (
    SqlAlchemyFamilyNeedRepository,
)


class FamilyNeedReadRepository(Protocol):
    async def list_events(
        self, *, tenant_id: str, family_id: str, event_name: str, limit: int = 100
    ) -> tuple[NeedEvent, ...]: ...

    async def get_outcome(
        self, *, tenant_id: str, family_id: str, outcome_id: str
    ) -> FamilyConfirmedOutcome | None: ...


class SqlAlchemyFamilyNeedEventReader:
    """Open a fresh connection for each read, safe across worker restarts."""

    def __init__(self, engine: AsyncEngine) -> None:
        if not isinstance(engine, AsyncEngine):
            raise TypeError("engine must be an AsyncEngine")
        self._engine = engine

    @asynccontextmanager
    async def _repository(self) -> AsyncIterator[SqlAlchemyFamilyNeedRepository]:
        async with self._engine.connect() as connection:
            yield SqlAlchemyFamilyNeedRepository(connection)

    async def list_events(
        self, *, tenant_id: str, family_id: str, event_name: str, limit: int = 100
    ) -> tuple[NeedEvent, ...]:
        async with self._repository() as repository:
            return await repository.list_events(
                tenant_id=tenant_id,
                family_id=family_id,
                event_name=event_name,
                limit=limit,
            )

    async def get_outcome(
        self, *, tenant_id: str, family_id: str, outcome_id: str
    ) -> FamilyConfirmedOutcome | None:
        async with self._repository() as repository:
            return await repository.get_outcome(
                tenant_id=tenant_id,
                family_id=family_id,
                outcome_id=outcome_id,
            )


__all__ = ["FamilyNeedReadRepository", "SqlAlchemyFamilyNeedEventReader"]
