"""Unit of Work abstraction.

The source repository never had a formal UnitOfWork class — the closest
equivalent (``membership/infrastructure/sqlalchemy_repository.py``) was a
hand-rolled ``commit()``/``_stage()`` convention private to one domain (see
governance/MIGRATION_MANIFEST.yaml capability `platform_persistence_uow`,
disposition REIMPLEMENT). This module is a from-scratch design: an
async-context-manager UnitOfWork so that multiple repositories operating in
the same request/command either all commit together or all roll back
together — no partial writes, which is also a precondition for R6 (no state
mutation without audit): the audit event write and the domain write must be
able to share one transaction boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.platform.persistence.session import get_sessionmaker


class UnitOfWork(ABC):
    """Abstract Unit of Work.

    Usage::

        async with uow:
            await some_repository.add(thing)
            await other_repository.add(other_thing)
            await uow.commit()
        # if commit() was never called, __aexit__ rolls back automatically.
    """

    committed: bool

    async def __aenter__(self) -> UnitOfWork:
        self.committed = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...

    @abstractmethod
    async def ping(self) -> bool:
        """Return True if the underlying persistence backend is reachable.

        Used by the readiness endpoint (backend/apps/family_api) so
        `/ready` reflects a real database check, not just process liveness.
        """
        ...


class SqlAlchemyUnitOfWork(UnitOfWork):
    """UnitOfWork backed by a SQLAlchemy AsyncSession.

    One `SqlAlchemyUnitOfWork` instance owns exactly one `AsyncSession` for
    the lifetime of the `async with` block. Repositories constructed inside
    the block must be handed `self.session` so their writes participate in
    the same transaction.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory or get_sessionmaker()
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        await super().__aenter__()
        self.session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await super().__aexit__(exc_type, exc, tb)
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def commit(self) -> None:
        assert self.session is not None, "UnitOfWork used outside of 'async with'"
        await self.session.commit()
        self.committed = True

    async def rollback(self) -> None:
        assert self.session is not None, "UnitOfWork used outside of 'async with'"
        await self.session.rollback()

    async def ping(self) -> bool:
        assert self.session is not None, "UnitOfWork used outside of 'async with'"
        result = await self.session.execute(text("SELECT 1"))
        return result.scalar_one() == 1
