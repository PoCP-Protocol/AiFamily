"""Real-Postgres tests for :class:`SqlAlchemyImprovementCandidateRepository`.

Follows the opt-in gated pattern from
``tests/domains/family_need/test_postgres_repository_integration.py`` and
``tests/domains/product_intelligence/test_course_content_postgres_repository_integration.py``:
every test is skipped unless ``AIFAMILY_TEST_DATABASE_URL`` is set (see
``tests/support/postgres.py``).
"""

from __future__ import annotations

import pytest

from backend.domains.product_intelligence.domain.improvement_candidate import (
    ImprovementCandidate,
)
from backend.domains.product_intelligence.infrastructure import (
    improvement_candidate_postgres_repository as icpr,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

SqlAlchemyImprovementCandidateRepository = icpr.SqlAlchemyImprovementCandidateRepository


def _candidate(**overrides) -> ImprovementCandidate:
    return ImprovementCandidate.record(
        component_id=overrides.pop("component_id", "COMMUNICATION"),
        component_shape=overrides.pop("component_shape", "SERVICE"),
        decision=overrides.pop("decision", "DID_NOT_HELP"),
        category=overrides.pop("category", "EDUCATION"),
        intervention_tier=overrides.pop("intervention_tier", "LIGHT_GUIDANCE"),
        **overrides,
    )


async def _apply_improvement_candidate_migration(engine) -> None:
    """Replay the 0060 migration's `upgrade()` directly against the
    schema-scoped engine, matching the family_need/course_content
    integration tests' own approach to a per-test disposable schema."""

    import importlib

    improvement_candidate_migration = importlib.import_module(
        "database.migrations.versions.0060_product_improvement_candidates"
    )

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_conn: _run_upgrade(sync_conn, improvement_candidate_migration)
        )


def _run_upgrade(sync_connection, migration_module) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
    with Operations.context(context):
        migration_module.upgrade()


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_save_and_list_improvement_candidates_round_trips_through_real_postgres() -> None:
    """The hard privacy proof at the persistence layer: this aggregate's own
    row shape has no family/tenant/child column to leak — only component/
    shape/decision/category/tier/recorded_at survive the round trip."""

    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_improvement_candidate_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyImprovementCandidateRepository(connection)
            candidate = _candidate()
            await repository.save_improvement_candidate(candidate)

            loaded = await repository.list_improvement_candidates()
            assert len(loaded) == 1
            assert loaded[0] == candidate
            assert loaded[0].component_id == "COMMUNICATION"
            assert loaded[0].decision == "DID_NOT_HELP"


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_list_improvement_candidates_returns_most_recent_first() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_improvement_candidate_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyImprovementCandidateRepository(connection)
            older = _candidate(component_id="COURSE_A")
            newer = _candidate(component_id="COURSE_B")
            await repository.save_improvement_candidate(older)
            await repository.save_improvement_candidate(newer)

            loaded = await repository.list_improvement_candidates()
            component_ids = {item.component_id for item in loaded}
            assert component_ids == {"COURSE_A", "COURSE_B"}
