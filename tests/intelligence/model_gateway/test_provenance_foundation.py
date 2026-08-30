"""Synthetic and persistence contract tests for Model Gateway provenance."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.model_gateway.provenance import (
    InMemoryModelDraftRegistry,
    ModelDraftIdentity,
    ModelDraftNotFound,
    ModelDraftRegistryBase,
    ModelDraftRegistryError,
    ModelDraftRow,
    ModelDraftScope,
    SqlAlchemyModelDraftRegistry,
    StoredModelDraft,
)

TENANT = "tenant-synthetic-1"
FAMILY = "family-synthetic-1"
SUBJECT = "subject-synthetic-1"
PURPOSE = "draft-summary"
CORRELATION = "correlation-synthetic-1"
GENERATED_AT = datetime(2026, 8, 30, 12, tzinfo=UTC)
CREATED_AT = datetime(2026, 8, 30, 12, 1, tzinfo=UTC)


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
        "subject_person_id": SUBJECT,
        "purpose": PURPOSE,
        "correlation_id": CORRELATION,
    }
    values.update(overrides)
    return ModelDraftScope(**values)


def _draft(*, output: dict[str, object] | None = None, status: str = "DRAFT") -> ModelDraft:
    return ModelDraft(
        output=output or {"headline": "synthetic draft", "status": "DRAFT"},
        provenance=AiProvenance(
            provider_id="fake-synthetic-provider",
            model="fake-synthetic-model",
            model_version="test-v1",
            prompt_version="summary.v1",
            schema_version="summary.v1",
            context_snapshot_ref="context:synthetic-1",
            latency_ms=12,
            data_class="SYNTHETIC",
            use_case="synthetic_summary",
            confidence=None,
            generated_at=GENERATED_AT,
        ),
        status=status,  # type: ignore[arg-type]
    )


async def _save(registry: SqlAlchemyModelDraftRegistry) -> None:
    await registry.save(
        draft_id="draft:synthetic-1",
        provenance_ref="model-draft:synthetic-1",
        scope=_scope(),
        draft=_draft(),
        created_at=CREATED_AT,
    )


def test_identity_is_stable_and_server_derived() -> None:
    identity = ModelDraftIdentity.from_run_id(" run-42 ")

    assert identity.draft_id == "draft:run-42"
    assert identity.provenance_ref == "model-draft:run-42"


@pytest.mark.parametrize("run_id", ["", " ", "x" * 129])
def test_identity_rejects_invalid_run_ids(run_id: str) -> None:
    with pytest.raises(ModelDraftRegistryError):
        ModelDraftIdentity.from_run_id(run_id)


def test_scope_requires_every_isolation_dimension() -> None:
    with pytest.raises(ModelDraftRegistryError, match="SCOPE_REQUIRED"):
        _scope(subject_person_id=" ")


@pytest.mark.asyncio
async def test_in_memory_registry_round_trips_and_hides_foreign_scope() -> None:
    registry = InMemoryModelDraftRegistry()
    stored = await registry.save(
        draft_id="draft:synthetic-1",
        provenance_ref="model-draft:synthetic-1",
        scope=_scope(),
        draft=_draft(),
        created_at=CREATED_AT,
    )

    assert isinstance(stored, StoredModelDraft)
    assert (
        await registry.resolve(
            "model-draft:synthetic-1",
            tenant_id=TENANT,
            family_id=FAMILY,
            subject_person_id=SUBJECT,
            purpose=PURPOSE,
            correlation_id=CORRELATION,
        )
        == _draft()
    )
    with pytest.raises(ModelDraftNotFound):
        await registry.resolve(
            "model-draft:synthetic-1",
            tenant_id=TENANT,
            family_id=FAMILY,
            subject_person_id="foreign-subject",
            purpose=PURPOSE,
            correlation_id=CORRELATION,
        )


@pytest.mark.asyncio
async def test_in_memory_registry_replays_identically_and_rejects_collisions() -> None:
    registry = InMemoryModelDraftRegistry()
    first = await registry.save(
        draft_id="draft:synthetic-1",
        provenance_ref="model-draft:synthetic-1",
        scope=_scope(),
        draft=_draft(),
        created_at=CREATED_AT,
    )
    replay = await registry.save(
        draft_id="draft:synthetic-1",
        provenance_ref="model-draft:synthetic-1",
        scope=_scope(),
        draft=_draft(),
        created_at=datetime(2026, 8, 30, 13, tzinfo=UTC),
    )
    assert replay == first

    with pytest.raises(ModelDraftRegistryError, match="REPLAY_MISMATCH"):
        await registry.save(
            draft_id="draft:synthetic-1",
            provenance_ref="model-draft:synthetic-1",
            scope=_scope(),
            draft=_draft(output={"headline": "changed"}),
        )
    with pytest.raises(ModelDraftRegistryError, match="PROVENANCE_REF_COLLISION"):
        await registry.save(
            draft_id="draft:synthetic-2",
            provenance_ref="model-draft:synthetic-1",
            scope=_scope(),
            draft=_draft(),
        )


@pytest.mark.parametrize(
    ("output", "status", "message"),
    [
        ({"family_score": 1}, "DRAFT", "cannot become a business fact"),
        ({"headline": "draft"}, "VALIDATED", "MUST_REMAIN_DRAFT"),
    ],
)
@pytest.mark.asyncio
async def test_in_memory_registry_fails_closed_for_unsafe_drafts(
    output: dict[str, object], status: str, message: str
) -> None:
    with pytest.raises(ModelDraftRegistryError, match=message):
        await InMemoryModelDraftRegistry().save(
            draft_id="draft:unsafe",
            provenance_ref="model-draft:unsafe",
            scope=_scope(),
            draft=_draft(output=output, status=status),
        )


@pytest.mark.asyncio
async def test_sqlalchemy_registry_round_trips_complete_provenance(session_factory) -> None:
    async with session_factory() as session:
        registry = SqlAlchemyModelDraftRegistry(session)
        await _save(registry)
        await session.commit()

    async with session_factory() as session:
        registry = SqlAlchemyModelDraftRegistry(session)
        loaded = await registry.resolve(
            "model-draft:synthetic-1",
            tenant_id=TENANT,
            family_id=FAMILY,
            subject_person_id=SUBJECT,
            purpose=PURPOSE,
            correlation_id=CORRELATION,
        )
        row = await session.get(
            ModelDraftRow,
            {"tenant_id": TENANT, "draft_id": "draft:synthetic-1"},
        )

    assert loaded == _draft()
    assert row is not None
    assert row.status == "DRAFT"
    assert row.may_mutate_business_state is False
    assert row.provenance_payload["model_version"] == "test-v1"
    assert row.provenance_payload["prompt_version"] == "summary.v1"
    assert row.provenance_payload["context_snapshot_ref"] == "context:synthetic-1"


@pytest.mark.asyncio
async def test_sqlalchemy_registry_rejects_tampered_output(session_factory) -> None:
    async with session_factory() as session:
        registry = SqlAlchemyModelDraftRegistry(session)
        await _save(registry)
        await session.commit()

    async with session_factory() as session:
        row = await session.get(
            ModelDraftRow,
            {"tenant_id": TENANT, "draft_id": "draft:synthetic-1"},
        )
        assert row is not None
        row.output_payload = {"canonical_state": "ACTIVE"}
        with pytest.raises(ModelDraftRegistryError, match="cannot become a business fact"):
            await SqlAlchemyModelDraftRegistry(session).resolve(
                "model-draft:synthetic-1",
                tenant_id=TENANT,
                family_id=FAMILY,
                subject_person_id=SUBJECT,
                purpose=PURPOSE,
                correlation_id=CORRELATION,
            )
