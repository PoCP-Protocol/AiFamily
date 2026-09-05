from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.agent_runtime.authorization_persistence import (
    AgentAuthorizationConflict,
    AgentAuthorizationNotFound,
    AgentAuthorizationPersistenceBase,
    AgentAuthorizationScope,
    SqlAlchemyAgentAuthorizationLeaseStore,
)
from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AuthorizationBudget

NOW = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(AgentAuthorizationPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def authorization(
    *,
    tenant_id: str = "tenant-1",
    family_id: str = "family-1",
    expires_at: datetime = NOW + timedelta(hours=1),
    tools: frozenset[str] = frozenset({"read_context"}),
) -> AgentAuthorization:
    return AgentAuthorization(
        authorization_id="auth-1",
        agent_id="parent_advisor",
        tenant_id=tenant_id,
        family_id=family_id,
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        allowed_tools=tools,
        issued_by="guardian-1",
        issued_at=NOW,
        expires_at=expires_at,
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=2, max_cost_micros=500),
        policy_version="agent-auth-v1",
        reason="assessment review",
        audit_ref="audit-issue-1",
    )


@pytest.mark.asyncio
async def test_issue_is_idempotent_and_audit_is_append_only(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyAgentAuthorizationLeaseStore(session)
        first = await store.issue(authorization())
        retry = await store.issue(authorization())
        assert retry == first
        events = await store.audit(
            scope=AgentAuthorizationScope("tenant-1", "family-1"), authorization_id="auth-1"
        )
        assert [(event.event_type, event.audit_ref) for event in events] == [
            ("ISSUED", "audit-issue-1")
        ]
        with pytest.raises(AgentAuthorizationConflict, match="REPLAY_MISMATCH"):
            await store.issue(authorization(tools=frozenset()))


@pytest.mark.asyncio
async def test_find_active_fails_closed_for_scope_use_case_tool_budget_and_expiry(
    session_factory,
) -> None:
    async with session_factory() as session:
        store = SqlAlchemyAgentAuthorizationLeaseStore(session)
        await store.issue(authorization())
        scope = AgentAuthorizationScope("tenant-1", "family-1")
        assert (
            await store.find_active(
                scope=scope,
                agent_id="parent_advisor",
                use_case="assessment_interpretation",
                issued_by="guardian-1",
                requested_tools={"read_context"},
                estimated_steps=2,
                estimated_cost_micros=500,
                now=NOW + timedelta(minutes=1),
            )
        ) is not None
        assert (
            await store.find_active(
                scope=scope,
                agent_id="parent_advisor",
                use_case="assessment_interpretation",
                issued_by="other-guardian",
                now=NOW + timedelta(minutes=1),
            )
        ) is None
        assert (
            await store.find_active(
                scope=scope,
                agent_id="parent_advisor",
                use_case="other_use_case",
                now=NOW + timedelta(minutes=1),
            )
        ) is None
        assert (
            await store.find_active(
                scope=AgentAuthorizationScope("tenant-1", "other-family"),
                agent_id="parent_advisor",
                use_case="assessment_interpretation",
                now=NOW + timedelta(minutes=1),
            )
        ) is None
        assert (
            await store.find_active(
                scope=scope,
                agent_id="parent_advisor",
                use_case="assessment_interpretation",
                estimated_steps=3,
                now=NOW + timedelta(minutes=1),
            )
        ) is None
        assert (
            await store.find_active(
                scope=scope,
                agent_id="parent_advisor",
                use_case="assessment_interpretation",
                now=NOW + timedelta(hours=2),
            )
        ) is None


@pytest.mark.asyncio
async def test_revoke_denies_active_lookup_and_records_actor_audit(session_factory) -> None:
    async with session_factory() as session:
        store = SqlAlchemyAgentAuthorizationLeaseStore(session)
        await store.issue(authorization())
        revoked = await store.revoke(
            "auth-1",
            scope=AgentAuthorizationScope("tenant-1", "family-1"),
            revoked_at=NOW + timedelta(minutes=5),
            actor_id="guardian-1",
            audit_ref="audit-revoke-1",
        )
        assert revoked.revoked_at == NOW + timedelta(minutes=5)
        assert (
            await store.find_active(
                scope=AgentAuthorizationScope("tenant-1", "family-1"),
                agent_id="parent_advisor",
                use_case="assessment_interpretation",
                now=NOW + timedelta(minutes=6),
            )
        ) is None
        events = await store.audit(
            scope=AgentAuthorizationScope("tenant-1", "family-1"), authorization_id="auth-1"
        )
        assert [event.event_type for event in events] == ["ISSUED", "REVOKED"]
        assert events[-1].actor_id == "guardian-1"
        with pytest.raises(AgentAuthorizationConflict, match="REPLAY_MISMATCH"):
            await store.revoke(
                "auth-1",
                scope=AgentAuthorizationScope("tenant-1", "family-1"),
                revoked_at=NOW + timedelta(minutes=5),
                actor_id="other-actor",
                audit_ref="audit-other",
            )
        with pytest.raises(AgentAuthorizationNotFound):
            await store.revoke(
                "missing",
                scope=AgentAuthorizationScope("tenant-1", "family-1"),
                revoked_at=NOW,
                actor_id="guardian-1",
                audit_ref="audit-missing",
            )
