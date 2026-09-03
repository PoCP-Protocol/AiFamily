# ADR-0115：SQLAlchemy Request Auth Composition

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/trusted_experience_scope.py`、`backend/platform/identity/trusted_context.py`

## 决策

新增 `SqlAlchemyBearerPrincipalResolver`，只接收请求 Authorization header 和
URL family，使用 token 的 SHA-256 摘要查询 `identity_sessions`，并校验会话未撤回、
未过期、账号有效且 family 一致。明文 token 不进入 SQL、scope、日志或 AI payload。

新增 `SqlAlchemyTrustedTenantScopeStoreFactory`，为每次 Account → Tenant → Family
链路查询打开短生命周期 SQL session，再复用既有 `SqlAlchemyTrustedTenantScopeStore`
和 `TrustedTenantScopeResolver` 的 fail-closed 语义。

`SqlAlchemyAuthenticatedEngagementScopeResolver` 将 bearer principal、trusted
scope、家庭主体、consent snapshot 和 Engagement scope 组合为一个部署可注入的
resolver；业务路由仍只依赖抽象 resolver，不解析凭据或直接访问数据库。

## 安全与边界

- 缺失/格式错误 bearer、未知/重复会话、跨家庭、撤回或过期会话统一拒绝。
- 每次 scope resolve 都重新读取 identity、租户和 consent，禁止静态缓存授权。
- 真实数据库权限、request-auth middleware、token 签发/轮换、PostgreSQL 并发与
  删除演练仍需部署验收；测试使用 SQLite 合约表只验证 SQL 组合语义。
