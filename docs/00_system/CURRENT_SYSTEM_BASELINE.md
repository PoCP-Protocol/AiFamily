---
id: SYS-BASELINE-001
title: AiFamily Current System Baseline
type: system
status: current
version: 2.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-30
canonical: true
supersedes: docs/00_foundation/MASTER_BLUEPRINT.md
superseded_by: null
---

# 当前系统基线 (Current System Baseline)

> 本文件只回答一个问题：**AiFamily 现在到底是什么。**
> 包括"哪些没做"。任何未来设计一律不得出现在 §1 Implemented。

---

## 0. 阅读规则与本文件的改造说明

### 0.1 四分区强制

按 `SYSTEM_MANIFEST.md` §4，本文件严格分为四区，**跨区搬运即为造假**：

| 分区 | 含义 | 判据 |
|---|---|---|
| **§1 Implemented** | 代码在 AiFamily 磁盘上、可运行、有测试 | 能指出文件路径 + 测试路径 |
| **§2 In Progress** | 已开工但未达可用状态 | 有部分产物，缺口明确 |
| **§3 Planned** | 已有决策与排期，尚未开工 | 有 governance 登记 |
| **§4 Not Implemented** | 明确不存在 | 用于阻断"我们有" |

### 0.2 本文件的改造说明（V1 → V2）

V1 是 `MASTER_BLUEPRINT.md` 直接重命名而来，内容以"蓝图/愿景"为主（系统全景图、三层价值网络、独占区归属、FGCN 落位），仅在第 5 节附一张现状核对表。这与文件名承诺的"系统现在到底是什么"不符 —— 症状是原文第 72 行不得不写"不要把这张全景图误读为已实现"。

**处理方式（已执行）**：

```text
目标态内容 → docs/00_system/TARGET_ARCHITECTURE.md（新建）
              全景图 / 三层价值网络 / 四个独占区归属判断 / FGCN 落位
              / 待人类裁决项，全部完整保留，未删减

现状内容   → 本文件 V2，重写为四分区
              原 §5 现状核对表 → 本文件 §1/§4 并已更新
              原 §5 的文档漂移指认 → 本文件 §5，并已扩充
```

**没有内容被丢弃**，只是按信息类型重新分区。

### 0.3 一句话现状

**治理体系与文档架构已建立；Python 平台内核骨架可运行（只会回答 `/health` 与 `/ready`）；5 个 Python 域与整个 Mobile 前端已迁入 —— 但零业务 API，34 个 UI 屏幕全部无法工作，数据库尚未建立，没有任何域上线。**

---

## 1. Implemented（已完成 —— 磁盘上有、可运行、有测试）

### 1.1 治理体系

| 产物 | 位置 | 说明 |
|---|---|---|
| 工程宪章 14 条（R1–R14） | `governance/REPOSITORY_CONSTITUTION.md` | 每条附带源仓库实测伤疤（含源文件路径与行号） |
| Domain 登记 | `governance/DOMAIN_REGISTRY.yaml` | R2 执行载体。**注意 status 字段已与磁盘漂移，见 §5** |
| 迁移登记 | `governance/MIGRATION_MANIFEST.yaml` | R3 执行载体。含 3 处 `project_owner_override` 记录 |
| 迁移审计报告 | `reports/migration/` | 4 份，是宪章每条伤疤的证据来源 |

### 1.2 文档架构 V1.0

16 层 `docs/` 结构已建立，既有文档已完成归位：

```text
L0  00_system                                   系统真相
L1  01_strategy 02_business 03_product           为什么 / 是什么
L2  04_domains 05_ai 06_platform 07_data         系统语义
L3  08_experience 09_operations 10_engineering 11_delivery   如何建 / 如何运行
L4  12_governance 13_research 14_reference 99_archive        治理 / 知识
```

由 `tests/architecture/test_docs_truth_boundary.py` 强制：`00_system/` 下 `CURRENT_*.md` 必须存在且非空、`SYSTEM_MANIFEST.md` 必须存在、`99_archive/` 文档必须自标 SUPERSEDED、`13_research/` 文档必须自标非权威。

