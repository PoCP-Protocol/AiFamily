"""Real-PostgreSQL durability checks for guardian growth-plan adoption."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.domains.journey.application.growth_plan_adoption import AdoptedGrowthPlan
from backend.domains.journey.infrastructure.growth_plan_adoption_postgres import (
    SqlAlchemyAdoptedGrowthPlanRepository,
)
from backend.platform.audit import AuditEvent
from tests.support.postgres import SKIP_REASON, postgres_test_url


def _plan(tenant: str, family: str) -> AdoptedGrowthPlan:
    return AdoptedGrowthPlan(
        plan_id=f"test-plan-{family}",
        tenant_id=tenant,
        family_id=family,
        subject_refs=("guardian-a", "child-a"),
        draft_ref="draft:test-growth-plan",
        draft_version=1,
        model_run_ref="run:test-growth-plan",
        provenance_ref="provenance:test-growth-plan",
        content_sha256="a" * 64,
        title="一次可暂停的家庭行动",
        family_goal={"statement": "减少晚间冲突"},
        why_this_plan="先试一次可观察步骤",
        duration={"days": 7},
        stages=({"stage_id": "START_SMALL"}, {"stage_id": "REFLECT_AND_ADJUST"}),
        adjustable_choices=({"choice_id": "pace", "options": ["今天", "稍后"]},),
        selected_choices={"pace": "今天"},
        unknowns_to_watch=("孩子是否能表达不同意见",),
        review_rhythm={"frequency": "一周"},
        limitations=("不是诊断或结果证明",),
        status="ACTIVE",
        adopted_by="guardian-a",
        adopted_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_postgres_adoption_is_idempotent_and_survives_repository_rebuild() -> None:
    url = postgres_test_url()
    if url is None:
        pytest.skip(SKIP_REASON)
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    plan = _plan("tenant-test-growth", "family-test-growth")
    event = AuditEvent(
        actor_id="guardian-a",
        tenant_id=plan.tenant_id,
        action="AdoptFamilyGrowthPlanDraft",
        resource_type="AdoptedGrowthPlan",
        resource_id=plan.plan_id,
        reason="postgres durability test",
        correlation_id="correlation-test-growth",
        after=plan.as_dict(),
        timestamp=plan.adopted_at,
    )
    try:
        repository = SqlAlchemyAdoptedGrowthPlanRepository(factory)
        stored, created, replayed = await repository.adopt_once(
            plan=plan,
            idempotency_key="adopt-test-growth-1",
            request_fingerprint="fingerprint-test-growth",
            audit_event=event,
        )
        assert created is True
        assert replayed is False
        assert stored.plan_id == plan.plan_id

        rebuilt = SqlAlchemyAdoptedGrowthPlanRepository(factory)
        readback = await rebuilt.get_current(
            tenant_id=plan.tenant_id,
            family_id=plan.family_id,
        )
        assert readback is not None
        assert readback.plan_id == plan.plan_id
        replay, created, replayed = await rebuilt.adopt_once(
            plan=plan,
            idempotency_key="adopt-test-growth-1",
            request_fingerprint="fingerprint-test-growth",
            audit_event=event,
        )
        assert replay.plan_id == plan.plan_id
        assert created is False
        assert replayed is True
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "delete from journey_adopted_growth_plans "
                    "where tenant_id='tenant-test-growth'"
                )
            )
            await connection.execute(
                text(
                    "delete from idempotency_keys "
                    "where idempotency_key like 'growth-plan-adopt:%'"
                )
            )
        await engine.dispose()
