from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.growth_plan_ai_api import (
    GrowthPlanAiHttpDependencies,
    GrowthPlanHttpIdentity,
    build_growth_plan_ai_router,
)
from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    GateScope,
    GateStatus,
    HumanGateBase,
    SqlAlchemyHumanGate,
)
from backend.platform.audit import AuditBase, AuditRecorder

NOW = datetime(2026, 9, 3, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_decision_endpoint_uses_server_owned_guardian_identity() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    proposal = ActionProposal(
        proposal_id="growth-plan-http-review",
        draft_id="draft-http-1",
        draft_status="DRAFT",
        action_name="CREATE_JOURNEY_PLAN_FROM_AI_DRAFT",
        action_arguments={"draft_id": "draft-http-1"},
        scope=GateScope(
            tenant_id="tenant-1",
            family_id="family-1",
            subject_ids=("child-1",),
            purpose="growth_tracking",
            consent_version="consent.v1",
            correlation_id="correlation:http-review",
        ),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref="model-draft:draft-http-1",
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    async with sessions() as session:
        gate = SqlAlchemyHumanGate(session)
        task = await gate.submit(proposal, recorder=AuditRecorder())
        await session.commit()

    async def identity(family_id, authorization, correlation_id, causation_id):
        del correlation_id, causation_id
        if authorization != "Bearer guardian-token":
            raise PermissionError("missing bearer")
        return GrowthPlanHttpIdentity("tenant-1", family_id, "guardian-from-token")

    dependencies = GrowthPlanAiHttpDependencies(
        session_factory=sessions,
        identity_resolver=identity,
        scope_resolver=lambda *args: None,
        composition_resolver=lambda *args: None,
        clock=lambda: NOW + timedelta(minutes=1),
    )
    app = FastAPI()
    app.include_router(build_growth_plan_ai_router(dependencies))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        missing = await client.post(
            f"/families/family-1/growth/human-tasks/{task.task_id}/decisions",
            json={"outcome": "ACCEPT"},
        )
        accepted = await client.post(
            f"/families/family-1/growth/human-tasks/{task.task_id}/decisions",
            headers={"Authorization": "Bearer guardian-token"},
            json={"outcome": "ACCEPT"},
        )
    async with sessions() as session:
        decided = await SqlAlchemyHumanGate(session).get(task.task_id)
    await engine.dispose()

    assert missing.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["accepted_action_queued"] is True
    assert decided.status is GateStatus.DECIDED
    assert decided.decision is not None
    assert decided.decision.actor_id == "guardian-from-token"
    assert decided.decision.actor_type is ActorType.GUARDIAN
