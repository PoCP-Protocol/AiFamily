---
id: DEL-MIG-001
title: 源仓库资产清单
type: delivery
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: false
supersedes: null
superseded_by: null
---

# 01 — 源仓库资产清单 (Repository Inventory)

- **审计对象**: `PoCP-Protocol/family-ai` @ `1ff168123d147f4d6a6eaaa677bc2f80986233d9`（本地路径 `D:\family-ai\50_开发_dev`）
- **审计日期**: 2026-08-29
- **审计口径**: 本报告为 AIFAMILY-000 七路只读审计的结构化浓缩，所有条目均来自实际读码/读文件，非估算或猜测。逐条证据的完整引用见 `governance/MIGRATION_MANIFEST.yaml` 与 `governance/REPOSITORY_CONSTITUTION.md`。
- **并发注意**: 审计时源仓库有 64 个未提交文件属于另一并发会话（family-gateway 网关重构、membership/growth_plan Python 域改动），本清单基于当时磁盘状态，未修改任一源文件。

本报告目的：让人类架构师一眼看清"这个仓库到底有多大、哪些部分活着、哪些部分只是挂在目录树上"。

---

## 1. 顶层目录总览

| 顶层目录 | 内容性质 | 是否有运行时入口 | CI 覆盖 | 存活判定 |
|---|---|---|---|---|
| `apps/api` | NestJS 生产 API | 有（真实监听端口，连真实 Postgres） | 有（family-35ui-alignment.yml 覆盖 api 路径） | **活的，唯一权威生产后端** |
| `apps/mobile` | React Native 移动端 | 有（真实构建产物+设备/模拟器可运行） | 有（同上，覆盖 mobile 路径） | **活的，唯一在CI中的前端** |
| `apps/web` | React Web（声称） | 无（build脚本仅 `tsc --noEmit`，无 bundler 产物） | 部分（同上覆盖 contracts 路径，但 web 本身路由未被覆盖） | 半活：契约参照价值 > 部署价值 |
| `apps/ai-runtime` | Python AI 运行时 | **无**（`.py` 源码已从磁盘删除，只剩 `.pyc`；git 从未跟踪） | 无 | **死的**，唯一证据是编译产物 |
| `apps/fes-api` | 声明 NestJS 依赖的应用 | 无（无 `@Module`/`NestFactory`/controller，运行即打印一行 JSON 后退出） | 无 | **死的**，从未真正监听端口 |
| `apps/fes-web` | 单文件前端 | 无（11 行单函数，零网络调用，零 UI 框架） | 无 | **死的**（占位） |
| `apps/consumer-web` | 目录占位 | 无（目录内仅 `node_modules`，无 `package.json`，无源码） | 无 | **空壳** |
| `apps/ops-web` | 目录占位 | 无（同上） | 无 | **空壳** |
| `backend/domains/*` | 5 个 Python 业务域 | **全部无运行时入口**（全仓库零个 `FastAPI()`/`uvicorn.run()`/`include_router()` 首方调用） | 无 | 详见第 3 节，成熟度差异极大 |
| `backend/intelligence/design_copilot` | AI 设计能力占位 | 无（`compiler.py`/`simulation.py` 全是 `NotImplementedError`） | 无 | 仅方法名分类可参考，无实现 |
| `backend/packages/contracts` | Python 跨域共享类型 | 是共享库不是应用，被 4 个域引用（无独立入口概念） | 无 | 唯一真正被多域复用的 Python 原语 |
| `legacy-system` | FELS 参考实现（自述非真实历史系统） | 无生产运行时引用（pnpm workspace 可见但零 import） | 有限（可能被自己的 spec 覆盖，非业务 CI） | 语义保留价值 > 代码价值，已抽取进 R9 |
| `database/migrations` | 58 个手写 SQL 迁移文件 (0001-0058) | 是（`tools/migrate.mjs` 顺序应用于真实 Postgres） | 无独立 CI，靠 `apps/api` 集成测试间接验证 | **活的但有已知缺陷**（4 组重号、死列共存） |
| `contracts` | 前端/后端边界契约 | 部分（`packages/contracts` 内 TS 文件含真实投影函数） | 有（family-35ui-alignment.yml 覆盖 contracts 路径） | Markdown 部分纯文档；TS 部分含真逻辑 |
| `packages/*` | 共享 npm 包（ai-gateway/principal-ai/principal-runtime/contracts/waf-contracts/program-runtime/harness 等） | 视包而定，`ai-gateway` 有真实实现且被多处引用；`program-runtime`/`harness` 未找到消费者 | 部分（contracts 类包被 CI path filter 覆盖） | 混合：核心网关活，个别包疑似孤儿 |
| `governance` | 治理 YAML + Markdown（~83 个文件） | 3 个被工具/CI 实际强制执行，其余约 80 个是纯文档 | 部分（仅 provider registry 生成器有 `--check`，且该检查在基线上 exit 1） | 大部分"治理"只是意图，非护栏 |
| `reports` | 历史 Sprint / Gate 证据（536 个文件） | 无运行时关联 | 无 | 历史档案，仅 2 个文件标注为最新快照 |
| `tools` | 构建/迁移/生成脚本（`migrate.mjs`、`build_provider_policy_snapshot.py` 等） | 是（被 CI 或人工手动调用） | 部分 | 活的支撑脚本，但生成器本身可处于失败态而无人拦截 |
| `products/we-are-family/apps/wf1-lab` | 纯前端 React demo | 有（可独立运行） | 无 | 活但零后端耦合，与本次后端迁移无关 |
| `products/famili-principal` | 纯文档树 | 无代码 | 无 | 待审（`review_required_index` 收录，疑似孤儿） |
| `agents` | （未在本次七路审计中单独列出细节；按 manifest 未见对应 entries） | 未知 | 未知 | 未覆盖，需补充审计 |
| `family-os` | （未在本次七路审计中单独列出细节） | 未知 | 未知 | 未覆盖，需补充审计 |
| `scaffold` | （未在本次七路审计中单独列出细节） | 未知 | 未知 | 未覆盖，需补充审计 |
| `factory` | 自驱开发工厂脚本 | 引用已损坏（`run-development-factory.mjs` 指向不存在的脚本） | 无 | 疑似死代码/孤儿，见报告 02 |
| `evals` | 契约测试（`*.contract.spec.ts`） | 是测试逻辑但**未被任何 workspace/CI 收集**（`evals/` 不在 `pnpm-workspace.yaml` 内） | **无**（这是问题本身） | 有价值的规格，零执行证据 |
| `architecture` | 蓝图/迁移计划文档 | 不适用 | 不适用 | 含与治理文档矛盾的"当前基线"声明，见报告 02 |
| `specs` | Ontology / policy YAML（如 `perspective-fact.policy.yaml`、`consent.schema.yaml`） | 部分被 e2e 断言引用 | 间接 | 有真实业务规则参考价值 |

