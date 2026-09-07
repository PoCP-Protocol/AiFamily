"""Fixtures for the identity domain, same pattern as
`tests/domains/membership/conftest.py`:

* `fake_repo` -- dict-backed, proves the application layer depends on the
  port, not on SQLAlchemy.
* `sqlalchemy_repo` -- the real ORM mapping against in-memory SQLite. Always
  runs.
* `postgres_repo` -- the same ORM mapping against real Postgres. Runs only
  when `AIFAMILY_TEST_DATABASE_URL` is set, skips otherwise.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.identity.infrastructure.fake_repository import FakeIdentityRepository
from backend.domains.identity.infrastructure.sqlalchemy_models import Base
from backend.domains.identity.infrastructure.sqlalchemy_repository import (
    SqlAlchemyIdentityRepository,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


@pytest.fixture
def fake_repo() -> FakeIdentityRepository:
    return FakeIdentityRepository()


@pytest_asyncio.fixture
async def sqlalchemy_repo() -> AsyncIterator[SqlAlchemyIdentityRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield SqlAlchemyIdentityRepository(session)
    await engine.dispose()


@pytest_asyncio.fixture
async def postgres_repo() -> AsyncIterator[SqlAlchemyIdentityRepository]:
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)

    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            yield SqlAlchemyIdentityRepository(session)


@pytest.fixture(params=["fake", "sqlalchemy", "postgres"])
def repo(request: pytest.FixtureRequest):
    return request.getfixturevalue(f"{request.param}_repo")