### 1.3 Wave 1 平台内核骨架

| 组件 | 代码 | 测试 |
|---|---|---|
| identity（`ActorContext` / `TenantContext`） | `backend/platform/identity/` | `tests/platform/identity/test_context.py` |
| authorization（`PolicyEngine`，fail-closed） | `backend/platform/authorization/` | `tests/platform/authorization/test_policy.py` |
| consent（`ConsentGate`） | `backend/platform/consent/` | `tests/platform/consent/test_gate.py` |
| audit（`AuditRecorder`，R6 载体） | `backend/platform/audit/` | `tests/platform/audit/test_recorder.py` |
| idempotency（`IdempotencyKey` / Store） | `backend/platform/idempotency/` | `tests/platform/idempotency/test_keys.py` |
| persistence（`UnitOfWork` / `SqlAlchemyUnitOfWork`） | `backend/platform/persistence/` | `tests/platform/persistence/test_unit_of_work.py` |
| localization（`LocaleContext` 四维语言上下文与 HTTP 适配器） | `backend/platform/localization/` | `tests/platform/localization/` |
| FastAPI 运行时入口 | `backend/apps/family_api/`（真实 FastAPI 实例） | `tests/apps/family_api/test_routes.py` |

```text
Wave 1 交付时测试总数  49 passed
端点                  GET /health, GET /ready   —— 仅此两个
业务端点              0
```

**测试总数是活动数字，不要引用本节的 49 作为当前值。** 本文件写作时 `uv run pytest` 实测为 **55 passed / 2 failed**（失败项来自另一会话的 membership WIP，见 §2.2）。权威值只有一个来源：**跑一次 `uv run pytest`**。

**这是 Python 侧第一次拥有运行时入口**：源仓库全域零个 `FastAPI()` / `uvicorn.run()` / `include_router()` 首方调用，唯一的 `APIRouter` 自述 "Not mounted into any app yet"。

### 1.4 依赖工具链

`pyproject.toml` + uv（R11），已装依赖：fastapi / uvicorn / pydantic v2 / sqlalchemy 2 / alembic / asyncpg / aiosqlite，dev：pytest / pytest-asyncio / pyyaml / ruff / httpx。由 `tests/architecture/test_single_toolchain.py` 强制单一工具链。

对比源仓库：**零个** `pyproject.toml` / `requirements*.txt` / lock 文件，两个 venv 无对应 manifest，`.pth` 硬编码绝对路径 `D:\family-ai\...` 不可移植。

### 1.5 架构测试（R14 执行）

`tests/architecture/` 下 6 个文件：`test_domain_registry.py`（R2）、`test_migration_manifest.py`（R3）、`test_no_direct_provider_calls.py`（R7）、`test_single_toolchain.py`（R11）、`test_no_layout_coupling.py`（R12）、`test_docs_truth_boundary.py`（R13）。

### 1.6 Python 域迁移（代码落位完成，能力状态另计）

以下代码**已在磁盘上**（这是 Implemented 的判据），但其**能力成熟度差异极大**，逐域真实状态见 `CURRENT_DOMAIN_MAP.md`，勿以"已迁入"推断"能力已具备"：

| 落点 | 内容 | 能力状态 |
|---|---|---|
| `backend/domains/product_intelligence` | 21 文件 / 1492 行，五层俱全 | `MIGRATED_TESTED`（6 测试通过，含 guardrail TEST_ORACLE） |
| `backend/domains/membership` | 2627 行，真实 SQLAlchemy 仓储 + 不变量策略 | `MIGRATED_UNTESTED` ← 最大单点风险，见 §2.2 |
| `backend/domains/market_intelligence` | 52 行 | `MIGRATED_STRUCTURE_ONLY`（空壳） |
| `backend/domains/product_strategy` | 159 行 | `MIGRATED_STRUCTURE_ONLY`（stub） |
| `backend/domains/growth_plan` | 单文件 37 行 | `MIGRATED_STRUCTURE_ONLY`（仅错误类型枚举） |
| `backend/packages/contracts` | 跨域共享 `Provenance` / `evidence` 原语 | 被 4 个域以 `backend.packages.contracts.*` 绝对包路径导入 |
| `backend/intelligence/design_copilot` | `compiler.py` / `simulation.py` | 全 `NotImplementedError`，零调用方、零测试 |

