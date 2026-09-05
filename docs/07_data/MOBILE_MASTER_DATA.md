---
id: DATA-MOBILE-MASTER-001
title: Mobile 场景主数据落地清单
type: data
status: current
version: 1.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: true
supersedes: null
superseded_by: null
---

# Mobile 场景主数据落地清单

本清单把 34 个移动端页面中需要“目录/供给”的内容，与主数据表和家庭事实表分开。目录主数据不带 `family_id`，家庭浏览、预约和购买意向才产生家庭私有事实。

| 移动场景 | 主数据 | Canonical 表 | 当前代码状态 |
|---|---|---|---|
| UI-19 名师专区 / UI-20 名师详情 / UI-21 预约 | 服务者、服务供给、可用时段 | `family_service_providers`、`family_service_offerings`、`family_service_availability_slots` | Python ORM、Port、查询与开发目录已具备 |
| UI-22 沙龙活动 / UI-23 活动详情 | 活动目录 | `family_activity_catalog` | baseline 已有表；Service 应用查询与移动端读取已接入（当前为 DEV/TEST fixture） |
| UI-13 商城 / UI-14 方案详情 | 商品供给、购买意向回执 | `family_product_offerings`、`family_order_intents`、`family_entitlements` | Commerce 目录、幂等意向写入与家庭投影已接入（DEV/TEST） |
| UI-06 / UI-18 / UI-30 会员 | 会员方案、权益定义 | `family_membership_plans`、`family_membership_benefit_definitions` | Python ORM、Port、查询与生命周期代码已具备 |
| UI-17 积分 | 积分规则、兑换目录 | `family_loyalty_points_earn_rules`、`family_loyalty_points_redemption_items` | Python ORM 已有；余额只能由 ledger 聚合，不允许默认值 |

## 边界

- 主数据版本由 `ref + version_no` 识别；发布后的版本不可被家庭事实回写。
- `fixture_only=true` 只标记当前数据为模拟目录；不得把它解释成测试环境缺少生产功能。生产切换的是数据来源和外部适配器，业务流程必须相同。
- UI-19 的开发目录由 `backend/domains/service/application/master_data.py` 幂等装载，稳定引用按租户隔离。
- UI-22/23 的目录由 `backend/domains/service/application/master_data.py` 幂等装载，读取接口为 `/families/{familyId}/orchestration/test-loop/services/activities`；活动详情只携带目录元数据，不产生报名或出席事实。
- 当前 `FakeServiceRepository` 已实现活动目录 Port；生产 SQLAlchemy repository 与 Alembic 写入尚未接入，不能把开发目录宣称为生产供给。
- UI-13/14 的商品 identity/version 由 Commerce 目录返回；价格、交付文案等展示字段仍保留在前端 presentation metadata，避免把展示文案误当成交易事实。
- Commerce 当前仅完成 DEV/TEST 目录和 no-op 意向回执；支付、通知、履约与生产 session/consent wiring 仍是后续能力。
- 预约、订单意向、权益发放和积分变动属于家庭事实/追加式 ledger，不与主数据表混写。
- 不包含家庭总分、排名、等级或跨家庭比较字段。
