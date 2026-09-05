# ADR-0125：AI runtime 部署侧调度契约

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/production_experience_outbox_wiring.py`、
  `backend/apps/family_api/production_achievement_notification_retention_wiring.py`

## 决策

Experience Outbox 投递与成就通知 retention 均暴露显式 schedule value object，包含
正数 interval、批量上限和（Outbox）最大轮询次数。生产组合根提供
`run_scheduled_tick`，只执行一次有界 tick，立即返回报告；不在 API 进程内启动常驻
线程、asyncio background task 或隐式 sleep。Kubernetes CronJob、队列平台或内部
调度器负责按 interval 触发 tick，并把 worker identity、metrics、paging 和审计
adapter 注入组合根。

staging 与 production 共用 schedule 校验、poll 顺序、lease、retry、dead-letter 和
retention 语义；测试可以直接调用同一 `run_scheduled_tick` 验证上限与重启行为。
调度失败只影响当前 tick，不改变 AI 输出 DRAFT-only、Human Gate 或领域事实写入
边界。

## 取舍

- 优点：调度参数可审计、可测试、可水平扩展，避免每个 API worker 重复消费；有界
  tick 能够在部署平台安全重试。
- 限制：部署平台必须实现实际 recurrence、锁/并发策略、告警升级和运行历史；interval
  本身不是 SLA 保证。
- 安全边界：scheduler 只调用 provider-neutral worker，不发送家庭通知内容，不直接
  调用模型供应商或业务域命令。
