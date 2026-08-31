"""Real-PostgreSQL integration test (PR-001R item 7 / chief-architect
review on PR #27). Everything else in this test suite runs against
SQLite (`tests/conftest.py`) or an in-memory fake — this module is the one
place that proves:

1. The real migration `migrations/0058_product_intelligence_domain.sql`
   (this domain's local, pre-Alembic SQL — see `migrations/README.md`)
   applies cleanly on real Postgres (not just "the SQLAlchemy models create
   tables that happen to also work on SQLite").
2. The Signal -> Insight -> Opportunity -> GrowthProblem prefix of the
   acceptance chain can be created through
   `SqlAlchemyProductIntelligenceRepository` against that real schema and
   reloaded (traced) back to the `MarketSignal`.
3. The full chain (including `GrowthHypothesis`/`GrowthStrategy`/
   `ProductConcept` and the Human Gate `validate_growth_hypothesis`)
   creates and reverse-traces correctly against real Postgres, including
   the `validated_by/validated_at/validation_reason` columns added to
   `GrowthHypothesisRow` and the 0058 migration to close the gap this test
   originally discovered (see git history for the pre-fix version of this
   docstring, which documented the `TypeError` this test used to hit
   before those columns existed).
4. The `product_intelligence_growth_strategies` table's
   `CHECK (jsonb_array_length(hypothesis_ids) > 0)` constraint is enforced
   by Postgres itself, independent of the Python-side pydantic validator in
   `domain/entities.py` — this is checked by issuing a raw INSERT that
   bypasses the domain/application layers entirely.

Requires a real, disposable Postgres reachable at `AIFAMILY_TEST_DATABASE_URL`
— the repository-wide convention introduced by T-03; see
`docker-compose.dev.yml` for how to stand one up. This domain's original
`PI_POSTGRES_TEST_DSN` still resolves as a deprecated fallback so existing
local setups keep working. Skipped entirely (not failed) when neither is set,
so CI without Docker/Postgres available is unaffected.
"""

from __future__ import annotations

import pathlib

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.platform.persistence.session import (
    TEST_DATABASE_URL_ENV_VAR,
    resolve_test_database_url,
)

from ..application import commands, queries
from ..application.context import ActorContext
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository

# Resolved via the platform helper so every real-Postgres test in the repository
# reads one variable (T-03). The helper also normalises a bare `postgresql://`
# onto the async driver and honours the deprecated `PI_POSTGRES_TEST_DSN`.
POSTGRES_TEST_URL = resolve_test_database_url()

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason=(
        f"{TEST_DATABASE_URL_ENV_VAR} not set — real-Postgres integration test skipped "
        "(`docker compose -f docker-compose.dev.yml up -d`, then export it)"
    ),
)

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "migrations"
    / "0058_product_intelligence_domain.sql"
)

