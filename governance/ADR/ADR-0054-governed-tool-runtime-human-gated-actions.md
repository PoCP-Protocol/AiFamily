---
id: ADR-0054
title: Tool Runtime 仅生成经 AgentAuthorization 校验的待人工确认 Named Action
status: Accepted
date: 2026-08-30
---

# ADR-0054：Tool Runtime 仅生成经 AgentAuthorization 校验的待人工确认 Named Action

## 背景

Agent Runtime 已能通过静态 AgentDefinition 和动态 AgentAuthorization 生成
`DRAFT`，但工具调用若直接返回任意字典，容易绕过工具白名单、家庭范围和人工闸门，
甚至被误当作业务事实。平台需要一个可组合、可替换 provider 的工具边界。

## 决策

1. `backend/intelligence/tool_runtime` 定义不可变 `ToolDefinition`、短期
   `ToolAuthorization`、`ToolCallRequest` 和 `ToolCallResult`。ToolDefinition
   必须声明显式大写 Named Action（拒绝 `UPDATE/PATCH/DELETE/WRITE/SET` 等泛化动作）。
2. `ToolRuntime` 在执行前同时校验真实 `AgentDefinition`、`AgentAuthorization`
   和 `ToolAuthorization`，复用 `AgentAuthorizer` 的租户/家庭范围、用例、工具白名单、
   TTL/撤回和预算规则；缺少任一边界即 fail-closed，且不会调用工具适配器。
3. 注入的 `ToolExecutionPort` 只能准备 Named Action 参数。运行时唯一成功结果是
   `PENDING_HUMAN_CONFIRMATION` 的 `ToolCallResult`，带有 `GateScope`、来源引用、
   风险级别和过期时间；`may_mutate_business_state` 固定为 `False`。
4. Tool Runtime 不导入业务域 repository，不调用模型供应商 SDK，也不执行
   `NamedActionRequest`。Human Gate 必须把 pending candidate 转为人工可审阅的
   proposal；业务域随后自行授权、审计、幂等并执行 Named Action。

## 后果

- 工具能力可在 dev/test/prod 使用同一套权限和人工确认语义，测试环境仅替换执行适配器。
- 非法工具调用在 provider/domain 副作用前被拒绝，结果可审计并携带精确家庭主体范围。
- 当前实现是进程内组合 seam；尚未提供工具目录持久化、租约存储或 durable queue，
  这些生产接线必须在后续迭代中补齐。

## 约束依据

- `governance/REPOSITORY_CONSTITUTION.md` R7、R8、R9、R10
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.5、§4
- `governance/ADR/ADR-0048-agent-runtime-authorization.md`
