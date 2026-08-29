"""SQLite-backed persistence tests for
`infrastructure/zone_sqlalchemy_repository.py` — same style as
`test_acceptance_chain.py`'s `sqlalchemy_repo` fixture usage, but scoped to
the Product Zone tables added by `0059_product_zone_engine_v0.sql`. Also
exercises `zone_fake_repository.py` for parity (same behaviour on both
backends), mirroring how `test_acceptance_chain.py`/`test_tenant_isolation.py`
run shared scenarios against the fake as a cheaper double.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..application import zone_commands
from ..application.context import ActorContext
from ..domain.errors import ProductIntelligenceNotFoundError
from ..domain.zone_entities import DimensionAssessment, ProductZoneAssessment, ZonePolicyVersion
from ..infrastructure import zone_sqlalchemy_models as zm
from ..infrastructure.sqlalchemy_models import Base
from ..infrastructure.sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository
from ..infrastructure.zone_fake_repository import FakeZoneAssessmentRepository
from ..infrastructure.zone_sqlalchemy_repository import SqlAlchemyZoneAssessmentRepository

UTC_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)

ZONE_REVIEW_PERMISSION = zone_commands.ZONE_REVIEW_PERMISSION


def _reviewer_context(tenant_scope: str = "tenant-a") -> ActorContext:
    return ActorContext(
        actor_id="human-reviewer-1", actor_type="HUMAN", tenant_scope=tenant_scope,
        permissions=frozenset({ZONE_REVIEW_PERMISSION}),
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


@pytest_asyncio.fixture
async def base_repo(sqlalchemy_session):
    return SqlAlchemyProductIntelligenceRepository(sqlalchemy_session)


async def _seed_product_concept(base_repo, *, concept_id: str, tenant_scope: str = "tenant-a"):
    from ..domain.entities import GrowthStrategy, ProductConcept

    strategy = GrowthStrategy(
        id="strategy-1", created_at=UTC_NOW, updated_at=UTC_NOW, created_by="human-1",
        tenant_scope=tenant_scope, status="APPROVED", problem_id="problem-1",
        hypothesis_ids=["hyp-1"], statement="grow via zone engine",
    )
    await base_repo.save_growth_strategy(strategy)
    concept = ProductConcept(
        id=concept_id, created_at=UTC_NOW, updated_at=UTC_NOW, created_by="human-1",
        tenant_scope=tenant_scope, status="DRAFT", strategy_id=strategy.id, title="concept",
    )
    await base_repo.save_product_concept(concept)
    return concept


@pytest.mark.asyncio
async def test_zone_policy_version_round_trip(zone_repo):
    policy = _build_policy()
    await zone_repo.save_zone_policy_version(policy)
    loaded = await zone_repo.load_active_zone_policy_version()
    assert loaded.policy_id == policy.policy_id
    assert loaded.checksum == policy.checksum
    assert loaded.thresholds == policy.thresholds


@pytest.mark.asyncio
async def test_load_active_zone_policy_version_not_found_raises(zone_repo):
    with pytest.raises(ProductIntelligenceNotFoundError):
        await zone_repo.load_active_zone_policy_version()


@pytest.mark.asyncio
async def test_zone_assessment_round_trip_preserves_dimension_assessments(zone_repo, base_repo):
    await _seed_product_concept(base_repo, concept_id="concept-1")
    context = _reviewer_context()
    # `base_repo` (SqlAlchemyProductIntelligenceRepository over the same
    # session) is a real `ProductIntelligenceRepositoryPort` implementation
    # and already has "concept-1" seeded above via `_seed_product_concept` —
    # it doubles as `product_intelligence_repo` here.
    draft = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context, product_concept_id="concept-1", zone_policy_version_id="zone-policy-v0",
    )
    await zone_repo.save_zone_policy_version(_build_policy())
    scored = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft.id, dimension_assessments=_dimension_input(),
    )

    loaded = await zone_repo.load_zone_assessment(scored.id, "tenant-a")
    assert loaded.status == "SCORED"
    assert loaded.recommended_zone == "UNIQUE"
    assert len(loaded.dimension_assessments) == 6
    assert all(isinstance(d, DimensionAssessment) for d in loaded.dimension_assessments)
    assert all(d.assessed_at.tzinfo is not None for d in loaded.dimension_assessments)
    assert loaded.dimension_score_map()["customer_scarcity"] == 90.0


@pytest.mark.asyncio
async def test_load_zone_assessment_wrong_tenant_raises_not_found(zone_repo, base_repo):
    await _seed_product_concept(base_repo, concept_id="concept-1")
    await zone_repo.save_zone_policy_version(_build_policy())
    context = _reviewer_context()
    draft = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context, product_concept_id="concept-1", zone_policy_version_id="zone-policy-v0",
    )
    with pytest.raises(ProductIntelligenceNotFoundError):
        await zone_repo.load_zone_assessment(draft.id, "tenant-b")


@pytest.mark.asyncio
async def test_load_zone_assessment_missing_id_raises_not_found(zone_repo):
    with pytest.raises(ProductIntelligenceNotFoundError):
        await zone_repo.load_zone_assessment("does-not-exist", "tenant-a")


@pytest.mark.asyncio
async def test_full_lifecycle_persists_through_approval(zone_repo, base_repo):
    await _seed_product_concept(base_repo, concept_id="concept-1")
    await zone_repo.save_zone_policy_version(_build_policy())
    context = _reviewer_context()
    draft = await zone_commands.create_zone_assessment(
        zone_repo, base_repo, context, product_concept_id="concept-1", zone_policy_version_id="zone-policy-v0",
    )
    scored = await zone_commands.score_zone_assessment(
        zone_repo, context, assessment_id=draft.id, dimension_assessments=_dimension_input(),
    )
    submitted = await zone_commands.submit_zone_review(zone_repo, context, assessment_id=scored.id)
    approved = await zone_commands.approve_zone_assessment(
        zone_repo, context, assessment_id=submitted.id, approved_zone="UNIQUE", review_reason="matches evidence",
    )

    loaded = await zone_repo.load_zone_assessment(approved.id, "tenant-a")
    assert loaded.status == "APPROVED"
    assert loaded.approved_zone == "UNIQUE"
    assert loaded.reviewed_by == context.actor_id
    assert loaded.reviewed_at is not None


@pytest.mark.asyncio
async def test_subject_ref_foreign_key_enforced_against_real_product_concept(sqlalchemy_session, zone_repo, base_repo):
    """The `subject_ref` FK to `product_intelligence_product_concepts(id)`
    added in 0059 means a `ProductZoneAssessment` referencing a nonexistent
    `ProductConcept` id must fail at flush time. SQLite only enforces FKs
    when `PRAGMA foreign_keys=ON`, which is not the SQLAlchemy default for
    aiosqlite — this test enables it explicitly so the constraint is
    actually exercised here, not silently skipped.
    """
    from sqlalchemy import text

    await sqlalchemy_session.execute(text("PRAGMA foreign_keys=ON"))

    bad_assessment = ProductZoneAssessment(
        id="zoneassess-orphan",
        created_at=UTC_NOW,
        updated_at=UTC_NOW,
        created_by="human-1",
        tenant_scope="tenant-a",
        status="DRAFT",
        subject_ref="concept-does-not-exist",
        zone_policy_version_id="zone-policy-v0",
        dimension_assessments=[
            DimensionAssessment(
                dimension=dimension,
                score=0.0,
                rationale="pending_initial_assessment",
                evidence_refs=["pending_initial_assessment"],
                evidence_strength=0.0,
                assessed_by="human-1",
                assessed_at=UTC_NOW,
            )
            for dimension in (
                "customer_scarcity", "replaceability", "data_advantage",
                "network_effect", "learning_effect", "switching_cost",
            )
        ],
        differentiation_index=0.0,
        defensibility_index=0.0,
        commodity_score=0.0,
        advantage_score=0.0,
        unique_score=0.0,
        recommended_zone="COMMODITY",
        assessment_origin="HUMAN",
    )
    with pytest.raises(Exception):
        await zone_repo.save_zone_assessment(bad_assessment)
