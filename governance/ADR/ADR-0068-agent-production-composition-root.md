# ADR-0068：Agent 生产组合根与身份/同意事务边界

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/production_agent_wiring.py`

## 决策

生产 Agent 必须由 `ProductionAgentRuntimeResolver` 组装。Resolver 只接受服务端
`scope_resolver` 返回的 `ContextScope`，拒绝 synthetic、失效同意、删除中 scope 和
family 不一致的任务；HTTP 请求不得自行提交 tenant/family/data class 作为信任来源。

每次执行在一个请求级 `SqlAlchemyUnitOfWork` 内同时绑定：

1. `ModelGateway.with_attempt_sink(SqlAlchemyAttemptSink(session))`；
2. `SqlAlchemyAgentRunStore(session)` 的 AgentRun/Trace durable store；
3. `ModelGatewayExecutionPort`、治理 AgentDefinition、Prompt/Schema Registry；
4. `ContextBoundAgentRuntime` 的 DRAFT-only、授权租约与 scope 校验。

只有 AgentRun 成功、Model Attempt 结果和 Trace 都写入后才提交事务；异常自动回滚。
供应商、Safety Runtime、provider admission 和 token/cost 记录继续由 Model Gateway
负责，Agent Runtime 不得读取 SDK 或直接写业务事实。

## 结果

- 测试环境可以使用同一组合逻辑和 FakeProvider，只替换显式配置，不删减功能。
- 真实身份/同意、Attempt、Trace 具有同一事务边界，便于回放和删除审计。
- 仍需在部署环境提供真实 `scope_resolver`、授权租约来源、已批准供应商和持久化
  rate card；缺任一项即 fail-closed。
