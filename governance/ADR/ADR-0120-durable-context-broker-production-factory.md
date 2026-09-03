# ADR-0120：Durable ContextBroker 生产组合工厂

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/context_engine/sql_store.py`、
  `backend/apps/family_api/production_experience_wiring.py`、
  `database/migrations/versions/0036_ai_context_engine.py`

## 决策

生产 Multimodal Draft 统一通过 `SqlContextBrokerFactory` 创建
`AsyncSqlContextBroker`。Broker 采用 session-per-operation 模式，每次 append、
snapshot、read、delete 都从应用注入的 `async_sessionmaker` 获取短生命周期会话，
避免把 SQLAlchemy session 跨请求或跨任务共享。HTTP 组合根支持显式注入已有
`context_broker`，或注入该 factory；两者同时提供或均缺失都 fail-closed。

Context Engine 的三张技术投影表由 migration `0036_ai_context_engine` 建立，
快照重建继续执行 tenant/family/subject/purpose/consent/TTL 校验。Context Broker
只保存技术上下文投影，不写入家庭领域事实；AI 输出仍保持 DRAFT-only 与人工闸门边界。

Context-bound 多模态服务支持显式注入 timezone-aware clock。生产默认使用 UTC
系统时钟，测试和回放可以固定时间，从而验证 observation/snapshot TTL，而不改变
生产路径的过期语义。

## 取舍

- 优点：生产组合根不再依赖调用方手工 new durable broker；进程重启和多 worker
  可读取同一快照，且会话生命周期清晰。
- 限制：Context Broker 与 Multimodal Draft 的业务写入仍不是跨库事务；需要由更高层
  UnitOfWork 或 outbox 在需要时编排原子业务事件。
- 保留可替换性：未来可将 factory 替换为其他 durable ContextBroker 实现，HTTP 路由和
  多模态应用不感知 SQL 细节。
