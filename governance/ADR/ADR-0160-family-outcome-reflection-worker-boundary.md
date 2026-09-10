---
id: ADR-0160
title: FamilyNeed 结果复盘的 worker 投影边界
status: proposed
date: 2026-09-09
decision_owner: project-owner
supersedes: null
superseded_by: null
---

# ADR-0160：FamilyNeed 结果复盘的 worker 投影边界

## Context

垂直家庭成长 AGI 的长期闭环要求：家庭确认结果先作为 FamilyNeed 事实持久化，
再通过事件投影为 Context Reflection，供下一轮理解使用。当前 FamilyNeed
PostgreSQL repository 绑定单个 `AsyncConnection`，而 Context SQL Broker 使用
`async_sessionmaker`；将前者直接放入常驻 worker 会留下断线与重启生命周期风险。

## Decision

1. `family_need.outcome_confirmed` 只通过 workflow worker 的有界 activity 投影到
   Context；不在 HTTP 请求内跨存储同步写入。
2. worker 侧使用 session-per-operation 的 `SqlAlchemyFamilyNeedEventReader`，每次
   事件/结果读取创建并关闭新连接。
3. ContextScope 必须由部署组合根通过可信 Identity/Consent/Deletion resolver
   构造；tenant/family 环境变量只能作为显式调度选择，不能生成授权 scope。
4. 投影 observation 使用确定性 ID；相同内容重放幂等，ID 内容漂移 fail-closed。
5. worker activity 不拥有时钟、线程或重试循环，统一由 `WorkflowWorkerRuntime`
   调度并将异常反映为失败/降级。

## Evidence

- `backend/workflow_worker/family_need_event_reader.py`：session-per-operation reader。
- `backend/intelligence/context_engine/family_need_outcome_poller.py`：有界轮询、scope
  一致性校验与批量限制。
- `backend/intelligence/context_engine/family_need_outcome_consumer.py`：事件类型、
  tenant/family/purpose/consent/data class/subject/aggregate 校验与幂等消费。
- `backend/intelligence/context_engine/outcome_reflection.py`：确定性 observation ID、
  provenance、feedback_ref 与 retention。
- 定向回归：Context/worker/FamilyNeed 共 `126 passed, 10 skipped`；架构门禁
  `111 passed, 1 skipped`。跳过项均因未配置 `AIFAMILY_TEST_DATABASE_URL` 或当前没有
  vector storage，不能替代真实 PostgreSQL 验证。

## Consequences

该决定保证 AI Runtime 不反向依赖 FamilyNeed 领域，也避免 worker 使用隐式授权或
进程内状态伪装成长期记忆。代价是生产组合根必须补齐真实 Scope resolver、数据库
生命周期与 outbox 调度，完成后才能宣称端到端复盘闭环。
