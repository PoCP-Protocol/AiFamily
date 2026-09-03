---
id: ADR-0052
title: Human Gate accepted action durable worker claim lease
status: proposed
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0052：Human Gate accepted action 使用 durable worker claim lease

## 背景

`consume_accepted_human_task` 原先先读取 accepted `NamedActionRequest`，再执行业务命令。
两个 workflow worker 可以同时读到同一个请求并同时开始执行；虽然 FGCN 的 request id
幂等键会保护最终 assignment，但它不能阻止重复的并发尝试，也不能表达某次尝试是否
已经失联。常驻队列、重启恢复和超时接管需要一个数据库可见的 claim/lease 边界。

## 决策

1. `ai_human_tasks.claim_owner` 与 `claim_expires_at` 组成成对的 nullable lease 状态。
   只有 `DECIDED` 且存在 accepted `NamedActionRequest` 的任务可以被 claim；其它状态
   在数据库约束和应用层同时拒绝。
2. claim 使用带有“未 claim 或 lease 已过期”条件的原子 UPDATE，并在同一事务写入
   `CLAIM_HUMAN_TASK` 审计事件。活动 lease 拒绝第二 worker；过期 lease 可以接管。
3. worker 必须先提交 claim 与审计，再执行 FGCN application command。执行失败不清除
   claim，让 lease 到期后重试；执行成功后原 owner 在有效期内清除 claim并写审计。
4. claim 不是业务完成标记。即使 worker 在 FGCN commit 后崩溃，下一次接管仍以
   `NamedActionRequest.request_id` 幂等重放，不能创建第二个 assignment 或重复业务审计。

## 正向与反向询证

正向：accepted task 可被一个 worker claim、执行、完成并再次安全重放；lease 到期后新
owner 可接管。

反向：open/rejected/expired task、AI/system claim owner、活动 lease 的第二 owner、
非 owner 完成、过期完成、claim 审计失败、FGCN 审计失败和 request 内容冲突均不能形成
未审计的业务事实或清除他人的 lease。

## 边界

本 ADR 只落地 durable claim/ack seam；通知、dead-letter、常驻调度器、生产 worker
身份认证、真实 identity/consent factory、资源准入、争议和结算仍未完成。

## Enforcement

- `backend/intelligence/human_gate/contracts.py`
- `backend/intelligence/human_gate/persistence.py`
- `backend/domains/service/fgcn/workflow_worker.py`
- `database/migrations/versions/0011_ai_human_task_claims.py`
- `tests/intelligence/human_gate/test_persistence.py`
- `tests/domains/service/fgcn/test_workflow_worker.py`
