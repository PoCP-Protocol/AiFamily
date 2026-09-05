---
id: PLT-PERSISTENCE-001
title: 平台内核规格 — Persistence
type: platform
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# Persistence — UnitOfWork / session

**代码**：`backend/platform/persistence/unit_of_work.py`（110 行）、`backend/platform/persistence/session.py`（135 行）
**测试**：`tests/platform/persistence/test_unit_of_work.py`（4 个测试）
**Registry**：`governance/CAPABILITY_REGISTRY.yaml` → capability `unit_of_work_transaction`（`status: IMPLEMENTED_TESTED`）
**唯一真实生产调用点**：`backend/apps/family_api/routes.py:29`（`/ready` 端点调 `ping()`）

> **并发注意**：`session.py` 在 2026-08-29 被 T-03（Alembic + Postgres 支持）改动过，本文件记录的是**当日改动落地后**的磁盘状态。`unit_of_work.py` 当日未被改动。若 T-03 继续演进，本文件需同步。

---

## 1. 实际提供什么

四个导出符号：`UnitOfWork` / `SqlAlchemyUnitOfWork` / `get_engine` / `get_sessionmaker`。

### 1.1 `UnitOfWork`（ABC，async context manager）

```python
async with uow:
    await repo_a.add(x)
    await repo_b.add(y)
    await uow.commit()
# 若 commit() 未被调用，__aexit__ 自动 rollback
```

- `__aenter__` 把 `committed` 置 `False` 并返回 self。
- `__aexit__` 检查 `committed`；为 `False` 则 `await self.rollback()`。
- 三个抽象方法：`commit()` / `rollback()` / `ping()`。

`ping()` 的存在理由写在 `unit_of_work.py:61-65`：让 `/ready` 反映真实数据库可达性，而不只是进程存活。

**设计出发点**（`unit_of_work.py:3-12`）：源仓库从未有过正式的 UnitOfWork，最接近的东西是 `membership/infrastructure/sqlalchemy_repository.py` 里一个私有于单个域的手搓 `commit()`/`_stage()` 约定。manifest 的 `platform_persistence_uow` 条目 disposition 是 REIMPLEMENT，本模块是从零设计。目的之一是**让审计写入与域写入能共享同一个事务边界**（R6 的前置条件）—— 注意这个目的目前尚未被兑现，见 §3 缺口 1。

### 1.2 `SqlAlchemyUnitOfWork`

一个实例在 `async with` 块的生命周期内**恰好持有一个 `AsyncSession`**。块内构造的 repository 必须被传入 `self.session` 才能参与同一事务（`unit_of_work.py:72-76`）。

- `__aenter__`：从 `session_factory` 建 session。
- `__aexit__`：先走父类（必要时 rollback），再 `close()` session 并置 `None`。
- `commit()` / `rollback()` / `ping()`：各自经私有 `_require_session(operation)`，session 为 `None` 时 `raise UnitOfWorkStateError`（T-14 改：原为 `assert`）。
- `ping()` 执行 `SELECT 1` 并断言结果为 `1`。

构造函数接受可选 `session_factory`；不传则用 `get_sessionmaker()`。

### 1.3 `session.py` —— 两个环境变量，两件不同的事

| 变量 | 作用 | 未设置时 |
|---|---|---|
| `DATABASE_URL` | 本进程真正服务的数据库 | 退回 `sqlite+aiosqlite:///:memory:` |
| `AIFAMILY_TEST_DATABASE_URL` | **仅测试用**的一次性 Postgres | Postgres 门控测试**跳过**，绝不静默回落 SQLite |

三个解析函数：
- `resolve_database_url()` —— 读 `DATABASE_URL`，缺省返回内存 SQLite。
- `resolve_test_database_url()` —— 读 `AIFAMILY_TEST_DATABASE_URL`，未设置返回 `None`；并把裸 `postgresql://` / `postgres://` 规范化为 `postgresql+asyncpg://`。
- `is_postgres_url(url)`。

