"""Real-Postgres integration test for the Product Zone (Three-Zone Strategy
Engine) closure — PR-002R Agent D scope ("真实Postgres/对抗验证"). Same style
and skip convention as `test_postgres_integration.py` (this domain's original
real-Postgres test for the PR-001/PR-001R acceptance chain): everything else
in this suite runs against SQLite or an in-memory fake; this module is the
one place that proves the real migration files (`0058` -> `0059` -> `0060`)
apply cleanly, in that order, on real Postgres, and that DB-level mechanisms
(triggers, partial unique indexes, FKs, CHECK constraints) introduced by
`0059`/`0060` are enforced by Postgres itself — not merely assumed to work
because the SQLite test suite (131 passed) happens to pass.

Requires a real, disposable Postgres reachable at `PI_POSTGRES_TEST_DSN`
(asyncpg DSN, e.g.
`postgresql+asyncpg://postgres:postgres@localhost:55440/pi_zone_test`).
Skipped entirely (not failed) when that env var is unset.

Coverage checklist (chief-architect's 10-item list for this Agent; item 4 is
folded into item 1 per the task brief's own note that they overlap):

1. Disposable Postgres, migrations 0058 -> 0059 -> 0060 applied in order,
   proving 0060 depends cleanly on 0058+0059 (also covers item 4).
2. Tenant-mismatch DB trigger (`trg_zone_assessment_subject_tenant_guard`
   from 0059) rejected via raw SQL, bypassing the application layer.
3. `uq_zone_policy_active_per_id` (0060) rejects two ACTIVE rows for the
   same `policy_id` via raw SQL -> `IntegrityError`.
5. Canonical `product_intelligence_zone_assessments_v0` full lifecycle
   (create -> score -> submit -> approve) via `zone_commands`, persisted and
   reloaded from real Postgres.
6. Legacy `product_intelligence_zone_assessments` (0058's placeholder table)
   confirmed absent after 0060 (dropped).
7. REJECTED excluded from `unreviewed_count` (`zone_queries.
   get_portfolio_zone_summary`), counted only in `rejected_count`.
8. RETIRED excluded from the active zone distribution
   (`commodity_count`/`advantage_count`/`unique_count`), counted only in
   `retired_count`.
9. Two policy versions with different `weights` produce different
   `differentiation_index` for the same six-dimension input, verified after
   a real Postgres persistence round trip (not just in-memory).
10. A historical (already-APPROVED) assessment scored under policy v1 is
    unaffected by a later policy v2 (different weights/thresholds) being
    created — `recommended_zone`/three scores/`zone_policy_version_id`
    reloaded from Postgres are bit-for-bit identical to what v1 computed.
11. `algorithm_version`/checksum stability across a real Postgres
    persistence round trip (save -> load -> recompute matches).
"""
from __future__ import annotations

import os
import pathlib
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..application import zone_commands
from ..application.context import ActorContext
from ..domain.errors import ProductIntelligenceValidationError
from ..domain.zone_entities import ProductZoneAssessment, ZonePolicyVersion
from ..infrastructure import zone_sqlalchemy_models as zm
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository
from ..infrastructure.zone_sqlalchemy_repository import (
    SqlAlchemyZoneAssessmentRepository,
    _load_zone_assessment,
)

PI_POSTGRES_TEST_DSN = os.environ.get("PI_POSTGRES_TEST_DSN")

pytestmark = pytest.mark.skipif(
    not PI_POSTGRES_TEST_DSN,
    reason="PI_POSTGRES_TEST_DSN not set — real-Postgres zone-engine integration test skipped (set it to run against a disposable container)",
)

_MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "migrations"
_MIGRATION_0058 = _MIGRATIONS_DIR / "0058_product_intelligence_domain.sql"
_MIGRATION_0059 = _MIGRATIONS_DIR / "0059_product_zone_engine_v0.sql"
_MIGRATION_0060 = _MIGRATIONS_DIR / "0060_product_zone_engine_canonical_cleanup.sql"

