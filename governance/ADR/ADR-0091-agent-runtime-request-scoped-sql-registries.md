---
id: ADR-0091
title: Request-scoped SQL Prompt and Schema registries in Agent Runtime composition
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0091：Agent Runtime 请求级 SQL Prompt/Schema Registry 组合

## Context

Agent Runtime 已经支持异步 SQL registry，但生产组合根仍只接受进程内
`PromptRegistry`/`SchemaRegistry`。这会让版本资产在重启后无法被真正的生产请求读取，
并使测试与生产的 registry 生命周期不一致。

## Decision

`ProductionAgentRuntimeResolver` 同时支持结构化 `resolve` registry 与按
`AsyncSession` 创建 registry 的工厂。`ProductionAgentRuntime.execute` 在自己的
`SqlAlchemyUnitOfWork` 内创建 Prompt/Schema SQL adapter，再与 Attempt、Safety、
Telemetry、AgentRun/Trace 共享同一事务；调用方仍必须显式提供 registry 或工厂，
禁止默认回退到内存资产。

## Consequences

- 请求读取的是当前数据库中已发布且有效的版本，跨进程/重启语义与测试一致。
- registry 读取和 Agent 运行记录具备相同事务边界，缺失或歧义仍 fail-closed。
- 真实身份、同意、签名发布和 PostgreSQL 并发压测仍由部署阶段接入；本 ADR 不改变
  AI 不得写业务事实的边界。
