"""Every ORM column exists in the migrated schema.

This is the guardrail for the failure T-03 recorded and asked not to repeat:
`product_intelligence` kept a private SQL copy inside its domain directory, so
three columns its ORM required were never created by the Alembic baseline — and
its tests did not catch it, because they built their own schema with
`Base.metadata.create_all` and therefore agreed with the ORM by construction.

Every other test in this package has that same blind spot. `create_all` cannot
detect a drift between the ORM and the migrations, because it *is* the ORM.
Closing the loop needs a database built by Alembic and compared against
`Base.metadata`, which is what this module does.

Gated on `AIFAMILY_TEST_DATABASE_URL`, like the rest of the real-Postgres path,
because `alembic upgrade head` replays legacy SQL that only Postgres can execute
(`gen_random_uuid()`, `plpgsql` triggers, partial indexes over `jsonb`). Skipping
is honest: the assertion is simply not evaluable without the database it is
about.

Direction of the check is one-way on purpose. Every ORM column must exist in the
migrated table; the migrated table may have columns the ORM does not map. That
asymmetry is deliberate — the legacy 0035 tables carry columns this domain has no
use for, and requiring the ORM to map all of them would force this module to grow
fields it does not need in order to satisfy a test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.domains.service.infrastructure.sqlalchemy_models import Base
from tests.support.postgres import SKIP_REASON, postgres_test_url

pytestmark = pytest.mark.asyncio

#: Tables 0035 creates and this revision only adds to. Split out from the one
#: table this domain owns outright so a failure says which side is at fault.
BASELINE_TABLES = frozenset(
    {
        "family_service_providers",
        "family_service_offerings",
        "family_service_availability_slots",
        "family_booking_requests",
        "family_booking_service_records",
    }
)
OWNED_TABLES = frozenset({"family_service_private_checkin_drafts"})


@pytest_asyncio.fixture
async def migrated_columns() -> dict[str, set[str]]:
    """Column names per table from a database Alembic built, not `create_all`.

    Reads the *existing* migrated database rather than running `alembic upgrade`
    here: the migration chain is verified by `alembic upgrade head` in the task's
    acceptance run and by `database/tests/`, and re-running it per test would make
    this module own a concern (migration execution) that is not what it checks.
    """
    url = postgres_test_url()
    if url is None:
        pytest.skip(SKIP_REASON)

    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            present = set(
                (
                    await conn.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = current_schema()"
                        )
                    )
                )
                .scalars()
                .all()
            )
            wanted = (BASELINE_TABLES | OWNED_TABLES) & present
            if not wanted:
                pytest.skip(
                    "the gated database has none of the service booking tables — it was not "
                    "built by `alembic upgrade head` (see database/migrations/env.py)"
                )

            def _columns(sync_conn):
                inspector = inspect(sync_conn)
                return {t: {c["name"] for c in inspector.get_columns(t)} for t in wanted}

            return await conn.run_sync(_columns)
    finally:
        await engine.dispose()


async def test_every_orm_column_exists_in_the_migrated_schema(
    migrated_columns: dict[str, set[str]],
) -> None:
    """An ORM column with no migrated counterpart is the T-03 bug, exactly."""
    missing: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in migrated_columns:
            missing.append(f"{table.name}: table absent from the migrated schema")
            continue
        for column in table.columns:
            if column.name not in migrated_columns[table.name]:
                origin = (
                    "must be added by a migration"
                    if table.name in BASELINE_TABLES
                    else "this domain owns the table, so its revision must create the column"
                )
                missing.append(f"{table.name}.{column.name} ({origin})")

    assert not missing, (
        "ORM/migration drift — these columns exist in "
        "backend/domains/service/infrastructure/sqlalchemy_models.py but not in the "
        "Alembic-built schema. This is the `product_intelligence` failure T-03 "
        "recorded: the SQLite tests cannot see it because they build the schema from "
        "the ORM itself.\n" + "\n".join(sorted(missing))
    )


async def test_this_domain_keeps_no_private_sql_copy() -> None:
    """No `.sql` file under `backend/domains/service/`.

    The drift above becomes possible the moment a domain owns a second copy of
    its schema. Checking for the *file* rather than only for the symptom means a
    future private copy fails here on the fast path, without needing Postgres.
    """
    from pathlib import Path

    domain_root = Path(__file__).resolve().parents[3] / "backend" / "domains" / "service"
    strays = sorted(p.name for p in domain_root.rglob("*.sql"))
    assert not strays, (
        "backend/domains/service must not hold its own SQL: the schema's single source is "
        f"database/baseline/ + database/migrations/. Found: {strays}"
    )
