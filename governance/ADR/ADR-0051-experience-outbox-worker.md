---
id: ADR-0051
title: Experience Outbox 使用 provider-neutral Worker 与可替换死信 Sink
status: Accepted
date: 2026-08-30
owner: chief-architect
---

# ADR-0051：Experience Outbox 使用 provider-neutral Worker 与可替换死信 Sink

## 背景

体验事件已由 `SqlAlchemyExperienceOutbox` 以不透明 JSON envelope 持久化，但仅有
append/pending/mark_published 还不能形成可重启的交付闭环。把投影、模型供应商或业务
事实写入逻辑塞进 outbox adapter 会破坏 R7/R9 边界，也会使测试环境和生产环境走不同
路径。

## 决策

1. `ExperienceOutboxWorker` 只依赖 `ExperienceOutboxStore`、
   `ExperienceOutboxConsumer` 与 `ExperienceDeadLetterSink` 三个
   provider-neutral port。默认的 `SqlAlchemyExperienceOutbox` 实现
   `ExperienceOutboxStore`；consumer 接收
   `StoredExperienceMessage`，不得从 Worker 直接调用模型 SDK、业务 repository 或写
   Family/Journey/Commerce 事实。
2. Worker 每次有界拉取 pending；只有 consumer 成功后才调用
   `SqlAlchemyExperienceOutbox.mark_published`。该调用是幂等的，且事务始终由组合根/调用
   方持有，Worker 不提交或关闭 `AsyncSession`。
3. consumer 失败默认保留 pending，直到 `max_attempts`；达到上限或抛出
   `PermanentExperienceDeliveryError` 时，先写入死信 Sink，再标记 outbox terminal。
   Sink 或 mark 失败时仍保留 pending，避免消息丢失。死信 Sink 必须按 `message_id`
   幂等；consumer 也必须按 `message_id` 幂等，因为 consume 成功与 mark 之间可能崩溃。
4. 本轮 Worker 的 attempt counter 是进程内策略；真正的耐久性来自 outbox 的 pending
   状态和可替换的 durable dead-letter sink。默认 `InMemoryExperienceDeadLetterSink`
   仅用于 dev/test，不能作为生产准入证据。
5. `ExperienceAchievementConsumer` 是第一个具体 consumer：仅接受
   `experience.<ExperienceEventType>` envelope，完整重建并校验 scope/provenance/
   idempotency 后调用 `AchievementEngine`。无法解析、scope 不一致、非事件类型或
   含未支持嵌套引用的 envelope 视为永久错误并进入 DLQ；生成的 Achievement 保留原
   event evidence/provenance，不写领域事实。

## 后果与未完成项

- 提供了可重启的至少一次交付语义、失败重试和死信边界，而不引入第二个业务后端。
- `published_at` 表示消息已由 consumer 或死信 Sink terminally acknowledged；真实生产
  仍需实现带租约/attempt 持久化的 Worker 调度器与 durable DLQ，并在 PostgreSQL 上做并发
  抢占验收。
- Worker 本身不把 AI 草稿变成事实；Human Gate/Named Action 仍是唯一业务变更闸门。

## 验收证据

- `backend/intelligence/experience/outbox_worker.py`
- `backend/intelligence/experience/achievement_consumer.py`
- `backend/intelligence/experience/persistence.py`
- `tests/intelligence/experience/test_outbox_worker.py`
- `tests/intelligence/experience/test_achievement_consumer.py`