迁移过程中的实质修复：

- **修复 6 处 R12 路径耦合违规**：源仓库全部用 `from packages.contracts.evidence import Provenance` 这类裸顶层导入，必须把 cwd 钉在 `50_开发_dev/backend` 才能跑；`product_strategy/domain/entities.py:17` 的注释直接在讨论 `50_开发_dev/backend/` 这个物理布局。
- **17/17 import 烟雾测试通过**，证明所有域可在无 cwd 假设下解析导入。

后三项（market_intelligence / product_strategy / growth_plan）的迁入依据是 `project_owner_override`（2026-08-29 指示"先把所有 Python 代码都迁移过来"），override 原文明确要求"**迁移后仍是空壳状态，不假装已完整**"。

### 1.7 Mobile 前端迁移

```text
位置    frontend/mobile/
规模    411 文件 / 35.62MB
屏幕    34 个（UI-02..UI-34 在 app/ui/，UI-01 = app/(tabs)/index.tsx，
        另有 app/ui/UI-02-result.tsx 结果页）
测试    35 个测试文件
设计    99 张设计基线图
```

disposition = MIGRATE（`project_owner_override` 推翻此前 KEEP_NON_PYTHON），manifest 状态 `MIGRATED_PENDING_BACKEND_INTEGRATION`。**代码完整迁入 ≠ 屏幕可用**，见 §4.1。

---

## 2. In Progress（已开工，未达可用）

### 2.1 family_api 的业务路由挂载

`backend/apps/family_api` 是真实进程，但零业务路由。`backend/domains/product_intelligence/api/routes.py` 有一个 `APIRouter`，**从未被挂载到任何 app**（这个缺陷从源仓库原样带入）。这是 Batch 1 的第一个技术动作。

### 2.2 membership 域的 guardrail test 补齐

**状态：已迁入，阻塞未解。**

`backend/domains/membership` 2627 行，是五个 Python 域中最大的，`domain/policies.py` 含真实不变量（`assert_tier_transition_legal` 等）。但：

- `infrastructure/sqlalchemy_repository.py:8-9` 的 docstring 声称 "Tests run this same class against an in-memory SQLite engine (`tests/conftest.py`)" —— **该 `tests/` 目录在源仓库磁盘上根本不存在**。
- `policies.py:24-28` 的 `FORBIDDEN_TIER_FIELD_TOKENS`（禁止 score / rank / level 字段）注释自称"由 guardrail test 强制" —— **该测试在源仓库与 AiFamily 中都不存在**。

`project_owner_override` 明确记录：原 REVIEW_REQUIRED/BLOCKED 判定"不是错误，而是被'先迁移进来再补测试'这一顺序决定覆盖 —— 迁移执行时必须原样带着这个已知缺口，**不得在迁移过程中假装测试已存在**"。

解锁路径：先写出 `FORBIDDEN_TIER_FIELD_TOKENS` 的 guardrail test，再决定 MIGRATE vs REIMPLEMENT。这既是 R4 的直接要求，也是 R14 的典型场景（写成注释的策略等于没有策略）。

**并发 WIP 记录（2026-08-29 本文件写作时观察到）**：`tests/domains/membership/` 已出现另一并发会话正在编写的验收测试（`conftest.py` / `helpers.py` / `test_acceptance_chain.py`，fake 与 sqlalchemy 双后端参数化）。其中 `test_annual_renewal_appends_a_new_period` 的两个参数化用例**当前为失败态**（`uv run pytest` = 2 failed / 55 passed）。这批测试覆盖的是会员周期验收链，**不是** `FORBIDDEN_TIER_FIELD_TOKENS` 的 guardrail test —— 后者在 `tests/` 与 `backend/` 下 grep 仍为零命中。因此：