# Full table set this domain's 0058 migration creates, dropped up front so
# re-running this suite against a persistent (not just disposable) database
# is idempotent. Mirrors `test_postgres_integration.py::_ALL_TABLES` plus the
# 0059 zone-engine tables (dropped separately below since they postdate that
# list).
_ALL_0058_TABLES = [
    "product_intelligence_service_blueprint_versions",
    "product_intelligence_product_definitions",
    "product_intelligence_product_patterns",
    "product_intelligence_product_components",
    "product_intelligence_product_concepts",
    "product_intelligence_zone_assessments",
    "product_intelligence_growth_strategies",
    "product_intelligence_contradiction_models",
    "product_intelligence_growth_hypotheses",
    "product_intelligence_growth_problems",
    "product_intelligence_unmet_needs",
    "product_intelligence_customer_insights",
    "product_intelligence_evidence",
    "product_intelligence_customer_segments",
    "product_intelligence_market_trends",
    "product_intelligence_signal_clusters",
    "product_intelligence_market_signals",
]
_ALL_0059_TABLES = [
    "product_intelligence_zone_assessments_v0",
    "product_intelligence_zone_policy_versions",
]

UTC_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)


def _split_statements(sql_text: str) -> list[str]:
    """Same naive-but-safe split used by `test_postgres_integration.py`:
    none of these three migration files have semicolons inside string
    literals/CHECK expressions/`$$ ... $$` function bodies that would break a
    plain split on ';' ... EXCEPT 0059's `CREATE FUNCTION ... $$ ... $$`
    body, which contains no semicolon-free statements of its own but the
    function *body* itself has internal semicolons inside the `$$` fence.
    A naive split would cut the function body into invalid fragments, so
    this splitter treats a `$$ ... $$`-delimited region as one atomic
    statement instead of splitting inside it.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_dollar_quote = False
    for line in sql_text.split("\n"):
        if "$$" in line:
            # Toggle dollar-quote state once per occurrence of "$$" on this
            # line (0059's function body has exactly one open and one close,
            # never two on the same line).
            occurrences = line.count("$$")
            if occurrences % 2 == 1:
                in_dollar_quote = not in_dollar_quote
        buf.append(line)
        if not in_dollar_quote and line.rstrip().endswith(";"):
            statement = "\n".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _strip_leading_comment_lines(statement: str) -> str:
    """A statement chunk may have leading `--` comment lines glued onto the
    real SQL that follows (this migration file uses `--` doc-comments
    directly above statements with no blank-line-only separation in some
    places) — strip them so the "was this whole chunk just comments"
    emptiness check below is accurate. Executing the comment lines together
    with the SQL is harmless to Postgres either way (it ignores `--`
    comments itself); this is purely for this helper's own is-empty check.
    """
    lines = statement.split("\n")
    while lines and lines[0].strip().startswith("--"):
        lines.pop(0)
    return "\n".join(lines).strip()


async def _apply_migration(conn, path: pathlib.Path) -> None:
    sql_text = path.read_text(encoding="utf-8")
    for statement in _split_statements(sql_text):
        if _strip_leading_comment_lines(statement):
            await conn.execute(text(statement))


@pytest_asyncio.fixture
async def pg_engine():
    assert PI_POSTGRES_TEST_DSN is not None
    engine = create_async_engine(PI_POSTGRES_TEST_DSN)

    async with engine.begin() as conn:
        for table in _ALL_0059_TABLES + _ALL_0058_TABLES:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        await conn.execute(
            text("DROP FUNCTION IF EXISTS product_intelligence_zone_assessment_subject_tenant_guard() CASCADE")
        )

        # Item 1 (+4): apply 0058 -> 0059 -> 0060 in order, verbatim, proving
        # migration-order correctness (0060's ALTER TABLE/CREATE INDEX depend
        # on tables 0058/0059 create).
        await _apply_migration(conn, _MIGRATION_0058)
        await _apply_migration(conn, _MIGRATION_0059)
        await _apply_migration(conn, _MIGRATION_0060)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    session_factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
def zone_repo(pg_session):
    return SqlAlchemyZoneAssessmentRepository(pg_session)


@pytest_asyncio.fixture
def base_repo(pg_session):
    return SqlAlchemyProductIntelligenceRepository(pg_session)


def _reviewer_context(tenant_scope: str = "tenant-a") -> ActorContext:
    return ActorContext(
        actor_id="human-reviewer-1", actor_type="HUMAN", tenant_scope=tenant_scope,
        permissions=frozenset({zone_commands.ZONE_REVIEW_PERMISSION}),
    )


def _build_policy(**overrides) -> ZonePolicyVersion:
    defaults = dict(
        policy_id="zone-policy-v0",
        version=1,
        dimension_definitions={
            "customer_scarcity": "positive",
            "replaceability": "negative",
            "data_advantage": "positive",
            "network_effect": "positive",
            "learning_effect": "positive",
            "switching_cost": "positive",
        },
        weights={
            "customer_scarcity": 1.0,
            "replaceability": 1.0,
            "data_advantage": 1.0,
            "network_effect": 1.0,
            "learning_effect": 1.0,
            "switching_cost": 1.0,
        },
        thresholds={
            "unique_defensibility_min": 75.0,
            "unique_floor_gate_min": 50.0,
            "commodity_differentiation_max": 40.0,
            "commodity_defensibility_max": 40.0,
        },
        classification_rules="UNIQUE if defensibility>=75 and floor>=50; COMMODITY if diff<40 and def<40; else ADVANTAGE",
        review_policy={"unique_requires_reviewers": 1},
        effective_from=UTC_NOW,
        status="ACTIVE",
    )
    defaults.update(overrides)
    return ZonePolicyVersion(**defaults)


def _dimension_input(score: float = 90.0) -> list[dict]:
    return [
        {
            "dimension": dimension,
            "score": score,
            "rationale": "strong signal",
            "evidence_refs": [f"evidence-{dimension}"],
            "evidence_strength": 0.8,
            "assessed_by": "human-scorer-1",
            "assessed_at": UTC_NOW,
        }
        for dimension in (
            "customer_scarcity",
            "replaceability",
            "data_advantage",
            "network_effect",
            "learning_effect",
            "switching_cost",
        )
    ]


async def _seed_product_concept(base_repo, *, concept_id: str, tenant_scope: str = "tenant-a"):
    from ..domain.entities import GrowthHypothesis, GrowthProblem, GrowthStrategy, ProductConcept

    # Real Postgres enforces the FKs `growth_strategies.problem_id ->
    # growth_problems.id` and (implicitly, via hypothesis_ids being validated
    # at the application layer only, not a DB FK — but a real
    # GrowthHypothesis row is still seeded here for realism/parity with the
    # SQLite fixture) `growth_hypotheses.problem_id -> growth_problems.id`,
    # unlike the SQLite test fixtures which never actually created a
    # `problem-1`/`hyp-1` row and got away with it because SQLite's default
    # FK pragma is off. Real rows are seeded here so this module exercises
    # the real constraint graph, not a fixture shortcut that only works
    # because the backend under test does not enforce it.
    problem = GrowthProblem(
        id=f"problem-for-{concept_id}", created_at=UTC_NOW, updated_at=UTC_NOW, created_by="human-1",
        tenant_scope=tenant_scope, status="ACTIVE", symptom="pain point for zone engine test",
    )
    await base_repo.save_growth_problem(problem)
    hypothesis = GrowthHypothesis(
        id=f"hyp-for-{concept_id}", created_at=UTC_NOW, updated_at=UTC_NOW, created_by="human-1",
        tenant_scope=tenant_scope, status="DRAFT", problem_id=problem.id, statement="hypothesis for zone engine test",
    )
    await base_repo.save_growth_hypothesis(hypothesis)
    strategy = GrowthStrategy(
        id=f"strategy-for-{concept_id}", created_at=UTC_NOW, updated_at=UTC_NOW, created_by="human-1",
        tenant_scope=tenant_scope, status="APPROVED", problem_id=problem.id,
        hypothesis_ids=[hypothesis.id], statement="grow via zone engine",
    )
    await base_repo.save_growth_strategy(strategy)
    concept = ProductConcept(
        id=concept_id, created_at=UTC_NOW, updated_at=UTC_NOW, created_by="human-1",
        tenant_scope=tenant_scope, status="DRAFT", strategy_id=strategy.id, title="concept",
    )
    await base_repo.save_product_concept(concept)
    return concept


async def _list_zone_assessments(pg_session, tenant_scope: str) -> list[ProductZoneAssessment]:
    """Minimal real-SQL adapter for `application/zone_query_ports.py::
    ZonePortfolioQueryPort`, test-local only (no production `ZonePortfolioQueryPort`
    SQL adapter exists yet in `infrastructure/` — the only shipped
    implementation of that Protocol as of this PR is the in-memory Fake in
    `test_portfolio_zone_view.py`). Issues a real `SELECT ... WHERE
    tenant_scope = ...` against Postgres and reuses this domain's own
    `_load_zone_assessment` row->entity mapper so the reload path is
    identical to `zone_repo.load_zone_assessment`'s.
    """
    result = await pg_session.execute(
        select(zm.ProductZoneAssessmentRow).where(zm.ProductZoneAssessmentRow.tenant_scope == tenant_scope)
    )
    return [_load_zone_assessment(row) for row in result.scalars().all()]


class _PgPortfolioQueryPort:
    def __init__(self, pg_session):
        self._session = pg_session

    async def list_zone_assessments(self, tenant_scope: str) -> list[ProductZoneAssessment]:
        return await _list_zone_assessments(self._session, tenant_scope)


# ---------------------------------------------------------------------------
# Item 1 (+4): migration order 0058 -> 0059 -> 0060 applies cleanly.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrations_0058_0059_0060_apply_in_order(pg_engine):
    """The `pg_engine` fixture itself already ran 0058 -> 0059 -> 0060 to
    completion (any statement failure would raise during fixture setup, not
    inside this test body) — this test additionally asserts the concrete,
    observable end state: 0060's `scoring_algorithm_version` column and
    `uq_zone_policy_active_per_id` index exist, proving 0060's ALTER
    TABLE/CREATE INDEX statements (which reference tables only 0058/0059
    create) actually ran against the schema those two migrations produced.
    """
    async with pg_engine.begin() as conn:
        column_check = await conn.execute(
            text(
                """
                SELECT column_name, column_default, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'product_intelligence_zone_policy_versions'
                  AND column_name = 'scoring_algorithm_version'
                """
            )
        )
        row = column_check.fetchone()
        assert row is not None, "0060's scoring_algorithm_version column is missing"
        assert row.is_nullable == "NO"
        assert "ZONE_SCORING_V0" in row.column_default

        index_check = await conn.execute(
            text(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'product_intelligence_zone_policy_versions'
                  AND indexname = 'uq_zone_policy_active_per_id'
                """
            )
        )
        assert index_check.fetchone() is not None, "0060's uq_zone_policy_active_per_id index is missing"