> **备注**：`agents`、`family-os`、`scaffold` 三个目录未出现在七路审计的浓缩发现清单中，本报告不臆造其内容评价，标记为"未覆盖，需补充审计"，避免把猜测当结论写进交付物。

---

## 2. 代码量与语言构成（按已核实条目汇总）

| 资产 | 语言 | 行数/文件数 | 备注 |
|---|---|---|---|
| `apps/api/src/modules/auth` | TypeScript | 1546 行 | 真实 Postgres，1 个显式替换点（`StubOtpSender`） |
| `apps/api/src/modules/family` | TypeScript | 14091 行（含 specs），核心 `family.service.ts` 2293 行 | 全仓库最大服务文件，60+ 路由 |
| `apps/api/src/modules/model` | TypeScript | 23 行 | 裸 provider，非真正 Nest module |
| `apps/api/src/modules/orchestration` | TypeScript | 5519 行 | 明确不写 Growth 权威表 |
| `apps/api/src/modules/principal` | TypeScript | 2337 行 | 真实 Postgres，DI 工厂 fail-closed |
| `apps/api/src/modules/waf` (waf-domain.service) | TypeScript | 261 行 | 纯内存 Map，零路由引用，死代码 |
| `packages/ai-gateway` | TypeScript | 894 行 | 唯一真实网关实现 |
| `backend/domains/product_intelligence` | Python | 21 文件 / 1492 行 | 五层俱全，唯一有 tests 的域 |
| `backend/domains/membership` | Python | 2627 行 | 代码量最大，零测试目录 |
| `backend/domains/market_intelligence` | Python | 52 行 | 空壳（仅 entities+errors） |
| `backend/domains/product_strategy` | Python | 159 行 | fake repo only，无测试 |
| `backend/domains/growth_plan` | Python | 37 行 | 仅错误类型枚举 |
| `database/migrations` | SQL | 58 个文件 (0001-0058) | 4 组文件名重号 |
| `apps/mobile` | TypeScript/React Native | 35 个测试文件 + 202 张 PNG 基线图 | 唯一在 CI 中的前端 |
| `apps/web` | TypeScript | 24 个 spec 文件 | 无 bundler，非可部署产物 |
| `legacy-system` | TypeScript | contracts + spec 文件（未逐一计行） | 自述 REFERENCE_IMPLEMENTATION=TRUE |
| `reports/` | Markdown | 536 个文件 | 仅 2 个标注为最新快照 |
| Python 依赖 manifest | — | **0 个** | 零 `pyproject.toml`/`requirements*.txt`/lock 文件，两个 venv 无对应 manifest |

