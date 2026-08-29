"""The 34 App UI surfaces, mirrored from the frontend registry.

Single source of truth is `apps/mobile/lib/family/ui-registry.ts`
(`FAMILY_SCREENS`). This module is the Python-side mirror so backend read
models can be *named and shaped per screen* instead of the backend inventing
its own page vocabulary — which is exactly how UI-06 / UI-18 / UI-30 ended up
each implying a different membership meaning before the
`FAMILY_MEMBERSHIP_OS_V2_BASELINE.md` UI contract was written.

Drift is not prevented by discipline here: `tests/test_ui_surface_registry_parity.py`
parses the TypeScript file and fails if the id/title/tab/loop of any of the 34
screens disagrees with this table, or if the count is no longer 34.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

FamilyTab = Literal["today", "growth", "discover", "services", "mine"]
FamilyLoop = Literal["成长", "计划", "评估", "服务", "商业", "社区"]


class UiSurface(NamedTuple):
    id: str
    title: str
    tab: str
    loop: str
    feature_points: tuple[str, ...]


FAMILY_UI_SURFACES: Final[tuple[UiSurface, ...]] = (
    UiSurface(
        "UI-01",
        "家庭成长首页",
        "today",
        "成长",
        ("今晚一件事", "当前成长旅程", "最近家庭里程碑", "21 天成长营入口"),
    ),
    UiSurface(
        "UI-02",
        "家庭测评",
        "growth",
        "评估",
        ("沟通与冲突", "学习与习惯", "手机与边界", "家长视角说明"),
    ),
    UiSurface(
        "UI-03",
        "AI成长诊断",
        "growth",
        "评估",
        ("综合成长评估", "核心问题", "成长建议", "个性化方案"),
    ),
    UiSurface(
        "UI-04",
        "90 天成长方案",
        "growth",
        "计划",
        ("看见与理解", "家长先行动", "亲子共同练习", "稳定与复盘"),
    ),
    UiSurface(
        "UI-05", "90 天陪跑", "growth", "计划", ("本周任务", "阶段复盘", "陪伴记录", "家长社群")
    ),
    UiSurface("UI-06", "我的会员", "mine", "商业", ("当前方案", "成长权益", "服务额度", "有效期")),
    UiSurface(
        "UI-07", "成长测评入口", "growth", "评估", ("推荐测评", "预计用时", "同意说明", "历史记录")
    ),
    UiSurface(
        "UI-08",
        "家庭过程回顾",
        "growth",
        "评估",
        ("过程记录", "观察方向", "证据来源", "需要进一步确认的内容"),
    ),
    UiSurface(
        "UI-09",
        "今日成长任务",
        "today",
        "成长",
        ("为什么做", "今晚做什么", "可以怎么说", "完成与反思"),
    ),
    UiSurface(
        "UI-10",
        "孩子成长小助手",
        "today",
        "成长",
        ("孩子友好练习", "表达选择", "可见性说明", "需要帮助"),
    ),
    UiSurface(
        "UI-11",
        "我们的成长节奏",
        "growth",
        "成长",
        ("本周参与", "阶段节奏", "暂停与恢复", "自己的变化"),
    ),
    UiSurface(
        "UI-12", "成长故事卡", "growth", "社区", ("家庭里程碑", "私有保存", "分享草稿", "家庭确认")
    ),
    UiSurface(
        "UI-13",
        "家庭成长商城",
        "discover",
        "商业",
        ("按场景查找", "课程与工具", "会员与服务", "已有权益"),
    ),
    UiSurface(
        "UI-14",
        "成长方案详情",
        "discover",
        "商业",
        ("适用家庭", "交付内容", "预计投入", "证据边界"),
    ),
    UiSurface(
        "UI-15", "邀请有礼", "discover", "商业", ("单层邀请", "成长权益", "隐私提示", "邀请记录")
    ),
    UiSurface(
        "UI-16",
        "家庭同行计划",
        "discover",
        "商业",
        ("同行意向", "参与规则", "家庭人数", "取消与恢复"),
    ),
    UiSurface(
        "UI-17", "成长积分", "discover", "商业", ("积分任务", "权益账本", "已领取", "规则说明")
    ),
    UiSurface(
        "UI-18", "会员中心", "mine", "商业", ("会员状态", "可用权益", "服务入口", "续费意向")
    ),
    UiSurface(
        "UI-19", "名师专区", "services", "服务", ("专家主题", "服务方式", "可用性", "选择说明")
    ),
    UiSurface(
        "UI-20", "名师详情", "services", "服务", ("专业背景", "适用问题", "服务边界", "可预约时段")
    ),
    UiSurface(
        "UI-21",
        "在线咨询预约",
        "services",
        "服务",
        ("需求草稿", "时间偏好", "家庭同意", "提交回执"),
    ),
    UiSurface(
        "UI-22", "沙龙活动", "services", "服务", ("线上活动", "线下沙龙", "主题筛选", "时间安排")
    ),
    UiSurface(
        "UI-23", "活动详情", "services", "服务", ("活动议程", "讲师介绍", "适用对象", "活动意向")
    ),
    UiSurface(
        "UI-24", "我的咨询与活动", "services", "服务", ("待确认", "已安排", "已完成", "后续记录")
    ),
    UiSurface(
        "UI-25", "家长社区", "discover", "社区", ("主题内容", "阶段群", "经审核经验", "收藏")
    ),
    UiSurface(
        "UI-26",
        "发布家庭小记",
        "discover",
        "社区",
        ("私有草稿", "去标识化提示", "可见性", "审核状态"),
    ),
    UiSurface(
        "UI-27", "家庭小记详情", "discover", "社区", ("作者视角", "互动评论", "事实来源", "可见性")
    ),
    UiSurface(
        "UI-28", "我的社区", "discover", "社区", ("私有小记", "待发布草稿", "已发布内容", "收藏")
    ),
    UiSurface(
        "UI-29", "成长成果", "growth", "评估", ("过程证据", "家庭里程碑", "阶段报告", "来源说明")
    ),
    UiSurface(
        "UI-30", "年度陪伴方案", "mine", "商业", ("年度计划", "会员权益", "积分与邀请", "续费意向")
    ),
    UiSurface(
        "UI-31", "我的服务", "services", "服务", ("进行中服务", "待处理", "已完成", "下一步")
    ),
    UiSurface(
        "UI-32", "订单与资产", "mine", "商业", ("方案意向", "已激活权益", "成长报告", "课程资产")
    ),
    UiSurface(
        "UI-33", "家庭档案", "mine", "成长", ("家庭成员", "角色与同意", "可见性", "成长重点")
    ),
    UiSurface(
        "UI-34",
        "服务记录",
        "services",
        "服务",
        ("服务发生记录", "顾问记录", "家长反馈", "来源与时间"),
    ),
)

FAMILY_UI_SURFACE_IDS: Final[frozenset[str]] = frozenset(s.id for s in FAMILY_UI_SURFACES)

FAMILY_UI_SURFACE_COUNT: Final[int] = 34

# --------------------------------------------------------------------------
# Which surfaces each backend domain is allowed to serve or be written from.
# --------------------------------------------------------------------------

# Screens whose loop is 商业 and which display membership or points state.
# A read model must declare the surface it serves; a surface outside this set
# is a sign the domain is leaking into a loop it does not own.
MEMBERSHIP_READ_SURFACES: Final[frozenset[str]] = frozenset(
    {"UI-06", "UI-13", "UI-18", "UI-30", "UI-31", "UI-32"}
)

POINTS_READ_SURFACES: Final[frozenset[str]] = frozenset({"UI-17", "UI-30"})

# Write-origin surfaces. `family_membership_benefit_ledger.source_page_id`
# (migration 0033) already CHECKs UI-30/31/32 — benefit units are only ever
# spent from the annual cockpit, my-services, or orders-and-assets. Keep the
# Python allow-list identical to the DDL rather than widening it here.
MEMBERSHIP_LEDGER_SOURCE_SURFACES: Final[frozenset[str]] = frozenset({"UI-30", "UI-31", "UI-32"})

# Points move from the points screen itself (UI-17 积分任务/权益账本), the
# annual cockpit (UI-30 积分与邀请), and the referral screen (UI-15 邀请有礼).
POINTS_LEDGER_SOURCE_SURFACES: Final[frozenset[str]] = frozenset({"UI-15", "UI-17", "UI-30"})


def get_surface(surface_id: str) -> UiSurface:
    for surface in FAMILY_UI_SURFACES:
        if surface.id == surface_id:
            return surface
    raise KeyError(f"unknown_ui_surface:{surface_id}")
