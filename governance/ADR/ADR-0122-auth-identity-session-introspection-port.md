# ADR-0122：auth_identity 会话 introspection 端口

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/platform/identity/session_port.py`、
  `backend/apps/family_api/trusted_experience_scope.py`

## 决策

身份会话端口除签发、轮换、撤销外，增加 `introspect(access_token)` 操作。该操作
只返回 `session_id/account_id/family_id/expires_at` 元数据，不返回或持久化明文
access token。`HttpIdentitySessionPort` 通过独立的 auth_identity endpoint 调用，
沿用 bootstrap credential、audience、mTLS、超时和 fail-closed 错误边界。

`HttpIdentityPrincipalResolver` 将 introspection 结果转换为 Family API 的
`AuthenticatedPrincipal`，并在进入 tenant/family/subject/consent 组合前再次校验
family 绑定与过期时间。`SqlAlchemyAuthenticatedContextScopeResolver` 与
`SqlAlchemyAuthenticatedEngagementScopeResolver` 提供 request principal factory seam，
生产 wiring 可把该 HTTP resolver 注入现有 SQL tenant/consent 组合；dev/test 继续使用
现有合成或 SQL fixture，不改变 API 契约和功能 parity。辅助工厂
`build_http_identity_principal_resolver_factory` 固定 request header 到 principal
resolver 的绑定方式，避免部署代码重复实现 token 解析。

## 取舍

- 优点：真实 auth_identity 会话不再要求 AI 服务复制或同步 token 表；撤销和过期由
  身份服务实时裁决。
- 限制：每个请求增加一次身份服务网络调用，需要部署侧连接池、超时、熔断和审计指标。
- 安全边界：introspection 响应只允许 opaque identity metadata，token 不进入 JSON
  body、日志或异常消息。
