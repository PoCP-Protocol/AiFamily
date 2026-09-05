# ADR-0067：Agent Runtime 使用服务端 ContextScope 绑定

## 状态

Accepted — 2026-08-30

## 背景

TrustedTenantScope/Consent/ContextBroker 已分别拥有身份、同意和删除状态边界。Agent Runtime 若直接接收 HTTP 的 tenant/family/data class，会重新制造一套容易漂移的授权逻辑。

## 决策

新增 `ContextBoundAgentRuntime`，只接受组合根解析出的 `ContextScope`，并在任何 AgentRun/Model Gateway 调用前验证：

- scope 仍处于 ACTIVE 且 consent 已授予；
- `AgentTask.tenant_id/family_id` 与 scope 完全一致；
- task data class 与 scope data class 一致。

验证失败直接拒绝，不创建 durable run、不触达模型。身份解析、ConsentGrant 查询和 subject 级授权继续由应用组合根负责；该适配器不缓存、不过度推断，也不写业务事实。

## 验证

- `tests/intelligence/agent_runtime/test_durable_runtime.py`
- `uv run pytest tests/intelligence/agent_runtime -q`

