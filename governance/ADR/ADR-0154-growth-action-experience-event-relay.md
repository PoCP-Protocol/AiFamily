---
id: ADR-0154
title: GrowthAction 到 Experience 的同库事务事件中继
status: accepted
date: 2026-09-03
---

# 决策

UI-09 的 `GrowthAction` 状态仍由 Action 域唯一持有。`workflow_worker` 只读取
`outbox_events` 中已提交的 Action 事件，将其转换成 `ExperienceEvent` 并写入
`experience_outbox_messages`；复制成功与该 consumer 的独立投递回执必须在同一数据库
事务完成，不占用共享 domain outbox 的全局 `published_at`。

事件映射为：开始 → `ACTION_STARTED`，恢复 → `ACTION_RESUMED`，暂停 →
`ACTION_PAUSED`，取消 →
`ACTION_SKIPPED`，PARTIAL → `ACTION_PARTIAL`，NOT_COMPLETED →
`ACTION_NOT_COMPLETED`，只有 COMPLETED → `ACTION_COMPLETED`。
Experience payload 只携带行动 ID、计划/阶段、日序和执行状态，不复制行动说明或
家庭反思正文。

# 约束

- 每条 Action 写请求必须携带服务端重验后的 tenant/family/subject/purpose/consent、
  region、locale 与 deletion ref；客户端不得提供这些范围字段。
- worker 投影前再次检查当前 Consent。授权已撤回时不创建 Experience 派生数据，
  写 metadata-only 拒绝审计后确认源消息，避免无限重试。
- Experience outbox 当前仍使用单一 ACK，因此近期固定由 composite fanout 在同一事务
  完成 Achievement、Notification、Analytics 与 GrowthGraph，全部成功后才统一确认；
  `ACTION_RESUMED` 必须能够在 worker 重启后无状态地产生暂停后继续里程碑。
- source outbox 的 poison message 使用独立 attempt/status receipt 重试并最终进入
  metadata-only `DEAD_LETTERED` 终态，不阻塞后续正常事件。
- Experience 成就只能描述 `FIRST_STEP`、`PAUSE_AND_RETURN` 等家庭私有过程里程碑；
  不生成分数、排名、等级、连胜或效果结论。
- AI 草案 provenance 作为来源引用保留，但状态变更事件的 actor/provenance 类型为
  HUMAN；不得把 AI 描述成实际完成行动的人。

# 结果

Action、Experience 与 Achievement 的所有权保持分离；同一 Action 事件可安全重放，
且 Consent 撤回不会继续产生新的体验层派生记录。常驻 scheduler、payload-preserving
DLQ/告警、共享 Consent canonical version 服务与部署监控仍由后续 workflow-worker
运行时增量完成。
