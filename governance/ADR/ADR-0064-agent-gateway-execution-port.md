# ADR-0064：Agent Runtime 通过 ModelGatewayExecutionPort 调用模型

## 状态

Accepted — 2026-08-30

## 背景

`AgentExecutionPort` 对 Agent Runtime 隐藏供应商细节，但此前只有测试桩实现，Agent 组合根无法明确表达“选择哪个已准入模型”。若让 Agent Runtime 自己读取 provider 或 SDK，会破坏 R7/R10 的单一网关边界。

## 决策

新增 `ModelGatewayExecutionPort`：由组合根显式注入一个 `ModelGateway` 和一个已 wiring 的 `provider_id`，实现 `AgentExecutionPort.generate_structured()`。适配器不复制准入、Safety、超时或 provenance 逻辑，而是把请求原样转交给 Gateway。

provider 选择仍属于组合根/路由层，不能由 `AgentTask` 或用户请求覆盖；未 wiring 的 provider 在启动时拒绝。这样 Agent 调用链固定为：

```text
AgentAuthorization → Prompt/Schema Registry → ModelGatewayExecutionPort
  → ModelGateway/Safety → DRAFT → Human Gate
```

## 验证

- `tests/intelligence/agent_runtime/test_gateway_port.py`
- `uv run pytest tests/intelligence/agent_runtime tests/intelligence/model_gateway -q`

## 未解决事项

生产组合根仍需将真实身份/同意、持久化 Attempt/Trace、发布的 provider registry 与该适配器绑定；本 ADR 不放宽任何供应商准入条件。

