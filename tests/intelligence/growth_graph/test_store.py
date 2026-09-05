from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.growth_graph.store import (
    GrowthGraphEdge,
    GrowthGraphPersistenceBase,
    SqlAlchemyGrowthGraphProjection,
)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(GrowthGraphPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _scope(tenant: str = "tenant-graph") -> ExperienceScope:
    return ExperienceScope(
        global_id=f"global-{tenant}",
        tenant_id=tenant,
        region_id="CN",
        family_id="family-graph",
        subject_ids=("child-graph", "guardian-graph"),
        purpose="growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete-graph", "graph.v1"),
        correlation_id="corr-graph",
        causation_id="cause-graph",
    )


def _edge(scope: ExperienceScope | None = None, edge_id: str = "edge-001") -> GrowthGraphEdge:
    scope = scope or _scope()
    return GrowthGraphEdge(
        edge_id=edge_id,
        scope=scope,
        source_node="need:morning_routine",
        target_node="action:shared_planning",
        relation="supports",
        event_ref="event:journey-001",
        evidence_refs=("evidence:journey-001",),
        provenance=ExperienceProvenance(
            provenance_ref="prov:graph-001",
            source_refs=("event:journey-001",),
            kind=ProvenanceKind.USER,
            policy_version="graph-policy.v1",
        ),
        observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        expires_at=datetime(2026, 9, 30, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_project_query_and_idempotent_replay(session_factory) -> None:
    edge = _edge()
    async with session_factory() as session:
        projection = SqlAlchemyGrowthGraphProjection(session)
        async with session.begin():
            assert await projection.project(edge) is edge
            replay = await projection.project(edge)
            assert replay.edge_id == edge.edge_id
        result = await projection.query(_scope(), subject_id="child-graph")
        assert tuple(item.edge_id for item in result) == ("edge-001",)


@pytest.mark.asyncio
async def test_query_is_scope_bound_and_expired_edges_are_hidden(session_factory) -> None:
    edge = _edge()
    async with session_factory() as session:
        projection = SqlAlchemyGrowthGraphProjection(session)
        async with session.begin():
            await projection.project(edge)
        assert await projection.query(_scope("tenant-other")) == ()
        assert await projection.query(_scope(), now=datetime(2026, 10, 1, tzinfo=UTC)) == ()


@pytest.mark.asyncio
async def test_cascade_delete_is_idempotent_and_auditable(session_factory) -> None:
    scope = _scope()
    async with session_factory() as session:
        projection = SqlAlchemyGrowthGraphProjection(session)
        async with session.begin():
            await projection.project(_edge(scope))
            proof = await projection.cascade_delete(
                tenant_id=scope.tenant_id,
                region_id=scope.region_id,
                family_id=scope.family_id,
                subject_id="child-graph",
                requested_by="guardian-graph",
            )
            replay = await projection.cascade_delete(
                tenant_id=scope.tenant_id,
                region_id=scope.region_id,
                family_id=scope.family_id,
                subject_id="child-graph",
                requested_by="guardian-graph",
            )
        assert proof.proof_id == replay.proof_id
        assert proof.deleted_edge_ids == ("edge-001",)
        assert await projection.query(scope) == ()
