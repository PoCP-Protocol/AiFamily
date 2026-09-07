from importlib import import_module

def test_course_release_baseline_migration_has_expected_revision_and_columns():
    migration = import_module("database.migrations.versions.0070_course_release_baseline")
    assert migration.revision == "0070_course_release_baseline"
    assert migration.down_revision == "0069_course_content_lineage"
    assert callable(migration.upgrade)
    assert callable(migration.downgrade)
