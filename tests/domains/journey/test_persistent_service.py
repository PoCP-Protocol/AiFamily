from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.journey.application.persistent_service import PersistentJourneyPlanService
from backend.domains.journey.application.plan_service import (
    ConfirmedGrowthIntent,
    PhaseReviewDecision,
)
from backend.domains.journey.domain.errors import JourneyConflictError
from backend.domains.journey.infrastructure.sqlalchemy_repository import JourneyBase


@pytest.fixture
async def service() -> PersistentJourneyPlanService:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(JourneyBase.metadata.create_all)

    async def event_writer(*_args):
        return None

    value = PersistentJourneyPlanService(
        async_sessionmaker(engine, expire_on_commit=False),
        event_writer_factory=lambda _session: event_writer,
    )
    yield value
    await engine.dispose()


async def test_persistent_facade_supports_user_journey(service) -> None:
    created = await service.create_plan_from_intent(
        intent=ConfirmedGrowthIntent(
            intent_id="intent-1",
            tenant_id="tenant-a",
            family_id="family-a",
            actor_id="parent-a",
            need_type="HOMEWORK_PROCESS",
            goal_text="把作业冲突拆成可观察的过程",
        ),
        idempotency_key="create-1",
    )
    plan_id = created["plan"]["plan_id"]
    confirmed = await service.confirm_plan(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        plan_id=plan_id,
        idempotency_key="confirm-1",
    )
    assert confirmed["plan"]["status"] == "ACTIVE"
    reviewed = await service.review_phase(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        plan_id=plan_id,
        decision=PhaseReviewDecision.CONTINUE,
        observation="模拟回访：家长能描述一次具体变化，继续观察下一阶段",
        idempotency_key="review-1",
    )
    assert reviewed["review"]["decision"] == "CONTINUE"
    assert reviewed["plan"]["current_phase"] == 2
    readback = await service.read_plan(plan_id=plan_id, tenant_id="tenant-a", family_id="family-a")
    assert readback["plan"]["intent_id"] == "intent-1"
    assert readback["reviews"][0]["observation"].startswith("模拟回访")
    replayed = await service.create_plan_from_intent(
        intent=ConfirmedGrowthIntent(
            intent_id="intent-1",
            tenant_id="tenant-a",
            family_id="family-a",
            actor_id="parent-a",
            need_type="HOMEWORK_PROCESS",
            goal_text="把作业冲突拆成可观察的过程",
        ),
        idempotency_key="create-1",
    )
    assert replayed["replayed"] is True
    with pytest.raises(JourneyConflictError, match="idempotency_conflict"):
        await service.create_plan_from_intent(
            intent=ConfirmedGrowthIntent(
                intent_id="intent-1",
                tenant_id="tenant-a",
                family_id="family-a",
                actor_id="parent-a",
                need_type="HOMEWORK_PROCESS",
                goal_text="换一个不同请求体",
            ),
            idempotency_key="create-1",
        )
