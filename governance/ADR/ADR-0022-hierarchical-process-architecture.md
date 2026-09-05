---
id: ADR-0022
title: 将分级流程架构纳入业务架构
status: proposed
date: 2026-08-30
deciders: project-owner / chief-architect
---

# 将分级流程架构纳入业务架构

## Context

原业务架构已描述定位、收入、FGCN、角色和战略原则，但流程主要分散在六类闭环、FGCN 说明和 UI 功能树中，缺少从价值流到系统操作的统一层级。这样会导致 UI、API、数据表或运营后台直接长出流程，业务边界无法追踪。

## Decision

在 `docs/02_business/BUSINESS_ARCHITECTURE.md` 中正式纳入六级流程架构：

```text
L0 价值流 → L1 端到端流程组 → L2 S/O 场景 → L3 子流程 → L4 节点/活动 → L5 系统操作
```

- L0 对齐商业蓝图五个价值流；
- L1 使用 `P01-P06` 作为唯一主归属；
- L2 使用业务场景 `S01-S24` 与平台运营场景 `O01-O14`；
- L3-L4 在业务场景闭环目录中细化；
- L5 由 API、Command、Domain Policy、Event/Outbox、Projection、Job 和 Human Task 实现；
- 一个场景只有一个主流程归属，横切能力通过引用复用，不复制事实源。

## Consequences

- 新功能必须先挂到 L2 场景，再设计节点、数据和 API；
- 业务架构、流程架构、数据架构和应用架构可以分别维护，但必须通过 `VS/P/S/O/N` 标识互相追踪；
- 现有功能树继续负责功能/端点完成度，不再承担流程架构的唯一真相；
- 流程状态、异常、人工接管和平台运营不允许因测试环境而删除。

## Enforcement

- 分级流程架构：`docs/02_business/BUSINESS_ARCHITECTURE.md` §7；
- 节点级契约：`docs/02_business/BUSINESS_SCENARIO_CLOSURE_CATALOG.md`；
- 数据映射：`docs/07_data/BUSINESS_SCENARIO_DATA_ARCHITECTURE.md`；
- 新增架构测试必须检查 L0-L5 层级及 S/O 覆盖，不能只检查 UI 或路由数量。
