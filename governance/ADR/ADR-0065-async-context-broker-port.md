# ADR-0065: Async Context Broker Port

## 状态

Accepted — 2026-08-30

## 背景

多模态体验应用和 Model Gateway 运行在异步请求链路中，而当前 Context
Engine 的确定性适配器是同步内存实现。若应用直接调用同步 broker，后续换成
SQL 或其他持久化实现时会把存储细节泄漏到业务编排层，也可能阻塞 Web 事件循环。

## 决策

建立 `AsyncContextBrokerPort`，将 `append`、`snapshot`、`read` 和
`delete_subject` 作为异步边界。`AsyncContextBrokerAdapter` 仅用于测试和本地
开发，通过线程池桥接现有同步 `ContextBroker`。生产组合根必须注入真正的
durable async 实现，并继续拒绝 `durability_mode=IN_MEMORY`。

## 约束

- scope、consent、TTL、deletion 和 provenance 校验仍由 Context Engine 合约负责；
- async port 不得写入家庭领域事实，也不得绕过 Model Gateway；
- 内存适配器不是生产持久化能力，不能用来满足重启恢复或跨进程一致性；
- durable SQL 实现需在迁移 head 稳定后单独落库并覆盖重启、跨 scope、过期和删除测试。

## 后续

实现 `AsyncSqlContextBroker`，并将多模态 Context-bound application 改为依赖
port，而不是依赖同步 `ContextBroker` 具体类。
