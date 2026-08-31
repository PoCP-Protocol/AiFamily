from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.journey.application.plan_service import (
    FamilyPractice,
    JourneyPlan,
    JourneyPlanStatus,
    PracticeRecord,
)
from backend.domains.journey.infrastructure.sqlalchemy_repository import (
    JourneyBase,
    SqlAlchemyJourneyRepository,
)


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(JourneyBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


def _plan() -> JourneyPlan:
    return JourneyPlan(
        plan_id="plan-1",
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        focus_id="PARENT_CHILD_COMMUNICATION",
        goal_text="先听懂彼此，再共同决定",
        status=JourneyPlanStatus.DRAFT,
        intent_id="intent-1",
        evidence_refs=("evidence-1",),
        knowledge_refs=("TH-001",),
    )


async def test_persistent_plan_practice_record_and_scope_readback(session) -> None:
    events: list[tuple[str, str]] = []

    async def write_event(action, resource_id, actor_id, tenant_id, family_id):
        events.append((action, resource_id))

    repository = SqlAlchemyJourneyRepository(session, write_event)
    plan = _plan()
    await repository.create_plan(plan)
    await repository.confirm_plan(
        plan_id=plan.plan_id, actor_id="parent-a", tenant_id="tenant-a", family_id="family-a"
    )
    practice = FamilyPractice(
        practice_id="practice-1",
        plan_id=plan.plan_id,
        tenant_id="tenant-a",
        family_id="family-a",
        title="冲突时先复述孩子想表达的事",
        rationale="对应已确认的沟通卡点",
        day_index=1,
    )
    await repository.add_practice(practice, actor_id="parent-a")
    await repository.record_practice(
        PracticeRecord(
            record_id="record-1",
            practice_id=practice.practice_id,
            plan_id=plan.plan_id,
            tenant_id="tenant-a",
            family_id="family-a",
            observation="孩子愿意多说了一句",
            blocker="时间太晚",
        ),
        actor_id="parent-a",
    )
    await session.commit()
    readback = await repository.read_plan(
        plan_id="plan-1", tenant_id="tenant-a", family_id="family-a"
    )
    assert readback["plan"]["status"] == "ACTIVE"
    assert readback["plan"]["evidence_refs"] == ["evidence-1"]
    assert readback["practices"][0]["status"] == "RECORDED"
    assert readback["records"][0]["blocker"] == "时间太晚"
    assert [event[0] for event in events] == [
        "PLAN_CREATED",
        "PLAN_CONFIRMED",
        "PRACTICE_PLANNED",
        "PRACTICE_RECORDED",
    ]

    with pytest.raises(PermissionError, match="journey_plan_scope_denied"):
        await repository.read_plan(plan_id="plan-1", tenant_id="tenant-a", family_id="family-b")


async def test_event_failure_rolls_back_domain_write(session) -> None:
    async def fail(*_args):
        raise RuntimeError("canonical event unavailable")

    repository = SqlAlchemyJourneyRepository(session, fail)
    with pytest.raises(RuntimeError, match="canonical event unavailable"):
        await repository.create_plan(_plan())
    await session.rollback()
    with pytest.raises(LookupError, match="journey_plan_not_found"):
        await repository.read_plan(plan_id="plan-1", tenant_id="tenant-a", family_id="family-a")
