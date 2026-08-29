"""Alembic environment for AiFamily.

Four deliberate design decisions, each stated because a future reader would
otherwise "fix" it back into a problem:

1. **Async engine, not a second sync driver.** Alembic's migration runner is
   synchronous, so the usual advice is "point Alembic at psycopg2 and the app at
   asyncpg". That would mean two Postgres drivers in `pyproject.toml` and two
   URLs to keep in sync — a second source of truth for "which database", plus a
   dependency whose only job is to exist. Instead this module uses Alembic's
   documented async pattern (`AsyncEngine` + `connection.run_sync`), so
   `asyncpg` (already the declared production driver) is the only Postgres
   driver in the project.

2. **No `sys.path` manipulation and no `sqlalchemy.url` in `alembic.ini`.**
   R12 (no implicit layout coupling) forbids resolving imports through cwd or
   path injection, so this module imports `backend.platform.persistence.session`
   as a normal installed package. The URL comes from that same module's
   `resolve_database_url()`, which reads `DATABASE_URL` — so `alembic upgrade`
   and the running FastAPI app can never target different databases, and no
   credential lives in version control.

3. **`target_metadata` is `None`, so `--autogenerate` is intentionally
   unavailable.** The baseline revision is a faithful replay of the legacy
   hand-written SQL (see `LINEARISATION_MAP.md`); no SQLAlchemy metadata
   describes those 151 tables, and inventing one would produce a baseline
   describing a schema the legacy system never had. Post-baseline revisions are
   hand-written per domain as those domains grow real models (T-05 onward).
   When a domain's `Base.metadata` becomes the authority for its own schema,
   register it here — until then `None` is the honest value, not a missing
   feature.

4. **`DATABASE_URL` must point at Postgres.** The legacy SQL uses
   Postgres-only constructs (`jsonb`, `uuid`, `CREATE TYPE ... AS ENUM`,
   `DO $$ ... $$`, partial indexes, `gen_random_uuid()`), so the baseline
   cannot apply to SQLite and does not pretend to. SQLite stays the fast
   domain-test path via `Base.metadata.create_all`, which bypasses Alembic
   entirely — see `docs/07_data/DATA_ARCHITECTURE.md`.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from backend.platform.persistence.session import resolve_database_url

# See docstring point 3. Explicitly None, not "not yet wired".
target_metadata = None


def _async_database_url() -> str:
    """Return the active database URL, forced onto an async driver.

    `resolve_database_url()` already yields async URLs for the drivers this
    project ships. A bare `postgresql://` (what an operator most naturally
    exports, and what `docker-compose.dev.yml` documents) is upgraded to
    `postgresql+asyncpg://` here rather than being rejected, so `alembic
    upgrade head` works with a plain libpq-style URL.
    """
    url = resolve_database_url()
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def _run_migrations(connection) -> None:  # noqa: ANN001 — sqlalchemy Connection
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_async_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_migrations_online_async() -> None:
    engine = async_engine_from_config(
        {"sqlalchemy.url": _async_database_url()},
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_migrations_online_async())
