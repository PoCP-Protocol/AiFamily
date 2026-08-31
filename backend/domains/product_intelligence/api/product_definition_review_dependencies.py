"""Application-owned session wiring for the PDM operator review API."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..application.product_definition_review import ProductDefinitionReviewRepository
from ..infrastructure.product_definition_review_repository import (
    SqlAlchemyProductDefinitionReviewRepository,
)

_session_factory: async_sessionmaker[AsyncSession] | None = None


def configure_product_definition_review_session_factory(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> None:
    global _session_factory
    _session_factory = session_factory


def clear_product_definition_review_session_factory() -> None:
    configure_product_definition_review_session_factory(None)


async def get_product_definition_review_repository() -> AsyncGenerator[
    ProductDefinitionReviewRepository, None
]:
    if _session_factory is None:
        raise RuntimeError("product definition review session factory is not configured")
    async with _session_factory() as session:
        yield SqlAlchemyProductDefinitionReviewRepository(session)


__all__ = [
    "clear_product_definition_review_session_factory",
    "configure_product_definition_review_session_factory",
    "get_product_definition_review_repository",
]
