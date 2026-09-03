"""Positive and adversarial tests for durable ModelDraft provenance."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.service.fgcn.api import dependencies as fgcn_dependencies
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.model_gateway.provenance import (
    ModelDraftNotFound,
    ModelDraftRegistryBase,
    ModelDraftRegistryError,
    ModelDraftRow,
    ModelDraftScope,
    SqlAlchemyModelDraftRegistry,
)

TENANT = "tenant-provenance-1"
FAMILY = "family-provenance-1"
CHILD = "child-provenance-1"
PURPOSE = "service_collaboration"
CORRELATION = "correlation-provenance-1"
CREATED_AT = datetime(2026, 8, 30, 12, tzinfo=UTC)
GENERATED_AT = datetime(2026, 8, 30, 11, 59, tzinfo=UTC)


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ModelDraftRegistryBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _scope(**overrides: str) -> ModelDraftScope:
    values = {
        "tenant_id": TENANT,
        "family_id": FAMILY,
        "subject_person_id": CHILD,
        "purpose": PURPOSE,
        "correlation_id": CORRELATION,
    }
    values.update(overrides)
    return ModelDraftScope(**values)


def _draft(*, output: dict[str, object] | None = None, status: str = "DRAFT") -> ModelDraft:
    return ModelDraft(
        output=output or {"candidate": "expert-provenance-1", "limitations": ["draft"]},
        provenance=AiProvenance(
            provider_id="fake-provider",
            model="fake-model",
            model_version="1.0.0",
            prompt_version="service-match.v1",
            schema_version="service-match.v1",
            context_snapshot_ref="context:provenance-1",
            latency_ms=12,
            data_class="MINOR_PERSONAL_DATA",
            use_case="service_matching_recommendation",
            confidence=0.7,
            generated_at=GENERATED_AT,
        ),
        status=status,  # type: ignore[arg-type]
    )


async def _save(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session:
        await SqlAlchemyModelDraftRegistry(session).save(
            draft_id="draft:provenance-1",
            provenance_ref="model-draft:provenance-1",
            scope=_scope(),
            draft=_draft(),
            created_at=CREATED_AT,
        )
        await session.commit()


@pytest.mark.asyncio
async def test_registry_round_trips_and_idempotently_replays_a_scoped_draft(session_factory):
    await _save(session_factory)

    async with session_factory() as session:
        registry = SqlAlchemyModelDraftRegistry(session)
        loaded = await registry.resolve(
            "model-draft:provenance-1",
            tenant_id=TENANT,
            family_id=FAMILY,
            subject_person_id=CHILD,
            purpose=PURPOSE,
            correlation_id=CORRELATION,
        )
        replay = await registry.save(
            draft_id="draft:provenance-1",
            provenance_ref="model-draft:provenance-1",
            scope=_scope(),
            draft=_draft(),
            created_at=CREATED_AT,
        )

    assert loaded == _draft()
    assert replay.draft == loaded
    assert replay.scope == _scope()


@pytest.mark.asyncio
async def test_fgcn_default_dependency_constructs_the_durable_registry(session_factory):
    async with session_factory() as session:
        resolver = fgcn_dependencies.get_draft_provenance_resolver(session)

    assert isinstance(resolver, SqlAlchemyModelDraftRegistry)


@pytest.mark.asyncio
async def test_registry_hides_unknown_and_foreign_scope_references(session_factory):
    await _save(session_factory)

    async with session_factory() as session:
        registry = SqlAlchemyModelDraftRegistry(session)
        for scope in (
            _scope(tenant_id="foreign-tenant"),
            _scope(family_id="foreign-family"),
            _scope(subject_person_id="foreign-child"),
            _scope(purpose="different-purpose"),
            _scope(correlation_id="foreign-correlation"),
        ):
            with pytest.raises(ModelDraftNotFound):
                await registry.resolve(
                    "model-draft:provenance-1",
                    tenant_id=scope.tenant_id,
                    family_id=scope.family_id,
                    subject_person_id=scope.subject_person_id,
                    purpose=scope.purpose,
                    correlation_id=scope.correlation_id,
                )
        with pytest.raises(ModelDraftNotFound):
            await registry.resolve(
                "model-draft:does-not-exist",
                tenant_id=TENANT,
                family_id=FAMILY,
                subject_person_id=CHILD,
                purpose=PURPOSE,
                correlation_id=CORRELATION,
            )


@pytest.mark.asyncio
async def test_registry_rejects_non_draft_and_forbidden_fact_shaped_output(session_factory):
    async with session_factory() as session:
        registry = SqlAlchemyModelDraftRegistry(session)
        with pytest.raises(ModelDraftRegistryError, match="MUST_REMAIN_DRAFT"):
            await registry.save(
                draft_id="draft:validated",
                provenance_ref="model-draft:validated",
                scope=_scope(),
                draft=_draft(status="VALIDATED"),
                created_at=CREATED_AT,
            )
        with pytest.raises(ModelDraftRegistryError, match="cannot become a business fact"):
            await registry.save(
                draft_id="draft:fact-shaped",
                provenance_ref="model-draft:fact-shaped",
                scope=_scope(),
                draft=_draft(output={"family_score": 99}),
                created_at=CREATED_AT,
            )


@pytest.mark.asyncio
async def test_registry_rejects_reference_collision_and_changed_replay(session_factory):
    await _save(session_factory)

    async with session_factory() as session:
        registry = SqlAlchemyModelDraftRegistry(session)
        with pytest.raises(ModelDraftRegistryError, match="PROVENANCE_REF_COLLISION"):
            await registry.save(
                draft_id="draft:another-id",
                provenance_ref="model-draft:provenance-1",
                scope=_scope(),
                draft=_draft(),
                created_at=CREATED_AT,
            )
        with pytest.raises(ModelDraftRegistryError, match="REPLAY_MISMATCH"):
            await registry.save(
                draft_id="draft:provenance-1",
                provenance_ref="model-draft:provenance-1",
                scope=_scope(),
                draft=_draft(output={"candidate": "changed"}),
                created_at=CREATED_AT,
            )


@pytest.mark.asyncio
async def test_registry_rejects_tampered_persisted_output_before_returning_it(session_factory):
    await _save(session_factory)

    async with session_factory() as session:
        row = await session.get(
            ModelDraftRow,
            {"tenant_id": TENANT, "draft_id": "draft:provenance-1"},
        )
        assert row is not None
        row.output_payload = {"canonical_state": "ACTIVE"}
        with pytest.raises(ModelDraftRegistryError, match="cannot become a business fact"):
            await SqlAlchemyModelDraftRegistry(session).resolve(
                "model-draft:provenance-1",
                tenant_id=TENANT,
                family_id=FAMILY,
                subject_person_id=CHILD,
                purpose=PURPOSE,
                correlation_id=CORRELATION,
            )
