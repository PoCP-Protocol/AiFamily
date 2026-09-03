# ADR-0076: Accepted Named Action dispatch boundary

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/intelligence/tool_runtime/accepted_dispatch.py`

## 决策

Human Gate 接受后产生的 `NamedActionRequest` 只能通过 `AcceptedNamedActionDispatcher` 进入业务域。Dispatcher 要求 action name 已由组合根显式注册，并校验 tenant/family scope；未注册或跨作用域请求 fail-closed。业务 handler 负责自身授权、事务、审计和领域幂等，返回绑定 `request_id/action_name` 的 `ActionExecutionReceipt`。

同一 request 重放直接返回首次 receipt，不重复调用 handler；这只保证运行时分发幂等，不能替代业务域的持久化幂等。AI Runtime、Tool Runtime 和 Human Gate 均不直接 import 业务仓储。

## 取舍与后续

本轮提供通用端口，不伪造 Blueprint 的服务交付实现。下一步由 `service`/`journey` 等域注册真实 Named Action handler，并把 dispatcher 放入 workflow worker 的事务组合根。
