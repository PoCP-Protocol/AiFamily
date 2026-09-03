# ADR-0066：Agent Runtime durable lifecycle wrapper

## 状态

Accepted — 2026-08-30

## 背景

`AgentRuntime` 已能执行授权、Prompt/Schema 解析和 DRAFT 生成，但若调用方只拿到内存 `AgentRun`，进程崩溃或 HTTP 重试会再次触达模型。AI 体验需要把授权后的执行与 AgentRun/Trace durable store 绑定。

## 决策

新增 `DurableAgentRuntime`，并由 `build_durable_agent_runtime` 组合工厂以
`AgentRunPersistencePort` 包裹现有 `AgentRuntime`：

- 首先以租户+家庭+幂等键建立稳定的 `STARTED` run 和 `run.started` trace；
- 已 `SUCCEEDED` 的记录直接重放 DRAFT，不再次调用模型；
- 已 `FAILED` 或仍 `STARTED` 的相同幂等键 fail-closed，不隐式重复执行（防止并发重复外呼）；
- 成功调用写入 durable DRAFT 和 `run.succeeded`，异常写入 `FAILED` 与错误码；
- wrapper 不提交事务、不执行 Named Action，commit 仍由组合根控制。

## 验证

- `tests/intelligence/agent_runtime/test_durable_runtime.py`
- `uv run pytest tests/intelligence/agent_runtime -q`

## 未解决事项

真实身份/同意、Agent 生产 registry 签名、持久化 Attempt/Cost sink 和 Human Gate/领域二次授权 consumer 仍需在生产组合根接线。
