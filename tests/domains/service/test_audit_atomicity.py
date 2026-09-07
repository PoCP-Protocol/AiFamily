"""Negative proof that service state cannot commit without durable audit."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.service.application import commands
from backend.domains.service.infrastructure import sqlalchemy_models as models
from backend.domains.service.infrastructure.sqlalchemy_models import Base
from backend.domains.service.infrastructure.sqlalchemy_repository import (
    SqlAlchemyServiceRepository,
)
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.audit.store import AuditBase

from .helpers import make_ctx

pytestmark = pytest.mark.asyncio


class FailingAuditRecorder(AuditRecorder):
    async def flush(self, session, *, clear: bool = True) -> int:
        raise RuntimeError("audit store unavailable")


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_provider_registration_rolls_back_when_audit_flush_fails(session_factory) -> None:
    async with session_factory() as session:
        repo = SqlAlchemyServiceRepository(session)
        recorder = FailingAuditRecorder()
        with pytest.raises(RuntimeError, match="audit store unavailable"):
            await commands.register_service_provider(
                repo,
                make_ctx(idempotency_key="audit-failure"),
                recorder,
                provider_ref="TEACHER_FAIL",
                display_name="失败测试",
                provider_kind="TEACHER",
                qualification_status="ACTIVE",
                admission_status="ADMITTED",
                source_ref="test:audit-failure",
                qualification_ref="cert-fail",
            )
        await session.rollback()

    async with session_factory() as verification_session:
        result = await verification_session.execute(
            select(models.ServiceProviderRow).where(
                models.ServiceProviderRow.provider_ref == "TEACHER_FAIL"
            )
        )
        assert result.scalars().first() is None