`get_engine(url=None)` 用一个手写 LRU（`OrderedDict` + `ENGINE_CACHE_SIZE = 8`）缓存 engine，**被逐出的 engine 会被 `dispose()`**（T-14 改：原为 `@lru_cache(maxsize=8)`，逐出即丢弃）。另导出 `clear_engine_cache()` 供测试重置。按 URL 分三档配置：
- **SQLite**：`StaticPool` + `check_same_thread=False` —— 否则每条连接各拿一个私有 `:memory:` 库（`session.py:91-93`）。
- **Postgres**：`pool_pre_ping=True` + `connect_args={"statement_cache_size": 0}`。理由写在 `session.py:102-112`：asyncpg 按 SQL 文本缓存 prepared statement；在 PgBouncer 之类的 transaction-mode 连接池后面，缓存的 statement 属于事务结束后客户端已不再拥有的服务端连接，表现为间歇性 `InvalidSQLStatementNameError`。禁用缓存是官方推荐的 pooler-safe 做法，代价是每次执行重新解析。`pool_pre_ping` 处理另一半问题：空闲期间被服务端或中间件关掉的连接，否则会让下一个请求的第一条查询失败。
- **其它**：裸 `create_async_engine(url)`。

`get_sessionmaker(url=None)` → `async_sessionmaker(bind=engine, expire_on_commit=False)`。

### 1.4 相邻但不属本模块：Alembic（T-03 产出）

`database/migrations/`（`env.py` + `versions/0001_legacy_schema_baseline.py`）与 `database/baseline/*.sql`。`env.py` 复用本模块的 `resolve_database_url()`，因此 `alembic upgrade head` 与运行中的 app **不可能指向不同数据库**，且 alembic.ini 里不含 URL、无凭据入版本库（R12）。`target_metadata` 故意为 `None` —— `--autogenerate` 不可用，因为 baseline 是对旧系统手写 SQL 的忠实复刻，没有 SQLAlchemy metadata 描述那 151 张表。

## 2. 实际约束

1. **不 commit 就 rollback**。三个测试锁定：显式 commit 后两个 repository 的写入都在（`test_commit_persists_writes_from_both_repositories`）；不 commit 则两者都回滚（`test_no_commit_rolls_back_both_repositories`）；块内抛异常则两者都回滚（`test_exception_before_commit_rolls_back_both_repositories`）。**"两个 repository"是刻意的** —— 单 repository 测不出 UoW 的全部价值（要么全提交要么全回滚）。
2. **块外使用即 `UnitOfWorkStateError`**（`RuntimeError` 子类）。`commit` / `rollback` / `ping` 三处共用 `_require_session`，且**在 `python -O` 下依然生效** —— `tests/platform/persistence/test_uow_state_guard.py::test_guards_still_fire_under_python_dash_oh` 起一个 `python -O` 子进程验证这一点（子进程先执行一句 `assert False`：`-O` 下该句被剥掉，能走到后面本身就是 `-O` 确实生效的证据）。
3. **无外部服务也能跑全绿**。默认内存 SQLite 是**刻意且承重的设计**（`session.py:9-10` 用词是 "deliberate and load-bearing, not a stopgap"），不是权宜。
4. **测试库与运行库严格分离**。`AIFAMILY_TEST_DATABASE_URL` 与 `DATABASE_URL` 分开的理由写在 `session.py:19-21`：Postgres 门控测试会创建和删除 schema 对象，把它指向开发者恰好设在 `DATABASE_URL` 里的库"就是开发库被搞死的方式"。
5. **R7 / R12 天然满足**：模块只 import `os` / `functools` / `sqlalchemy`，不碰模型供应商，不硬编码物理路径。

## 3. 已知缺口

按严重度：

