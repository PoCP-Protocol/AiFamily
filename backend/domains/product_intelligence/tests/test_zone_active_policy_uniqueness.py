"""Active-policy-version uniqueness fail-closed test — PR-002R Agent C scope
("Active Policy唯一性"). Companion to
`infrastructure/zone_sqlalchemy_repository.py::load_active_zone_policy_version`'s
closure fix and the partial unique index added by
`database/migrations/0060_product_zone_engine_canonical_cleanup.sql`
(`uq_zone_policy_active_per_id`).

This test deliberately bypasses the normal application-layer write path
(there is no command in this domain that would let two `ACTIVE` rows for the
same `policy_id` coexist in the first place) and inserts two `ACTIVE` rows
for the same `policy_id` directly via the ORM/session, simulating "the data
is already inconsistent" (e.g. a pre-migration Postgres instance without the
partial unique index yet, or a direct DB write). The read path must fail
closed rather than silently pick one.

SQLite (this test's backend, same as `test_zone_persistence.py`) has no
native support for Postgres-style partial unique indexes, so this test only
exercises the *application-level* fail-closed check in
`load_active_zone_policy_version` — the DDL-level constraint itself is real
Postgres syntax verified by inspection/Agent D's real-Postgres pass, not by
this SQLite suite.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..domain.errors import ProductIntelligenceValidationError
from ..infrastructure import zone_sqlalchemy_models as zm
from ..infrastructure.sqlalchemy_models import Base
from ..infrastructure.zone_sqlalchemy_repository import SqlAlchemyZoneAssessmentRepository

UTC_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)


def _policy_row(*, row_id: str, policy_id: str, version: int) -> zm.ZonePolicyVersionRow:
    return zm.ZonePolicyVersionRow(
        id=row_id,
        policy_id=policy_id,
        version=version,
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
        classification_rules="UNIQUE if defensibility>=75 and floor>=50; else ADVANTAGE",
        review_policy={"unique_requires_reviewers": 1},
        effective_from=UTC_NOW,
        status="ACTIVE",
        checksum=f"checksum-{row_id}",
        scoring_algorithm_version="ZONE_SCORING_V0",
    )


@pytest_asyncio.fixture
async def sqlalchemy_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def zone_repo(sqlalchemy_session):
    return SqlAlchemyZoneAssessmentRepository(sqlalchemy_session)


@pytest.mark.asyncio
async def test_two_active_versions_for_same_policy_id_fails_closed(sqlalchemy_session, zone_repo):
    # Direct session inserts, bypassing save_zone_policy_version /
    # zone_commands entirely -- this is the "data already inconsistent"
    # scenario, not something the normal write path can produce.
    sqlalchemy_session.add(_policy_row(row_id="p1:1", policy_id="zone-policy-v0", version=1))
    sqlalchemy_session.add(_policy_row(row_id="p1:2", policy_id="zone-policy-v0", version=2))
    await sqlalchemy_session.flush()

    with pytest.raises(ProductIntelligenceValidationError) as exc_info:
        await zone_repo.load_active_zone_policy_version()

    assert exc_info.value.code == "multiple_active_policy_versions_for_policy_id"


@pytest.mark.asyncio
async def test_single_active_version_per_policy_id_still_loads_normally(sqlalchemy_session, zone_repo):
    sqlalchemy_session.add(_policy_row(row_id="p1:1", policy_id="zone-policy-v0", version=1))
    await sqlalchemy_session.flush()

    loaded = await zone_repo.load_active_zone_policy_version()

    assert loaded.policy_id == "zone-policy-v0"


@pytest.mark.asyncio
async def test_active_versions_across_different_policy_ids_do_not_trigger_false_positive(sqlalchemy_session, zone_repo):
    # One ACTIVE row per distinct policy_id must NOT be treated as a
    # conflict -- only >1 ACTIVE row sharing the SAME policy_id is a
    # violation. (V0's load_active_zone_policy_version has no policy_id
    # parameter, so with more than one distinct active policy_id this will
    # deterministically return whichever query returns first -- that
    # ambiguity is out of this task's scope per the task brief's "no
    # platform-wide single lineage constraint" instruction. This test only
    # asserts that the multi-policy_id case does not spuriously raise the
    # same-policy_id conflict error.)
    sqlalchemy_session.add(_policy_row(row_id="p1:1", policy_id="zone-policy-v0", version=1))
    sqlalchemy_session.add(_policy_row(row_id="p2:1", policy_id="zone-policy-v1", version=1))
    await sqlalchemy_session.flush()

    loaded = await zone_repo.load_active_zone_policy_version()

    assert loaded.policy_id in {"zone-policy-v0", "zone-policy-v1"}
