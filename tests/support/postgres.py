"""Shared helper for the opt-in real-Postgres test path.

Why this exists
---------------
Every domain repository test in this repository runs against
`sqlite+aiosqlite:///:memory:` — fast, no external service, and the default so
that a contributor with no Docker still gets a full green run. That path is
deliberate and stays. But SQLite is not Postgres, and the gap is not cosmetic:
`membership`'s and `product_intelligence`'s SQLAlchemy models widen `uuid` to
`String` and `jsonb` to `JSON` precisely so the same models can run on SQLite,
which means the SQLite pass proves the *mapping* works and proves nothing about
whether it works on the database production uses. Both domains' conftests said
so in prose ("A real-Postgres pass is a separate follow-up"). This module is
that follow-up's plumbing.

Contract
--------
`postgres_test_url()` returns `None` when `AIFAMILY_TEST_DATABASE_URL` is unset,
and callers **skip**. It never falls back to SQLite: a test whose purpose is to
prove Postgres behaviour must not report success against a database that cannot
express that behaviour.

Schema isolation
----------------
Each engine gets a **dedicated, randomly-named Postgres schema** that is
dropped when the fixture tears down, rather than creating tables in `public`.
Three reasons, all of which cost real debugging time if ignored:

1. `public` on a baselined database already holds the 151 legacy tables, and
   several domain models map onto legacy table *names* (`family_membership_plans`
   comes from the legacy `0036` migration) with deliberately widened column
   types. `create_all` into `public` would either collide with the real table or,
   worse, silently bind to it and let a test mutate the baselined schema.
2. Tests can run concurrently (`pytest-xdist`, or simply two agents on one box —
   this repository has several sessions working in parallel). Per-run schemas
   cannot interfere.
3. `DROP SCHEMA ... CASCADE` is one statement and cannot leave orphans, unlike
   dropping a list of tables that may have grown since the list was written.

See `docker-compose.dev.yml` for how to stand the database up.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.platform.persistence.session import (
    TEST_DATABASE_URL_ENV_VAR,
    resolve_test_database_url,
)

SKIP_REASON = (
    f"{TEST_DATABASE_URL_ENV_VAR} is not set — real-Postgres test skipped. Start the database with "
    "`docker compose -f docker-compose.dev.yml up -d` and export "
    f"{TEST_DATABASE_URL_ENV_VAR}=postgresql+asyncpg://aifamily:aifamily@localhost:55442/aifamily_test"
)


def postgres_test_url() -> str | None:
    """The opt-in Postgres URL, or ``None`` when the gated path is disabled."""
    return resolve_test_database_url()


def _unique_schema_name() -> str:
    # Postgres identifiers are limited to 63 bytes; this is well inside it.
    return f"t_{uuid.uuid4().hex[:16]}"


@asynccontextmanager
async def postgres_schema_engine(metadata: MetaData) -> AsyncIterator[AsyncEngine]:
    """Yield an engine whose default schema is a fresh, disposable one.

    `metadata`'s tables are created inside that schema. The schema is dropped on
    exit even if the test failed, so a failing run never leaves state that makes
    the *next* run fail for a different reason.

    Setting `search_path` per connection (rather than stamping `schema=` onto
    every model) means domain models stay schema-agnostic — they must, since the
    same classes run against SQLite, which has no schemas.
    """
    url = postgres_test_url()
    if url is None:  # pragma: no cover — callers skip before reaching here
        raise RuntimeError(SKIP_REASON)

    schema = _unique_schema_name()

    # A bootstrap engine on the default search_path, used only for CREATE/DROP
    # SCHEMA. Kept separate from the test engine so the test engine's connections
    # are pinned to the new schema from their very first statement.
    bootstrap = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with bootstrap.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        engine = create_async_engine(
            url,
            connect_args={
                "statement_cache_size": 0,
                # asyncpg passes `server_settings` straight through as
                # connection-level GUCs, so every connection this engine hands
                # out starts already pointed at the test schema.
                "server_settings": {"search_path": schema},
            },
        )
        try:
            async with engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
            yield engine
        finally:
            await engine.dispose()
    finally:
        async with bootstrap.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap.dispose()
