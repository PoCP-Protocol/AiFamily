---
id: ADR-0021
title: 业务场景驱动的总数据架构与 WIP 整合
status: proposed
date: 2026-08-30
deciders: project-owner / chief-architect
---

# 业务场景驱动的总数据架构与 WIP 整合

## Context

当前仓库同时存在 legacy Alembic baseline、Family/Assessment/Journey/Service/Commerce/Membership/Loyalty/Product Intelligence 等 Agent WIP、移动端 Projection，以及平台 identity/consent/audit/context-engine WIP。若只按新文档建表，会产生第二套事实源；若只按历史表迁移，又无法覆盖 24 个业务闭环和 14 个平台运营闭环。

## Decision

1. 以 `docs/02_business/BUSINESS_SCENARIO_CLOSURE_CATALOG.md` 的 S01-S24/O01-O14 为场景目录，以本 ADR 配套的数据架构工作稿为总设计入口。
2. 每个业务概念只有一个权威写入域；WIP ORM、SQL repository、移动端 contract 和历史表均登记到该域的兼容矩阵，不允许平行事实源。
3. legacy `database/baseline` 保持只读；所有 WIP ORM 与私有 SQL 的差异必须转成 baseline 之后的 Alembic revision，并让 PostgreSQL 集成测试从同一 migration 建库。
4. 预约子链与 FGCN 案件/任务/验收链统一归 `service` 域的不同聚合；目录主数据与家庭私有事实分离；product intelligence 只产生运营/产品决策，不写儿童成长事实。
5. 跨域传播统一使用带租户、主体、目的、同意、幂等和 provenance 的事件信封；UI、AI、报表和缓存只消费 Projection。
6. 开发、测试、生产使用同一 schema、状态机、权限、审计、错误码和 workflow；只替换合成数据及外部适配器。

## Consequences

- 现有 WIP 可以复用，但必须先声明是权威表、兼容适配器、投影还是待迁移对象。
- `product_intelligence` 的 ORM/私有迁移领先 baseline 的字段不能直接进入生产；必须补 revision 并消除测试建库漂移。
- `loyalty_points` 以追加式 ledger 为权威，余额由事件聚合；不得恢复 UI-17 的硬编码余额。
- `platform_audit_events` 为新审计事实，legacy `audit_logs` 只读兼容；审计、outbox、幂等记录与业务事务保持可追踪关联。
- 总设计在业务负责人确认每个场景的字段级契约前保持 `draft`，不得将设计覆盖率宣称为实现覆盖率。

## Enforcement

- 总数据设计：`docs/07_data/BUSINESS_SCENARIO_DATA_ARCHITECTURE.md`；
- 场景目录：`docs/02_business/BUSINESS_SCENARIO_CLOSURE_CATALOG.md`；
- WIP 覆盖测试：`tests/architecture/test_data_architecture_catalog.py`；
- migration 约束：`database/migrations/versions/` 与 `tests/database/`；
- 环境等价：`docs/10_engineering/ENVIRONMENT_PARITY.md` 与 ADR-0020。
