---
id: ADR-0153
title: UI-09 GrowthAction 由 Action 域唯一拥有并承接已确认 AI 计划
status: accepted
date: 2026-09-03
owners: [action, journey, ai-platform]
---

# 决策

`GrowthAction`、开始/暂停/继续/取消/完成状态机、CheckIn 与 Reflection 的唯一业务 Owner 是
`backend/domains/action`。`backend/domains/journey` 只拥有 JourneyPlan、JourneyPhase 与阶段复盘，
不得实现单个行动的执行状态。

AI `growth_plan_draft` 经两次 Guardian Human Gate 后，`CONFIRM_AI_JOURNEY_PLAN` 可以：

1. 由 Journey 域把计划从 DRAFT 变为 ACTIVE；
2. 通过 Action application port 创建该计划第一个 `GrowthAction(NOT_STARTED)`。

第二步使用已经被监护人接受的 draft digest、provenance 与首阶段 small action，不代表 AI
获得事实写权限；canonical write 仍由 Action 域在 Named Action 执行上下文中完成。

# 不变量

- Action 完成记录不是 Outcome、教育效果、得分、排名或诊断。
- START、PAUSE、RESUME、CANCEL、CHECK_IN 只能由当前授权家庭成员触发。
- 暂停没有 streak、积分或惩罚。
- Reflection 是家庭原始表达，边界固定为 `REFLECTION_IS_RAW_MATERIAL_NOT_OUTCOME`。
- 状态变更、Audit、Outbox 与幂等回执必须在同一 PostgreSQL 事务。
- UI-09 的 test/staging/production 使用同一 API、状态机、错误码和 Consent 边界。

# API

- `GET /families/{family_id}/today`
- `POST /families/{family_id}/tasks/{task_id}/state`
- `POST /families/{family_id}/tasks/{task_id}/check-in`

# 后续

- Action outbox 转 ExperienceEvent 后，才能产生 feedback/achievement 派生投影。
- AI 成就候选仍须 Human Gate；确定性里程碑也必须证据绑定、家庭私有且可删除。
