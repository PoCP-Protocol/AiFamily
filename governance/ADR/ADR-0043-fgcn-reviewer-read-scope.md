---
id: ADR-0043
title: FGCN HumanTask 读取资格与提案 reviewer scope 一致
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0043：FGCN `HumanTask` 读取资格与 proposal reviewer scope 一致

## 背景

FGCN 的 decision 写入已经由 Human Gate 校验 reviewer 是否属于 proposal 的
`allowed_actor_types`。但原来的 `GET human-task` 只校验 tenant 和 family，
不具备该任务角色的 human reviewer 仍可先读取任务内容。

## 决策

1. `GET /families/{family_id}/fgcn/human-tasks/{task_id}` 在加载持久化任务后，
   必须校验 `HumanReviewerContext.actor_type` 属于 proposal 的
   `allowed_actor_types`。
2. 读取失败返回 403，不能通过把 URL、请求体或 reviewer 自报字段改成另一
   个角色来绕过。
3. 这只是 proposal 级 reviewer 类型检查；真实 Account → Family membership、
   逐人授权和第36条 staff access approval 仍由生产 identity/approval resolver
   提供，不能把这个最小检查描述为完整身份系统。

## 正向与反向询证

正向：允许的 `GUARDIAN` reviewer 可以读取任务并继续走 ACCEPT/REJECT。

反向：同 tenant 但 proposal 未允许的 `PROFESSIONAL` reviewer 在读取阶段即被
拒绝；decision handler 仍保留自己的二次校验，防止绕过 GET 直接写入。

## Enforcement

- `backend/domains/service/fgcn/api/routes.py`
- `tests/apps/family_api/test_fgcn_routes.py`
- `backend/intelligence/human_gate/persistence.py`

