# `database/` — schema 与迁移

- **状态**: CURRENT
- **上游依据**: `governance/MIGRATION_MANIFEST.yaml` 条目 `database_schema`（`target: [database/migrations, database/baseline]`）、`docs/07_data/DATA_ARCHITECTURE.md`
- **产出任务**: `docs/11_delivery/TASK_BACKLOG.md` T-03

## 目录职责

| 路径 | 是什么 | 可以改吗 |
|---|---|---|
| `baseline/*.sql` | 源仓库 62 个手写 SQL 迁移的线性化副本。**内容逐字节等于源文件**，只重编号 | **不可改**。这是历史制品，`tests/database/test_baseline_linearisation.py` 用 sha256 守着 |
| `migrations/LINEARISATION_MAP.md` | 62 行"原文件名 → 新序号"映射 + 4 组重号的排序理由与实测证据 | 只在重新线性化时改，且须同 PR 改测试里的 `EXPECTED_FILE_COUNT` |
| `migrations/env.py` | Alembic 环境。从 `backend.platform.persistence.session` 取 URL | 可改 |
| `migrations/versions/` | Alembic revision。`0001_legacy_schema_baseline.py` 是 baseline | **不可改已有 revision**，只能新增 |

## 为什么 baseline 是"replay SQL"而不是 `op.create_table`

源系统唯一的 schema 权威是手写 SQL，没有 ORM 模型可以生成。把 151 张表 / 60 个枚举 / 7 个视图 / 373 个索引 / 317 个外键 / 1874 个 CHECK 约束手抄成 `op.*` 调用，每一个抄写错误都会让 baseline 描述一个源系统**从未有过**的 schema，而且抄错了无法验证。逐字节 replay 让"忠实"这件事变成**可校验的**：制品与源文件 sha256 相同，测试守着这一点。

按 `DATA_ARCHITECTURE.md` §5 的要求，baseline **只是快照**，不含任何目标态重设计——§2 的按域分 schema（`identity.*` / `family.*` / `assessment.*` …）与每域独立 DB role 是后续独立 PR，这样 bisect 时"因为重设计而变"和"因为忠实搬运历史而变"永远不会混在一起。

## 常用命令

```bash
# 起一个一次性 Postgres（端口 55442，仅绑 loopback）
docker compose -f docker-compose.dev.yml up -d --wait

# 应用 baseline 到空库
DATABASE_URL=postgresql+asyncpg://aifamily:aifamily@localhost:55442/aifamily_test \
  uv run alembic upgrade head

uv run alembic current    # 应显示 0001_legacy_schema_baseline (head)
uv run alembic history

# 打开真实 Postgres 测试路径（默认 skip，不设就只跑 SQLite 快路径）
export AIFAMILY_TEST_DATABASE_URL=postgresql+asyncpg://aifamily:aifamily@localhost:55442/aifamily_test
uv run pytest -q

# 校验 baseline 未偏离源仓库（需要源仓库可达）
AIFAMILY_LEGACY_MIGRATIONS_DIR=<legacy>/database/migrations \
  uv run pytest tests/database/test_baseline_linearisation.py -v

docker compose -f docker-compose.dev.yml down
```

## 两个环境变量，两件事，别混

| 变量 | 作用 | 未设时 |
|---|---|---|
| `DATABASE_URL` | 这个进程真正服务的库；`alembic upgrade` 读的也是它（同一个真相） | 退回内存 SQLite |
| `AIFAMILY_TEST_DATABASE_URL` | **仅测试用**的一次性 Postgres。相关测试会建/删 schema 对象 | 相关测试 **skip**，绝不退回 SQLite |

分成两个变量是刻意的：真实 Postgres 测试会创建和删除 schema 对象，把它对准开发者恰好放在 `DATABASE_URL` 里的库，就是开发库被清空的经典事故。

`product_intelligence` 早于本约定，自己发明了 `PI_POSTGRES_TEST_DSN`，现作为**已废弃的回退**继续生效（见 `session.py::LEGACY_TEST_DATABASE_URL_ENV_VARS`），新代码只用 `AIFAMILY_TEST_DATABASE_URL`。

## SQLite 快路径为什么必须保留

绝大多数域仓储测试跑在 `sqlite+aiosqlite:///:memory:` 上——没有外部服务、秒级反馈，是**默认**路径，没起 docker 的人也能跑全绿。真实 Postgres 测试是**门控增量**，不是替代品。

同时要如实知道 SQLite 证明不了什么：`membership` / `product_intelligence` 的 SQLAlchemy 模型把 `uuid` 放宽成 `String`、`jsonb` 放宽成 `JSON`，正是为了能在 SQLite 上跑。所以 SQLite 那一轮证明的是**映射本身**成立，而不是它在生产用的数据库上成立。后者由 `AIFAMILY_TEST_DATABASE_URL` 那一轮证明。

## 已知缺口（如实写明）

- 域仓储的 Postgres 测试用 `Base.metadata.create_all` 在一次性 schema 里建表，**不走 baseline**。因此源 SQL 里的 DB 级 CHECK 约束（如 `external_effect = false`、`decided_by NOT LIKE 'ai:%'`）在这两个域仍未被测试覆盖。要覆盖需把模型与 baseline 化的表对齐，那是 T-05 的工作。
- `growth_profiles` 两代列（`subject_type`/`subject_ref_id` 与 `profile_scope`/`subject_person_id`）在 baseline 里原样共存。它们**不是死列**——源仓库运行时同时写两代列，`0048` 迁移还以旧列为读取谓词。详见 `migrations/LINEARISATION_MAP.md` §4，含待裁决项。
