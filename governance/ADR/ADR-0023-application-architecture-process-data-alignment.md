---
id: ADR-0023
title: 应用架构按流程和数据架构分级对齐
status: proposed
date: 2026-08-30
deciders: chief-architect
---

# ADR-0023：应用架构按流程和数据架构分级对齐

## 背景

AiFamily 已建立业务架构的 L0-L5 流程层、S01-S24/O01-O14 场景目录，以及数据对象、表和关系目录。仅有路由、UI 或 Domain 代码会造成“接口存在即能力存在”的误判，也会使主数据、业务事实和投影被应用层混写。

## 决策

1. 应用架构采用 A0-A6 七级：应用系统、渠道/进程、应用模块、用例/应用服务、工作流、接口契约、运行组件。
2. A0-A6 分别映射业务 L0-L5；A3/A4 只能编排数据域，不拥有领域事实。
3. 34 个 UI 必须映射到 A3 Query/Command；`UI-02-result` 视为 UI-02 的结果子路由，不新增场景。
4. 每个用例必须登记 `scenario_id/process_group_id/node_id`、数据对象/表/关系、事件、投影和测试证据。
5. 跨域使用 Query Port、Command 或 Event/Outbox；禁止应用服务跨 schema 直接写表。
6. dev/test/prod 使用同一应用路由、状态机、权限、错误码、事件和工作流，仅替换数据工厂和外部适配器。

## 影响

- 业务架构修正 `S16` 的主归属为 `P04/VS-03`，Growth/Service 通过 Entitlement Query Port 读取，不再双写会员事实。
- `family_journey_plans` 是计划主表，`growth_journeys` 只作为 onboarding/兼容聚合。
- Commerce 的 PurchaseIntent 不再被应用层解释为 Order/Payment；正式交易表和支付适配器完成前只能返回受控状态。
- 社区、数据权利、运营、伙伴和 Workflow Worker 必须补齐应用服务、投影、作业和测试后，才能改变能力成熟度。

## 拒绝的替代方案

- 以 UI 路由作为应用模块边界；
- 以数据库表作为跨域应用服务边界；
- 在每个 Domain 内各自调用模型/支付供应商；
- 为测试环境创建阉割版路由或状态机；
- 以 fixture、静态 JSON 或路由挂载证明生产能力。

## 参考

- `docs/02_business/BUSINESS_ARCHITECTURE.md` §7、§9
- `docs/02_business/BUSINESS_SCENARIO_CLOSURE_CATALOG.md`
- `docs/07_data/BUSINESS_SCENARIO_DATA_ARCHITECTURE.md` §14
- `docs/07_data/DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md`
- `docs/06_platform/APPLICATION_ARCHITECTURE.md`