- membership 的能力状态**仍为 `MIGRATED_UNTESTED`**：R4 要求"测试须能在 CI 中真实运行"，红色测试不构成能力证明。
- §2.2 的阻塞条件**未解除**。
- 该 WIP 属其它会话，本文件只记录观察，不做修改。

### 2.3 治理登记的状态刷新

`DOMAIN_REGISTRY.yaml` 头部仍写"Wave 0 阶段：本表全部 status = NOT_STARTED，不含任何业务代码"，全部 Wave 1/2 条目也仍是 `NOT_STARTED` —— 与 §1.3/§1.6 的磁盘实况矛盾。需一次 registry 刷新，详见 §5。

---

## 3. Planned（已有决策与排期，未开工）

排期依据：`docs/11_delivery/migration/MIGRATION_PLAN_V2.md` §4（精选式批次划分）。批次优先级 = "该域当前证据状态 × 它所属的三区区域"的乘积，不是域名字母顺序。

```text
Batch 1  平台地基 + Assessment 域 (UI-02/UI-03)
Batch 2  SERVICE 预约子链 (TeacherProfile/ProviderProfile/BookingRequest/ServiceRecord)
         ← 从 V1 Batch 5 提前，已验证的付费闭环
Batch 3  Family/Relationship/Consent 核心聚合
Batch 4  GrowthIntent/GrowthPlan（仅 PLAN 已打通部分）
Batch 5  Principal/Conversation/Human Handoff
         （AttemptRecordingGateway 等 fail-closed 机制必须先于业务逻辑）
Batch 6  21-Day Program + COMMERCE 闭环（前置：清理 UI-17 硬编码积分、
         明确未成年人商业权限规则）
Batch 7  COMMUNITY 闭环 + Organization/Teacher (B2B2C, 完整 FGCN)
Batch 8  条件性收尾：删除范围 = 已完成 cutover 的域，不是"无条件删除全部 NestJS"
```

其它已决策未开工项：

| 项 | 决策 | 阻塞条件 |
|---|---|---|
| ~~Alembic baseline~~ | **已于 2026-08-29 由 T-03 完成** —— 62 个源 SQL 迁移线性化 + Alembic baseline 落地，见 §4.2 | 阻塞已解除 |
| 域接管节奏 | `NEST_ACTIVE → PYTHON_READY → CUTOVER → PYTHON_ACTIVE → NEST_REMOVED`，**禁止双写、禁止双主** | — |
| GROWTH 闭环（UI-08/11/12/29） | **允许路径继续建设；当前仍未实现**。私有回顾、证据绑定成果和经同意分享按环境等价原则重建；家庭总分/家庭排名等红线统一拒绝、审计并保留人工处理 | 需补齐 GROWTH 应用/事实/投影链，并逐项核对 R9 红线 |
| `frontend_web` | REVIEW_REQUIRED / BLOCKED | 需人工裁决 |

---

## 4. Not Implemented（明确不存在 —— 用于阻断"我们有"）

### 4.1 零业务 API —— 最重要的一条

```text
AiFamily 可用业务端点        0
Mobile 依赖端点              ~40+ 业务路径 + 4 个 /auth/* 端点
34 个 UI 屏幕可工作数量       0
```

**34 个屏幕在 AiFamily 内全部无法真正工作。** 逐屏状态见 `CURRENT_PRODUCT_MAP.md`；那里的所有 `E2E_READY` / `BACKEND_READY` 等状态词都是**源仓库 NestJS 后端下测得的**，在 AiFamily 内一律不成立。

