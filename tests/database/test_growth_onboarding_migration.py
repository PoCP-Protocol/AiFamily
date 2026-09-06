"""Evidence for the complete PostgreSQL migration chain behind onboarding.

These tests deliberately use a fresh disposable database.  ``Base.metadata``
or a hand-built test schema would miss the exact failure this file is meant to
catch: the runtime onboarding reader must run against the schema produced by
the real Alembic chain, including the current AI-runtime graph head.

The database path is opt-in through ``AIFAMILY_TEST_DATABASE_URL``.  An unset
or unreachable disposable database is an explicit skip; SQLite is never used
as a substitute for this evidence.
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VERSIONS_DIR = REPO_ROOT / "database" / "migrations" / "versions"


def _revision_constants(path: pathlib.Path) -> tuple[str, str | None]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value_node = node.value
        else:
            continue
        if name not in {"revision", "down_revision"} or value_node is None:
            continue
        try:
            values[name] = ast.literal_eval(value_node)
        except (TypeError, ValueError):
            continue

    revision = values.get("revision")
    down_revision = values.get("down_revision")
    assert isinstance(revision, str), f"{path.name} must declare a string revision"
    assert down_revision is None or isinstance(down_revision, str)
    return revision, down_revision


def _discover_full_chain() -> tuple[str, ...]:
    """Derive the ordered revision chain straight from `database/migrations/versions/`.

    This used to be a hand-maintained tuple. It fell three revisions (0058-0066)
    behind reality because nobody remembered to touch this file when a new
    migration landed elsewhere in the tree — the exact class of bug a dynamic
    scan cannot have, since there is nothing to remember. The chain is a pure
    function of the on-disk `revision`/`down_revision` graph, so deriving it here
    and asserting linearity (single root, single head, no branches) is strictly
    stronger evidence than a tuple a human typed by hand.

    If you are staring at a failure from this function: it means the on-disk
    migration graph is not a single linear chain (a fork, a gap, or a missing
    file) — not that this file needs editing.
    """
    files = sorted(VERSIONS_DIR.glob("*.py"))
    parsed = dict(_revision_constants(path) for path in files)
    down_revisions = {down for down in parsed.values() if down}
    heads = [revision for revision in parsed if revision not in down_revisions]
    assert len(heads) == 1, f"migration graph must have exactly one head, found: {heads}"
    ordered: list[str] = []
    current: str | None = heads[0]
    while current is not None:
        assert current not in ordered, f"migration graph has a cycle at {current!r}"
        ordered.append(current)
        current = parsed[current]
    return tuple(reversed(ordered))


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


async def _scalar(database_url: str, statement: str, **params: object) -> object:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(statement), params)
    finally:
        await engine.dispose()


async def _columns(database_url: str, table_name: str) -> set[str]:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    """
                    select column_name
                    from information_schema.columns
                    where table_schema='public' and table_name=:table_name
                    """
                ),
                {"table_name": table_name},
            )
            return {str(row.column_name) for row in rows}
    finally:
        await engine.dispose()


@pytest.fixture
async def disposable_database_url() -> str:
    """Create and later remove one empty database for real Alembic DDL."""

    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    if not admin_url.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
        pytest.fail(f"AIFAMILY_TEST_DATABASE_URL must be a PostgreSQL URL; got {admin_url!r}")

    database_name = f"growth_onboarding_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"statement_cache_size": 0},
    )
    created = False
    try:
        try:
            async with admin.connect() as connection:
                await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
            created = True
        except (OSError, SQLAlchemyError) as error:
            pytest.skip(
                "external dependency unavailable: cannot create disposable "
                f"PostgreSQL database ({type(error).__name__}: {error})"
            )

        database_url = (
            make_url(admin_url).set(database=database_name).render_as_string(hide_password=False)
        )
        yield database_url
    finally:
        if created:
            try:
                async with admin.connect() as connection:
                    await connection.execute(
                        text(
                            "SELECT pg_terminate_backend(pid) "
                            "FROM pg_stat_activity "
                            "WHERE datname=:database_name "
                            "AND pid <> pg_backend_pid()"
                        ),
                        {"database_name": database_name},
                    )
                    await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
            finally:
                await admin.dispose()
        else:
            await admin.dispose()


def test_all_alembic_revisions_form_one_complete_chain_through_current_head() -> None:
    full_chain = _discover_full_chain()
    files = sorted(VERSIONS_DIR.glob("*.py"))
    parsed = [_revision_constants(path) for path in files]
    revisions = dict(parsed)

    assert len(revisions) == len(files), "migration revision ids must be unique"
    oversized = sorted(revision for revision in revisions if len(revision) > 32)
    assert oversized
    assert oversized[0] == "0026_experience_outbox_delivery_attempts"
    assert all(len(revision) <= 128 for revision in oversized)
    widening_source = next(
        path.read_text(encoding="utf-8")
        for path in files
        if _revision_constants(path)[0] == oversized[0]
    )
    assert '"alembic_version"' in widening_source
    assert "type_=sa.String(length=128)" in widening_source
    assert full_chain[0] == "0001_legacy_schema_baseline"


async def test_full_chain_upgrade_downgrade_and_rebuild(
    disposable_database_url: str,
) -> None:
    full_chain = _discover_full_chain()
    for target in full_chain:
        result = _run_alembic("upgrade", target, database_url=disposable_database_url)
        assert result.returncode == 0, (
            f"alembic upgrade {target} failed:\n{result.stdout}\n{result.stderr}"
        )
        assert (
            await _scalar(disposable_database_url, "select version_num from alembic_version")
            == target
        )

    assert (
        await _scalar(
            disposable_database_url,
            "select to_regclass('public.growth_onboarding_intent_bindings')",
        )
        == "growth_onboarding_intent_bindings"
    )

    rollback = _run_alembic(
        "downgrade", "0015_ai_achievement_projections", database_url=disposable_database_url
    )
    assert rollback.returncode == 0, (
        f"alembic downgrade 0016 -> 0015 failed:\n{rollback.stdout}\n{rollback.stderr}"
    )
    assert (
        await _scalar(
            disposable_database_url,
            "select version_num from alembic_version",
        )
        == "0015_ai_achievement_projections"
    )
    assert (
        await _scalar(
            disposable_database_url,
            "select to_regclass('public.growth_onboarding_intent_bindings')",
        )
        is None
    )

    rebuild = _run_alembic("upgrade", "head", database_url=disposable_database_url)
    assert rebuild.returncode == 0, (
        f"alembic rebuild 0015 -> head failed:\n{rebuild.stdout}\n{rebuild.stderr}"
    )
    assert (
        await _scalar(disposable_database_url, "select version_num from alembic_version")
        == full_chain[-1]
    )
    assert (
        await _scalar(
            disposable_database_url,
            "select character_maximum_length from information_schema.columns "
            "where table_schema='public' and table_name='alembic_version' "
            "and column_name='version_num'",
        )
        == 128
    )


async def test_pre_0016_schema_exposes_intent_and_consent_contract_gaps(
    disposable_database_url: str,
) -> None:
    """Check the base schema before 0016 masks its own application failure."""

    result = _run_alembic(
        "upgrade", "0015_ai_achievement_projections", database_url=disposable_database_url
    )
    assert result.returncode == 0, f"alembic upgrade 0015 failed:\n{result.stdout}\n{result.stderr}"

    intent_columns = await _columns(disposable_database_url, "growth_intents")
    assert "boundary" in intent_columns, (
        "schema_gap: runtime reader requires growth_intents.boundary, "
        "but the pre-0016 canonical schema does not provide it"
    )

    consent_columns = await _columns(disposable_database_url, "consents")
    required_consent_columns = {
        "family_id",
        "subject_person_id",
        "purpose",
        "status",
        "policy_version",
        "granted_at",
        "withdrawn_at",
    }
    assert required_consent_columns <= consent_columns, (
        "schema_gap: canonical consents columns are incomplete: "
        f"{sorted(required_consent_columns - consent_columns)}"
    )
    assert "tenant_id" not in consent_columns
    assert "expires_at" not in consent_columns
    assert "effective_from" not in consent_columns
    assert "effective_to" not in consent_columns


async def test_head_schema_contains_the_runtime_onboarding_contract(
    disposable_database_url: str,
) -> None:
    result = _run_alembic("upgrade", "head", database_url=disposable_database_url)
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"

    binding_columns = await _columns(disposable_database_url, "growth_onboarding_intent_bindings")
    assert {
        "binding_id",
        "tenant_family_binding_id",
        "tenant_id",
        "family_id",
        "intent_id",
        "onboarding_id",
        "subject_person_id",
        "created_at",
    } <= binding_columns, "schema_gap: 0016 binding columns are incomplete"

    intent_columns = await _columns(disposable_database_url, "growth_intents")
    assert "boundary" in intent_columns, (
        "schema_gap: runtime reader requires growth_intents.boundary, "
        "but the complete Alembic chain does not create it"
    )

    consent_columns = await _columns(disposable_database_url, "consents")
    required_consent_columns = {
        "family_id",
        "subject_person_id",
        "purpose",
        "status",
        "policy_version",
        "granted_at",
        "withdrawn_at",
    }
    assert required_consent_columns <= consent_columns, (
        "schema_gap: canonical consents columns are incomplete: "
        f"{sorted(required_consent_columns - consent_columns)}"
    )
    assert "tenant_id" not in consent_columns
    assert "expires_at" not in consent_columns
    assert "effective_from" not in consent_columns
    assert "effective_to" not in consent_columns


async def test_growth_plan_review_envelope_is_immutable_on_postgres(
    disposable_database_url: str,
) -> None:
    result = _run_alembic("upgrade", "head", database_url=disposable_database_url)
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
    engine = create_async_engine(
        disposable_database_url,
        connect_args={"statement_cache_size": 0},
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    insert into ai_growth_plan_draft_reviews(
                      tenant_id,draft_id,request_id,agent_run_id,provenance_ref,
                      family_id,region_id,subject_person_id,purpose,consent_version,
                      data_class,locale,deletion_ref,generation_correlation_id,
                      scope_payload,intent_id,onboarding_id,priority_id,input_refs,
                      stable_digest,status,may_mutate_business_state,retention_policy,
                      created_at,expires_at
                    ) values (
                      'tenant-test','draft:test','request:test','run:test','model-draft:test',
                      'family-test','CN','child-test','growth_tracking','consent.v1',
                      'MINOR_PERSONAL_DATA','zh-CN','deletion:test','correlation:test',
                      '{}'::jsonb,'intent-test','onboarding-test','priority-test','[]'::jsonb,
                      repeat('a',64),'DRAFT',false,'growth-plan-human-review.v1',
                      CURRENT_TIMESTAMP,CURRENT_TIMESTAMP + interval '1 day'
                    )
                    """
                )
            )
        with pytest.raises(SQLAlchemyError, match="immutable"):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update ai_growth_plan_draft_reviews "
                        "set priority_id='tampered' "
                        "where tenant_id='tenant-test' and draft_id='draft:test'"
                    )
                )
    finally:
        await engine.dispose()
