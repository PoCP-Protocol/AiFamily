# ADR-0119：多模态 Draft HTTP 请求认证组合

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/apps/family_api/production_experience_wiring.py`、
  `backend/apps/family_api/main.py`

## 决策

多模态 Draft 路由通过 `install_sql_experience_runtime_wiring` 接收请求级
Authorization、Correlation 和 Causation 头，并为每次请求构造
`SqlAlchemyAuthenticatedContextScopeResolver`。该 resolver 复用 bearer session、
trusted tenant/family binding、subject membership 与 consent 快照，再注入
`ProductionExperienceRuntimeResolver`。

## 边界

- `create_app()` 暴露显式 `experience_runtime_wiring` hook；resolver 与 wiring
  互斥，未安装时路由仍稳定返回 503。
- staging/production 使用 SQL durable ContextBroker、Attempt/Safety/Telemetry
  sinks、Prompt/Schema/Model Gateway 和相同状态机；dev/test 仅替换 synthetic
  scope/provider，不改变 API 或人工闸门。
- 身份、consent、模型凭据不进入请求 body；token 不缓存、不记录，跨家庭或失效会话
  在 scope resolver 处 fail-closed。
