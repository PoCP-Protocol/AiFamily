"""Fixtures for the service booking domain.

Every test using `repo` runs the same path against each available repository,
mirroring `tests/domains/membership/conftest.py`:

* `fake_repo` — dict-backed, proves the application layer depends on the port.
* `sqlalchemy_repo` — the real ORM mapping against in-memory SQLite, proves the
  models and the round-trip work. Always runs.
* `postgres_repo` — the same ORM mapping against real Postgres. Runs only when
  `AIFAMILY_TEST_DATABASE_URL` is set and **skips** otherwise, so the no-Docker
  path stays green.

Stated rather than hidden: `postgres_repo` builds its tables from
`Base.metadata`, so the *legacy DDL's* own CHECK constraints from
`database/baseline/0035_family_service_booking_objects.sql`
(`external_effect = false`, `fixture_only = true`, the `source_page_id`
allow-list, `reserved_count <= capacity`) are absent from it. Only the
domain-layer equivalents are exercised by these tests. What `postgres_repo` does
prove is that the ORM mapping round-trips on the database production uses, where
`uuid`/`jsonb` are real types rather than the `String`/`JSON` widenings the
models use to stay SQLite-compatible.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.service.infrastructure.fake_repository import (
    FakeConsentQuery,
    FakeServiceRepository,
)
from backend.domains.service.infrastructure.sqlalchemy_models import Base
from backend.domains.service.infrastructure.sqlalchemy_repository import (
    SqlAlchemyServiceRepository,
)
from backend.platform.audit.recorder import AuditRecorder
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


@pytest.fixture
def fake_repo() -> FakeServiceRepository:
    return FakeServiceRepository()


@pytest_asyncio.fixture
async def sqlalchemy_repo() -> AsyncIterator[SqlAlchemyServiceRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield SqlAlchemyServiceRepository(session)
    await engine.dispose()


@pytest_asyncio.fixture
async def postgres_repo() -> AsyncIterator[SqlAlchemyServiceRepository]:
    """Same repository class, real Postgres. Skips unless the gate is open.

    `postgres_schema_engine` puts the tables in a throwaway schema rather than
    `public`: `public` on a baselined database already owns
    `family_service_providers` and friends from the legacy `0035` migration, and
    these models map onto those names with widened column types.
    """
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)

    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            yield SqlAlchemyServiceRepository(session)


@pytest.fixture(params=["fake", "sqlalchemy", "postgres"])
def repo(request: pytest.FixtureRequest):
    """Parametrised repository — every test using it runs against each backend."""
    return request.getfixturevalue(f"{request.param}_repo")


@pytest.fixture
def consent() -> FakeConsentQuery:
    """A consent source with no grants. Tests add what they need.

    Empty by default on purpose: a fixture that pre-granted consent would make
    every booking test pass the gate without saying so, and the "no consent"
    refusal would be the only test that looked deliberate.
    """
    return FakeConsentQuery()


@pytest.fixture
def recorder() -> AuditRecorder:
    return AuditRecorder()
