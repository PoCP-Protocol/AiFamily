---
id: ADR-0097
title: Metadata-only AI Telemetry 按 started_at TTL 批量删除
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0097：Metadata-only AI Telemetry 按 `started_at` TTL 批量删除

## 背景

`ai_telemetry_spans` 只保存 trace、opaque scope、版本、状态和错误码等低基数元数据，
但没有 retention/deletion worker 时，metadata 仍可能无限期留存。当前表没有名为
`created_at` 的列，`started_at` 是 span 的创建时间，故 TTL 必须以它为唯一时间基准。

## 决策

1. 新增 `TelemetryRetentionStore` provider-neutral port，以及 SQL 和 InMemory 实现；
   SQL 实现只查询/删除 `ai_telemetry_spans`，不读取 payload（表中也不得存原文），并
   只 `flush`，事务由调用方持有。
2. `TelemetryRetentionWorker.run_once(ttl, limit, now)` 计算 `cutoff = now - ttl`，
   按 `(started_at, span_id)` 稳定排序、最多处理 `limit` 行；`limit=0` 是合法空批次，
   负数或无时区时间 fail-closed。
3. 每行删除返回不可变 `TelemetryDeletionReceipt`（span、cutoff、deleted_at、opaque
   tenant/family ref），可选 `TelemetryDeletionAuditSink` 在同一调用方事务中幂等保存
   回执。重复执行不会重复删除或重复审计。
4. 默认 InMemory store/audit 仅用于 dev/test；生产必须注入 SQL store 与 durable audit
   proof，并由 scheduler 触发 bounded runs。Worker 不调用模型 provider、不写领域事实。

## 后果与缺口

- 删除范围和批次边界明确，支持重启后继续清理；回执使每次删除可观测、可审计。
- PostgreSQL 并发 claim/lease、定时调度、删除证明专表和告警尚未接入；在这些接线完成
  前不能宣称部署级 retention 已上线。

## 验收证据

- `backend/intelligence/observability/retention.py`
- `backend/intelligence/observability/persistence.py`
- `tests/intelligence/observability/test_retention.py`
