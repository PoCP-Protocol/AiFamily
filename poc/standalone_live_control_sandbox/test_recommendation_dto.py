from datetime import UTC, datetime, timedelta

import pytest

from poc.standalone_live_control_sandbox.family_need_service_adapter import (
    AdultContext,
    ConfirmedNeedProjection,
    LiveNeedBridgeRejected,
)
from poc.standalone_live_control_sandbox.recommendation_dto import (
    DynamicPlanProjection,
    build_recommendation,
)

NOW = datetime(2026, 9, 4, 12, tzinfo=UTC)
GUARDIAN = AdultContext("tenant.synthetic", "family.synthetic", "guardian.synthetic")


def need(**overrides):
    values = dict(
        need_id="need.synthetic.1",
        tenant_id=GUARDIAN.tenant_id,
        family_id=GUARDIAN.family_id,
        status="CONFIRMED",
        growth_theme="家庭沟通",
        consent_version="v1",
        expires_at=NOW + timedelta(hours=1),
    )
    values.update(overrides)
    return ConfirmedNeedProjection(**values)


def plan(**overrides):
    values = dict(
        plan_ref="plan.synthetic.1",
        tenant_id=GUARDIAN.tenant_id,
        family_id=GUARDIAN.family_id,
        status="ACTIVE",
        next_step="今晚先复述一句你听到的话。",
    )
    values.update(overrides)
    return DynamicPlanProjection(**values)


def test_dto_connects_confirmed_need_and_active_plan_without_child_or_payment_data():
    dto = build_recommendation(
        session_ref="live.synthetic.1", need=need(), plan=plan(), guardian=GUARDIAN, now=NOW
    )
    assert dto.as_json() == {
        "session_ref": "live.synthetic.1",
        "need_id": "need.synthetic.1",
        "plan_ref": "plan.synthetic.1",
        "growth_theme": "家庭沟通",
        "need_statement": "放学后的沟通常常以争执收场。",
        "recommendation_reason": "本场围绕“家庭沟通”提供当前方案需要的练习。",
        "audience_label": "希望减少冲突的家长与照护者",
        "next_step": "今晚先复述一句你听到的话。",
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
        "external_effect": False,
    }
    assert not any("child" in key or "payment" in key for key in dto.as_json())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"need": need(status="CAPTURED")},
        {"need": need(expires_at=NOW)},
        {"plan": plan(status="PAUSED")},
        {
            "guardian": AdultContext(
                "tenant.synthetic", "family.synthetic", "child.synthetic", "CHILD"
            )
        },
    ],
)
def test_invalid_scope_or_lifecycle_fails_closed(kwargs):
    values = dict(
        session_ref="live.synthetic.1", need=need(), plan=plan(), guardian=GUARDIAN, now=NOW
    )
    values.update(kwargs)
    with pytest.raises(LiveNeedBridgeRejected):
        build_recommendation(**values)
