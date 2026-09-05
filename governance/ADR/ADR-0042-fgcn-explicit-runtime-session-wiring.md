---
id: ADR-0042
title: FGCN family_api 显式运行时数据库接线
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0042：FGCN `family_api` 显式运行时数据库接线

## 背景

ADR-0041 已将 FGCN Human Gate 控制面挂载到 `family_api`，并要求生产环境
提供真实 session factory。但此前 `configure_session_factory` 没有被组合根
调用：FGCN 的 SQLAlchemy repository 和 Human Gate durable adapter 虽然存在，
运行进程仍无法获得正式数据库 session。

同时，平台 persistence 为本地内核测试保留了 SQLite fallback。若组合根在生产
环境无条件调用 `get_sessionmaker()`，一个缺失 `DATABASE_URL` 的部署就可能把
内存 SQLite 误当成业务数据库，既丢失持久化又掩盖配置错误。

## 决策

1. `family_api` 创建 app 时只读取显式 `DATABASE_URL`；未设置时清除 FGCN
   process-level session wiring，使 FGCN dependency 继续抛出配置错误。
2. 非开发/测试环境只接受 PostgreSQL URL。生产环境传入 SQLite 或其他 URL
   不会获得 session factory，也不会静默回退到默认 SQLite。
3. `postgresql://` 和 `postgres://` 在组合根归一化为项目已安装的
   `postgresql+asyncpg://` 驱动；显式开发/测试 SQLite 仍可用于隔离测试。
4. `clear_session_factory()` 是显式反向护栏。多次创建 app 或切换测试环境时，
   后一个未配置实例不能继承前一个实例的数据库连接。
5. 这只完成 FGCN 的数据库 session 接线，不宣称完成 Account →
   TenantMembership → Family identity、reviewer role、consent store、队列
   lease 或常驻 workflow worker。上述依赖仍 fail-closed。

## 正向与反向询证

正向：显式 `DATABASE_URL=sqlite+aiosqlite:///:memory:` 的测试 app 可以从
FGCN session dependency 获得 SQLAlchemy session；显式 PostgreSQL URL 会经
asyncpg factory 接线，不需要在 app import 时建立数据库连接。

反向：生产未设置 `DATABASE_URL`、或设置为 SQLite 时，FGCN session dependency
均拒绝服务；在先创建过已接线 app 后重新创建未配置的生产 app，也不会继承旧
factory。已有 API 身份、reviewer 和 worker 依赖仍分别拒绝未配置调用者。

## Enforcement

- `backend/apps/family_api/main.py`
- `backend/domains/service/fgcn/api/dependencies.py`
- `tests/apps/family_api/test_fgcn_routes.py`
- `governance/ADR/ADR-0041-fgcn-human-gate-family-api-control-plane.md`
