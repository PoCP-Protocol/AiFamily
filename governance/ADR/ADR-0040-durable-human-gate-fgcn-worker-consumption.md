---
id: ADR-0040
title: Human Gate 持久化并由 FGCN worker 消费 Named Action
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0040：Human Gate 持久化并由 FGCN worker 消费 Named Action

## 背景

ADR-0039 已把 `NamedActionRequest` 接到 FGCN 的 durable assignment command，
但 Human Gate 仍由 `InMemoryHumanGate` 保存。进程退出后，已生成的 proposal、
真人 decision、scope 和 provenance reference 消失；因此无法证明重启后的
请求仍是同一个请求，也没有可安全重试的跨进程消费入口。

## 决策

1. `ai_human_tasks` 是 Human Gate 的持久化聚合表，保存完整 proposal、decision
   和 accepted `NamedActionRequest` 快照，同时保存 tenant/family/subject/purpose/
   consent/correlation、expiry、risk 和 provenance scalar 以便索引与审计查询。
2. `SqlAlchemyHumanGate.submit/decide` 只使用调用方 session，不自行 commit；每个
   状态变更必须带 `AuditRecorder`，由调用方在同一事务 flush 后 commit。重启加载
   通过契约重新校验 payload 与 scalar snapshot，篡改或不完整数据 fail closed。
3. 同一 tenant + proposal id 只能建立一个 HumanTask；decision id 与 accepted
   request id 使用数据库 partial unique index 防止跨进程重复。相同内容的 replay
   返回既有快照，内容冲突拒绝。
4. `consume_accepted_human_task` 是 FGCN 的窄 worker handler。它只消费已决定且
   有 action request 的任务，并委托 ADR-0039 的应用命令；不在 Human Gate 写业务
   ORM。应用命令以 request id 幂等，因此 worker 在 command commit 后崩溃并重试时
   不会制造第二个 assignment 或重复 FGCN audit。

## 正向与反向询证

正向：新 session 可以加载与原 proposal 相同的 HumanTask、decision、scope 和
provenance，并由 worker 将 accepted request 变成 TaskAssignment；再次消费返回
同一 assignment。

反向：跨租户/家庭/主体/用途/correlation 的业务请求、AI/system 决策、过期任务、
proposal/decision 重放冲突、直接篡改 persisted payload、审计 flush 失败和无
accepted request 的任务都不能形成业务事实；未 commit 的 gate 事务不留痕。

## 后果与边界

这一步实现了持久化闸门和可重试的 FGCN handler，但不是完整的常驻
`workflow_worker` 进程：尚未实现队列 lease、并发 claim、通知、dead-letter、
超时调度和生产 identity/consent factory。真实 provider、资源准入、返工、争议、
支付和结算仍不属于 P0。

## Enforcement

- `backend/intelligence/human_gate/persistence.py`
- `backend/domains/service/fgcn/workflow_worker.py`
- `database/migrations/versions/0006_ai_human_tasks.py`
- `tests/intelligence/human_gate/test_persistence.py`
- `tests/domains/service/fgcn/test_workflow_worker.py`

## References

- `governance/ADR/ADR-0039-fgcn-named-action-durable-command-boundary.md`
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md`
- `governance/REPOSITORY_CONSTITUTION.md` R6/R8/R9/R10
