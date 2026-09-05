---
id: ADR-0070
title: Durable AI release decision ledger
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0070：持久化 AI 发布准入决策账本

## Context

`AiReleaseGate` 已将离线评测证据与 `ProviderRegistry` 准入绑定，但纯函数
返回值无法支持跨进程审计、重放和运营查询。把报告原文或模型输出复制到运行
时库又会扩大儿童数据暴露面。

## Decision

新增 `ReleaseDecisionSink` 与 `SqlAlchemyReleaseDecisionSink`，将
`ReleaseDecision` 的状态、候选/供应商/模型版本、环境、不可变 `report_ref`
和稳定 failure codes 写入 AI-runtime-owned `ai_release_decisions`（migration
0020）。决策指纹作为幂等主键，重复投递返回已存记录；事务由组合根提交。

账本不保存 benchmark payload、媒体、Prompt、模型输出、密钥或部署副作用。
`ReleaseAdmissionService` 提供显式的“评测→门禁→记录”异步应用边界。
它记录“门禁判定是什么”，不等于人工签名批准；真正生产发布仍需审批人/签名、
回滚控制器和部署系统的独立接线。

## Consequences

- 测试与生产使用同一持久化契约，重启后仍可查询 ADMITTED/BLOCKED 历史。
- 决策可按 candidate/environment 或 provider/environment 查询，且重复评测安全重放。
- 账本不会把评测数据复制进运行时，也不会绕过 ProviderRegistry、Human Gate 或部署审批。
