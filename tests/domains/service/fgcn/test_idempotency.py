"""Tests for the tenant-scoped durable FGCN mutation claim."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.service.domain.errors import ServiceConflictError
from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.fgcn.idempotency import mutation_request_hash
from backend.domains.service.fgcn.persistence import FGCNBase, SqlAlchemyFGCNRepository


def _scope(tenant_id: str) -> GateServiceScope:
    return GateServiceScope(
        tenant_id=tenant_id,
        family_id="family-idempotency",
        subject_person_id="subject-idempotency",
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="correlation-idempotency",
    )


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(FGCNBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_mutation_claim_replays_durable_resource_without_second_claim(session_factory):
    scope = _scope("tenant-a")
    request_hash = mutation_request_hash(
        "SUBMIT_SERVICE_DELIVERY",
        scope,
        {"task_id": "task-1", "delivery_id": "delivery-1"},
    )
    async with session_factory() as session:
        repository = SqlAlchemyFGCNRepository(session)
        first = await repository.claim_mutation(
            scope=scope,
            action_name="SUBMIT_SERVICE_DELIVERY",
            idempotency_key="same-client-key",
            request_hash=request_hash,
        )
        assert first.is_new is True
        await repository.complete_mutation(
            scope=scope,
            action_name="SUBMIT_SERVICE_DELIVERY",
            idempotency_key="same-client-key",
            request_hash=request_hash,
            resource_id="delivery-1",
        )
        await session.commit()

    async with session_factory() as session:
        replay = await SqlAlchemyFGCNRepository(session).claim_mutation(
            scope=scope,
            action_name="SUBMIT_SERVICE_DELIVERY",
            idempotency_key="same-client-key",
            request_hash=request_hash,
        )
    assert replay.is_new is False
    assert replay.resource_id == "delivery-1"


@pytest.mark.asyncio
async def test_mutation_key_is_tenant_scoped_but_payload_reuse_conflicts(session_factory):
    scope_a = _scope("tenant-a")
    scope_b = _scope("tenant-b")
    hash_a = mutation_request_hash(
        "VERIFY_SERVICE_DELIVERY", scope_a, {"review_id": "review-1", "note": "approved"}
    )
    hash_b = mutation_request_hash(
        "VERIFY_SERVICE_DELIVERY", scope_b, {"review_id": "review-1", "note": "approved"}
    )
    async with session_factory() as session:
        repository = SqlAlchemyFGCNRepository(session)
        claim_a = await repository.claim_mutation(
            scope=scope_a,
            action_name="VERIFY_SERVICE_DELIVERY",
            idempotency_key="shared-client-key",
            request_hash=hash_a,
        )
        claim_b = await repository.claim_mutation(
            scope=scope_b,
            action_name="VERIFY_SERVICE_DELIVERY",
            idempotency_key="shared-client-key",
            request_hash=hash_b,
        )
        assert claim_a.is_new is True
        assert claim_b.is_new is True
        await session.rollback()

    changed_hash = mutation_request_hash(
        "VERIFY_SERVICE_DELIVERY", scope_a, {"review_id": "review-1", "note": "changed"}
    )
    async with session_factory() as session:
        repository = SqlAlchemyFGCNRepository(session)
        await repository.claim_mutation(
            scope=scope_a,
            action_name="VERIFY_SERVICE_DELIVERY",
            idempotency_key="shared-client-key",
            request_hash=hash_a,
        )
        await repository.complete_mutation(
            scope=scope_a,
            action_name="VERIFY_SERVICE_DELIVERY",
            idempotency_key="shared-client-key",
            request_hash=hash_a,
            resource_id="review-1",
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(
            ServiceConflictError,
            match="fgcn_mutation_idempotency_replay_mismatch",
        ):
            await SqlAlchemyFGCNRepository(session).claim_mutation(
                scope=scope_a,
                action_name="VERIFY_SERVICE_DELIVERY",
                idempotency_key="shared-client-key",
                request_hash=changed_hash,
            )


@pytest.mark.asyncio
async def test_uncommitted_mutation_claim_is_released_by_rollback(session_factory):
    scope = _scope("tenant-restart")
    request_hash = mutation_request_hash(
        "RECORD_SERVICE_CONTRIBUTION", scope, {"contribution_id": "contribution-1"}
    )
    async with session_factory() as session:
        repository = SqlAlchemyFGCNRepository(session)
        first = await repository.claim_mutation(
            scope=scope,
            action_name="RECORD_SERVICE_CONTRIBUTION",
            idempotency_key="crashed-request",
            request_hash=request_hash,
        )
        assert first.is_new is True
        await session.rollback()

    async with session_factory() as session:
        replay_after_rollback = await SqlAlchemyFGCNRepository(session).claim_mutation(
            scope=scope,
            action_name="RECORD_SERVICE_CONTRIBUTION",
            idempotency_key="crashed-request",
            request_hash=request_hash,
        )
    assert replay_after_rollback.is_new is True
