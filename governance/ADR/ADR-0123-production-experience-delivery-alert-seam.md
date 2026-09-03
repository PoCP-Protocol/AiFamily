# ADR-0123：生产 Experience Outbox 告警 seam

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/production_experience_outbox_wiring.py`

## 决策

`ProductionExperienceOutboxRuntime` 增加可选的 provider-neutral `alert_sink`。
每次有重试或死信结果时，运行时在数据库事务提交完成后将
`OutboxWorkerReport` 交给该 sink；没有失败结果时不产生告警。告警 sink 只接收
消息 ID、状态、尝试次数和脱敏错误摘要等 worker report 元数据，不接收原始事件
payload，也不负责发送家庭通知或执行领域命令。

Outbox acknowledgement、Achievement projection 和 dead-letter 写入仍由原有事务
边界负责。告警传输失败不得回滚已经提交的投影或 outbox 状态；调度平台可以按
`run_once`/`run_until_idle` 周期触发，并将 sink 接到内部 metrics、日志或 paging
系统。staging 与 production 使用同一运行时和失败语义，只有基础设施 adapter 由
组合根注入。

## 取舍

- 优点：生产具备可观测的 retry/DLQ 告警端口，且告警故障不会造成消息重复或事务
  回滚；测试可以使用内存/断言 sink 验证同构行为。
- 限制：告警是 best-effort 的外部副作用，部署平台仍需提供持久化 metrics、告警
  去重、升级策略和 scheduler。
- 安全边界：不发送家庭内容、不暴露模型输出、不绕过 Human Gate，也不把告警 sink
  当作通知供应商调用入口。
