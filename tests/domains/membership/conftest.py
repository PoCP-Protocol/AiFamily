"""Fixtures for the membership domain.

Closes the R4 debt recorded in `governance/MIGRATION_MANIFEST.yaml`
(capability `membership`): the domain was bulk-migrated under a project-owner
override with the explicit note that it carried a known gap — its
`sqlalchemy_repository.py` docstring claimed "tests run this same class against
an in-memory SQLite engine (`tests/conftest.py`)" while no such directory
existed. This file makes that sentence true.

Every test runs the acceptance path twice, once per repository:

* `fake_repo` — dict-backed, proves the application layer depends on the port.
* `sqlalchemy_repo` — the real ORM mapping against in-memory SQLite, proves the
  models and the round-trip actually work.

Known gap, stated rather than hidden: SQLite is not Postgres. The DB-level
CHECK constraints (activation-source allow-list, `external_effect = false`,
`decided_by NOT LIKE 'ai:%'`) are not exercised here — the domain-layer
equivalents are. A real-Postgres pass is a separate follow-up.

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


@pytest.fixture(params=["fake", "sqlalchemy"])
def repo(request: pytest.FixtureRequest):
    """Parametrised repository — every test using it runs against both."""
    return request.getfixturevalue(f"{request.param}_repo")
