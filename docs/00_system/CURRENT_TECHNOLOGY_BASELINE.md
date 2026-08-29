# 当前技术架构 (Current Tech Architecture)

- **状态**: CURRENT — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29 (AIFAMILY-000, Wave 0 结束时快照)

---

## 0. 范围声明

本文件描述 AiFamily 仓库在 Wave 0 (AIFAMILY-000) 结束时的技术基线现状，不描述未来 Wave 的目标架构（后者见 `docs/00_foundation/CURRENT_PROGRAM_PLAN.md`）。

## 1. 语言与依赖工具链：已建立

- **语言**：Python >= 3.12。
- **依赖管理**：uv + `pyproject.toml`，已在仓库根建立（`governance/REPOSITORY_CONSTITUTION.md` R11）。
- **禁止**：pip/poetry/pipenv/requirements.txt 并存；不可移植的环境产物入仓（绝对路径 `.pth`、已构建 venv、`.pyc`）。

对应 `governance/MIGRATION_MANIFEST.yaml` 条目 `dependency_management`（disposition: REIMPLEMENT，target: `pyproject.toml`，**status: DONE**）：

> 源仓库零个 `pyproject.toml`/`requirements*.txt`/lock 文件；两个 venv 无对应 manifest；`apps/ai-runtime` 的 `.pth` 硬编码绝对路径 `D:\family-ai\...` 不可移植。AiFamily 已用 uv + `pyproject.toml` 建立。

## 2. 后端运行时：不存在（Wave 1 才建）

FastAPI / SQLAlchemy / Alembic / PostgreSQL **在 AiFamily 当前不存在**。这是 Wave 1 (AIFAMILY-001) 的产出，不是 Wave 0 的产出。

依据 `governance/REPOSITORY_CONSTITUTION.md` R1，正式后端唯一确定为 Python/FastAPI/SQLAlchemy/PostgreSQL。依据 `MIGRATION_MANIFEST.yaml` 条目 `fastapi_runtime_entrypoint`（disposition: REIMPLEMENT，target: `backend/apps/family_api`，status: PLANNED）：

> 全仓库零个 `FastAPI()`/`uvicorn.run()`/`include_router()` 首方调用，唯一 `APIRouter`（`product_intelligence/api/routes.py`）自述"Not mounted into any app yet"。Python 侧从未有过运行时入口，Wave 1 是第一次创建。

数据库迁移工具链同样是 Wave 1+ 议题：源仓库权威 schema（`50_开发_dev/database/migrations/*.sql`，58 个文件，0001-0058）是手写 SQL + `schema_migrations` 追踪表，非 TypeORM/Prisma。判定为 **MIGRATE**（`MIGRATION_MANIFEST.yaml` 条目 `database_schema`），但存在阻塞项：4 组文件名重号（0022/0023/0024/0053 各有两个不同内容的文件）必须先解决，才能生成 Alembic 首个 revision。

## 3. 架构测试：位于 tests/architecture

`tests/architecture/` 目录承载 `governance/REPOSITORY_CONSTITUTION.md` R14 要求的机械检验：

| 规则 | 测试文件 |
|---|---|
| R2 唯一领域真相 | `tests/architecture/test_domain_registry.py` |
| R3 无 Manifest 不得入仓 | `tests/architecture/test_migration_manifest.py` |
| R7 领域不直连供应商 | `tests/architecture/test_no_direct_provider_calls.py` |
| R11 单一依赖管理 | `tests/architecture/test_single_toolchain.py` |
| R12 无隐式路径耦合 | `tests/architecture/test_no_layout_coupling.py` |
| R13 历史文档不充当真相 | `tests/architecture/test_docs_truth_boundary.py` |

R14 的纪律本身来自一条实测伤疤：`50_开发_dev/governance/FPAI_PROVIDER_REGISTRY.yaml` 声明 3 个供应商，其生成物 `provider-registry.generated.ts` 只有 2 个（缺 `deepseek-chat`），生成器 `--check` 在基线 commit 上就是 exit 1——因为源仓库没有 CI 真正跑它。AiFamily 的架构测试必须在 CI 中运行，写成常量或文档不算执行。

