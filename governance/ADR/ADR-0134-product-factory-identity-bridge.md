# ADR-0134: Product Factory trusted identity bridge

- Status: Accepted
- Date: 2026-08-31
- Scope: Family API / Product Intelligence

## Decision

Product Factory 的 HTTP 身份由应用层适配器负责：先从 Authorization Bearer
取得不透明 token，调用 `IdentitySessionPort.introspect()` 验证会话，再调用应用
注入的租户范围解析器，最后生成领域 `ActorContext`。领域依赖不解析 token、不过
信请求体，也不把 family/account 字段直接当作租户证明。

适配器只接受未过期的已验证会话；token 缺失、身份服务异常、租户解析失败或返回
非法范围时统一拒绝。未安装 resolver 时 `get_actor_context` 继续 fail-closed。

## Consequences

- 主应用可以在不修改 Product Intelligence 领域的情况下接入真实 auth_identity。
- 租户/家庭绑定逻辑必须由应用提供，并可单独审计和测试。
- 当前适配器不推断 AI 身份；AI 草案应通过受控的内部执行上下文注入，不能伪装成
  Web Bearer 用户。
