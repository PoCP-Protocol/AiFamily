---
id: SYS-TECHBASELINE-001
title: AiFamily 当前技术基线
type: system
status: current
version: 2.0
owner: chief-architect
created: 2026-08-29
updated: 2026-09-10
canonical: true
supersedes: null
superseded_by: null
---

# 当前技术架构 (Current Tech Architecture)

- **状态**: 见上方 front matter `status: current` — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-09-10（本次核实基于仓库自带 `.venv`（Python 3.12.10）实跑验证，非静态阅读代码推断）

---

## 0. 范围声明

本文件描述 AiFamily 仓库**当前**（本次核实时点）的技术基线现状，不描述未来 Wave 的目标架构（后者见 `docs/11_delivery/CURRENT_PROGRAM_PLAN.md`）。历史演进（例如"Wave 0 时后端运行时尚不存在"）见文末《History》一节，不与下方当前状态描述混排。

## 1. 语言与依赖工具链

- **语言**：`pyproject.toml` 声明 `requires-python = ">=3.12"`；仓库 `.venv` 实测 Python 3.12.10。
- **依赖管理**：uv + `pyproject.toml`（仓库根），无 pip/poetry/pipenv/requirements.txt 并存。

## 2. 后端运行时：真实存在且已挂载

`pyproject.toml` 的 `[project.dependencies]` 实测声明并锁定：

- `fastapi>=0.115`、`uvicorn[standard]>=0.30`、`pydantic>=2.7`
- `sqlalchemy>=2.0`、`alembic>=1.13`
- `asyncpg>=0.29`（生产 Postgres 驱动）、`aiosqlite>=0.20`（测试用内存库）
- `httpx>=0.27`、`pyyaml>=6.0`
- `opentelemetry-api>=1.27`、`opentelemetry-sdk>=1.27`

实测验证（本次会话）：

- `backend/apps/family_api/main.py` 存在真实 `FastAPI()` 应用；用 `.venv/Scripts/python.exe` 加载该 app 并调用 `app.openapi()['paths']`，**默认环境（无 AIFAMILY_ENV）实测 98 个路径**（`AIFAMILY_ENV=test` 会额外装载 dev/test 专属路由，变成 108 个，见 CURRENT_SYSTEM_BASELINE.md §1.3——两个数字都真实，差异来自环境变量）（在系统解释器 Python 3.11 下会因语法特性 (`type X = (...)`) 报错，必须用仓库自带 `.venv` 3.12 才能正常导入——记录此坑供后续核实者避免误判）。
- `grep -rl "sqlalchemy" backend --include="*.py"` 命中 **166 个文件**（含测试）。
- `database/migrations/versions/` 下 Alembic revision 脚本实测 **79 个 `.py` 文件**。`alembic.ini` 存在于仓库根。
- `grep -rl "opentelemetry" backend --include="*.py"` 命中 **2 个文件**：`backend/intelligence/observability/opentelemetry.py`、`backend/intelligence/observability/__init__.py`——即 OpenTelemetry 目前只接入了 observability 这一处 span sink，尚未验证是否已在其余域普遍使用。
- `docker-compose.dev.yml` 定义 `aifamily-dev-postgres`（`postgres:16-alpine`）服务；`grep -rl "asyncpg\|postgresql://" backend --include="*.py"` 命中 **8 个文件**，说明存在真实指向 PostgreSQL 连接串/驱动的代码路径（未逐一重跑集成测试确认 round-trip 全绿，此点为"not verified this pass"）。

**结论：FastAPI / SQLAlchemy / Alembic / PostgreSQL 在当前仓库中均为真实存在、已接线的依赖，不是规划中或占位的依赖。** 关于此前"不存在"的判断为何过期，见文末 History。

## 3. 架构测试：位于 tests/architecture

`tests/architecture/` 目录承载 `governance/REPOSITORY_CONSTITUTION.md` R14 要求的机械检验（本次未逐条重跑，清单本身未变更，沿用既有记录）：

