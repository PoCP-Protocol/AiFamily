"""Fixtures for the membership domain.

Closes the R4 debt recorded in `governance/MIGRATION_MANIFEST.yaml`
(capability `membership`): the domain was bulk-migrated under a project-owner
override with the explicit note that it carried a known gap — its
`sqlalchemy_repository.py` docstring claimed "tests run this same class against
an in-memory SQLite engine (`tests/conftest.py`)" while no such directory
existed. This file makes that sentence true.

Every test using `repo` runs the acceptance path against each available
repository:

* `fake_repo` — dict-backed, proves the application layer depends on the port.
* `sqlalchemy_repo` — the real ORM mapping against in-memory SQLite, proves the
  models and the round-trip actually work. Always runs.
* `postgres_repo` — the same ORM mapping against real Postgres. Runs only when
  `AIFAMILY_TEST_DATABASE_URL` is set (see `docker-compose.dev.yml`), and
  **skips** otherwise so the no-Docker path stays green.

The `postgres_repo` parameter closes the gap this docstring previously recorded
as an open follow-up ("SQLite is not Postgres ... A real-Postgres pass is a
separate follow-up", T-03). What it proves is that the ORM mapping round-trips
on the database production actually uses — where `uuid`/`jsonb` are real types
rather than the `String`/`JSON` widenings `sqlalchemy_models.py` uses to stay
SQLite-compatible.

Still not covered, stated rather than hidden: the *legacy DDL's* own CHECK
constraints (activation-source allow-list, `external_effect = false`,
`decided_by NOT LIKE 'ai:%'`) are defined in the legacy SQL replayed by the
Alembic baseline, not in these SQLAlchemy models. `postgres_repo` builds its
tables from `Base.metadata`, so those constraints are absent from it too. Only
the domain-layer equivalents are exercised. Proving the DB-level constraints
needs the models reconciled against the baselined tables — that is T-05's job,
not a fixture's.

Shared constants and the catalogue seeder live in `helpers.py`, not here, so
test modules can import them by a real module path instead of reaching into a
conftest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.membership.infrastructure.fake_repository import FakeMembershipRepository
from backend.domains.membership.infrastructure.sqlalchemy_models import Base
from backend.domains.membership.infrastructure.sqlalchemy_repository import (
    SqlAlchemyMembershipRepository,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


@pytest.fixture
def fake_repo() -> FakeMembershipRepository:
    return FakeMembershipRepository()


@pytest_asyncio.fixture
async def sqlalchemy_repo() -> AsyncIterator[SqlAlchemyMembershipRepository]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield SqlAlchemyMembershipRepository(session)
    await engine.dispose()


@pytest_asyncio.fixture
async def postgres_repo() -> AsyncIterator[SqlAlchemyMembershipRepository]:
    """Same repository class, real Postgres. Skips unless the gate is open.

    `postgres_schema_engine` puts the tables in a throwaway schema rather than
    `public`, because `public` on a baselined database already owns
    `family_membership_plans` and friends from the legacy `0036` migration and
    these models map onto those names with widened column types.
    """
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)

    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            yield SqlAlchemyMembershipRepository(session)


@pytest.fixture(params=["fake", "sqlalchemy", "postgres"])
def repo(request: pytest.FixtureRequest):
    """Parametrised repository — every test using it runs against each backend.

    `postgres` skips (not fails) when `AIFAMILY_TEST_DATABASE_URL` is unset, so
    the default `uv run pytest` still passes with no Docker running.
    """
    return request.getfixturevalue(f"{request.param}_repo")
