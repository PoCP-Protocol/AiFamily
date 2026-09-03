"""Proves the Alembic baseline actually applies to a real, empty Postgres.

`tests/database/test_baseline_linearisation.py` proves the baseline SQL is the
legacy SQL. This module proves the baseline *runs* — that the replay mechanism
in `0001_legacy_schema_baseline.py` (raw simple-query execution through asyncpg,
which needed a specific escape hatch to handle multi-statement `DO $$` scripts)
works end to end, and that the resulting schema has the object counts a
faithful replay must produce.  Additive revisions are asserted separately so
their tables cannot silently change the historical baseline contract.

Gated on `AIFAMILY_TEST_DATABASE_URL` and skipped otherwise. Each run gets a
throwaway *database* rather than a schema, because `alembic upgrade head`
targets `public` and stamps `alembic_version`: running it inside the shared test
database would leave 151 legacy tables behind for every other test to trip over.

Expected baseline object counts come from an independent measurement, not from
this code: the 62 legacy files were applied to a scratch Postgres 16 with
`psql` (bypassing Alembic entirely) and the catalog was counted.  The head
expectation adds only tables owned by revisions 0002-0008; views and enum types
remain unchanged.  If the concurrent 0009 WIP revision is present, its single
additional table has its own explicit head expectation.  Keeping these two
contracts separate makes schema drift auditable instead of hiding it by
changing the baseline constant.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import uuid

import pytest
import yaml
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Measured by applying the 62 linearised files with psql on an empty Postgres 16.
EXPECTED_LEGACY_TABLES = 151
EXPECTED_VIEWS = 7
EXPECTED_ENUM_TYPES = 60

_ALEMBIC_BOOKKEEPING_TABLES = 1

# Additive table owners after the baseline through revision 0008:
# 0002 (audit), 0003 (private check-in), 0006 (Human Gate), 0007 (outbox),
# and 0008 (experience run, event, checkpoint).
EXPECTED_0008_ADDITIVE_TABLES = 7
EXPECTED_BASELINE_COUNTS = {
    "tables": EXPECTED_LEGACY_TABLES + _ALEMBIC_BOOKKEEPING_TABLES,
    "views": EXPECTED_VIEWS,
    "enums": EXPECTED_ENUM_TYPES,
}
EXPECTED_0008_COUNTS = {
    "tables": EXPECTED_BASELINE_COUNTS["tables"] + EXPECTED_0008_ADDITIVE_TABLES,
    "views": EXPECTED_VIEWS,
    "enums": EXPECTED_ENUM_TYPES,
}

# AI-runtime heads are recognized explicitly, but are not silently folded into
# the 0004-0008 responsibility boundary.
EXPECTED_HEAD_COUNTS_BY_REVISION = {
    "0008_experience_runs": EXPECTED_0008_COUNTS,
    "0009_ai_model_drafts": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 1,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    "0010_experience_run_interactions": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 2,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    # 0011 only adds Human Gate claim columns; 0012 adds the AgentRun and
    # Trace runtime-owned tables on top of the same additive chain.
    "0012_ai_agent_runs": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 4,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    # 0013 adds authorization lease/audit tables; 0011 only changes Human
    # Gate columns, so the additive table count increases by two.
    "0013_ai_authorization_leases": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 6,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    # 0014 adds the pending ToolCall/Named Action outbox table.
    "0014_tool_action_outbox": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 7,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    # 0015 adds the durable evidence-bound achievement projection table.
    "0015_ai_achievement_projections": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 8,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    # 0016-0053 add 42 runtime-owned tables after the eight tables owned by
    # 0009-0015. Alter-only revisions do not change the object count. Keeping
    # 0054 adds the durable engagement-review envelope. Keeping the current
    # head explicit makes a future migration fail until its object ownership
    # has been reviewed instead of silently accepting schema drift.
    "0054_ai_engagement_draft_reviews": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 51,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    # 0055 owns the family_need domain's first PostgreSQL persistence: five
    # tables (need_signals, family_needs, need_profiles, solution_drafts,
    # family_need_events).
    "0055_family_need_domain": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 56,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    # 0056 owns product_intelligence's course_content table (one table).
    "0056_course_content": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 57,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
    # 0057 adds the immutable UI-05 growth-plan review companion envelope.
    "0057_ai_growth_plan_draft_reviews": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 58,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
}

_MODEL_DRAFTS_ADR = (
    REPO_ROOT / "governance" / "ADR" / "ADR-0045-durable-model-draft-provenance-registry.md"
)
_MODEL_DRAFTS_MIGRATION = (
    REPO_ROOT / "database" / "migrations" / "versions" / "0009_ai_model_drafts.py"
)
_EXPERIENCE_INTERACTIONS_ADR = (
    REPO_ROOT / "governance" / "ADR" / "ADR-0047-async-sql-experience-run-ledger.md"
)
_EXPERIENCE_INTERACTIONS_MIGRATION = (
    REPO_ROOT / "database" / "migrations" / "versions" / "0010_experience_run_interactions.py"
)
_AGENT_RUNS_ADR = (
    REPO_ROOT / "governance" / "ADR" / "ADR-0053-agent-run-trace-durable-persistence.md"
)
_AGENT_RUNS_MIGRATION = REPO_ROOT / "database" / "migrations" / "versions" / "0012_ai_agent_runs.py"
_AUTHORIZATION_LEASE_ADR = (
    REPO_ROOT / "governance" / "ADR" / "ADR-0055-agent-authorization-lease-persistence.md"
)
_AUTHORIZATION_LEASE_MIGRATION = (
    REPO_ROOT / "database" / "migrations" / "versions" / "0013_ai_authorization_leases.py"
)
_TOOL_ACTION_OUTBOX_ADR = (
    REPO_ROOT / "governance" / "ADR" / "ADR-0057-tool-action-durable-outbox.md"
)
_TOOL_ACTION_OUTBOX_MIGRATION = (
    REPO_ROOT / "database" / "migrations" / "versions" / "0014_tool_action_outbox.py"
)
_ACHIEVEMENT_PROJECTION_ADR = (
    REPO_ROOT / "governance" / "ADR" / "ADR-0058-durable-achievement-projection.md"
)
_ACHIEVEMENT_PROJECTION_MIGRATION = (
    REPO_ROOT / "database" / "migrations" / "versions" / "0015_ai_achievement_projections.py"
)
_MIGRATION_MANIFEST = REPO_ROOT / "governance" / "MIGRATION_MANIFEST.yaml"


@pytest.fixture
async def throwaway_database_url() -> str:
    """Create an empty database, yield its URL, drop it afterwards."""
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)

    db_name = f"alembic_baseline_{uuid.uuid4().hex[:12]}"

    # CREATE/DROP DATABASE cannot run inside a transaction block, hence
    # AUTOCOMMIT rather than the usual `engine.begin()`.
    admin = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        # `str(URL)` masks the password as "***"; the subprocess needs the real
        # one, so render explicitly.
        yield make_url(admin_url).set(database=db_name).render_as_string(hide_password=False)
    finally:
        async with admin.connect() as conn:
            # Terminate leftover sessions first: asyncpg pools can hold a
            # connection open past engine disposal, and DROP DATABASE fails
            # while any session is attached.
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    """Invoke Alembic as a subprocess, exactly as an operator or CI would.

    Calling `alembic.command.upgrade()` in-process would skip `alembic.ini`
    parsing and `env.py` loading — the two places T-03 actually changed, and the
    two places that broke during development (an `alembic.ini` comment with a
    non-ASCII character made `configparser` fail under Windows' GBK locale).
    A subprocess exercises the real entry point.
    """
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


def _head_from_result(result: subprocess.CompletedProcess[str]) -> str:
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"migration graph must have exactly one head, got: {lines!r}"
    return lines[0].split(maxsplit=1)[0]


def _migration_is_tracked(path: pathlib.Path) -> bool:
    """Require a migration to be tracked before governance can approve it."""

    try:
        relative_path = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative_path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and relative_path in result.stdout.splitlines()


def _model_drafts_head_is_approved() -> bool:
    """Require both the exact ADR and an approved manifest entry for 0009."""

    if (
        not _migration_is_tracked(_MODEL_DRAFTS_MIGRATION)
        or not _MODEL_DRAFTS_ADR.is_file()
        or not _MIGRATION_MANIFEST.is_file()
    ):
        return False
    try:
        manifest = yaml.safe_load(_MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
    if not isinstance(entries, list):
        return False
    approved_statuses = {"APPROVED", "ACCEPTED", "DONE", "MIGRATED", "MIGRATED_TESTED"}
    return any(
        isinstance(entry, dict)
        and "0009_ai_model_drafts" in repr(entry)
        and str(entry.get("status", "")).upper() in approved_statuses
        for entry in entries
    )


def _experience_interactions_head_is_approved() -> bool:
    """Require ADR-0047 and its explicit migration-manifest registration."""

    if (
        not _migration_is_tracked(_EXPERIENCE_INTERACTIONS_MIGRATION)
        or not _EXPERIENCE_INTERACTIONS_ADR.is_file()
        or not _MIGRATION_MANIFEST.is_file()
    ):
        return False
    try:
        manifest = yaml.safe_load(_MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
    approved_statuses = {"APPROVED", "ACCEPTED", "DONE", "MIGRATED", "MIGRATED_TESTED"}
    return any(
        isinstance(entry, dict)
        and "experience_run_http_sql_ledger" in repr(entry)
        and str(entry.get("status", "")).upper() in approved_statuses
        for entry in entries
    )


def _agent_runs_head_is_approved() -> bool:
    """Require ADR-0053 and its explicit migration-manifest registration."""

    if (
        not _migration_is_tracked(_AGENT_RUNS_MIGRATION)
        or not _AGENT_RUNS_ADR.is_file()
        or not _MIGRATION_MANIFEST.is_file()
    ):
        return False
    try:
        manifest = yaml.safe_load(_MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
    approved_statuses = {"APPROVED", "ACCEPTED", "DONE", "MIGRATED", "MIGRATED_TESTED"}
    return any(
        isinstance(entry, dict)
        and "agent_runtime" in repr(entry)
        and "0012_ai_agent_runs.py" in repr(entry)
        and str(entry.get("status", "")).upper() in approved_statuses
        for entry in entries
    )


def _authorization_lease_head_is_approved() -> bool:
    """Require ADR-0055 and its explicit migration-manifest registration."""

    if (
        not _migration_is_tracked(_AUTHORIZATION_LEASE_MIGRATION)
        or not _AUTHORIZATION_LEASE_ADR.is_file()
        or not _MIGRATION_MANIFEST.is_file()
    ):
        return False
    try:
        manifest = yaml.safe_load(_MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
    approved_statuses = {"APPROVED", "ACCEPTED", "DONE", "MIGRATED", "MIGRATED_TESTED"}
    return any(
        isinstance(entry, dict)
        and "0013_ai_authorization_leases.py" in repr(entry)
        and "ADR-0055-agent-authorization-lease-persistence.md" in repr(entry)
        and str(entry.get("status", "")).upper() in approved_statuses
        for entry in entries
    )


def _tool_action_outbox_head_is_approved() -> bool:
    """Require ADR-0057 and its explicit migration-manifest registration."""

    if (
        not _migration_is_tracked(_TOOL_ACTION_OUTBOX_MIGRATION)
        or not _TOOL_ACTION_OUTBOX_ADR.is_file()
        or not _MIGRATION_MANIFEST.is_file()
    ):
        return False
    try:
        manifest = yaml.safe_load(_MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
    approved_statuses = {"APPROVED", "ACCEPTED", "DONE", "MIGRATED", "MIGRATED_TESTED"}
    return any(
        isinstance(entry, dict)
        and "0014_tool_action_outbox.py" in repr(entry)
        and "ADR-0057-tool-action-durable-outbox.md" in repr(entry)
        and str(entry.get("status", "")).upper() in approved_statuses
        for entry in entries
    )


def _achievement_projection_head_is_approved() -> bool:
    """Require ADR-0058 and its explicit migration-manifest registration."""

    if (
        not _migration_is_tracked(_ACHIEVEMENT_PROJECTION_MIGRATION)
        or not _ACHIEVEMENT_PROJECTION_ADR.is_file()
        or not _MIGRATION_MANIFEST.is_file()
    ):
        return False
    try:
        manifest = yaml.safe_load(_MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return False
    entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
    approved_statuses = {"APPROVED", "ACCEPTED", "DONE", "MIGRATED", "MIGRATED_TESTED"}
    return any(
        isinstance(entry, dict)
        and "0015_ai_achievement_projections.py" in repr(entry)
        and "ADR-0058-durable-achievement-projection.md" in repr(entry)
        and str(entry.get("status", "")).upper() in approved_statuses
        for entry in entries
    )


def _assert_accepted_head(head: str) -> str:
    """Validate one registered head and reject unregistered concurrent WIP."""

    assert head in EXPECTED_HEAD_COUNTS_BY_REVISION, (
        "unknown migration head; update the explicit object-owner map and review the chain: "
        f"{head!r}"
    )
    if head == "0009_ai_model_drafts":
        assert _model_drafts_head_is_approved(), (
            "0009_ai_model_drafts is present as head but is not approved: require "
            "governance/ADR/ADR-0045-durable-model-draft-provenance-registry.md and an approved "
            "MIGRATION_MANIFEST entry"
        )
    if head == "0010_experience_run_interactions":
        assert _experience_interactions_head_is_approved(), (
            "0010_experience_run_interactions is present as head but is not approved: require "
            "governance/ADR/ADR-0047-async-sql-experience-run-ledger.md and an approved "
            "MIGRATION_MANIFEST entry"
        )
    if head == "0012_ai_agent_runs":
        assert _agent_runs_head_is_approved(), (
            "0012_ai_agent_runs is present as head but is not approved: require "
            "governance/ADR/ADR-0053-agent-run-trace-durable-persistence.md and an approved "
            "MIGRATION_MANIFEST entry"
        )
    if head == "0013_ai_authorization_leases":
        assert _authorization_lease_head_is_approved(), (
            "0013_ai_authorization_leases is present as head but is not approved: require "
            "governance/ADR/ADR-0055-agent-authorization-lease-persistence.md and an approved "
            "MIGRATION_MANIFEST entry"
        )
    if head == "0014_tool_action_outbox":
        assert _tool_action_outbox_head_is_approved(), (
            "0014_tool_action_outbox is present as head but is not approved: require "
            "governance/ADR/ADR-0057-tool-action-durable-outbox.md and an approved "
            "MIGRATION_MANIFEST entry"
        )
    if head == "0015_ai_achievement_projections":
        assert _achievement_projection_head_is_approved(), (
            "0015_ai_achievement_projections is present as head but is not approved: require "
            "governance/ADR/ADR-0058-durable-achievement-projection.md and an approved "
            "MIGRATION_MANIFEST entry"
        )
    return head


def _discovered_single_head(database_url: str) -> str:
    """Read the one graph head without applying the approval policy."""

    result = _run_alembic("heads", database_url=database_url)
    assert result.returncode == 0, f"alembic heads failed:\n{result.stdout}\n{result.stderr}"
    return _head_from_result(result)


def _single_head(database_url: str) -> str:
    """Return the one approved migration head, failing on unknown/unapproved WIP."""

    return _assert_accepted_head(_discovered_single_head(database_url))


async def _count_objects(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            tables = await conn.scalar(
                text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
            )
            views = await conn.scalar(
                text("SELECT count(*) FROM information_schema.views WHERE table_schema = 'public'")
            )
            enums = await conn.scalar(
                text(
                    "SELECT count(DISTINCT t.typname) FROM pg_type t "
                    "JOIN pg_enum e ON e.enumtypid = t.oid "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public'"
                )
            )
        return {"tables": tables or 0, "views": views or 0, "enums": enums or 0}
    finally:
        await engine.dispose()


async def test_upgrade_baseline_applies_to_empty_postgres(throwaway_database_url: str) -> None:
    """The historical baseline alone remains exactly 151/7/60 objects."""

    before = await _count_objects(throwaway_database_url)
    assert before == {"tables": 0, "views": 0, "enums": 0}, (
        f"the throwaway database was not empty: {before}"
    )

    result = _run_alembic(
        "upgrade", "0001_legacy_schema_baseline", database_url=throwaway_database_url
    )
    assert result.returncode == 0, (
        f"alembic upgrade 0001_legacy_schema_baseline failed:\n{result.stdout}\n{result.stderr}"
    )

    after = await _count_objects(throwaway_database_url)
    assert after == EXPECTED_BASELINE_COUNTS, (
        f"replayed baseline schema does not match the psql-measured reference: {after}"
    )

    current = _run_alembic("current", database_url=throwaway_database_url)
    assert "0001_legacy_schema_baseline" in current.stdout


async def test_upgrade_0008_applies_fgcn_human_gate_additive_revisions(
    throwaway_database_url: str,
) -> None:
    """0004-0008 add seven owned tables without changing views or enums."""

    result = _run_alembic("upgrade", "0008_experience_runs", database_url=throwaway_database_url)
    assert result.returncode == 0, (
        f"alembic upgrade 0008_experience_runs failed:\n{result.stdout}\n{result.stderr}"
    )

    after = await _count_objects(throwaway_database_url)
    assert after == EXPECTED_0008_COUNTS, (
        f"0008 schema does not match the baseline plus additive migration object reference: {after}"
    )

    current = _run_alembic("current", database_url=throwaway_database_url)
    assert "0008_experience_runs" in current.stdout


def test_unregistered_0009_head_is_blocked() -> None:
    """A concurrent 0009 file must not become an accepted head by presence alone."""

    if not _MODEL_DRAFTS_MIGRATION.is_file():
        pytest.skip("0009_ai_model_drafts is not present in this checkout")
    assert _MODEL_DRAFTS_ADR.is_file(), (
        "0009 approval requires the canonical ADR file: "
        "governance/ADR/ADR-0045-durable-model-draft-provenance-registry.md"
    )
    if _model_drafts_head_is_approved():
        pytest.skip("0009_ai_model_drafts is registered and approved in this checkout")
    with pytest.raises(AssertionError, match="0009_ai_model_drafts.*not approved"):
        _assert_accepted_head("0009_ai_model_drafts")


def test_untracked_0010_head_is_blocked() -> None:
    """An unapproved 0010 migration cannot pass the head approval gate."""

    if not _EXPERIENCE_INTERACTIONS_MIGRATION.is_file():
        pytest.skip("0010_experience_run_interactions is not present in this checkout")
    if _experience_interactions_head_is_approved():
        pytest.skip("0010_experience_run_interactions is registered and approved in this checkout")
    with pytest.raises(AssertionError, match="0010_experience_run_interactions.*not approved"):
        _assert_accepted_head("0010_experience_run_interactions")


def test_unknown_migration_head_is_blocked() -> None:
    """An unreviewed future head cannot silently change the head object count."""

    with pytest.raises(AssertionError, match="unknown migration head"):
        _assert_accepted_head("0011_unreviewed_future")


def test_untracked_0012_head_is_blocked() -> None:
    """An unapproved AgentRun migration cannot pass the head approval gate."""

    if not _AGENT_RUNS_MIGRATION.is_file():
        pytest.skip("0012_ai_agent_runs is not present in this checkout")
    if _agent_runs_head_is_approved():
        pytest.skip("0012_ai_agent_runs is registered and approved in this checkout")
    with pytest.raises(AssertionError, match="0012_ai_agent_runs.*not approved"):
        _assert_accepted_head("0012_ai_agent_runs")


def test_untracked_0013_head_is_blocked() -> None:
    """An unapproved authorization lease migration cannot pass the head gate."""

    if not _AUTHORIZATION_LEASE_MIGRATION.is_file():
        pytest.skip("0013_ai_authorization_leases is not present in this checkout")
    if _authorization_lease_head_is_approved():
        pytest.skip("0013_ai_authorization_leases is registered and approved in this checkout")
    with pytest.raises(AssertionError, match="0013_ai_authorization_leases.*not approved"):
        _assert_accepted_head("0013_ai_authorization_leases")


def test_untracked_0014_head_is_blocked() -> None:
    """An unapproved Tool Action outbox migration cannot pass the head gate."""

    if not _TOOL_ACTION_OUTBOX_MIGRATION.is_file():
        pytest.skip("0014_tool_action_outbox is not present in this checkout")
    if _tool_action_outbox_head_is_approved():
        pytest.skip("0014_tool_action_outbox is registered and approved in this checkout")
    with pytest.raises(AssertionError, match="0014_tool_action_outbox.*not approved"):
        _assert_accepted_head("0014_tool_action_outbox")


def test_untracked_0015_head_is_blocked() -> None:
    """An unapproved achievement projection migration cannot pass the head gate."""

    if not _ACHIEVEMENT_PROJECTION_MIGRATION.is_file():
        pytest.skip("0015_ai_achievement_projections is not present in this checkout")
    if _achievement_projection_head_is_approved():
        pytest.skip("0015_ai_achievement_projections is registered and approved in this checkout")
    with pytest.raises(AssertionError, match="0015_ai_achievement_projections.*not approved"):
        _assert_accepted_head("0015_ai_achievement_projections")


async def test_downgrade_then_upgrade_is_repeatable(throwaway_database_url: str) -> None:
    """Guards the failure mode that `DROP SCHEMA public CASCADE` caused.

    The first version of `downgrade()` dropped the whole `public` schema, which
    took `alembic_version` with it; Alembic's very next statement is
    `DELETE FROM alembic_version`, so the downgrade blew up mid-flight and left
    the database in a state no command reported correctly. Asserting a full
    up -> down -> up cycle is what makes that class of bug visible.
    """
    discovered_head = _discovered_single_head(throwaway_database_url)
    head = _assert_accepted_head(discovered_head)
    expected_head_counts = EXPECTED_HEAD_COUNTS_BY_REVISION[head]

    up = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert up.returncode == 0, f"alembic upgrade head failed:\n{up.stdout}\n{up.stderr}"
    assert await _count_objects(throwaway_database_url) == expected_head_counts
    current = _run_alembic("current", database_url=throwaway_database_url)
    assert head in current.stdout and "(head)" in current.stdout

    down = _run_alembic("downgrade", "base", database_url=throwaway_database_url)
    assert down.returncode == 0, f"alembic downgrade base failed:\n{down.stdout}\n{down.stderr}"

    after_down = await _count_objects(throwaway_database_url)
    assert after_down == {"tables": _ALEMBIC_BOOKKEEPING_TABLES, "views": 0, "enums": 0}, (
        "downgrade must remove every legacy object but keep Alembic's own "
        f"version table: {after_down}"
    )

    up_again = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert up_again.returncode == 0, f"re-upgrade failed:\n{up_again.stdout}\n{up_again.stderr}"

    after_up = await _count_objects(throwaway_database_url)
    assert after_up == expected_head_counts
    current_again = _run_alembic("current", database_url=throwaway_database_url)
    assert head in current_again.stdout and "(head)" in current_again.stdout