| 规则 | 测试文件 |
|---|---|
| R2 唯一领域真相 | `tests/architecture/test_domain_registry.py` |
| R3 无 Manifest 不得入仓 | `tests/architecture/test_migration_manifest.py` |
| R7 领域不直连供应商 | `tests/architecture/test_no_direct_provider_calls.py` |
| R11 单一依赖管理 | `tests/architecture/test_single_toolchain.py` |
| R12 无隐式路径耦合 | `tests/architecture/test_no_layout_coupling.py` |
| R13 历史文档不充当真相 | `tests/architecture/test_docs_truth_boundary.py` |

## 4. 前端：Mobile 与 Web 均已入仓

实测（本次会话）：

- `frontend/mobile/package.json`：Expo `~54.0.29`、React `19.1.0`、React Native `0.81.5`、TypeScript `~5.9.3`。`find frontend/mobile -type f -not -path "*/node_modules/*"` 实测 **508 个文件**。
- `frontend/web/package.json`（package name: `aifamily-experience-studio-web`）：React `^19.1.1`、Vite `^7.1.3`、TypeScript `^5.9.2`；脚本包含 `vitest`、`playwright test`、`eslint`——即 Web 侧已有真实构建/测试/lint 工具链，不是此前记录的"无组件框架、无 bundler"状态。此前文档中 `frontend_web` 为 `REVIEW_REQUIRED / BLOCKED` 的判断已过期，需 chief-architect 确认最新 manifest 状态（本次未核实 `governance/MIGRATION_MANIFEST.yaml` 中 `frontend_web` 当前 disposition 字段，标注 not verified this pass）。

## 5. 当前技术基线小结

| 项 | 状态（本次实测） |
|---|---|
| Python >= 3.12（.venv 实测 3.12.10）+ uv + pyproject.toml | 已建立 |
| FastAPI（真实 app，98 openapi paths）| 已建立并挂载 |
| SQLAlchemy（166 个引用文件）/ Alembic（79 个 migration 脚本）| 已建立 |
| PostgreSQL（docker-compose 定义 + 8 个文件含 asyncpg/postgresql:// 连接）| 已建立，round-trip 全量未在本次重跑 |
| OpenTelemetry（2 个文件，仅 observability sink）| 已接入，范围未验证是否覆盖全域 |
| frontend/mobile（Expo 54 / RN 0.81 / React 19，508 文件）| 已入仓 |
| frontend/web（Vite 7 / React 19 / vitest / playwright）| 已入仓，构建工具链真实存在 |
| tests/architecture | 已建立目录，测试清单未重跑 |

---

## History（历史记录，不代表当前状态）

以下内容是本文件较早版本对 **Wave 0 结束时（2026-08-29 前后）** 状态的记录，仅作历史参考，读者不应据此判断当前仓库状态：

- 当时判断："FastAPI / SQLAlchemy / Alembic / PostgreSQL 在 AiFamily 当前不存在"，理由是全仓库零个 `FastAPI()`/`uvicorn.run()`/`include_router()` 首方调用，唯一 `APIRouter`（`product_intelligence/api/routes.py`）自述"Not mounted into any app yet"；数据库迁移工具链尚处于源仓库手写 SQL（`50_开发_dev/database/migrations/*.sql`，58 个文件）阶段，未生成 Alembic revision，且存在 4 组文件名重号阻塞项。这一判断在 Wave 1（AIFAMILY-001）落地后已不成立。
- 当时判断："AiFamily 当前无前端代码"，后被 project-owner override 推翻：`frontend_mobile` 改判为 MIGRATE，34 个 UI 屏幕（411 个文件 / 35.62 MB）整体迁入 `frontend/mobile/`；当时记录 `frontend_web` 为 `REVIEW_REQUIRED / BLOCKED`（无组件框架、无 bundler）。本次核实确认 Web 侧此后也已建立真实 Vite/React 工具链，不再是 BLOCKED 状态（细节见上方第 4 节）。
- 当时的架构故障教训（R12 无隐式路径耦合的来源）：源仓库 `backend/domains/*` 使用裸顶层导入 `from packages.contracts.evidence import Provenance`，依赖把 cwd 钉在 `50_开发_dev/backend` 才能运行；R14（架构测试必须在 CI 中运行）的教训来自 `FPAI_PROVIDER_REGISTRY.yaml` 声明与生成物不一致但 CI 从未真正跑过检查器的实测伤疤。这两条治理纪律本身仍然有效，只是其触发案例属于历史。