# ---------------------------------------------------------------------------
# Item 2: tenant-mismatch DB trigger, raw SQL, bypassing the application
# layer entirely.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_mismatch_rejected_by_db_trigger_via_raw_sql(pg_session, base_repo):
    """`trg_zone_assessment_subject_tenant_guard` (0059) must reject an
    INSERT whose `subject_ref` points at a `ProductConcept` belonging to a
    *different* tenant than the assessment's own `tenant_scope` — verified
    here via a raw INSERT that never goes through `zone_commands.
    create_zone_assessment` (which already guards this at the application
    layer via `load_product_concept`), so a failure here can only be the
    database trigger, not Python-side validation.
    """
    await _seed_product_concept(base_repo, concept_id="concept-tenant-a", tenant_scope="tenant-a")

    # A PL/pgSQL `RAISE EXCEPTION` (used by this trigger, not a native
    # constraint violation) surfaces through SQLAlchemy as the more generic
    # `DBAPIError`, not `IntegrityError` (that subclass is reserved for
    # actual constraint/FK/unique-index violations at the wire-protocol
    # level) — asyncpg's `RaiseError` is exactly this "user-raised" case.
    with pytest.raises(DBAPIError) as excinfo:
        await pg_session.execute(
            text(
                """
                INSERT INTO product_intelligence_zone_assessments_v0
                    (id, version, created_at, updated_at, created_by, tenant_scope, status,
                     subject_type, subject_ref, zone_policy_version_id, dimension_assessments,
                     differentiation_index, defensibility_index, commodity_score, advantage_score,
                     unique_score, recommended_zone, assessment_origin)
                VALUES
                    (:id, 1, now(), now(), :created_by, :tenant_scope, 'DRAFT',
                     'PRODUCT_CONCEPT', :subject_ref, :policy_id, '[]'::jsonb,
                     0.0, 0.0, 0.0, 0.0, 0.0, 'COMMODITY', 'HUMAN')
                """
            ),
            {
                "id": "zoneassess-cross-tenant",
                "created_by": "human-1",
                # This row DECLARES tenant-b, but subject_ref points at a
                # ProductConcept that actually belongs to tenant-a.
                "tenant_scope": "tenant-b",
                "subject_ref": "concept-tenant-a",
                "policy_id": "zone-policy-v0",
            },
        )
        await pg_session.flush()
    await pg_session.rollback()

    assert "does not belong to tenant_scope" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Item 3: uq_zone_policy_active_per_id rejects two ACTIVE rows for the same