附带风险：源仓库有 9+ 个屏幕（UI-10/11/12/22/23/25/27/28/29）依赖自述 `SYNTHETIC_DEV_ONLY` 的 `/dev/*` 合成路由。Python 后端必须为它们显式决定数据来源，否则结果不是"清理了假数据"而是"白屏"。

### 4.2 数据库

**2026-08-29 T-03 后已变化的部分**（原文划线保留以便追溯）：

- ~~未建立 Alembic baseline~~ → **已建立**：`database/migrations/versions/0001_legacy_schema_baseline.py`。`alembic upgrade head` 在空 Postgres 16 上成功（151 表 / 7 视图 / 60 枚举），up→down→up 循环可重复。
- ~~58 个源 SQL 迁移文件仍在源仓库~~ → **已迁入** `database/baseline/`（实测 62 个文件，"58" 是最大编号非文件数），内容逐字节不变，sha256 由 `tests/database/test_baseline_linearisation.py` 守着。
- ~~4 组文件名重号未线性化~~ → **已线性化**，映射与逐组排序理由见 `database/migrations/LINEARISATION_MAP.md`。
- ~~无 Postgres 集成测试~~ → 真实 Postgres 测试路径已建立，由 `AIFAMILY_TEST_DATABASE_URL` 门控（默认 skip，SQLite 快路径保留为默认）。`membership` 与 `product_intelligence` 两个域、以及 `/ready` 端点都有真实 Postgres 测试通过。

**仍然不存在的部分（不要据上面的进展推断已完成）**：

- PostgreSQL **按域分 schema 未建立**。151 张表全在 `public`，`identity.*`/`family.*`/`assessment.*` 与每域独立 DB role 都还没做——baseline 刻意只做忠实快照，见 `docs/07_data/DATA_ARCHITECTURE.md` §5。
- **没有任何域拥有持久化真相。** baseline 建的是空表，没有任何域的运行时读写落在这些表上；`membership`/`product_intelligence` 的 Postgres 测试用的是 `Base.metadata.create_all` 建在一次性 schema 里的表，**不是** baseline 化的表。因此源 SQL 里的 DB 级 CHECK 约束在这两个域仍未被覆盖。
- 已发现一处**待裁决的 schema 矛盾**：`product_intelligence` 域本地 SQL 副本比 baseline 多三列（`validated_by`/`validated_at`/`validation_reason`），而 ORM 要求这三列 —— 在只跑过 `alembic upgrade head` 的库上该域会失败。详见 `backend/domains/product_intelligence/migrations/README.md`。

### 4.3 AI Runtime

`backend/intelligence/` 下**只有** `design_copilot`，其 `ProductCompiler` / `DesignSimulator` 每个方法都是 `NotImplementedError`，零调用方、零测试。

（历史基线）不存在：Model Gateway、Context Engine、Agent Runtime、Tool Runtime、Memory、Prompt Registry、Schema Registry、Safety、Human Gate、Evaluation、Observability、AI Provenance。5 个业务 Agent（家长顾问/孩子陪练/助教助手/成长规划师/经营助手）零实现。详见 `CURRENT_AI_MAP.md`。

> **2026-08-30 基线校正**：上述段落描述迁移初始状态，不再代表当前实现。当前 AI Map 已记录 12 项 EXPERIMENT；Context Engine 已通过 `AsyncSqlContextBroker`、`SqlContextBrokerFactory` 与 Alembic 0036 具备 durable 快照、作用域/consent/TTL 校验和主体删除证明，Experience operations audit 已通过 Alembic 0037 提供 metadata-only operator 访问记录，运维 HTTP 边界已增加请求 bearer 绑定与 `HttpRequestOperatorIdentityPort`（ADR-0129），dev/test 已能用 synthetic runtime 走完同一 operator query 契约；Memory 已通过 `SqlAlchemyMemoryStore` 与 Alembic 0022 具备 durable 引用、作用域读取、级联删除证明和过期清理。Growth Graph 与五类业务 Agent 仍未达到可生产状态。

