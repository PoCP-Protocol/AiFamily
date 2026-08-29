"""商业域的四条架构级护栏。

宪章 R14 原话:「**写成常量或文档的策略等于没有策略。**」`backend/packages/contracts/`
下的 `gamification.py` / `value_ordering.py` 与两个商业域里的拒绝清单,在本文件之前
正处于那个状态 —— 它们被写下来了,但没有任何东西执行它们。

四条护栏:

1. `test_axis_separation_*` —— 会籍与积分两个包互不 import(四轴不可换算)
2. `test_no_cross_family_reads_*` —— Port 里没有跨家庭读方法(不做家庭排行=查不出来)
3. `test_gamification_*` —— 读模型不出现禁用字段名/文案(含"自证有效"负例)
4. `test_no_cash_equivalence_*` —— 积分不做折现表达(含负例)

每条都带一个故意违规的负例,否则前一条可能是永远为真的测试。
"""

from __future__ import annotations

import ast
import contextlib
import inspect
from pathlib import Path

import pytest

from backend.packages.contracts.gamification import (
    FORBIDDEN_GAMIFICATION_KEY_TOKENS,
    assert_gamification_safe,
)
from backend.packages.contracts.value_ordering import (
    EMOTIONAL_FIRST_BLOCK_ORDER,
    assert_no_cash_equivalence,
    order_blocks,
)

MEMBERSHIP_PKG = "backend/domains/membership"
POINTS_PKG = "backend/domains/loyalty_points"


# --------------------------------------------------------------------------
# 1. 四轴分离 —— 靠包依赖图,不靠 code review
# --------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    """静态解析 import,不用 import 后看属性 —— 后者会被运行时条件掩盖。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


@pytest.mark.parametrize(
    ("package", "forbidden_prefix"),
    [
        (MEMBERSHIP_PKG, "backend.domains.loyalty_points"),
        (POINTS_PKG, "backend.domains.membership"),
    ],
)
def test_axis_separation_is_a_package_graph_fact(
    repo_root: Path, package: str, forbidden_prefix: str
) -> None:
    """会籍档位 / 成长阶段 / 积分 / 社区身份四轴"可同时展示、不可互相换算"。

    拆成互不依赖的包,让这条约束成为**包依赖图的事实**。如果两个域可以互相 import,
    "不可换算"就只是一句口头承诺,而第一个想做「积分兑换会员」的需求就会把它磨掉。
    """
    pkg_dir = repo_root / package
    if not pkg_dir.is_dir():
        pytest.skip(f"{package} 不存在,无可检验对象")

    offenders: list[str] = []
    for py in sorted(pkg_dir.rglob("*.py")):
        for module in _imported_modules(py):
            if module.startswith(forbidden_prefix):
                offenders.append(f"{py.relative_to(repo_root).as_posix()} → {module}")

    assert not offenders, (
        f"{package} 不得依赖 {forbidden_prefix}:{offenders}。"
        "四轴必须可同时展示、不可互相换算;拆包是这条约束的执行机制。"
    )


def test_axis_separation_negative_control(tmp_path: Path) -> None:
    """自证:扫描器确实能发现越界 import。"""
    offender = tmp_path / "bad.py"
    offender.write_text(
        "from backend.domains.loyalty_points.domain.policies import compute_balance\n",
        encoding="utf-8",
    )
    assert any(m.startswith("backend.domains.loyalty_points") for m in _imported_modules(offender))


# --------------------------------------------------------------------------
# 2. 不做家庭排行 —— 查不出来,而不是不许查
# --------------------------------------------------------------------------

CROSS_FAMILY_NAME_TOKENS = (
    "top",
    "rank",
    "leaderboard",
    "compare",
    "percentile",
    "count_by",
    "all_families",
)

# 目录主数据不属于任何家庭(会籍档位定义、积分规则、兑换目录),所以它们的读方法
# 天然没有 family 作用域。豁免必须逐个列名并说明理由,不许模糊放过。
CATALOGUE_METHOD_EXEMPTIONS = {
    "list_tier_definitions",  # PLATFORM/TENANT 档位定义
    "list_earn_rules",  # 积分发放规则
    "list_redemption_items",  # 兑换目录
}


