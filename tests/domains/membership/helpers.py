"""Shared constants, context builder and catalogue seeder for membership tests.

Kept separate from `conftest.py` on purpose: `conftest.py` holds pytest
fixtures, this module holds plain importable helpers. Test modules import from
here rather than from `conftest`, because importing a conftest by module path
works by accident rather than by contract.

Scope note carried over from the fixtures: the catalogue masters seeded here are
PLATFORM-scope (a plan, three tier definitions, one benefit definition). None of
them carry `family_id` — catalogue rows never hold family facts.
"""

from __future__ import annotations

from backend.domains.membership.application.context import ActionContext
from backend.domains.membership.domain.entities import (
    BenefitDefinition,
    MembershipPlan,
    MembershipTierDefinition,
    utcnow,
)

TENANT = "tenant-001"
FAMILY = "family-001"
GUARDIAN = "person-guardian-001"
CHILD = "person-child-001"


def make_ctx(*, idempotency_key: str | None = None, actor: str = "guardian:001") -> ActionContext:
    """A human-actor context.

    `actor` defaults to a `guardian:` prefix rather than `ai:` deliberately —
    `assert_human_actor` in the domain policy layer rejects `ai:`-prefixed
    actors, so a test that needs to prove that rejection must pass `actor`
    explicitly instead of relying on this default.
    """
    return ActionContext(
        tenant_id=TENANT,
        family_id=FAMILY,
        actor_person_id=GUARDIAN,
        actor=actor,
        correlation_id="corr-001",
        environment="TEST",
        idempotency_key=idempotency_key,
    )


async def seed_catalogue(repo) -> tuple[MembershipPlan, BenefitDefinition]:
    """Minimal PLATFORM-scope catalogue: one plan, three tier definitions, one
    benefit definition."""
    now = utcnow()
    plan = MembershipPlan(
        plan_id="plan-annual",
        plan_ref="ANNUAL_FAMILY_GROWTH",
        title="年度家庭成长会员",
        source_ref="catalogue:seed",
        effective_from=now,
        created_at=now,
        created_by="ops:seed",
        updated_at=now,
        updated_by="ops:seed",
    )
    await repo.save_plan(plan)

    for code, title, entry, value in (
        ("M0_FREE", "家庭会员", "建立家庭账户与基础关系", "基础测评、精选内容、家庭私有成长记录"),
        ("M1_GROWTH", "成长会员", "激活 21 天或 90 天成长产品", "成长方案、AI 陪伴、成长记录"),
        ("M2_ANNUAL", "年度会员", "成功激活年度家庭成长会员", "365 天陪伴、四个成长周期、家庭管家"),
    ):
        await repo.save_tier_definition(
            MembershipTierDefinition(
                tier_definition_id=f"tierdef-{code}",
                tier_code=code,
                title=title,
                entry_rule_text=entry,
                value_summary=value,
                effective_from=now,
                created_at=now,
                created_by="ops:seed",
                updated_at=now,
                updated_by="ops:seed",
            )
        )

    benefit = BenefitDefinition(
        benefit_definition_id="benefitdef-expert",
        plan_id=plan.plan_id,
        benefit_ref="EXPERT_CONSULTATION",
        title="专家咨询",
        allocation_type="COUNT",
        units_per_grant=2,
        valid_days=365,
        effective_from=now,
        created_at=now,
        created_by="ops:seed",
        updated_at=now,
        updated_by="ops:seed",
    )
    await repo.save_benefit_definition(benefit)
    await repo.commit()
    return plan, benefit
