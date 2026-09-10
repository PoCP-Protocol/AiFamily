---
id: SYS-BASELINE-001
title: AiFamily Current System Baseline
type: system
status: current
version: 3.0
owner: chief-architect
created: 2026-08-29
updated: 2026-09-10
canonical: true
supersedes: docs/00_foundation/MASTER_BLUEPRINT.md
superseded_by: null
---

# 当前系统基线 (Current System Baseline)

> 本文件只回答一个问题：**AiFamily 现在到底是什么。**
> 遵循"现状真相不与历史混排"：本文件正文只写此刻为真的事实；所有旧快照、
> 已被推翻的断言、迁移过程记录，一律放到文末 §6 History，不与正文交织。

---

## 0. 阅读规则

按 `SYSTEM_MANIFEST.md` §4，本文件严格分为四区，**跨区搬运即为造假**：

| 分区 | 含义 | 判据 |
|---|---|---|
| **§1 Implemented** | 代码在 AiFamily 磁盘上、可运行、有测试 | 能指出文件路径 + 测试路径 |
| **§2 In Progress** | 已开工但未达可用状态 | 有部分产物，缺口明确 |
| **§3 Planned** | 已有决策与排期，尚未开工 | 有 governance 登记 |
| **§4 Not Implemented** | 明确不存在 | 用于阻断"我们有" |

一句话现状（本轮，2026-09-10 实测）：治理体系与文档架构已建立；`backend/apps/family_api`
真实 FastAPI 进程在 `AIFAMILY_ENV=test` 下暴露 **109 个 HTTP operation**（108 个 path，
含 dev/test 专属路由）；默认环境（无 `AIFAMILY_ENV`，生产 fail-closed 姿态）下为
**99 个 operation / 98 个 path**（`CURRENT_PRODUCT_MAP.md`/`CURRENT_TECHNOLOGY_BASELINE.md`
用的是这个数字）——两个数字都真实，差异来自环境变量，不是统计口径不一致；
`backend/domains/` 下 **15 个**域目录；`backend/intelligence/` 下 **22 个**子模块/文件级条目；
`database/migrations/versions/` 下 **79 个**真实 Alembic 迁移文件；
`tests/architecture/` 下 **28 个测试文件**，本次实测 **138 passed / 1 skipped**。
全量 `uv run pytest`（含所有测试目录）本次未能在单次调用超时窗口内跑完，
**未验证本次全量总数**，不得引用旧文档中的历史全量数字。

---

## 1. Implemented（已完成 —— 磁盘上有、可运行、有测试）

### 1.1 治理体系

| 产物 | 位置 | 说明 |
|---|---|---|
| 工程宪章 14 条（R1–R14） | `governance/REPOSITORY_CONSTITUTION.md` | 每条附带源仓库实测伤疤 |
| Domain 登记 | `governance/DOMAIN_REGISTRY.yaml` | R2 执行载体；本次实测含 46 条 `status:` 字段（未逐条核对与磁盘一致性，"未验证"） |
| 迁移登记 | `governance/MIGRATION_MANIFEST.yaml` | R3 执行载体 |

### 1.2 文档架构

16 层 `docs/` 结构已建立。由 `tests/architecture/test_docs_truth_boundary.py` 强制：
`00_system/` 下 `CURRENT_*.md` 必须存在且非空、`SYSTEM_MANIFEST.md` 必须存在、
`99_archive/` 文档必须自标 SUPERSEDED、`13_research/` 文档必须自标非权威。

### 1.3 FastAPI 运行时与业务端点（本次实测）

以 `AIFAMILY_ENV=test` 起 `create_app()`，读取 `app.openapi()['paths']`（不是数声明的路由，是实际起进程读 OpenAPI spec）：

```text
HTTP operations 总数    109
HTTP paths 总数         108
覆盖的 tags             ai-evaluation, ai-experience-operations, commerce,
                        experience, experience-feedback, family-growth-ai,
                        fgcn, journey-growth-plan, membership,
                        product-intelligence-courses,
                        product-intelligence-experience-signals,
                        product-intelligence-improvement-candidates,
                        service
```

复现命令：

```bash
AIFAMILY_ENV=test uv run python -c "
from backend.apps.family_api.main import create_app
app = create_app()
paths = app.openapi()['paths']
print('operations:', sum(len(v) for v in paths.values()))
print('paths:', len(paths))
"
```

`backend/apps/family_api/` 下共 **59 个** `.py` 文件（本次 `find` 实测）。

**"109 个业务 operation 存在" 不等于 "34 个 Mobile 屏幕能用"。** 后者需要 Mobile
前端实际发起请求并验证响应契约，本次未核实，见 §4.1。

