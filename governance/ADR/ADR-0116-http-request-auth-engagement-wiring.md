# ADR-0116：HTTP Request Auth Engagement Wiring

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/production_engagement_wiring.py`、`backend/apps/family_api/main.py`

## 决策

新增 `install_sql_engagement_runtime_wiring`，并通过 `create_app` 的显式
`engagement_runtime_wiring` hook 在 `family_api` 组合根注册请求级
依赖：从 Authorization、`X-Correlation-ID` 和 `X-Causation-ID` 读取传输元数据，
按请求创建 `SqlAlchemyAuthenticatedEngagementScopeResolver`，再组装
`ProductionEngagementRuntimeResolver`。身份和 consent 不放入全局缓存，route body
不能覆盖这些值。

## 边界

- 安装器只接受显式 `AsyncEngine`、`async_sessionmaker`、Model Gateway 和 durable
  sink factories；配置不完整时构造期拒绝。
- Bearer token 仅在 identity adapter 中哈希查询，跨家庭/失效会话统一 403；未安装
  该生产 wiring 时路由仍保持 503 fail-closed。
- staging/production 共用同一 runtime；dev/test 继续使用明确隔离的 synthetic
  wiring，不得把 synthetic provider 注入此安装器。
- 主入口的真实部署调用、PostgreSQL 权限、token 签发/轮换和并发验收仍属于部署
  owner 的上线门禁。
