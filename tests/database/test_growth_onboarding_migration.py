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

FULL_CHAIN = (
    "0001_legacy_schema_baseline",
    "0002_platform_audit_events_worm",
    "0003_service_booking_additions",
    "0004_fgcn_p0_persistence",
    "0005_fgcn_assignment_idempotency",
    "0006_ai_human_tasks",
    "0007_experience_outbox",
    "0008_experience_runs",
    "0009_ai_model_drafts",
    "0010_experience_run_interactions",
    "0011_ai_human_task_claims",
    "0012_ai_agent_runs",
    "0013_ai_authorization_leases",
    "0014_tool_action_outbox",
    "0015_ai_achievement_projections",
    "0016_growth_onboarding",
    "0017_ai_model_attempts",
    "0018_ai_safety_decisions",
    "0019_ai_runtime_scope_columns",
    "0020_ai_release_decisions",
    "0021_ai_telemetry_spans",
    "0022_ai_memory_store",
    "0023_ai_growth_graph_projection",
    "0024_ai_accepted_action_delivery",
    "0025_service_blueprint_proposals",
    "0026_experience_outbox_delivery_attempts",
    "0027_experience_outbox_dead_letters",
    "0028_ai_achievement_occurrences",
    "0029_ai_experience_feedback_projections",
    "0030_ai_prompt_schema_registry",
    "0031_ai_release_controls",
    "0032_ai_release_candidates",
    "0033_ai_release_deployment_receipts",
    "0034_ai_benchmark_report_archive",
    "0035_ai_benchmark_report_slices",
    "0036_ai_context_engine",
    "0037_ops_audit",
    "0038_product_definition",
    "0039_competitor_evidence",
    "0040_ai_experience_bundles",
    "0041_ai_canary_assessments",
    "0042_ai_canary_alerts",
    "0043_ai_canary_jobs",
    "0044_ai_model_budget_reservations",
    "0045_ai_bundle_runtime_policies",
    "0046_ai_experience_release_sets",
    "0047_ai_release_set_deployments",
    "0048_ai_runtime_release_evidence",
    "0049_ai_release_set_signed_controls",
    "0050_ai_release_projection_invocation_fence",
    "0051_ai_release_transition_state_machine",
    "0052_ai_execution_materials",
    "0053_ai_release_transition_reconciliation",
    "0054_ai_engagement_draft_reviews",
    "0055_family_need_domain",
    "0056_course_content",
    "0057_ai_growth_plan_draft_reviews",
)


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
    files = sorted(VERSIONS_DIR.glob("*.py"))
    parsed = [_revision_constants(path) for path in files]
    revisions = dict(parsed)
    down_revisions = {down_revision for down_revision in revisions.values() if down_revision}

    assert set(revisions) == set(FULL_CHAIN)
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
    assert set(revisions) - down_revisions == {FULL_CHAIN[-1]}

    ordered: list[str] = []
    current: str | None = FULL_CHAIN[-1]
    while current is not None:
        ordered.append(current)
        current = revisions[current]
    assert tuple(reversed(ordered)) == FULL_CHAIN


async def test_full_chain_upgrade_downgrade_and_rebuild(
    disposable_database_url: str,
) -> None:
    for target in FULL_CHAIN:
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
        == FULL_CHAIN[-1]
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