def _port_protocols():
    from backend.domains.membership.application.ports import MembershipRepositoryPort

    ports = [("membership", MembershipRepositoryPort)]
    try:
        from backend.domains.loyalty_points.application.ports import LoyaltyPointsRepositoryPort

        ports.append(("loyalty_points", LoyaltyPointsRepositoryPort))
    except ModuleNotFoundError:  # pragma: no cover - 域尚未建时
        pass
    return ports


@pytest.mark.parametrize(("domain", "port"), _port_protocols())
def test_no_cross_family_read_methods_exist(domain: str, port: type) -> None:
    """Port 不提供跨家庭形状,后来者就**建不出**排行榜 UI。

    宪章 R9:「AiFamily 不计算、不存储、不暴露家庭总分与家庭排行。」
    这条测试把"不暴露"落到接口形状上:没有任何方法能返回超过一个家庭的数据。
    """
    offenders: list[str] = []
    for name, member in inspect.getmembers(port, inspect.isfunction):
        if name.startswith("_"):
            continue
        lowered = name.lower()
        for token in CROSS_FAMILY_NAME_TOKENS:
            if token in lowered:
                offenders.append(f"{domain}.{name} 含跨家庭聚合语义 '{token}'")

        if name in CATALOGUE_METHOD_EXEMPTIONS or name == "commit":
            continue
        params = set(inspect.signature(member).parameters)
        returns_collection = "list" in str(inspect.signature(member).return_annotation)
        if returns_collection and not {"tenant_id", "family_id"} <= params:
            offenders.append(f"{domain}.{name} 返回集合但未同时以 tenant_id + family_id 作用域")

    assert not offenders, f"跨家庭读不得存在:{offenders}"


def test_cross_family_detection_negative_control() -> None:
    """自证:检测逻辑对一个真的越界方法名会报警。"""

    class BadPort:
        async def list_top_families_by_points(self) -> list: ...

    offenders = [
        name
        for name, _ in inspect.getmembers(BadPort, inspect.isfunction)
        if any(t in name.lower() for t in CROSS_FAMILY_NAME_TOKENS)
    ]
    assert offenders == ["list_top_families_by_points"]


# --------------------------------------------------------------------------
# 3. 游戏化不越线
# --------------------------------------------------------------------------


