---
id: ADR-0037
title: FGCN P0 事实接入同事务持久化适配器
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0037：FGCN P0 事实接入同事务持久化适配器

## 背景

ADR-0036 已经证明了 FGCN 的内存业务不变量，但 `FGCNEngine` 仍不能在进程
重启后保留案件、任务、分派、验收、贡献和影子分配。历史 baseline 已经有
这些表，却缺少能够承载当前 P0 合同的 ORM/Repository；直接把 baseline 当作
运行时能力会把“有表”误报为“可运行”。

## 决策

1. 新增 `SqlAlchemyFGCNRepository`，映射既有 `service_cases`、`service_tasks`、
   `task_assignments`、`task_quality_reviews`、`service_contributions`、
   `service_case_allocation_runs` 和 `service_contribution_allocations`。
2. Repository 只 stage，不自行 commit；业务写入和 `AuditRecorder.flush(session)`
   必须共享调用方的 `SqlAlchemyUnitOfWork`。审计写入失败时，业务事务一起失败。
3. 新增 Alembic `0004_fgcn_p0_persistence`，不改历史 baseline：保存验收标准、
   Human Gate 来源/确认人、租户与 scope 元数据，并把 case-level allocation 的
   `task_ref` 改为可空。用虚构 task 来绕过历史 `NOT NULL` 是禁止的。
4. 交付凭证暂存于 baseline 已有的 `service_tasks.deliverable` JSON；独立
   `service_deliveries` 表仍是后续目标态，不能在本 ADR 中冒充已存在。

## 正向与反向验收

正向：完整 P0 事实链可在同一 SQLite session 中 round-trip，包含蓝图快照、
验收标准、交付凭证、质量状态、贡献、100 单位影子分配和同事务审计。

反向：未提交的 UoW 必须同时回滚业务行和审计行；缺失租户/scope 元数据、缺失
贡献依据、错误的重复主键和 case-level allocation 的伪造 task basis 均 fail closed。

## 能力边界

该 ADR 只交付 durable repository seam 和 schema correction，不宣称 FGCN 已经
拥有 FastAPI 路由、跨进程 HumanTask 队列、重启重建完整 engine、资源准入、返工、
争议裁决、质量池释放或真实资金通道。上述能力必须在后续 ADR/测试中分别落地。
