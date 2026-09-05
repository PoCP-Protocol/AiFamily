---
id: ADR-0053
title: AgentRun 与 Trace 采用 AI Runtime 自有的可回放持久化账本
status: Accepted
date: 2026-08-30
---

# AgentRun 与 Trace 采用 AI Runtime 自有的可回放持久化账本

## 背景

Agent Runtime 已经能够通过授权与 Prompt/Schema Registry 生成 `DRAFT`，但进程
重启后无法回答“这次执行是否开始、为何失败、模型草稿是什么、发生了哪些步骤”。
仅依赖模型 Gateway 的进程内 attempt 记录也无法提供 Agent 级别的幂等和回放，且把
运行记录写入业务域会违反 AI Runtime 隔离边界。

## 决策

1. 在 `backend/intelligence/agent_runtime/persistence.py` 提供
   `AgentRunPersistencePort` 与 `SqlAlchemyAgentRunStore`。适配器只依赖
   `AsyncSession`，每个命令只 `flush`，不 `commit`，由组合根决定事务边界。
2. `ai_agent_runs` 保存 tenant/family scope、request/agent/use-case、trace、
   幂等键与指纹、`STARTED/SUCCEEDED/FAILED` 生命周期、错误码以及带完整
   provenance 的 `DRAFT`。同一 scope 重放相同幂等键返回原记录，内容不同则拒绝。
3. `ai_agent_traces` 是按 trace/sequence 排序的追加账本。创建、成功、失败会自动
   写入生命周期事件，业务调用方可追加模型/工具等事件；事件重放同幂等键必须内容
   一致。所有读取都要求完整 tenant/family scope，跨 scope 返回空。
4. 持久化边界拒绝原始 bytes、内联媒体、家庭总分/排名/权威事实等字段，且 Draft
   状态不可被提升为业务事实。Named Action 与 Human Gate 仍由业务域负责。
5. Alembic `0012_ai_agent_runs` 负责生产表结构；进入发布前必须将迁移、ADR 和
   `MIGRATION_MANIFEST` 一并登记并通过真实 PostgreSQL 往返测试。

## 后果

- AgentRun 可在进程重启后按 scope 幂等恢复并回放，具备与测试环境一致的生产运行
  语义；provider 仍可替换，持久化层不引入 SDK。
- 组合根可以把 AgentRun、Trace、Outbox 放入同一事务，避免“模型已调用但运行记录
  丢失”或“记录存在但业务事件未投递”的孤儿状态。
- 当前实现是持久化 seam，不包含 durable worker lease、OpenTelemetry exporter、
  cost 聚合和真实 provider；这些能力需在后续 ADR/迭代中接入。

## 约束依据

- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.5、§4
- `docs/05_ai/AI_TECHNICAL_ARCHITECTURE.md` §8、§12
- `governance/REPOSITORY_CONSTITUTION.md` R7、R8、R9、R10
