---
id: ADR-0151
title: UI-05 成长计划草案使用专用不可变审核信封
status: accepted
date: 2026-09-03
owners: [ai-platform, journey]
---

# 决策

UI-05 的 `growth_plan_draft` 在进入 Human Gate 前，必须同时持久化：

1. 通用 `ai_model_drafts` 中唯一的模型正文与 provenance；
2. `ai_growth_plan_draft_reviews` 中专用、不可变的审核信封。

两条记录在同一数据库事务中写入。审核信封绑定 tenant、family、subject、region、purpose、
consent version、data class、locale、deletion ref、AgentRun、三类业务引用、全部 input refs、
TTL、retention policy 和覆盖完整模型草案的稳定摘要。

后续 HTTP 审核请求只提交 `draft_id`。服务端以当前可信 `ContextScope` 回读信封；生成请求与
审核请求的 correlation 可以不同，但家庭、主体、用途、同意、删除和 locale 边界必须一致。

Human Gate 接受仅生成具名动作 `CREATE_JOURNEY_PLAN_FROM_AI_DRAFT`。该动作最多允许 Journey
领域创建 `JourneyPlan(DRAFT)`；激活计划必须由另一项监护人明示确认完成。

# 原因

通用 `ai_model_drafts` 没有 consent、deletion、TTL、retention、input refs 与 review digest，
且其 correlation 是模型产物注册范围，不应被误用为跨 HTTP 请求的审核授权范围。专用 companion
信封保留一份模型正文，同时补齐未成年人数据生命周期和人工闸门所需的不可变绑定。

# 约束

- 表只允许 `status='DRAFT'`、`may_mutate_business_state=false`。
- PostgreSQL `BEFORE UPDATE` trigger 拒绝原地修改；到期清理由显式 retention worker 执行删除。
- 跨 scope、过期、摘要漂移、业务引用漂移均 fail closed。
- AI、SYSTEM、worker identity 不得替代 Guardian 决策人。
- 测试环境与 staging/production 使用同一 SQL store、Human Gate 和 Model Gateway 组合。

# 已实现接线

- `GrowthPlanAcceptedActionHandler` 已注册到共享 accepted-action runtime；第一次接受只创建
  `JourneyPlan(DRAFT)`，并生成第二个 Guardian-only HumanTask。
- 第二次接受产生 `CONFIRM_AI_JOURNEY_PLAN`，执行时再次校验当前 scope、Consent、原始
  draft digest、provenance 与当前 Journey DRAFT，只有该动作可以激活计划。
- 认证 HTTP router 与 PostgreSQL bearer/tenant/family/guardian/subject/Consent 组合入口已建立。
- worker 通过 HumanDecision actor 重新解析当前 guardian account、tenant/family binding、subject
  与 GROWTH_TRACKING Consent，不把历史 bearer 或历史授权当作当前权限。

# 未完成项

- 部署主应用挂载与常驻 worker 调度仍由后续迭代完成。
- 真实 PostgreSQL Evidence Reader E2E、并发压力测试与 retention worker 仍需完成。
