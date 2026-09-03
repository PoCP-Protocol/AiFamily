from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    MemoryLevel,
    MemoryRef,
    MemoryScope,
    ProvenanceKind,
    ScopeMismatchError,
)
from backend.intelligence.memory.store import (
    MemoryDeletionProofRow,
    MemoryPersistenceBase,
    SqlAlchemyMemoryStore,
)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(MemoryPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _scope(tenant_id: str = "tenant-memory") -> ExperienceScope:
    return ExperienceScope(
        global_id=f"global-{tenant_id}",
        tenant_id=tenant_id,
        region_id="CN",
        family_id="family-memory",
        subject_ids=("child-memory",),
        purpose="growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete-memory", "memory.v1"),
        correlation_id="corr-memory",
        causation_id="cause-memory",
    )


def _memory(scope: ExperienceScope | None = None) -> MemoryRef:
    scope = scope or _scope()
    created = datetime(2026, 8, 30, tzinfo=UTC)
    return MemoryRef(
        memory_id="memory:sql-001",
        memory_ref="memory://memory:sql-001",
        tenant_id=scope.tenant_id,
        region_id=scope.region_id,
        family_id=scope.family_id,
        subject_ids=scope.subject_ids,
        memory_scope=MemoryScope.CHILD,
        level=MemoryLevel.M3_DURABLE,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        consent_granted=True,
        data_class=scope.data_class,
        locale=scope.locale,
        provenance=ExperienceProvenance(
            provenance_ref="prov:memory:sql",
            source_refs=("event:sql-001",),
            kind=ProvenanceKind.USER,
            policy_version="memory-policy.v1",
        ),
        deletion_ref=scope.deletion_ref,
        source_ref="event:sql-001",
        correlation_id=scope.correlation_id,
        causation_id=scope.causation_id,
        created_at=created,
        expires_at=created + timedelta(days=30),
        derived_memory_ids=("memory:sql-001:derived",),
    )


@pytest.mark.asyncio
async def test_round_trip_and_idempotent_put(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyMemoryStore(session)
        memory = _memory()
        async with session.begin():
            assert await store.put(memory) == memory
            assert await store.put(memory) == memory
        loaded = await store.retrieve(memory.memory_id, _scope(), purpose="growth_support")
        assert loaded == memory


@pytest.mark.asyncio
async def test_scope_isolation_and_deletion_proof_survive_restart(session_factory) -> None:
    memory = _memory()
    async with session_factory() as session:
        store = SqlAlchemyMemoryStore(session)
        async with session.begin():
            await store.put(memory)
            with pytest.raises(ScopeMismatchError, match="CROSS_TENANT"):
                await store.retrieve(
                    memory.memory_id,
                    _scope("tenant-other"),
                    purpose="growth_support",
                )
            proof = await store.delete(memory.memory_id, _scope(), requested_by="guardian-1")
        assert proof.deleted_memory_ids == (memory.memory_id, "memory:sql-001:derived")

    async with session_factory() as session:
        store = SqlAlchemyMemoryStore(session)
        loaded = await store.get_deletion_proof(proof.proof_id, _scope())
        assert loaded == proof
        assert await session.scalar(select(MemoryDeletionProofRow)) is not None
        with pytest.raises(ExperienceContractError, match="MEMORY_NOT_FOUND"):
            await store.retrieve(memory.memory_id, _scope(), purpose="growth_support")


@pytest.mark.asyncio
async def test_expired_purge_creates_audit_proof(session_factory) -> None:
    scope = _scope()
    memory = _memory(scope)
    expired = replace(
        memory,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        expires_at=datetime(2026, 8, 29, tzinfo=UTC),
    )
    async with session_factory() as session:
        store = SqlAlchemyMemoryStore(session)
        async with session.begin():
            await store.put(expired)
            assert await store.purge_expired(now=datetime(2026, 8, 30, tzinfo=UTC)) == 1
        proof = await store.get_deletion_proof("proof:delete-memory", scope)
        assert proof.requested_by == "retention-worker"
