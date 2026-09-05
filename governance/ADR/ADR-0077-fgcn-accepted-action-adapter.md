# ADR-0077: FGCN accepted Named Action adapter

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/domains/service/fgcn/accepted_action.py`

## 决策

FGCN 作为首个业务域，为 `AcceptedNamedActionDispatcher` 注册
`CONFIRM_SERVICE_TASK_ASSIGNMENT`。适配器只绑定已有的
`execute_task_assignment_named_action` 应用命令，并把 `TaskAssignment` 转为
provider-neutral `ActionExecutionReceipt`；领域命令继续负责 Human Gate actor
校验、tenant/family scope、provider admission、审计、事务和持久化幂等。

## 边界

适配器不读取模型凭据、不调用模型、不直接操作 ORM，也不把
`PROPOSE_SERVICE_BLUEPRINT` 推荐当成事实。Blueprint 推荐仍必须经 Human Gate
并由后续业务命令消费。当前 factory 是组合根可复用的显式注册点，尚未替代既有
`consume_accepted_human_task` worker；生产接线仍需在 worker 中注入 durable
dispatcher、租约与 DLQ。

## 结果

这让 AI → Human Gate → Named Action → FGCN assignment 的第一条真实业务链可以
以统一 dispatcher 做 contract test，同时保持测试环境与生产命令语义一致。
