"""Engine and session factory for the platform persistence layer.

Two environment variables, two different jobs:

``DATABASE_URL``
    The database this process actually serves from. Unset falls back to an
    in-memory SQLite database via ``aiosqlite``, so the platform kernel and
    the domain repository tests are exercisable with no external service —
    that fast path is deliberate and load-bearing, not a stopgap. Production
    deployments must set this to a real ``postgresql+asyncpg://...`` URL. The
    Alembic baseline (``database/migrations/``) reads this same variable, so
    ``alembic upgrade head`` and the running app can never disagree about
    which database they mean.

``AIFAMILY_TEST_DATABASE_URL``
    Opt-in, test-only. Points at a disposable Postgres (see
    ``docker-compose.dev.yml``) for the tests that exist specifically to prove
    Postgres-only behaviour. Unset means those tests **skip**, never that they
    quietly rerun against SQLite. Kept separate from ``DATABASE_URL`` because
    those tests create and drop schema objects, and aiming that at whatever a
    developer happened to have in ``DATABASE_URL`` is how a dev database dies.

Nothing in this module hardcodes a repository-specific physical path (R12) or
reaches out to a model provider (R7) — it is pure persistence wiring.
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

#: Opt-in URL for the real-Postgres test path. Tests that need Postgres
#: semantics (``jsonb``, enum types, DB-level CHECK constraints, ``DO $$``
#: blocks — none of which SQLite has) read this via
#: :func:`resolve_test_database_url` and **skip** when it is unset, so a
#: contributor with no Docker running still gets a full green SQLite run. It is
#: a separate variable from ``DATABASE_URL`` on purpose: pointing
#: ``DATABASE_URL`` at a database and then having the test suite drop and
#: recreate tables in it is exactly how somebody loses a dev database.
TEST_DATABASE_URL_ENV_VAR = "AIFAMILY_TEST_DATABASE_URL"

#: Deprecated predecessor, honoured only as a fallback. `product_intelligence`
#: shipped its real-Postgres tests before a repository-wide convention existed
#: and invented its own variable. Keeping it working means nobody's existing
#: local setup or CI job breaks; keeping it *second* means
#: ``AIFAMILY_TEST_DATABASE_URL`` is unambiguously the one to set. Remove once
#: no runbook references it.
LEGACY_TEST_DATABASE_URL_ENV_VARS = ("PI_POSTGRES_TEST_DSN",)


def resolve_database_url() -> str:
    """Resolve the active database URL.

    ``DATABASE_URL`` wins when set. Otherwise fall back to an in-memory
    SQLite URL so the platform kernel is exercisable without any external
    service.
    """
    return os.environ.get(DATABASE_URL_ENV_VAR, DEFAULT_TEST_DATABASE_URL)


def resolve_test_database_url() -> str | None:
    """Return the opt-in real-Postgres test URL, or ``None`` when not configured.

    ``None`` means "skip the Postgres-gated tests", never "fall back to
    SQLite" — a test whose whole point is to exercise Postgres behaviour must
    not silently pass against a database that cannot express that behaviour.

    A bare ``postgresql://`` URL (the form an operator most naturally exports,
    and the form ``docker-compose.dev.yml`` documents) is normalised onto the
    async driver this project ships, so callers never have to remember the
    ``+asyncpg`` suffix.
    """
    url = os.environ.get(TEST_DATABASE_URL_ENV_VAR)
    if not url:
        for legacy_var in LEGACY_TEST_DATABASE_URL_ENV_VARS:
            url = os.environ.get(legacy_var)
            if url:
                break
    if not url:
        return None
    for bare_prefix in ("postgresql://", "postgres://"):
        if url.startswith(bare_prefix):
            return "postgresql+asyncpg://" + url[len(bare_prefix) :]
    return url


def is_postgres_url(database_url: str) -> bool:
    return database_url.startswith(("postgresql", "postgres://"))


def clear_engine_cache() -> None:
    """Clear cached engines without changing existing sessionmaker bindings.

    The cache is process-local state. HTTP integration tests use this hook
    between application lifecycles so a new app resolves and constructs its
    engine from the current database URL. Clearing the cache deliberately
    does not dispose an engine: a sessionmaker already handed to an app keeps
    its original engine for the rest of that app's lifecycle.
    """
    _cached_engine.cache_clear()


@lru_cache(maxsize=8)
def _cached_engine(database_url: str) -> AsyncEngine:
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
    if is_postgres_url(database_url):
        # asyncpg caches a prepared statement per distinct SQL string. Behind a
        # connection pooler in transaction mode (PgBouncer and equivalents),
        # cached statements belong to a server connection the client no longer
        # owns after its transaction ends, which surfaces as sporadic
        # `InvalidSQLStatementNameError`. Disabling the cache is the documented
        # way to make asyncpg pooler-safe; the cost is re-parsing per execution,
        # which is not the bottleneck for this workload.
        #
        # pool_pre_ping guards the other half of the problem: a connection that
        # the server or an intermediary closed while idle would otherwise fail
        # the first query of the next request rather than being replaced.
        return create_async_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"statement_cache_size": 0},
        )
    return create_async_engine(database_url)


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