# policy_id via raw SQL.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_active_policy_versions_same_policy_id_rejected_by_unique_index(pg_session):
    insert_sql = text(
        """
        INSERT INTO product_intelligence_zone_policy_versions
            (id, policy_id, version, dimension_definitions, weights, thresholds,
             classification_rules, review_policy, effective_from, status, checksum,
             scoring_algorithm_version)
        VALUES
            (:id, :policy_id, :version, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
             'rule', '{}'::jsonb, now(), 'ACTIVE', :checksum, 'ZONE_SCORING_V0')
        """
    )
    await pg_session.execute(
        insert_sql,
        {"id": "policy-row-1", "policy_id": "zone-policy-dup", "version": 1, "checksum": "checksum-1"},
    )
    await pg_session.flush()

    with pytest.raises(IntegrityError) as excinfo:
        await pg_session.execute(
            insert_sql,
            {"id": "policy-row-2", "policy_id": "zone-policy-dup", "version": 2, "checksum": "checksum-2"},
        )
        await pg_session.flush()
    await pg_session.rollback()

    assert "uq_zone_policy_active_per_id" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Item 5: canonical zone table full lifecycle create -> score -> submit ->
# approve, persisted and reloaded from real Postgres.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_canonical_zone_table_full_lifecycle_persists_through_approval(pg_session, zone_repo, base_repo):
    await _seed_product_concept(base_repo, concept_id="concept-lifecycle")
    await zone_repo.save_zone_policy_version(_build_policy())
    context = _reviewer_context()

    draft = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context, product_concept_id="concept-lifecycle", zone_policy_version_id="zone-policy-v0",
    )
    scored = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft.id, dimension_assessments=_dimension_input(),
    )
    submitted = await zone_commands.submit_zone_review(zone_repo, context, assessment_id=scored.id)
    approved = await zone_commands.approve_zone_assessment(
        zone_repo, context, assessment_id=submitted.id, approved_zone="UNIQUE", review_reason="matches evidence",
    )
    await pg_session.commit()

    loaded = await zone_repo.load_zone_assessment(approved.id, "tenant-a")
    assert loaded.status == "APPROVED"
    assert loaded.approved_zone == "UNIQUE"
    assert loaded.recommended_zone == "UNIQUE"
    assert loaded.reviewed_by == context.actor_id
    assert loaded.reviewed_at is not None
    assert len(loaded.dimension_assessments) == 6


