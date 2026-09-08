"""Deployment-owned dependencies for the production Commerce read slice."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.commerce.application.ports import CommerceRepositoryPort
from backend.domains.commerce.infrastructure.sqlalchemy_repository import (
    SqlAlchemyCommerceRepository,
)


async def provide_commerce_repository(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[CommerceRepositoryPort]:
    """Yield one request-scoped repository and always close its session."""

    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("session_factory must be an async_sessionmaker")
    async with session_factory() as session:
        yield SqlAlchemyCommerceRepository(session)


__all__ = ["provide_commerce_repository"]
