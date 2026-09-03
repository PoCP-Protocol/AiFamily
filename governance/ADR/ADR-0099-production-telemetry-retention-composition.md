---
id: ADR-0099
title: Explicit composition root for telemetry retention
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0099：Telemetry retention 的生产组合根

## Context

`TelemetryRetentionWorker` 已具备 SQL TTL 删除和 metadata-only 回执，但若由部署脚本
直接创建 worker，容易遗漏事务边界或删除审计。生产需要一个与发布和 Experience
Outbox 一致的 bounded、可重启组合入口。

## Decision

新增 `ProductionTelemetryRetentionRuntime`：

- 仅接受 `staging`/`production`，每次 `run_once` 创建独立 SQL session 和事务；
- 强制注入 `TelemetryDeletionAuditSink` factory，删除和回执在同一事务内完成；
- TTL、limit、时区和排序继续由 `TelemetryRetentionWorker` 校验，runtime 不绕过这些
  约束；
- runtime 不负责周期调度，scheduler 只触发 bounded run，测试仅替换 SQL 数据源和
  audit adapter。

## Consequences

- 测试、预发布和生产共享相同的 TTL、删除、回执和回滚语义。
- 生产仍需 durable deletion-proof 表、scheduler、告警、PostgreSQL 多 worker 并发压测
  与保留策略审批；InMemory audit 仅可用于测试，不能作为生产证明。
