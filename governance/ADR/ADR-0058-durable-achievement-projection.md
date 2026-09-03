---
id: ADR-0058
title: Durable evidence-bound achievement projection
status: Accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0058：成就投影持久化与重启幂等

## 背景

体验 Outbox 已能将 `ExperienceEvent` 至少一次投递给
`ExperienceAchievementConsumer`，但成就仍只在进程内保存。进程重启或多实例
消费会丢失回读结果，无法满足测试环境与生产环境功能 parity，也无法证明证据链
可恢复。

## 决策

1. 定义 provider-neutral `AchievementProjectionPort`。`AchievementEngine` 保留
   同步 `apply` 兼容既有 InMemory 测试，并提供 `apply_async` 组合路径；consumer
   统一调用异步路径，因此 SQL 与 InMemory 适配器共享同一成就规则。
2. 新增 `SqlAlchemyAchievementProjection` 与 `ai_achievement_projections` 表。
   以规范化 scope fingerprint + `achievement_key` 为唯一身份；重复写入只返回
   首次持久化的记录，稳定证据/文案/来源不一致则 fail-closed。
3. 表中保留完整 scope payload、`evidence_refs`、provenance payload、原始
   `earned_at` 与租户幂等键，支持删除定位和重启后按 scope/key 回读。该投影不
   计算或存储家庭总分、排名、连胜或奖励余额。
4. SQL adapter 只 `add`/`flush`，不 commit/rollback，不调用模型供应商，也不
   写入 Family/Journey/Service/Commerce canonical 事实；事务由 composition root
   管理。

## 后果与缺口

- Outbox worker 在 projection 成功后才确认消息，崩溃重放仍返回同一成就。
- SQLite dev/test 与 PostgreSQL production 使用同一 port、唯一约束和序列化契约。
- 仍需在生产组合根注入 SQL projection、接入 durable worker lease/DLQ，并补充删除
  worker 的实际运行态验收；本 ADR 不授权自动业务变更。

## 验收证据

- `backend/intelligence/experience/achievement.py`
- `backend/intelligence/experience/achievement_persistence.py`
- `backend/intelligence/experience/achievement_consumer.py`
- `database/migrations/versions/0015_ai_achievement_projections.py`
- `tests/intelligence/experience/test_achievement_persistence.py`
