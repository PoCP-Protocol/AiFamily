"""Fixtures for the loyalty points domain.

Same dual-repository shape as the membership tests: every test using the `repo`
fixture runs twice — against the dict-backed Fake (proving the application layer
depends on the port) and against the real ORM mapping on in-memory SQLite
(proving the models and round-trip work).

Known gap, stated rather than hidden: SQLite is not Postgres. The DB-level CHECK
constraints this schema will carry in a real migration are not exercised here —
only their domain-layer equivalents are.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.loyalty_points.infrastructure.fake_repository import (
    FakeLoyaltyPointsRepository,
)
from backend.domains.loyalty_points.infrastructure.sqlalchemy_models import Base
from backend.domains.loyalty_points.infrastructure.sqlalchemy_repository import (
    SqlAlchemyLoyaltyPointsRepository,
)


@pytest.fixture
def fake_points_repo() -> FakeLoyaltyPointsRepository:
    return FakeLoyaltyPointsRepository()


@pytest_asyncio.fixture
async def sqlalchemy_points_repo() -> AsyncIterator[SqlAlchemyLoyaltyPointsRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield SqlAlchemyLoyaltyPointsRepository(session)
    await engine.dispose()


@pytest.fixture(params=["fake", "sqlalchemy"])
def repo(request: pytest.FixtureRequest):
    return request.getfixturevalue(f"{request.param}_points_repo")