def _flatten_keys(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.append(str(key))
            _flatten_keys(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _flatten_keys(item, out)


async def _membership_screens():
    from backend.domains.membership.application import commands, queries
    from backend.domains.membership.application.context import ActionContext
    from backend.domains.membership.infrastructure.fake_repository import (
        FakeMembershipRepository,
    )
    from tests.domains.membership.helpers import FAMILY, TENANT, seed_catalogue

    repo = FakeMembershipRepository()
    plan, benefit_def = await seed_catalogue(repo)
    ctx = ActionContext(
        tenant_id=TENANT,
        family_id=FAMILY,
        actor_person_id="p-1",
        actor="guardian:001",
        correlation_id="c",
        environment="TEST",
        idempotency_key="guard-1",
    )
    sub = await commands.subscribe_membership(
        repo, ctx, plan_id=plan.plan_id, subscription_ref="S1", consent_ref="c1"
    )
    await commands.activate_membership_tier(
        repo,
        ActionContext(**{**ctx.__dict__, "idempotency_key": "guard-2"}),
        to_tier="M0_FREE",
        activation_source_type="FAMILY_ACCOUNT_CREATED",
        activation_source_ref="account:1",
        decided_by="guardian:001",
    )
    await commands.grant_membership_benefit(
        repo,
        ActionContext(**{**ctx.__dict__, "idempotency_key": "guard-3"}),
        membership_subscription_id=sub.membership_subscription_id,
        benefit_definition_id=benefit_def.benefit_definition_id,
        grant_ref="G1",
        source_page_id="UI-30",
    )
    return [
        await queries.get_ui06_my_membership(repo, tenant_id=TENANT, family_id=FAMILY),
        await queries.get_ui18_membership_center(repo, tenant_id=TENANT, family_id=FAMILY),
        await queries.get_ui30_annual_companion(repo, tenant_id=TENANT, family_id=FAMILY),
        await queries.get_ui32_orders_and_assets(repo, tenant_id=TENANT, family_id=FAMILY),
    ]


async def _points_screens():
    from backend.domains.loyalty_points.application import commands, queries
    from backend.domains.loyalty_points.infrastructure.fake_repository import (
        FakeLoyaltyPointsRepository,
    )
    from tests.domains.loyalty_points.helpers import (
        FAMILY,
        RULE_CHECKIN,
        TENANT,
        make_ctx,
        seed_catalogue,
    )

    repo = FakeLoyaltyPointsRepository()
    await seed_catalogue(repo)
    await commands.open_points_account(repo, make_ctx(), account_ref="A1")
    await commands.earn_points(
        repo,
        make_ctx(idempotency_key="g-1"),
        rule_ref=RULE_CHECKIN,
        evidence_ref="growth_action:day-1",
        source_page_id="UI-17",
    )
    return [await queries.get_ui17_growth_points(repo, tenant_id=TENANT, family_id=FAMILY)]


async def _all_screens():
    screens = await _membership_screens()
    with contextlib.suppress(ModuleNotFoundError):  # pragma: no cover
        screens += await _points_screens()
    return screens


async def test_no_read_model_emits_a_forbidden_gamification_shape() -> None:
    """真实调用四个会籍屏 + 积分屏,把所有 blocks 的键与文案喂给契约检查器。

    守的是:一个未来叫 `family_rank` 或 `tier_progress_pct` 的字段,在被前端画成
    进度条或排行榜之前先让构建失败。
    """
    for screen in await _all_screens():
        keys: list[str] = []
        _flatten_keys(screen.blocks, keys)
        assert_gamification_safe(keys, screen.notices)


def test_gamification_checker_negative_control() -> None:
    """自证:没有这一条,上面那条可能永远为真。"""
    with pytest.raises(ValueError, match="forbidden_gamification_key"):
        assert_gamification_safe(["family_rank"], [])
    with pytest.raises(ValueError, match="forbidden_gamification_copy"):
        assert_gamification_safe(["ok_key"], ["你们家超过了 80% 的家庭"])
    # 抽样确认清单里的 token 真的会被拦,而不是只有我随手挑的那个
    for token in ("leaderboard", "total_score", "tier_progress"):
        assert token in FORBIDDEN_GAMIFICATION_KEY_TOKENS
        with pytest.raises(ValueError):
            assert_gamification_safe([f"family_{token}"], [])


# --------------------------------------------------------------------------
# 4. 情绪价值优先 + 积分不折现
# --------------------------------------------------------------------------


async def test_blocks_are_ordered_emotional_value_first() -> None:
    """数字与期限(服务额度 / 有效期 / 规则说明 / 续费意向)必须排在最后。

    商业界面的默认写法是余额、额度、价格打头 —— 那是经济价值优先,方向相反。
    """
    trailing = {"服务额度", "有效期", "规则说明", "续费意向"}
    for screen in await _all_screens():
        order = list(screen.blocks)
        positions = [i for i, name in enumerate(order) if name in trailing]
        others = [i for i, name in enumerate(order) if name not in trailing]
        if positions and others:
            assert min(positions) > max(others), (
                f"{screen.surface_id} 的块序把数字排到了前面:{order}"
            )


def test_unknown_block_sorts_to_the_transactional_end() -> None:
    """新块名默认排到最后是安全方向:一个未分类的块不该抢到关系块前面。"""
    ordered = list(order_blocks({"未登记的新块": 1, "当前方案": 2, "有效期": 3}))
    assert ordered[0] == "当前方案"
    assert ordered[-1] == "未登记的新块"
    assert "当前方案" in EMOTIONAL_FIRST_BLOCK_ORDER


async def test_no_read_model_expresses_points_as_money() -> None:
    """积分一旦被显示成钱,就从"我们家参与的证明"退化为小额代金券。"""
    for screen in await _all_screens():
        keys: list[str] = []
        _flatten_keys(screen.blocks, keys)
        assert_no_cash_equivalence(keys, screen.notices)


def test_cash_equivalence_checker_negative_control() -> None:
    with pytest.raises(ValueError, match="forbidden_cash_equivalence_key"):
        assert_no_cash_equivalence(["cash_value"], [])
    with pytest.raises(ValueError, match="forbidden_cash_equivalence_copy"):
        assert_no_cash_equivalence(["ok"], ["当前积分 ≈¥12.80"])
