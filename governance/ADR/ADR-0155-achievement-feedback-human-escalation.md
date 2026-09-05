---
id: ADR-0155
title: 成就反馈与家庭人工请求的原子闭环
status: accepted
date: 2026-09-03
---

# 决策

家庭可对真实 Experience Achievement 提交 `helpful`、`not_helpful` 或
`request_human`。反馈是 append-only `FeedbackSignal`，只形成体验层证据，不修改
GrowthAction、JourneyPlan、Achievement 或 Outcome。

`request_human` 必须在同一 PostgreSQL 事务内创建反馈、`HumanTask` 和两份
`AuditEvent`。任一写入或审计失败，全部回滚。Human Gate 提案增加显式
`source_kind=USER_REQUEST`，避免把家庭主动请求伪装成 AI 草案；旧 AI 路径默认保持
`AI_DRAFT`。

# 约束

- HTTP body 只接受 signal、枚举化 reason code 和事件时间；actor、tenant、family、
  subject、purpose、Consent、region、locale 与 deletion ref 全部由服务端解析。
- 目标 Achievement 必须属于当前完整 ExperienceScope；跨 tenant/family/subject、旧
  Consent 版本和不存在目标均不得写入。
- `not_helpful` 与 `request_human` 必须提供 reason code，不保存自由文本、模型原文或
  家庭反思正文。
- 同 tenant/idempotency key 使用事务级 advisory lock 串行化；同 payload 返回原回执，
  不同 payload 返回冲突。
- 人工 reviewer 仅限 Professional/Operator。后续接受最多产生明确 Named Action
  `RESPOND_TO_EXPERIENCE_FEEDBACK`，不得修改任何领域事实。

# 结果与后续

UI-09 的真实行动成就已有可追溯反馈和人工升级入口，测试环境与生产环境使用相同路由、
PostgreSQL、Consent、幂等与 Human Gate 规则。主体删除时联动清理 feedback/HumanTask、
该 Named Action 的 worker handler、共享 main 挂载与通知派送仍需后续增量完成。
