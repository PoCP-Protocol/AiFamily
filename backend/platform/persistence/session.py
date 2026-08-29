"""Engine and session factory for the platform persistence layer.

The database URL is read from the ``DATABASE_URL`` environment variable.
When it is unset (the default in test environments and in this repository's
Wave 1 CI, which has no Postgres service yet), we fall back to an in-memory
SQLite database via ``aiosqlite``. This mirrors the pattern used by the
source repository's only tested Python domain (`product_intelligence`, see
governance/MIGRATION_MANIFEST.yaml), which runs its repository tests against
an in-memory SQLite engine rather than requiring a live Postgres instance
for every test run.

Production deployments must set ``DATABASE_URL`` to a real
``postgresql+asyncpg://...`` URL. Nothing in this module hardcodes a
repository-specific physical path (R12) or reaches out to a model provider
(R7) — it is pure persistence wiring.
"""

from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DEFAULT_TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
DATABASE_URL_ENV_VAR = "DATABASE_URL"


def resolve_database_url() -> str:
    """Resolve the active database URL.

    ``DATABASE_URL`` wins when set. Otherwise fall back to an in-memory
    SQLite URL so the platform kernel is exercisable without any external
    service.
    """
    return os.environ.get(DATABASE_URL_ENV_VAR, DEFAULT_TEST_DATABASE_URL)


@lru_cache(maxsize=8)
def _cached_engine(database_url: str) -> AsyncEngine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        # A single shared in-memory SQLite database must use StaticPool so
        # every connection created by the engine sees the same database
        # rather than each connection getting its own private :memory: DB.
        from sqlalchemy.pool import StaticPool

        return create_async_engine(
            database_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(database_url, connect_args=connect_args)


def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Return the (cached) engine for the given database URL.

    Callers in tests may pass an explicit ``database_url`` to get an
    isolated engine independent of the process-wide default; production
    code should call this with no arguments so it resolves from the
    environment.
    """
    return _cached_engine(database_url or resolve_database_url())


def get_sessionmaker(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    engine = get_engine(database_url)
    return async_sessionmaker(bind=engine, expire_on_commit=False)
