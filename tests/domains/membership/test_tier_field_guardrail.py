"""The guardrail test `governance/MIGRATION_MANIFEST.yaml` demands by name.

That manifest entry (capability `membership`) carries:

    blocking_action: "必须先写出 FORBIDDEN_TIER_FIELD_TOKENS 的 guardrail test,
                      再决定 MIGRATE vs REIMPLEMENT"

and records the audit finding behind it: `domain/policies.py`'s
`FORBIDDEN_TIER_FIELD_TOKENS` comment claimed the rule was "由 guardrail test
强制" while no such test existed anywhere on disk. That is the R14 failure mode
in miniature — 写成常量的策略等于没有策略. This file is that test.

What it protects: 会员档位是"关系深度",不是等级分。宪章 R9 的原话是
「AiFamily 不计算、不存储、不暴露家庭总分与家庭排行」。一个名叫 `tier_level`
或 `growth_score` 的字段一旦被加进实体,产品侧就会自然而然长出等级进度条,
然后长出跨家庭比较 —— 所以这里守的是**字段名**,在语义走偏之前。
"""

from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel

from backend.domains.membership.domain import entities as membership_entities
from backend.domains.membership.domain.errors import MembershipForbiddenError
from backend.domains.membership.domain.policies import (
    FORBIDDEN_TIER_FIELD_TOKENS,
    assert_no_score_semantics,
)


def _entity_classes() -> list[type[BaseModel]]:
    """Every Pydantic model defined in the membership entities module.

    Reflected rather than hand-listed on purpose: a hand-written list would go
    stale the moment someone adds an entity, which is exactly when this test
    needs to fire.
    """
    return [
        obj
        for _, obj in inspect.getmembers(membership_entities, inspect.isclass)
        if issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == membership_entities.__name__
    ]


def test_entity_module_actually_exposes_entities() -> None:
    """Guard the guard: if reflection silently found nothing, every assertion
    below would pass vacuously."""
    classes = _entity_classes()
    assert len(classes) >= 8, f"expected the membership entity set, found {len(classes)}"


@pytest.mark.parametrize("token", sorted(FORBIDDEN_TIER_FIELD_TOKENS))
def test_no_entity_field_carries_a_score_token(token: str) -> None:
    """No membership entity may have a field whose name contains a scoring,
    ranking or levelling token.

    Parametrised per token so a failure names the offending concept directly
    instead of reporting "one of eight tokens matched somewhere".
    """
    offenders = [
        f"{cls.__name__}.{field}"
        for cls in _entity_classes()
        for field in cls.model_fields
        if token in field.lower()
    ]
    assert not offenders, (
        f"字段名含 '{token}':{offenders}。"
        "会员档位是关系深度,不是等级分 —— 宪章 R9:不计算、不存储、不暴露家庭总分与家庭排行。"
    )


def test_tier_code_has_exactly_three_relationship_depth_values() -> None:
    """三档定死。多一档就会诱发"再消费 X 元升级"的阶梯叙事,那是 VIP 价格梯,
    不是关系深度。"""
    from backend.domains.membership.domain.value_objects import TIER_CODES

    assert TIER_CODES == ("M0_FREE", "M1_GROWTH", "M2_ANNUAL")


def test_no_numeric_tier_depth_leaks_onto_an_entity() -> None:
    """`_TIER_DEPTH` 存在,但只用于给审计事实打 UPGRADE/DOWNGRADE 标签。

    它必须留在 value_objects 内部,不得成为任何实体的字段、也不得被持久化 ——
    否则它就是一个可被渲染成进度条的等级分。
    """
    from backend.domains.membership.infrastructure import sqlalchemy_models

    depth_like = {"depth", "tier_depth", "tier_order", "tier_index", "tier_weight"}
    for cls in _entity_classes():
        assert not (depth_like & set(cls.model_fields)), f"{cls.__name__} 暴露了档位数值"

    for _, table_cls in inspect.getmembers(sqlalchemy_models, inspect.isclass):
        table = getattr(table_cls, "__table__", None)
        if table is None:
            continue
        columns = {c.name for c in table.columns}
        assert not (depth_like & columns), f"{table_cls.__name__} 持久化了档位数值"


def test_attributes_escape_hatch_refuses_smuggled_score() -> None:
    """`attributes` 是唯一能塞任意键的口子,所以它必须被单独守住。"""
    assert_no_score_semantics({"note": "guardian asked to pause"})  # 正常键放行

    for smuggled in ("family_score", "child_rank", "tier_level", "growth_percentile"):
        with pytest.raises(MembershipForbiddenError):
            assert_no_score_semantics({smuggled: 87})


def test_entity_construction_rejects_scored_attributes() -> None:
    """端到端:护栏挂在实体校验上,不只是一个可以被绕过的独立函数。"""
    from backend.domains.membership.domain.entities import MembershipPlan, utcnow

    now = utcnow()
    common = {
        "plan_id": "plan-x",
        "plan_ref": "REF",
        "title": "t",
        "source_ref": "s",
        "effective_from": now,
        "created_at": now,
        "created_by": "ops",
        "updated_at": now,
        "updated_by": "ops",
    }
    MembershipPlan(**common)  # 无 attributes 时正常

    with pytest.raises(MembershipForbiddenError):
        MembershipPlan(**common, attributes={"family_score": 91})
