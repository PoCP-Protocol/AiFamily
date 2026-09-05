# ADR-0124：成就提醒投影留存与删除证明

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/notification_retention.py`、
  `backend/apps/family_api/production_achievement_notification_retention_wiring.py`

## 决策

成就提醒属于 AI runtime-owned 的通知读模型，不是成就事实。新增有界
`AchievementNotificationRetentionWorker`，按正数 TTL、批量上限和调用方提供的
时钟删除 `ai_achievement_notifications` 中过期行。SQL adapter 只删除该读模型，
只 `flush`，由生产组合根持有事务；每次删除通过注入的 audit sink 记录不含标题、
正文、subject 或模型输出的 metadata-only receipt。

staging 与 production 共用同一 worker、排序、TTL 和失败语义，部署平台负责周期
调度和持久化 audit sink。删除提醒不会删除 `Achievement`、ExperienceEvent 或
任何业务域事实；未读状态不改变留存期限，避免以用户是否查看来延长敏感数据保留。

## 取舍

- 优点：通知投影有明确生命周期、可重启的有界批处理和可审计删除证明，测试环境
  不会因为使用 fake adapter 而缩减能力。
- 限制：audit sink 与 scheduler 仍需由部署平台提供 durable 实现；TTL 需要按合规
  分类与运营需求配置并经过审批。
- 安全边界：worker 不发送通知、不调用模型、不执行领域命令，也不暴露家庭内容。