**源仓库 TS 侧有真实网关实现（`packages/ai-gateway/src/index.ts`，894 行）不等于 AiFamily 有** —— 按 R1，正式后端只能是 Python。

### 4.4 四个独占区候选：全部空白

- **Family Context**：源仓库审计确认 `FamilyMemoryDialogueRuntime` **未接入任何调用方**，embedding / pgvector **完全不存在于代码**。
- **Family Growth Graph**：完全空白，且归属分歧未定（见 `TARGET_ARCHITECTURE.md` §6）。
- **Growth Intervention Engine**：源仓库有雏形数据结构，缺 `primary_contradiction` 排序层；AiFamily 内零实现。
- **Service Blueprint Library**：零实现。

`AI_NATIVE_PRINCIPLES.md` §3.3 已定性：前两项是 AI 原生的**地基而非可选增强**，且因完全空白，**它们是新建，不是优化**。

### 4.5 workflow_worker 进程

`backend/workflow_worker/` 已出现首个可执行增量：`growth_action_experience_relay.py`
以同库事务和 per-consumer receipt 把 UI-09 Action outbox 转为 ExperienceEvent，并在当前
Consent 被撤回或版本变化时拒绝创建派生数据；`experience_fanout.py` 以固定组合消费者在
一次事务中完成 Achievement/Notification/Analytics/GrowthGraph 后统一 ACK。它已有真实
PostgreSQL 验证，但**尚不是完整进程**：没有统一入口、常驻 scheduler、部署健康检查、
payload-preserving DLQ/告警，也尚未承载 21/90 天节奏与服务 SLA。

Experience 闭环已新增成就反馈写入：`helpful/not_helpful/request_human` 进入 append-only
反馈表，其中 `request_human` 与 `source_kind=USER_REQUEST` 的 HumanTask、两类审计同事务
提交。真实 PostgreSQL 已验证并发重放、payload 冲突、审计失败回滚和 Consent 撤回拒绝；
共享 main、主体删除 worker 与人工响应 Named Action handler 尚未完成。

### 4.6 技术基线中声明但依赖未装

以下在技术基线文档里被声明，但**尚未加入 `pyproject.toml`**（OpenTelemetry 已于本轮加入并完成 SDK adapter）：

| 组件 | 用途 | 状态 |
|---|---|---|
| Redis | 缓存 / 队列 | 未装 |
| Temporal | 长流程编排（workflow_worker 的前提） | 未装 |
| mypy | 静态类型检查 | 未装（只有 ruff） |
| OpenTelemetry | 可观测性 / trace | 已声明并已接入 provider-neutral SDK adapter；collector/exporter 部署待配置 |

**"技术基线里写了"不等于"依赖已装"** —— 这正是 R14 的语义（写成文档的东西不会自己生效）。

本轮已将 OpenTelemetry API/SDK 加入运行时依赖，并完成 AI Runtime adapter；生产
collector/exporter 仍需部署配置。

### 4.7 远端仓库与 CI

- **GitHub 远端仓库尚未创建**（计划 `PoCP-Protocol/AiFamily`）。
- CI workflow 文件已写，但**从未在远端运行过**，无任何 CI 运行记录。
- 所有测试目前只在本地执行。

按 R4（测试须能在 CI 中**真实运行**）与 R14（架构测试必须在 CI 中运行）的字面要求，**当前的护栏严格来说尚未处于"被执行"状态** —— 它们在本地可运行，但没有任何机制阻止一次未跑测试的提交进入主线。这是当前最容易被忽视的治理债务，也正是源仓库的失败模式（全域只有一个真正生效的 CI workflow，且被 path filter 限定在三处，导致一个正在失败的不变量被提交进了主线）。

### 4.8 其它明确不存在