---

## 3. Python 域现实核验（反驳"只有 product_intelligence 成熟"的计划假设）

计划文档曾假设 5 个 Python 域中只有 `product_intelligence` 达到生产可用标准。实测结果与该假设有重大偏差：

| 域 | 行数 | 测试 | 关键发现 |
|---|---|---|---|
| `product_intelligence` | 1492 | **有**（唯一） | `api/routes.py` 自述"未挂载"；无 Postgres 集成测试（只有 SQLite）；自称 V0.1 |
| `membership` | **2627**（最大） | **无**（零测试目录） | 含真实不变量策略 `assert_tier_transition_legal`；`FORBIDDEN_TIER_FIELD_TOKENS` 注释自称"由 guardrail test 强制"但该测试不存在；docstring 声称的 `tests/conftest.py` 在磁盘上不存在 |
| `market_intelligence` | 52 | 无 | 空壳，仅 entities+errors |
| `product_strategy` | 159 | 无 | 仅 domain+ports+fake repository |
| `growth_plan` | 37 | 无 | 仅错误类型枚举 |

**结论**：`membership` 是全仓库最大的单点风险——代码量最大、不变量最真实，但零测试覆盖，且文档自称的测试基础设施根本不存在。这不是"次成熟"，是"文档与代码矛盾"。详见报告 03、04 及 `governance/MIGRATION_MANIFEST.yaml` 的 `membership` 条目（`disposition: REVIEW_REQUIRED`, `status: BLOCKED`）。

---

## 4. CI 覆盖现状

全仓库只有**一个**真正生效的 CI workflow：`.github/workflows/family-35ui-alignment.yml`。其 path filter 限定在 `mobile/api/contracts` 三处。

这意味着：
- 536 个 `reports/` 历史 Sprint 证据文件，**不受任何 CI 覆盖**（属于静态档案，其正确性无法被自动验证）。
- `evals/*.contract.spec.ts` 因不在 `pnpm-workspace.yaml` 内，**从未被任何 runner 收集**，尽管其断言逻辑有真实规格价值。
- `governance/FPAI_PROVIDER_REGISTRY.yaml` 的生成器 `tools/build_provider_policy_snapshot.py --check` 在基线 commit 上就是 `exit 1`——一个正在失败的不变量被提交进主线，因为没有 CI 拦截它。
- Python 侧（`backend/domains/*`）没有出现在该 CI 的 path filter 中，其测试（仅 `product_intelligence` 有）从未在 CI 中被验证过是否持续通过。

---

## 5. 依赖与环境资产

- **Python 依赖 manifest**: 0 个（无 `pyproject.toml`/`requirements*.txt`/lock 文件）
- **Python 虚拟环境**: 2 个 venv，均无对应 manifest 可反推依赖集
- **不可移植产物**: `apps/ai-runtime` 的 `.pth` 文件硬编码绝对路径 `D:\family-ai\50_开发_dev\apps\ai-runtime\src`，换机即失效
- **数据库迁移工具**: `tools/migrate.mjs`（自定义顺序应用器 + `schema_migrations` 追踪表），非 TypeORM/Prisma/Alembic

---

## 6. 本清单与 governance 文件的关系

本报告是 `governance/MIGRATION_MANIFEST.yaml`（能力级 disposition 登记）与 `governance/REPOSITORY_CONSTITUTION.md`（规则与伤疤）的**目录级前置视图**。三者关系：

1. 本报告（01）回答"仓库里有什么、有多大、活不活"
2. `MIGRATION_MANIFEST.yaml` 回答"每个能力该往哪个 disposition 走"
3. `REPOSITORY_CONSTITUTION.md` 回答"为什么定这些规则、防止哪次事故重演"

三份文档应一起阅读，互不重复叙述细节，仅互相引用。