# ---------------------------------------------------------------------------
# Item 6: legacy product_intelligence_zone_assessments table absent after
# 0060.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_zone_assessments_table_dropped_by_0060(pg_engine):
    async with pg_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'product_intelligence_zone_assessments'
                """
            )
        )
        assert result.fetchone() is None, "legacy product_intelligence_zone_assessments table still exists after 0060"

    # Belt-and-suspenders: a direct SELECT against the dropped table must
    # itself raise (UndefinedTable), not merely be absent from the catalog.
    async with pg_engine.connect() as conn:
        with pytest.raises(Exception) as excinfo:
            await conn.execute(text("SELECT 1 FROM product_intelligence_zone_assessments LIMIT 1"))
        assert "does not exist" in str(excinfo.value).lower() or "undefined" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# Items 7 & 8: REJECTED excluded from unreviewed_count; RETIRED excluded
# from active zone distribution. Both verified via zone_queries.get_
# portfolio_zone_summary against real Postgres.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejected_and_retired_excluded_from_active_distribution(pg_session, zone_repo, base_repo):
    from ..application import zone_queries

    await _seed_product_concept(base_repo, concept_id="concept-rejected")
    await _seed_product_concept(base_repo, concept_id="concept-retired")
    await _seed_product_concept(base_repo, concept_id="concept-approved")
    await zone_repo.save_zone_policy_version(_build_policy())
    context = _reviewer_context()

    # --- REJECTED assessment ---
    draft_r = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context, product_concept_id="concept-rejected", zone_policy_version_id="zone-policy-v0",
    )
    scored_r = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft_r.id, dimension_assessments=_dimension_input(),
    )
    submitted_r = await zone_commands.submit_zone_review(zone_repo, context, assessment_id=scored_r.id)
    await zone_commands.reject_zone_assessment(
        zone_repo, context, assessment_id=submitted_r.id, review_reason="does not match evidence",
    )

    # --- RETIRED assessment (must pass through APPROVED first) ---
    draft_t = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context, product_concept_id="concept-retired", zone_policy_version_id="zone-policy-v0",
    )
    scored_t = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft_t.id, dimension_assessments=_dimension_input(),
    )
    submitted_t = await zone_commands.submit_zone_review(zone_repo, context, assessment_id=scored_t.id)
    approved_t = await zone_commands.approve_zone_assessment(
        zone_repo, context, assessment_id=submitted_t.id, approved_zone="UNIQUE", review_reason="matches evidence",
    )
    await zone_commands.retire_zone_assessment(zone_repo, context, assessment_id=approved_t.id, reason="superseded")

    # --- APPROVED (currently active) assessment, for contrast ---
    draft_a = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context, product_concept_id="concept-approved", zone_policy_version_id="zone-policy-v0",
    )
    scored_a = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft_a.id, dimension_assessments=_dimension_input(),
    )
    submitted_a = await zone_commands.submit_zone_review(zone_repo, context, assessment_id=scored_a.id)
    await zone_commands.approve_zone_assessment(
        zone_repo, context, assessment_id=submitted_a.id, approved_zone="UNIQUE", review_reason="matches evidence",
    )
    await pg_session.commit()

    port = _PgPortfolioQueryPort(pg_session)
    summary = await zone_queries.get_portfolio_zone_summary(port, context, now=UTC_NOW)

    assert summary.total_count == 3
    # Item 7: REJECTED must not inflate unreviewed_count.
    assert summary.unreviewed_count == 0
    assert summary.rejected_count == 1
    # Item 8: RETIRED must not appear in unique_count (active distribution),
    # only in retired_count.
    assert summary.retired_count == 1
    assert summary.unique_count == 1
    assert summary.commodity_count == 0
    assert summary.advantage_count == 0
    assert (
        summary.commodity_count + summary.advantage_count + summary.unique_count
        + summary.unreviewed_count + summary.rejected_count + summary.retired_count
        == summary.total_count
    )


# ---------------------------------------------------------------------------
# Item 9: two policy versions with different weights produce different
# differentiation_index for the same six-dimension input, after a real
# Postgres persistence round trip.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_different_policy_weights_produce_different_differentiation_index_after_pg_round_trip(
    pg_session, zone_repo, base_repo
):
    await _seed_product_concept(base_repo, concept_id="concept-weights-a")
    await _seed_product_concept(base_repo, concept_id="concept-weights-b")

    policy_equal = _build_policy(policy_id="zone-policy-equal-weights")
    await zone_repo.save_zone_policy_version(policy_equal)
    await pg_session.commit()
    context = _reviewer_context()

    draft_equal = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context,
        product_concept_id="concept-weights-a", zone_policy_version_id=policy_equal.policy_id,
    )
    # Heterogeneous dimension scores so weight changes actually move the
    # index (a uniform-score input would be weight-invariant).
    mixed_input = _dimension_input(score=90.0)
    for row in mixed_input:
        if row["dimension"] == "replaceability":
            row["score"] = 20.0
    scored_equal = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft_equal.id, dimension_assessments=mixed_input,
    )
    await pg_session.commit()

    # Second policy: retire the first (real-Postgres-only concern —
    # load_active_zone_policy_version has no policy_id filter, so exactly one
    # ACTIVE row must exist platform-wide for this test's own query to be
    # unambiguous) then activate a differently-weighted one under a
    # DIFFERENT policy_id (uq_zone_policy_active_per_id is scoped to
    # policy_id, not global).
    retired_equal = policy_equal.model_copy(update={"status": "RETIRED"})
    await zone_repo.save_zone_policy_version(retired_equal)

    policy_skewed = _build_policy(
        policy_id="zone-policy-skewed-weights",
        weights={
            "customer_scarcity": 4.0,
            "replaceability": 1.0,
            "data_advantage": 1.0,
            "network_effect": 1.0,
            "learning_effect": 1.0,
            "switching_cost": 1.0,
        },
    )
    await zone_repo.save_zone_policy_version(policy_skewed)
    await pg_session.commit()

    draft_skewed = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context,
        product_concept_id="concept-weights-b", zone_policy_version_id=policy_skewed.policy_id,
    )
    scored_skewed = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft_skewed.id, dimension_assessments=mixed_input,
    )
    await pg_session.commit()

    reloaded_equal = await zone_repo.load_zone_assessment(scored_equal.id, "tenant-a")
    reloaded_skewed = await zone_repo.load_zone_assessment(scored_skewed.id, "tenant-a")

    assert reloaded_equal.differentiation_index != reloaded_skewed.differentiation_index
    assert reloaded_equal.zone_policy_version_id == policy_equal.policy_id
    assert reloaded_skewed.zone_policy_version_id == policy_skewed.policy_id


# ---------------------------------------------------------------------------
# Item 10: historical (already-APPROVED) assessment under policy v1
# unaffected by a later, differently-weighted policy v2.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_historical_assessment_not_rewritten_by_later_policy_version(pg_session, zone_repo, base_repo):
    await _seed_product_concept(base_repo, concept_id="concept-historical")

    policy_v1 = _build_policy(policy_id="zone-policy-historical", version=1)
    await zone_repo.save_zone_policy_version(policy_v1)
    await pg_session.commit()
    context = _reviewer_context()

    draft = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context,
        product_concept_id="concept-historical", zone_policy_version_id=policy_v1.policy_id,
    )
    mixed_input = _dimension_input(score=90.0)
    for row in mixed_input:
        if row["dimension"] == "replaceability":
            row["score"] = 20.0
    scored = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft.id, dimension_assessments=mixed_input,
    )
    submitted = await zone_commands.submit_zone_review(zone_repo, context, assessment_id=scored.id)
    approved = await zone_commands.approve_zone_assessment(
        zone_repo, context, assessment_id=submitted.id,
        approved_zone=scored.recommended_zone, review_reason="matches evidence",
    )
    await pg_session.commit()

    original_snapshot = (
        approved.recommended_zone,
        approved.differentiation_index,
        approved.defensibility_index,
        approved.commodity_score,
        approved.advantage_score,
        approved.unique_score,
        approved.zone_policy_version_id,
    )

    # Retire v1, publish v2 under a NEW policy_id (uq_zone_policy_active_per_id
    # is per-policy_id) with materially different weights/thresholds.
    retired_v1 = policy_v1.model_copy(update={"status": "RETIRED"})
    await zone_repo.save_zone_policy_version(retired_v1)
    policy_v2 = _build_policy(
        policy_id="zone-policy-historical-v2",
        version=1,
        weights={
            "customer_scarcity": 5.0,
            "replaceability": 0.2,
            "data_advantage": 3.0,
            "network_effect": 0.1,
            "learning_effect": 0.1,
            "switching_cost": 0.1,
        },
        thresholds={
            "unique_defensibility_min": 10.0,
            "unique_floor_gate_min": 5.0,
            "commodity_differentiation_max": 90.0,
            "commodity_defensibility_max": 90.0,
        },
    )
    await zone_repo.save_zone_policy_version(policy_v2)
    await pg_session.commit()

    reloaded = await zone_repo.load_zone_assessment(approved.id, "tenant-a")
    reloaded_snapshot = (
        reloaded.recommended_zone,
        reloaded.differentiation_index,
        reloaded.defensibility_index,
        reloaded.commodity_score,
        reloaded.advantage_score,
        reloaded.unique_score,
        reloaded.zone_policy_version_id,
    )

    assert reloaded_snapshot == original_snapshot
    assert reloaded.zone_policy_version_id == policy_v1.policy_id
    assert reloaded.zone_policy_version_id != policy_v2.policy_id


# ---------------------------------------------------------------------------
# Item 11: algorithm_version/checksum stability across a real Postgres
# persistence round trip.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_algorithm_version_and_checksum_stable_after_pg_round_trip(zone_repo, pg_session):
    policy = _build_policy(policy_id="zone-policy-checksum-stability")
    original_checksum = policy.checksum
    original_recomputed = policy.compute_checksum()
    assert original_checksum == original_recomputed  # sanity: checksum matches its own recompute pre-save

    await zone_repo.save_zone_policy_version(policy)
    await pg_session.commit()

    reloaded = await zone_repo.load_active_zone_policy_version()

    assert reloaded.checksum == original_checksum
    assert reloaded.scoring_algorithm_version == policy.scoring_algorithm_version == "ZONE_SCORING_V0"
    # The reloaded entity's own recompute (over the reloaded field values,
    # not the cached checksum) must still land on the identical hash — this
    # is the real "stable and reproducible after a DB round trip" check, not
    # merely "the same string came back unchanged".
    assert reloaded.compute_checksum() == original_checksum
