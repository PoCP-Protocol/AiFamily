# ADR-0078: Accepted Named Action durable delivery worker

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/intelligence/tool_runtime/accepted_delivery.py`、
  `backend/intelligence/tool_runtime/accepted_worker.py`

## 决策

Human Gate 接受后的 `NamedActionRequest` 使用独立的
`ai_accepted_action_deliveries` metadata-only ledger 记录 attempts、状态、错误
和不透明 result ref。`AcceptedNamedActionWorker` 的顺序固定为：

1. 读取已接受 HumanTask；
2. 获取 Human Gate durable claim lease；
3. 递增 durable attempt；
4. 通过显式注册的 `AcceptedNamedActionDispatcher` 调用业务域 handler；
5. 成功写入 receipt 后清理 claim。

未注册动作、scope 不匹配等 dispatcher 错误直接进入 `DEAD_LETTERED`；其他错误在
达到 `max_attempts` 前保留 lease 等待接管。Worker 不保存 action arguments、原始媒体
或模型输出，不调用供应商，也不替业务域提交事务。

## 崩溃与幂等

业务域可能已经提交而 worker 尚未写 receipt；重启后同一 request_id 会再次调用
handler，领域自己的持久化幂等保证不产生第二个事实。receipt 已存在时 worker 只
完成 claim，不重复调用 handler。DLQ 状态是终态，重复投递只返回原终态。

## 取舍与缺口

本轮提供 one-shot worker seam、bounded `run_once` queue poll、`run_until_idle`
调度器和 SQL migration 0024；跨进程 lease takeover 压测、运维告警和生产 DLQ 查询
仍由部署组合根负责。
Blueprint 推荐动作仍不能通过
本 worker 直接执行，必须先有业务域 Named Action handler。