| 项 | 状态 |
|---|---|
| Teacher Workspace / Institution Console / Operations Console | `PLANNED_NO_CODE`，见 `CURRENT_PRODUCT_MAP.md` §4 |
| `frontend/web` | 未迁入，disposition = REVIEW_REQUIRED / BLOCKED |
| 14 个业务域（family/growth/assessment/journey/action/outcome/service/teacher/institution/commerce/community/tenancy 等） | `NOT_STARTED`，见 `CURRENT_DOMAIN_MAP.md` |
| domain events / outbox 机制 | PostgreSQL `outbox_events` 已被多个域写入；UI-09 已有首条 workflow-worker → Experience outbox 中继。统一 broker、多消费者投递账本与部署监控仍未完成 |
| `backend/platform/tenant` | manifest 列为 target，磁盘上不存在 |
| 任何域达到 `PRODUCTION` | **0 个**。前提条件（业务 API / 数据库 / 远端 CI）全部缺失 |

---

## 5. 已识别的文档漂移（本文件的核销清单）

### 5.1 本次已核销（原 V1 §5 指出的漂移）

| 漂移 | 原状态 | 现状 |
|---|---|---|
| `CURRENT_TECH_ARCHITECTURE.md` 写"FastAPI/SQLAlchemy/Alembic/PostgreSQL 在 AiFamily 当前不存在" | 已被 Wave 1 落地推翻 | 文件已更名 `CURRENT_TECHNOLOGY_BASELINE.md`；**该断言是否已修正需独立复核，见 §5.2** |
| `CURRENT_TECH_ARCHITECTURE.md` 写"frontend_mobile 判定为 KEEP_NON_PYTHON" | 已被 `project_owner_override` 推翻 | disposition 现为 MIGRATE，代码已实体迁入 |
| `MASTER_BLUEPRINT.md` 混装目标态与现状 | — | 已拆分：目标态 → `TARGET_ARCHITECTURE.md`，现状 → 本文件 V2 |
| 原 §5 称 `backend/intelligence/*` "不存在" | — | 已更新：`design_copilot` 已迁入但全 `NotImplementedError` |
| 原 §5 称 `backend/domains/*` "不存在于 AiFamily" | — | 已更新：5 个域已迁入，见 §1.6 |

### 5.2 未核销（需后续独立动作）

| # | 漂移 | 依据 |
|---|---|---|
| 1 | **`DOMAIN_REGISTRY.yaml` 状态全面滞后** —— 头部注释仍称"本表全部 status = NOT_STARTED，不含任何业务代码"，Wave 1/2 全部条目仍写 `NOT_STARTED`，与 §1.3/§1.6 矛盾 | R2 要求"canonical_path 下若存在代码，必须能追溯到本文件的一行登记"；登记行存在但 status 失真 |
| 2 | **`DOMAIN_REGISTRY.yaml` 缺 2 个已迁入域的登记** —— `market_intelligence`、`growth_plan` 有 manifest 条目且代码已在磁盘，但 registry 中无对应行 | R2 |
| 3 | **`tenancy` canonical path 与实际不一致** —— manifest target 写 `backend/platform/tenant`，该目录不存在；`TenantContext` 实际落在 `backend/platform/identity` | `MIGRATION_MANIFEST.yaml` → `platform_actor_tenant_context` |
| 4 | **`identity` 两条 registry 条目共用同一 canonical_path**（`platform_actor_tenant_context` + `auth_identity`），平台原语与业务身份域边界模糊 | R2 |
| 5 | **`growth_plan` stub 与未来 `journey` 域语义重叠**，Batch 4 前不裁决即违反 R2 | `CURRENT_DOMAIN_MAP.md` §3.16 |
| 6 | ~~**`CURRENT_TECHNOLOGY_BASELINE.md` 缺 YAML front matter**，且正文仍引用已废弃的 `docs/00_foundation/` 路径~~ —— **已修（T-10, 2026-08-29）**：front matter 已补，`docs/00_foundation/` / `docs/40_platform/` 引用已改指现路径 | `SYSTEM_MANIFEST.md` front matter 规范 |
| 7 | **`SYSTEM_MANIFEST.md` §5.1 列出的 `CURRENT_PROGRAM_STATUS.md` 与 `DOCUMENTATION_MAP.md` 尚不存在** | manifest 声明的 canonical 文档清单未齐 |
| 8 | ~~**多份文档仍引用旧路径** `docs/00_foundation/`、`docs/20_product/`、`docs/10_domain`、`governance/MIGRATION_PLAN_V2.md`~~ —— **已修（T-10, 2026-08-29）**：正文里的死路径引用已批量校正到 16 层结构下的真实路径。**唯一保留的例外**是 `CURRENT_AI_MAP.md` / `CURRENT_SYSTEM_BASELINE.md` / `TARGET_ARCHITECTURE.md` 三份 front matter 里的 `supersedes:` 字段 —— 它指向的是**已被取代的旧文档 id**，按定义就该是旧路径，改掉反而丢失溯源 | 文档架构 V1.0 归位后遗留的引用未同步 |
| 9 | **矩阵001 内部对 UI-19/UI-20 有两个不同状态** —— 主表 `GATE_BOUNDARY`，服务对象链回归表 `BACKEND_READY` | `CURRENT_PRODUCT_MAP.md` §2.1 SERVICE 段已记录 |
| 10 | **源仓库"三份自称当前基线"的裁决未完成** —— manifest 条目 `docs_current_baseline_CONTRADICTION` 状态 BLOCKED，其 blocking_action 要求人工裁决"AIFAMILY-000 与源仓库既有 `FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` 是同一决定被重复下达还是两个冲突方案" | 该裁决未完成前，**AiFamily 不得假设自己是唯一正在进行的 Python 迁移工作** |

