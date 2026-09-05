"""Real-Postgres contract for the single ``experience_outbox_messages`` writer."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.intelligence.experience.outbox import (
    ExperienceOutboxConflictError,
    ExperienceOutboxMessage,
    SqlAlchemyExperienceOutboxWriter,
)
from backend.platform.audit import AuditEvent, AuditRecorder
from backend.platform.audit.store import create_audit_schema
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork

DATABASE_URL = os.environ.get("AIFAMILY_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="AIFAMILY_TEST_DATABASE_URL not set — real-Postgres outbox test skipped",
)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(DATABASE_URL, poolclass=None)
    async with AsyncSession(engine) as session:
        await create_audit_schema(session)
        await session.commit()
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _message(
    *, tenant_id: str = "outbox-test-tenant", payload: dict | None = None
) -> ExperienceOutboxMessage:
    return ExperienceOutboxMessage(
        message_id=f"message:{tenant_id}",
        event_type="consent.deletion_requested",
        tenant_id=tenant_id,
        region_id="CN",
        family_id="outbox-test-family",
        subject_ids=("outbox-test-subject",),
        purpose="ai_personalization",
        consent_version="consent:effective:v1",
        idempotency_key="delete:subject:1",
        schema_version="v1",
        payload=payload or {"deletion_ref": "deletion:outbox-test-subject"},
        enqueued_at=datetime.now(UTC),
    )


async def _count(session: AsyncSession, table: str, tenant_id: str) -> int:
    return int(
        await session.scalar(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id=:tenant_id"),
            {"tenant_id": tenant_id},
        )
        or 0
    )


async def _clear_test_tenants(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Remove only this test module's deterministic fixture rows."""

    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM experience_outbox_messages WHERE tenant_id LIKE 'outbox-%'")
        )
        await session.commit()


async def test_append_replay_cross_tenant_conflict_and_restart_readback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _clear_test_tenants(session_factory)
    first = _message()
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        assert await SqlAlchemyExperienceOutboxWriter(uow.session).append(first) == first
        await uow.commit()

    # A new engine/session is the process-restart read path: nothing from the
    # writer's identity map or pooled connection can supply the replay.
    restarted_engine = create_async_engine(DATABASE_URL, poolclass=None)
    restarted_factory = async_sessionmaker(restarted_engine, expire_on_commit=False)
    async with restarted_factory() as restarted_session:
        replay = await SqlAlchemyExperienceOutboxWriter(restarted_session).append(first)
        assert replay.message_id == first.message_id
        await restarted_session.commit()
    await restarted_engine.dispose()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        cross_tenant = _message(tenant_id="outbox-test-tenant-other")
        assert (
            await SqlAlchemyExperienceOutboxWriter(uow.session).append(cross_tenant) == cross_tenant
        )
        await uow.commit()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        with pytest.raises(ExperienceOutboxConflictError, match="idempotency replay mismatch"):
            await SqlAlchemyExperienceOutboxWriter(uow.session).append(
                _message(payload={"changed": True})
            )

    async with session_factory() as verify:
        assert await _count(verify, "experience_outbox_messages", "outbox-test-tenant") == 1
        assert await _count(verify, "experience_outbox_messages", "outbox-test-tenant-other") == 1


async def test_audit_and_outbox_rollback_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _clear_test_tenants(session_factory)
    message = _message(tenant_id="outbox-rollback-tenant")
    recorder = AuditRecorder()
    recorder.record(
        AuditEvent(
            actor_id="guardian:test",
            tenant_id=message.tenant_id,
            action="consent.deletion_requested",
            resource_type="consent",
            resource_id=message.consent_version,
            reason="test only",
            correlation_id="corr:outbox-rollback",
            after={"deletion_ref": message.payload["deletion_ref"]},
        )
    )

    with pytest.raises(RuntimeError, match="fault after append"):
        async with SqlAlchemyUnitOfWork(session_factory) as uow:
            assert uow.session is not None
            await recorder.flush(uow.session)
            await SqlAlchemyExperienceOutboxWriter(uow.session).append(message)
            raise RuntimeError("fault after append")

    async with session_factory() as verify:
        assert await _count(verify, "experience_outbox_messages", message.tenant_id) == 0
        assert await _count(verify, "platform_audit_events", message.tenant_id) == 0