1. **审计与域写入共享事务的能力尚未兑现。** `unit_of_work.py:10-12` 声明这是本模块的设计目的之一，但 `AuditRecorder` 完全不接触 `UnitOfWork`（见 `AUDIT.md` 缺口 3）。这是 R6 目前不成立的直接原因之一。
2. **无租户隔离。** `SqlAlchemyUnitOfWork` 不接受 `ActorContext` / `TenantContext`，不注入任何 tenant filter，也没有 Postgres RLS。多租户隔离**完全依赖 domain 层在每条查询里手写 `where tenant_id = ...`**，而这一点没有任何测试或架构检查器覆盖。一个漏写的 filter 就是跨租户数据泄露，且不会有任何东西报警。
   **T-14 明确判定此项超出该任务范围，未修，未假装修。** 理由：真正的修法（Postgres RLS + 每事务 `SET LOCAL app.tenant_id` + 151 张基线表的 `tenant_id` 列约定 + 逐条既有仓储查询审计 + Alembic 策略 DDL）横跨 persistence、全部业务域与迁移基线，且必然改动业务域查询语义 —— 而 T-14 的约束之一是不得改业务域语义。
   **建议单独立项**（暂名 TENANCY-RLS-001），最小范围建议：(a) 先写 ADR 定"tenant_id 列约定 + 哪些表属于非租户维度（如 `product_intelligence` 全域 0 处 tenant_id）"；(b) `UnitOfWork` 增加可选 `TenantContext`，进入块时对 Postgres 发 `SET LOCAL`；(c) Alembic 增量迁移逐表加 RLS policy；(d) 加架构检查器扫描仓储层 `select(` 是否带 tenant 谓词，配 ADR 批准的豁免名单。注意 (d) 单独做会在 `assessment`（并发任务在改）与 `product_intelligence`（本就非租户维度）上产生误报，故必须先有 (a)。
   另注意：T-14 修好的 `PolicyEngine` 租户门是**授权门**（暂停的租户不能操作），不是数据隔离（查询只能看到本租户行）。两者不可互替。
3. **`ping()` 只在 `/ready` 里被用；`commit`/`rollback` 无生产调用方。** 也就是说事务能力本身**尚未承载任何真实业务写入**。`IMPLEMENTED_TESTED` 而非 `PRODUCTION` 的含义就在这里。
4. ~~**`get_engine` 的 `lru_cache(maxsize=8)` 有隐患。** 超过 8 个不同 URL 后旧 engine 被 LRU 逐出而**不会被 `dispose()`**，连接池泄漏；且缓存无法清空。~~ **已修（T-14）**：改为手写 `OrderedDict` LRU，逐出时调 `engine.sync_engine.dispose()`（同步方法，因为逐出发生在同步访问器里、可能身处运行中的事件循环，`await` 不可用），并导出 `clear_engine_cache()`。测试：`tests/platform/persistence/test_engine_cache.py`（以 `engine.pool` 对象身份被替换作为 dispose 确实执行的可观测证据，并另测 LRU 顺序未被改坏、缓存仍是缓存而非工厂）。
   **这个泄漏是本目录测试夹具本来就能触发的** —— `test_unit_of_work.py` 的 fixture 每个测试生成一个唯一 URL。
5. **`UnitOfWork` 无嵌套/savepoint 语义。** 嵌套 `async with` 同一实例会让内层 `__aenter__` 把 `committed` 重置为 `False` 并**覆盖 `self.session`**（旧 session 泄漏，永不 close）。没有 savepoint、没有嵌套检测、没有测试覆盖此场景。
6. ~~**`assert` 而非 `raise`。** `python -O` 下三处保护全部失效，`self.session` 为 `None` 时会退化成 `AttributeError`。~~ **已修（T-14）**：三处收敛到 `_require_session`，抛 `UnitOfWorkStateError`。`-O` 子进程测试验证退化确已消失（还原成 `assert` 时该测试报出 `GUARD_STRIPPED:commit:'NoneType' object has no attribute 'commit'`，正是本条描述的退化）。
7. **无 repository 基类或注册机制。** "把 `self.session` 传给 repository"是纯文档约定（`unit_of_work.py:72-76`），没有 `Repository` 抽象、没有 `uow.repositories` 注册表。忘了传 session 的 repository 会自己开一个新 session，从而**静默地不参与事务** —— 这正是 UoW 要防的事，而它防不住。
8. **`expire_on_commit=False` 的含义未在任何文档记录其取舍。** 它让 commit 后对象仍可读（避免意外的懒加载查询），代价是对象可能与库中最新状态不一致。这是个合理选择，但没有写下理由，未来读者容易"修正"回去。
9. **Postgres 路径的测试是门控的**，`AIFAMILY_TEST_DATABASE_URL` 未设时全部跳过。也就是说 CI 默认绿灯**不证明 Postgres 路径正确**（`session.py:16-18` 对此是诚实的：跳过永不意味着回落 SQLite，但也确实意味着没被验证）。
