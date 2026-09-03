---
id: ADR-0059
title: Durable Tool Action to Human Gate inbox
status: Accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0059：Tool Action Outbox 到 Human Gate Inbox

## 背景

Tool Runtime 只能产生 `PENDING_HUMAN_CONFIRMATION`，但此前没有明确的
provider-neutral 适配层把 durable outbox 消息送入 Human Gate。直接在 worker
中拼装任务会绕过草稿状态、范围校验和 Human Gate 的幂等语义。

## 决策

1. 新增 `ToolActionHumanGateInbox`，只接受 `StoredToolActionMessage`，严格校验
   pending 状态、事件类型、payload 快照、租户/家庭/purpose 范围和时间戳。
2. 将消息转换为 `DRAFT` 状态的 `ActionProposal`，proposal/draft id 由
   `tenant_id + call_id` 的稳定摘要生成，交由 `SqlAlchemyHumanGate.submit` 创建
   `OPEN` `HumanTask`。重放同一 call 返回同一任务，内容变更由 Human Gate
   `PROPOSAL_REPLAY_MISMATCH` fail-closed。
3. 默认仅允许 Guardian 审查，部署组合根可显式提供其他真人角色；过期消息被拒绝，
   不产生任务。适配器不调用模型、不执行 Named Action、不提交事务，outbox
   `mark_published` 与 commit 由 worker/组合根负责。

## 后果与缺口

- Tool Action 的 scope、provenance、risk、expiry 在进入人工队列时保持不变，审计
  事件与 HumanTask 可在同一事务提交。
- 本 ADR 不实现通知、租约、dead-letter 或业务域二次授权；这些仍是生产组合根和
  worker 的后续工作。

## 验收证据

- `backend/intelligence/human_gate/tool_action_inbox.py`
- `tests/intelligence/human_gate/test_tool_action_inbox.py`