## 4. 无隐式路径耦合：R12 的具体约束

禁止依赖进程 cwd、`sys.path` 注入、或目录深度来解析导入；所有内部包必须以真实可安装包的方式解析；禁止在代码中硬编码仓库物理路径或目录名。这条约束直接来自源仓库的实测故障（`backend/domains/*` 全部用裸顶层导入 `from packages.contracts.evidence import Provenance`，只有把 cwd 钉在 `50_开发_dev/backend` 才能跑）。Wave 1 建立 FastAPI 运行时入口时必须遵守。

## 5. 前端：Mobile 已整体迁入，Web 待裁决

> **2026-08-29 更新**：本节此前写的"AiFamily 当前无前端代码 / frontend_mobile 判定为 KEEP_NON_PYTHON"已经**过期**，被 project-owner override 推翻并已实际执行。保留此说明是因为宪章 R13 要求 CURRENT 文档必须与磁盘现状一致，不得让读者读到与事实矛盾的断言。

现状（可验证）：

- `governance/REPOSITORY_CONSTITUTION.md` R1 仍然有效："前端（Web / Mobile）**不要求**迁为 Python，可继续使用 TypeScript / React / React Native。"迁入本仓库不等于要改写成 Python。
- `MIGRATION_MANIFEST.yaml` 中 `frontend_mobile` 已由 project-owner override 改判为 **MIGRATE**，status = `MIGRATED_PENDING_BACKEND_INTEGRATION`。理由（原话）：34 个 UI 已经做得很好，要把整个 Mobile 迁移过来。
- 实体已在 `frontend/mobile/`：411 个文件 / 35.62 MB，字节级校验与源一致；`app/ui/UI-02.tsx` … `UI-34.tsx` 均存在；35 个测试文件与设计基线图一并迁入。`node_modules`/`dist` 未迁（可重装的构建产物）。
- 依赖缺口：**零**。全树搜索 `workspace:` 与 `@family/contracts` 无命中——该 app（`package.json` name: `app-template`）没有 monorepo 内部包依赖。
- `lib/family/family-api-client.ts:101` 确认 base URL 由环境变量 `EXPO_PUBLIC_FAMILY_API_BASE_URL` 驱动，未配置时 fail-closed（`FAMILY_API_NOT_CONFIGURED`），无硬编码后端地址。
- `frontend_web` 仍为 **REVIEW_REQUIRED / BLOCKED**（无组件框架、无 bundler，build 脚本只是 `tsc --noEmit`），未迁入。
- 待修正的记录错误：manifest 证据文本写"202 张 PNG 设计基线"，实测为 87 PNG + 12 WEBP = 99 张图片。这是早期审计的引用错误，已记录在 `docs/40_platform/MOBILE_MIGRATION_NOTES.md`，待更正 manifest 证据文本。

结论：Mobile 前端在本仓库内，但**其可运行性阻塞于 Python 后端**——它消费 ~40+ 后端路径 + 4 个 `/auth/*` 端点，其中 9+ 屏幕依赖源仓库的 `/dev/*` 合成路由。Python FastAPI 必须先满足端点清单，否则 34 个屏幕中最多 24 个会白屏。下一步对齐时机见 `docs/40_platform/MOBILE_MIGRATION_NOTES.md`（Batch 1 Assessment / Batch 2 SERVICE 上线后）。

## 6. 当前技术基线小结

| 项 | 状态 |
|---|---|
| Python >= 3.12 + uv + pyproject.toml | 已建立 |
| FastAPI / SQLAlchemy / Alembic / PostgreSQL | 不存在，Wave 1 建立 |
| tests/architecture | 已建立目录，测试内容随每条规则的架构测试同 PR 补齐 |
| node_modules / 前端代码 | 不存在，非本仓库范围 |
