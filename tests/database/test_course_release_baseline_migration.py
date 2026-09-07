from importlib import import_module

import pytest

from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


def test_course_release_baseline_migration_has_expected_revision_and_columns():
    migration = import_module("database.migrations.versions.0070_course_release_baseline")
    assert migration.revision == "0070_course_release_baseline"
    assert migration.down_revision == "0069_course_content_lineage"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_course_release_baseline_migration_creates_and_drops_table():
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import MetaData, text

    migration = import_module("database.migrations.versions.0070_course_release_baseline")
    async with postgres_schema_engine(MetaData()) as engine, engine.begin() as connection:
            def run(sync_connection):
                context = MigrationContext.configure(
                    sync_connection, opts={"target_metadata": None}
                )
                with Operations.context(context):
                    migration.upgrade()
                    tables = sync_connection.execute(
                        text("select to_regclass('course_release_baseline')")
                    ).scalar()
                    assert tables == "course_release_baseline"
                    migration.downgrade()
                    assert sync_connection.execute(
                        text("select to_regclass('course_release_baseline')")
                    ).scalar() is None
            await connection.run_sync(run)