---

## 6. 宪章执行状态（R14 视角的真实护栏覆盖）

| 规则 | 执行方式 | 真实状态 |
|---|---|---|
| R2 唯一领域真相 | `test_domain_registry.py` | 测试在，但 registry 数据已漂移（§5.2 #1） |
| R3 无 Manifest 不得入仓 | `test_migration_manifest.py` | 有效 |
| R7 领域不直连供应商 | `test_no_direct_provider_calls.py` | 有效（但当前无 AI 代码可违规） |
| R11 单一依赖管理 | `test_single_toolchain.py` | 有效 |
| R12 无隐式路径耦合 | `test_no_layout_coupling.py` | 有效，迁移中已修 6 处违规 |
| R13 历史文档不充当真相 | `test_docs_truth_boundary.py` | 部分（只检查存在性/非空/标记，不检查内容是否真实） |
| R1 唯一后端真相 | — | **无测试**。当前只有一个后端，属事实上满足 |
| R4 无测试不得称能力 | — | **无测试**。membership 域是活跃反例（§2.2） |
| R5 合成数据隔离 | — | **无测试**。Wave 1 起需在路由层禁止 `SYNTHETIC` 标记产物 |
| R6 / R8 / R9 / R10 | — | **无测试**。随能力落地补 |
| R14 架构测试必须在 CI 中运行 | — | **未满足**：无远端仓库、无 CI 运行记录（§4.7） |

**未被架构测试覆盖的规则只是意图，不是护栏。** 当前 6/14 条有机械执行，且这 6 条也只在本地运行。

---

## 7. 相关文档

| 文档 | 回答什么 |
|---|---|
| `SYSTEM_MANIFEST.md` | 系统身份与边界；哪些文档算真相 |
| `TARGET_ARCHITECTURE.md` | 要建成什么（全景图 / 独占区归属 / FGCN 落位） |
| `CURRENT_PRODUCT_MAP.md` | 有哪些产品/端，34 UI 逐屏状态 |
| `CURRENT_DOMAIN_MAP.md` | 业务真相由哪些 Domain 管理，边界与成熟度 |
| `CURRENT_AI_MAP.md` | AI 能力版图与成熟度 |
| `CURRENT_TECHNOLOGY_BASELINE.md` | 技术基线 |
| `governance/REPOSITORY_CONSTITUTION.md` | 14 条工程宪章 |
| `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` | Batch 划分与 disposition 分类法 |