### 1.4 依赖工具链

`pyproject.toml`（`name = "aifamily"`）+ uv（R11）。由 `tests/architecture/test_single_toolchain.py` 强制单一工具链。

### 1.5 架构测试（本次实测运行）

`tests/architecture/` 下 **28 个测试文件**（`test_docs_truth_boundary.py`、
`test_domain_registry.py`、`test_migration_manifest.py`、`test_no_direct_provider_calls.py`、
`test_single_toolchain.py`、`test_no_layout_coupling.py`、`test_capability_registry.py`、
`test_ai_runtime_isolation.py`、`test_lint_debt_ratchet.py` 等，完整清单见目录本身）。

```text
$ uv run pytest tests/architecture/ -q
138 passed, 1 skipped in 45.22s
```

跳过项：`test_compliance_constraints.py:372`（"no vector/embedding storage exists yet"）。

### 1.6 数据库迁移（本次实测）

`database/migrations/versions/` 下 **79 个** `.py` 迁移文件（目录 `ls | wc -l` 报 80，
差值为 `__pycache__`，已核实非迁移文件）。本次未重新执行 upgrade/downgrade 循环验证，
文件计数已验证，循环可用性**未验证本次**。

### 1.7 Python 业务域（磁盘落位，本次实测目录清单）

`backend/domains/` 下 **15 个**目录：`action`、`assessment`、`commerce`、`family`、
`family_need`、`growth`、`growth_plan`、`identity`、`journey`、`loyalty_points`、
`market_intelligence`、`membership`、`product_intelligence`、`product_strategy`、`service`。

逐域代码行数/测试覆盖/成熟度分级**本次未重新核对**，历史分级（`MIGRATED_TESTED` /
`MIGRATED_UNTESTED` / `MIGRATED_STRUCTURE_ONLY` 等）需要独立核实，见
`CURRENT_DOMAIN_MAP.md`；不要在本文件里推断这些分级仍然成立。

### 1.8 Python AI/Intelligence 包（磁盘落位，本次实测目录清单）

`backend/intelligence/` 下 **22 个**条目（目录与顶层 `.py` 文件混合）：
`agent_runtime/`、`agi_assessment_bridge.py`、`agi_growth_path_projection.py`、
`agi_vertical_composition.py`、`agi_vertical_dev_wiring.py`、`agi_vertical_durable.py`、
`agi_vertical_feedback.py`、`agi_vertical_runtime.py`、`agi_vertical_service.py`、
`capability_registry/`、`context_engine/`、`design_copilot/`、`evaluation/`、
`experience/`、`growth_graph/`、`human_gate/`、`intervention/`、`knowledge/`、
`market_insight/`、`media_factory/`、`memory/`、`model_gateway/`、`observability/`、
`principal/`、`product_management/`、`prompt_registry/`、`safety/`、`schema_registry/`、
`tool_runtime/`。

各子模块的能力成熟度（EXPERIMENT / PILOT / PRODUCTION）**本次未重新核对**，见
`CURRENT_AI_MAP.md`；不要沿用旧文档中的"12 项 EXPERIMENT"等数字，那是历史快照。

### 1.9 Mobile 前端迁移

```text
位置    frontend/mobile/
```

本次未重新核对文件数/行数/屏幕数/测试数，历史值（411 文件、34 屏幕、35 测试文件）
**未在本轮验证，不得当作当前值引用**。代码是否可用见 §4.1。

---

## 2. In Progress（已开工，未达可用）

### 2.1 membership 域 guardrail test 补齐

历史记录该域存在测试缺口（`FORBIDDEN_TIER_FIELD_TOKENS` guardrail test 缺失）。
本次**未重新核对**该缺口是否仍存在，需要独立复核后才能在此写实测结论。

### 2.2 治理登记与磁盘状态的一致性

`governance/DOMAIN_REGISTRY.yaml` 本次实测含 46 条 `status:` 字段。是否与 §1.7
磁盘现状逐条一致，**本次未逐条核对**，不下结论。

---

## 3. Planned（已有决策与排期，未开工）

排期依据：`docs/11_delivery/migration/MIGRATION_PLAN_V2.md` §4。本节内容属计划性质，
非本次核实范围，具体批次划分见该文件，不在本文件重复维护以避免漂移。

---

## 4. Not Implemented / 未核实边界（本次核实范围内的诚实边界）

### 4.1 业务端点存在 ≠ 前端可用

