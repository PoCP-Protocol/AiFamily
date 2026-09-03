from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.feedback_read import (
    SharedExperienceFeedbackRuntimeResolver,
)
from tests.intelligence.experience.test_gateway import _scope


class DraftRuntime:
    def __init__(self, scope):
        self.scope = scope


class DraftResolver:
    def __init__(self, scope):
        self.scope = scope
        self.calls: list[str] = []

    async def resolve(self, family_id: str):
        self.calls.append(family_id)
        return DraftRuntime(self.scope)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_shared_resolver_reuses_draft_scope_authority(session_factory) -> None:
    scope = _scope()
    source = DraftResolver(scope)
    resolver = SharedExperienceFeedbackRuntimeResolver(source, session_factory)

    runtime = await resolver.resolve(scope.family_id)

    assert source.calls == [scope.family_id]
    assert runtime.scope.family_id == scope.family_id
    assert runtime.scope.tenant_id == scope.tenant_id


@pytest.mark.asyncio
async def test_shared_resolver_rejects_scope_family_mismatch(session_factory) -> None:
    source = DraftResolver(_scope(family_id="family-a"))
    resolver = SharedExperienceFeedbackRuntimeResolver(source, session_factory)

    with pytest.raises(PermissionError, match="requested family"):
        await resolver.resolve("family-b")
