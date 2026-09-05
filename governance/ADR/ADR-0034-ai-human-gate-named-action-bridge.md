---
id: ADR-0034
title: AI 草案必须经过 Human Gate 才能形成 Named Action 请求
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0034：AI 草案必须经过 Human Gate 才能形成 Named Action 请求

## 背景

AiFamily 的 Model Gateway 已能返回带完整 Provenance 的 `ModelDraft`，但
“草案需要人工确认”如果只停留在字段或提示语中，仍然可能被调用方直接当作
服务分派、验收、贡献或结算事实。FGCN 的高影响动作必须有可测试的人工闸门，且
AI Runtime 不得持有业务域仓储。

## 决策

新增 `backend/intelligence/human_gate` 作为 AI Runtime 的人工确认边界：

1. 只有状态为 `DRAFT` 且 `may_mutate_business_state` 为 `False` 的模型结果可以入闸。
2. 入闸产物是 `ActionProposal` 和 `OPEN` 的 `HumanTask`，保存精确的租户、家庭、
   主体、用途、同意版本、Provenance、截止时间和允许的真人角色。
3. 只有允许的 `GUARDIAN`、`PROFESSIONAL` 或 `OPERATOR` 明确 `ACCEPT` 后，才返回
   `NamedActionRequest`。该对象是发送给业务域的请求，不是业务事实；业务域仍须
   自己做授权、同意、版本、幂等、事务、审计和领域校验。
4. `REJECT`、`ESCALATE`、过期、AI/系统角色、越权角色和通用写操作名称均 fail closed，
   不产生 Named Action 请求。
5. 第一版只提供 `InMemoryHumanGate`，用于契约测试和开发环境；在持久化、队列、
   通知、超时 worker、审计和业务域 Named Action 接线完成前，不宣称生产可用。

## 正向与反向验收

正向路径必须证明：`ModelDraft → HumanTask(OPEN) → 真人 ACCEPT → NamedActionRequest`
能够保留原始范围和 Provenance。

反向路径必须证明：AI/系统不能决定，未授权真人不能决定，截止后不能决定，拒绝不产出
请求，通用 `UPDATE/PATCH` 不能伪装成 Named Action，同一提案重放不重复创建任务。

## 后续接入

FGCN 服务域应提供自己的 `CONFIRM_SERVICE_TASK_ASSIGNMENT` Named Action handler，
接收并重新校验本 ADR 定义的请求后，才可以在同一事务中写入
`TaskAssignment`、审计事件和 Outbox。该 handler 不属于本 ADR 的实现范围。