```text
真实业务 HTTP operations 数（AIFAMILY_ENV=test，本次实测）   109
Mobile/Web 前端能否调用这些端点            未核实本次
远端 CI 运行记录                          未核实本次（历史记录为"从未运行过"）
生产部署                                  未核实本次（历史记录为"不存在"）
```

### 4.2 数据库分 schema

PostgreSQL 是否已按域分 schema（`identity.*` / `family.*` 等）**本次未核实**，
历史记录为"151 张表全在 `public`，未分 schema"，需要独立复核才能确认是否仍然成立。

### 4.3 全量测试套件总数

本次尝试运行全量 `uv run pytest`（不限 `tests/architecture/`），在 150 秒超时窗口内
未跑完（可观察到大量 `.`/`s` 进度但未见最终 `passed` 汇总行）。**全量测试总数本次
未验证**，不得引用旧文档中的历史全量数字（如"55 passed"等）作为当前值。下一次核实
应使用更长的超时或后台任务方式重新运行。

### 4.4 其余历史记录的"不存在"项

社区闭环、商品/订单/会员权益、Teacher Workspace/Institution Console/Operations
Console、`frontend/web` 迁入状态、四个独占区候选（Family Context/Growth Graph/
Growth Intervention Engine/Service Blueprint Library）——这些项本次**均未核实**，
不代表"没问题"也不代表"仍不存在"，只是"这次没查"。需要时应逐项重新核实后
再写入本文件。

---

## 5. 相关文档

| 文档 | 回答什么 |
|---|---|
| `SYSTEM_MANIFEST.md` | 系统身份与边界；哪些文档算真相 |
| `TARGET_ARCHITECTURE.md` | 要建成什么 |
| `CURRENT_PRODUCT_MAP.md` | 有哪些产品/端，34 UI 逐屏状态 |
| `CURRENT_DOMAIN_MAP.md` | 业务真相由哪些 Domain 管理，边界与成熟度 |
| `CURRENT_AI_MAP.md` | AI 能力版图与成熟度 |
| `CURRENT_TECHNOLOGY_BASELINE.md` | 技术基线 |
| `governance/REPOSITORY_CONSTITUTION.md` | 14 条工程宪章 |
| `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` | Batch 划分与 disposition 分类法 |

---

## 6. History（历史记录，不代表当前状态）

本节收纳此前版本中记录的迁移过程、已被推翻的旧断言、并发 WIP 观察记录。
**任何引用本节数字作为当前值的行为都是错误** —— 当前值只在 §0–§4，且只来自
本轮实测。

- **V1（2026-08-29）**：`MASTER_BLUEPRINT.md` 直接重命名而来，内容以蓝图/愿景为主。
  目标态内容已拆分至 `TARGET_ARCHITECTURE.md`。
- **Wave 0 → Wave 1 迁移初始状态（2026-08-29）**：当时实测为"业务端点 0 个，
  数据库尚未建立，5 个 Python 域与 Mobile 前端已迁入但零业务 API 可用"。此状态
  已被后续多轮实测（2026-09-04、2026-09-07）推翻，业务端点数从 0 → 85 → 87 → 109
  持续增长，说明这是一个活动值，每次核实都必须重新跑命令，不能沿用任何历史数字。
- **2026-08-29 T-03**：完成 Alembic baseline 落地（62 个源 SQL 迁移线性化），
  62 个源 SQL 迁移文件迁入 `database/baseline/`，4 组文件名重号已线性化。
- **2026-09-01～09-04 闭环记录**：`family_need` N0–N8 全生命周期端到端打通；
  `service/fgcn` 人工授权派单从内存态切换为可选 durable 路径；AI Coach 接入
  跨轮次会话记忆；`product_intelligence` 去标识化跨家庭信号上线。
- **2026-09-07 复核**：业务 operation 数从 85 增至 87；确认 `family_need`/
  `service·fgcn` 等域已有持久化真相，推翻"没有任何域拥有持久化真相"的更早断言；
  `CURRENT_AI_MAP.md` 记录"12 项 EXPERIMENT、0 项 PILOT/PRODUCTION"；AI Coach
  已有可选真实供应商接入路径（DeepSeek），默认仍为 FakeProvider。
- **2026-09-08 核实**：课程服务产品 IPD/PDM/PLM 纵向切片形成可运行状态
  （6 阶段 × 24 课时 `CourseSystem`，`ReleaseBaseline` 生命周期管理），前端全量
  测试 237 passed，课程后端链路 21 passed。
- **并发 WIP 观察（2026-08-29 记录）**：`tests/domains/membership/` 出现另一
  并发会话编写的验收测试，当时存在 2 个失败参数化用例；这是对其他会话工作的
  观察记录，不代表本文件作者所做的修改。
