# ADR-0121：Engagement Context Snapshot 作用域复核

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/production_engagement_wiring.py`

## 决策

生产 Engagement Draft 在把 `context_snapshot_ref` 交给 Model Gateway 前，
可以通过显式注入的 `AsyncContextBrokerPort` 读取并复核快照。复核使用从
`ExperienceScope` 投影出的 `ContextScope`，因此 tenant、family、subject、purpose、
consent、locale、deletion 与 correlation 边界由 Context Engine 再次执行，而不是
信任部署层返回的字符串引用。

HTTP 组合根支持 `context_broker` 或 `context_broker_factory` 二选一；未提供时保留
既有 resolver 兼容路径，便于 dev/test 使用合成上下文。staging/production 应显式
提供 durable `SqlContextBrokerFactory`，Context Broker 读取失败即在 provider 外呼前
终止请求。

## 取舍

- 优点：阻断跨家庭、过期或撤销同意的快照引用进入成就候选生成；Engagement 与
  Multimodal Draft 共享同一 Context Engine 作用域语义。
- 限制：一次请求增加一次 Context Broker 读取；Context 快照与 Engagement outbox
  仍由上层 UnitOfWork 编排，不宣称跨存储原子事务。