_ALL_TABLES = [
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


@pytest_asyncio.fixture
async def pg_repo():
    assert POSTGRES_TEST_URL is not None
    engine = create_async_engine(POSTGRES_TEST_URL)

    # Drop first so re-running this test against a persistent (not just
    # disposable) database is idempotent, then apply the real migration
    # file verbatim -- this is the point of the test: prove *that file*
    # works on real Postgres, not a hand-rewritten equivalent.
    async with engine.begin() as conn:
        for table in _ALL_TABLES:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
        # asyncpg's SQLAlchemy dialect refuses to execute a string containing
        # multiple statements in one call. The migration file has no
        # semicolons inside string literals/CHECK expressions, so a naive
        # split on ";" is safe here and lets us run the file verbatim,
        # statement by statement, exactly as psql would.
        for statement in migration_sql.split(";"):
            statement = statement.strip()
            if statement:
                await conn.execute(text(statement))

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session, SqlAlchemyProductIntelligenceRepository(session)
    await engine.dispose()


def _human_ctx(tenant: str = "tenant-pg-1") -> ActorContext:
    return ActorContext(
        actor_id="pm-1",
        actor_type="HUMAN",
        tenant_scope=tenant,
        permissions=frozenset({"product_intelligence.hypothesis.review"}),
    )


def _ai_ctx(tenant: str = "tenant-pg-1") -> ActorContext:
    return ActorContext(actor_id="ai:market.insight.generate", actor_type="AI", tenant_scope=tenant)


@pytest.mark.asyncio
async def test_migration_applies_and_full_chain_creates_and_traces(pg_repo):
    session, repo = pg_repo
    human = _human_ctx()
    ai = _ai_ctx()

    signal = await commands.create_market_signal(
        repo, human, raw_text="家长普遍反映每天辅导作业太累"
    )
    insight = await commands.create_customer_insight(
        repo,
        ai,
        signal_id=signal.id,
        statement="小学高年级家长群体存在学习管理退出困难",
        evidence_refs=[f"market-signal:{signal.id}"],
        model_ref="claude-sonnet-4-6",
        prompt_use_case_version="v1",
        confidence=0.7,
    )
    opportunity = await commands.create_opportunity(
        repo, human, insight_id=insight.id, statement="学习责任转移计划"
    )
    problem = await commands.create_growth_problem(
        repo, human, opportunity_id=opportunity.id, symptom="孩子写作业拖延"
    )
    hypothesis = await commands.create_growth_hypothesis(
        repo,
        human,
        problem_id=problem.id,
        statement="家长控制增加导致孩子自主感下降",
    )
    strategy = await commands.create_growth_strategy(
        repo,
        human,
        problem_id=problem.id,
        hypothesis_ids=[hypothesis.id],
        statement="先完成学习责任逐步转移",
    )
    concept = await commands.create_product_concept(
        repo, human, strategy_id=strategy.id, title="学习自主21天计划"
    )
    await session.commit()

    validated = await commands.validate_growth_hypothesis(
        repo, human, hypothesis_id=hypothesis.id, reason="matches evidence"
    )
    await session.commit()
    assert validated.status == "VALIDATED"
    assert validated.validated_by == human.actor_id
    assert validated.validated_at is not None

    chain = await queries.get_product_concept_chain(repo, human, product_concept_id=concept.id)
    assert chain["product_concept"].id == concept.id
    assert chain["growth_strategy"].id == strategy.id
    assert chain["growth_problem"].id == problem.id
    assert [h.id for h in chain["growth_hypotheses"]] == [hypothesis.id]
    assert chain["opportunity"].id == opportunity.id
    assert chain["customer_insight"].id == insight.id
    assert chain["market_signal"].id == signal.id
    assert chain["market_signal"].raw_text == signal.raw_text


@pytest.mark.asyncio
async def test_growth_strategy_check_constraint_rejects_empty_hypothesis_ids_at_db_level(pg_repo):
    """This deliberately bypasses `domain/entities.py` (the pydantic-level
    validator already tested in `test_acceptance_chain.py::
    test_growth_strategy_requires_at_least_one_hypothesis`) and issues a raw
    INSERT, to prove the database schema itself — the
    `CHECK (jsonb_array_length(hypothesis_ids) > 0)` constraint on
    `product_intelligence_growth_strategies` — is a real, independent
    safety net, not something that only exists in application code.
    """
    session, repo = pg_repo
    human = _human_ctx()

    # Need a real parent growth_problem row to satisfy the FK constraint on
    # problem_id, so the only constraint violation triggered is the CHECK.
    signal = await commands.create_market_signal(
        repo, human, raw_text="raw text for constraint test"
    )
    insight = await commands.create_customer_insight(
        repo, human, signal_id=signal.id, statement="insight"
    )
    opportunity = await commands.create_opportunity(
        repo, human, insight_id=insight.id, statement="opportunity"
    )
    problem = await commands.create_growth_problem(
        repo, human, opportunity_id=opportunity.id, symptom="symptom"
    )
    await session.commit()

    with pytest.raises(IntegrityError) as excinfo:
        await session.execute(
            text(
                """
                INSERT INTO product_intelligence_growth_strategies
                    (id, version, created_at, updated_at, created_by, tenant_scope, status,
                     problem_id, hypothesis_ids, statement)
                VALUES
                    (:id, 1, now(), now(), :created_by, :tenant_scope, 'DRAFT',
                     :problem_id, '[]'::jsonb, :statement)
                """
            ),
            {
                "id": "strategy-constraint-test",
                "created_by": human.actor_id,
                "tenant_scope": human.tenant_scope,
                "problem_id": problem.id,
                "statement": "empty hypothesis_ids should be rejected by the DB",
            },
        )
        await session.flush()
    await session.rollback()

    # Postgres reports this as a CheckViolation, surfaced by SQLAlchemy as
    # an IntegrityError wrapping asyncpg's CheckViolationError.
    assert "check" in str(excinfo.value).lower() or "violat" in str(excinfo.value).lower()
