"""legacy schema baseline — faithful replay of the linearised legacy SQL

Revision ID: 0001_legacy_schema_baseline
Revises: None
Create Date: 2026-08-29

This is the first Alembic revision in AiFamily's history and it deliberately
does *not* use `op.create_table`. It replays, verbatim and in order, the 62
linearised legacy SQL files in `database/baseline/`.

Why replay SQL instead of expressing the schema in SQLAlchemy operations
-----------------------------------------------------------------------
The legacy system's only authoritative schema definition was hand-written SQL
applied in filename order by a small Node runner (`tools/migrate.mjs` in the
source repository). There is no ORM model set to generate from. Re-expressing
151 tables / 60 enum types / 7 views / 373 indexes / 317 foreign keys / 1874
CHECK constraints as `op.*` calls would be a hand transcription of ~4300 lines
of SQL, and every transcription error would silently become a baseline that
describes a schema the legacy system never actually had. Replaying the files
byte-for-byte makes the baseline *verifiable*: the artefact under
`database/baseline/` is checksum-identical to the legacy migration it came
from, which `database/tests/test_baseline_linearisation.py` asserts.

Per `docs/07_data/DATA_ARCHITECTURE.md` §5, this revision is a faithful
snapshot only. It contains no target-state redesign: the by-domain schema
split (`identity.*` / `family.*` / `assessment.*` / ...) described in that
document's §2 is explicitly a later PR, so that "behaviour changed because we
redesigned" and "behaviour changed because we replayed history" can never be
confused in a bisect.

Provenance
----------
The legacy sources were `50_开发_dev/database/migrations/*.sql` in the source
repository; `database/migrations/LINEARISATION_MAP.md` records the full
62-row original-name -> new-sequence mapping and the ordering rationale for the
four duplicate-number groups (0022/0023/0024/0053). Only filenames changed;
SQL content is unmodified.

Downgrade
---------
There is no statement-level reverse for the legacy SQL — the legacy runner had
no `down` path at all (it documented an explicit "forward fix only" policy) —
and hand-writing 1800+ inverse statements would be fiction. So `downgrade()`
drops every table and enum type the baseline created, discovered by querying
the catalog rather than from a hardcoded list.

It does *not* do the obvious `DROP SCHEMA public CASCADE`: `alembic_version`
also lives in `public`, so dropping the schema destroys Alembic's own
bookkeeping table and the very next thing Alembic does is
`DELETE FROM alembic_version ...`, which then fails with `UndefinedTableError`
and leaves the database in a state where neither `upgrade` nor `downgrade`
reports the truth. (This was observed, not theorised — it is why the catalog
sweep below exists.) `alembic_version` is therefore excluded by name.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

from alembic import op

revision: str = "0001_legacy_schema_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Resolved relative to this module's own location, which is what Python's
# import system already guarantees. This is *not* the layout coupling R12
# forbids: R12 targets resolution through process cwd, sys.path injection, or
# hardcoded repository paths. `__file__`-relative resolution of a data file
# that ships alongside the code is stable under any cwd and contains no
# absolute path.
_BASELINE_SQL_DIR = pathlib.Path(__file__).resolve().parents[2] / "baseline"

EXPECTED_FILE_COUNT = 62


def _baseline_sql_files() -> list[pathlib.Path]:
    files = sorted(_BASELINE_SQL_DIR.glob("*.sql"))
    if len(files) != EXPECTED_FILE_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_FILE_COUNT} baseline SQL files in {_BASELINE_SQL_DIR.name}/, "
            f"found {len(files)}. The baseline is a fixed historical artefact — if files were "
            f"added or removed, LINEARISATION_MAP.md and EXPECTED_FILE_COUNT must be updated in "
            f"the same change, and a *new* revision (not an edit to this one) must carry any "
            f"schema delta."
        )
    return files


def _execute_script(connection, sql: str) -> None:  # noqa: ANN001 — sqlalchemy Connection
    """Execute a multi-statement SQL script as one raw simple query.

    Neither `op.execute()` nor `connection.exec_driver_sql()` can carry these
    files:

    * `op.execute(str)` wraps the string in `sqlalchemy.text()`, which treats
      `:` as a bind-parameter marker — the legacy SQL is full of `::jsonb`
      casts and would be mangled.
    * `exec_driver_sql()` on asyncpg goes through the extended query protocol,
      which is one-statement-only: asyncpg raises "cannot insert multiple
      commands into a prepared statement". Each legacy file is a multi-statement
      script containing `DO $$ ... $$` blocks, so naively splitting on `;` is
      not safe either (it would cut inside the dollar-quoted bodies).

    asyncpg's own `Connection.execute()` uses the *simple* query protocol when
    given no parameters, which accepts multiple statements — the same thing
    `psql` and the legacy Node runner did. `driver_connection` reaches that
    object, and `await_only` bridges back into the async world from inside the
    `run_sync` greenlet that Alembic's migration function runs in.

    The sync-driver branch is a fallback for completeness only — this revision
    requires Postgres, and `asyncpg` is the only Postgres driver this project
    declares, so in practice the async branch is always the one taken.
    """
    if connection.dialect.is_async:
        from sqlalchemy.util import await_only

        await_only(connection.connection.driver_connection.execute(sql))
    else:
        connection.exec_driver_sql(sql)


def upgrade() -> None:
    connection = op.get_bind()
    # pgcrypto is not required on Postgres 13+ (gen_random_uuid() is built in),
    # but the legacy SQL assumes the function exists and the legacy runner was
    # pointed at databases where an operator had already enabled it. Creating
    # it here makes the baseline self-sufficient on a genuinely empty database
    # instead of depending on out-of-band setup.
    _execute_script(connection, "CREATE EXTENSION IF NOT EXISTS pgcrypto")

    for sql_file in _baseline_sql_files():
        _execute_script(connection, sql_file.read_text(encoding="utf-8"))


ALEMBIC_BOOKKEEPING_TABLE = "alembic_version"


def downgrade() -> None:
    """Drop everything the baseline created, except Alembic's own version table.

    See the module docstring for why this is a catalog sweep and not
    `DROP SCHEMA public CASCADE`.
    """
    connection = op.get_bind()

    tables = [
        row[0]
        for row in connection.exec_driver_sql(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        if row[0] != ALEMBIC_BOOKKEEPING_TABLE
    ]
    # CASCADE handles the 7 views and all 317 foreign keys; dropping tables in
    # one statement avoids needing a topological order.
    if tables:
        _execute_script(
            connection, "DROP TABLE IF EXISTS " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"
        )

    enums = [
        row[0]
        for row in connection.exec_driver_sql(
            "SELECT DISTINCT t.typname FROM pg_type t "
            "JOIN pg_enum e ON e.enumtypid = t.oid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = 'public'"
        )
    ]
    if enums:
        _execute_script(
            connection, "DROP TYPE IF EXISTS " + ", ".join(f'"{e}"' for e in enums) + " CASCADE"
        )
