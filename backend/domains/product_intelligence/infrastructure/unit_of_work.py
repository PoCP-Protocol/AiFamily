"""Unit of Work — owns transaction commit/rollback at the request boundary.

PR-001R (chief-architect review on PR #27, item 6): `SqlAlchemyProductIntelligenceRepository.save_*`
no longer commits internally (only `merge()`+`flush()`). Something has to
own the commit — that something is this class, used by
`api/dependencies.py::get_repository` (and by test fixtures), not the
repository itself. This is what lets a future PR (e.g. the Compiler writing
`ProductDefinition` + `ServiceBlueprintVersion` together) commit multiple
aggregate saves atomically in one request, instead of each `save_*` call
being its own committed transaction.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object) -> None:
        if exc_type is not None:
            await self._session.rollback()
            return
        await self._session.commit()
