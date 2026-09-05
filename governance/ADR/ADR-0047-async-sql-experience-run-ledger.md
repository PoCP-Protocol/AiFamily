---
id: ADR-0047
title: Async SQL ExperienceRun HTTP ledger adapter
status: accepted
date: 2026-08-30
decision_owner: project-owner
supersedes: null
superseded_by: null
---

# ADR-0047：异步 SQL ExperienceRun HTTP ledger adapter

## 背景

`backend/intelligence/experience/run_http.py` 的第一版
`ExperienceRunLedger` 是同步 Protocol，配套的 `InMemoryExperienceRunLedger`
用于测试和演示。实际 `family_api` 与平台持久化层使用
`AsyncSession`；把异步数据库伪装成同步方法会阻塞事件循环，也无法说明
一次交互由谁提交。进程重启后，决定、反馈、人工请求和删除事件仍需能够按
租户/家庭/主体作用域重放。

## 决策

1. 新增 `SqlAlchemyExperienceRunLedger`，实现独立的
   `AsyncExperienceRunLedger` Protocol。它不是当前同步 HTTP Protocol 的直接
   注入对象；组合根必须 `await` 其调用，或显式安装 async bridge 后再替换内存
   ledger。禁止通过 `asyncio.run`、线程阻塞或“返回 coroutine 但标成同步结果”
   绕过这条边界。
2. 运行状态、事件和 DRAFT checkpoint 继续复用
   `SqlAlchemyExperienceRunStore` 的 `experience_runs`、
   `experience_run_events`、`experience_run_checkpoints`。迁移 `0010` 增加
   `experience_run_interactions` 追加式交互流，并在 run envelope 上记录创建幂等
   指纹、`RESERVED/FINALIZED` 生命周期、删除状态及经过 schema 校验的 HTTP
   response projection。
3. 每一行交互复制完整 `tenant_id + family_id + subject_ids` scope，并以
   `tenant_id/run_id/idempotency_key` 与 `event_sequence` 唯一约束守住重放顺序。
   相同幂等键和相同指纹返回 `replayed`；不同指纹或不同作用域 fail-closed。
4. adapter 只执行 `flush`，不自动提交或关闭传入的 `AsyncSession`。调用方使用
   `ledger.transaction()` 或现有 `SqlAlchemyUnitOfWork`，把 run、interaction、
   audit/outbox 组合到同一显式事务。
5. 删除请求本身保留为 append-only interaction；随后仅擦除派生 checkpoint 的
   draft 内容、artifact references 和运行态的删除标记。这是删除权要求的窄化
   隐私擦除例外，不允许借此更新或删除历史交互来重写审计轨迹。
6. SQL ledger 不导入 Family/Growth/Service/Commerce domain，也不调用 Model
   Gateway。所有输出依旧是 `DRAFT`，`may_mutate_business_state` 始终为 false。

## 后果

### 正面

- 运行重启后可以恢复完整交互顺序，且创建、交互和删除均有数据库唯一约束。
- 显式事务让 Human Gate/outbox/audit 的原子组合成为可能；adapter 可在测试环境
  与 PostgreSQL 生产环境之间替换。
- 删除会清理模型派生物而保留最小审计事件，满足“可追溯”与“可删除”的冲突边界。

### 代价与未决项

- HTTP 路由已通过 ADR-0050 的 awaitable dispatch 兼容同步与异步 ledger；
  `AsyncExperienceRunLedgerBridge` 在检测到生命周期方法时直接委托 durable
  preflight/finalize/release。生产 composition root 仍需显式注入
  AsyncSession/UoW 和本 adapter，不能自动替换 dev/test 的内存实现。
- SQLite 测试验证 ORM/事务/重放语义；本轮已在配置
  `AIFAMILY_TEST_DATABASE_URL` 的本地 PostgreSQL 完成 migration upgrade/downgrade
  round-trip，生产环境仍需按容量执行并发压测。
- 并发冲突的重试策略由后续 worker/HTTP adapter 决定；本实现将数据库唯一冲突
  映射为稳定的 `INTERACTION_APPEND_CONFLICT`，不静默重写事件。

## Enforcement

- `backend/intelligence/experience/sql_run_ledger.py`
- `backend/intelligence/experience/run_store.py`
- `database/migrations/versions/0010_experience_run_interactions.py`
- `tests/intelligence/experience/test_sql_run_ledger.py`
