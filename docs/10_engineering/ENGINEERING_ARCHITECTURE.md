---
id: ENG-ARCH-001
title: 工程/技术架构
type: engineering
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# 技术架构 (Technical Architecture)

- **状态**: 见上方 front matter `status: current` — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29
- **与既有文档的关系**: 本文档在 `docs/00_system/CURRENT_TECHNOLOGY_BASELINE.md`（Wave 0 结束快照）基础上扩展为完整版，不推翻其已建立的断言（uv+pyproject.toml已建立、R11/R12约束、架构测试清单），仅补充 Wave 1 已发生的新事实（平台内核已有真实代码、frontend_mobile 判定变更）与尚未写清楚的分层/通信/前端技术栈细节。凡与 `CURRENT_TECHNOLOGY_BASELINE.md` 冲突之处，以本文档更新后的事实为准，且需要一次独立任务同步刷新该文件（见 `docs/00_system/CURRENT_SYSTEM_BASELINE.md` §5 说明）。
- **上游依据**: `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` 第0节保留清单、`governance/REPOSITORY_CONSTITUTION.md` R1/R2/R7/R10/R11/R12/R14

## 1. 技术栈全景

沿用 `MIGRATION_PLAN_V2.md` 第0节"V1没有做错的部分（保留）"列出的目标技术栈，不重新发明：

| 层 | 技术 | 现状 |
|---|---|---|
| 语言/运行时 | Python >= 3.12 | 已建立（`.python-version`, `pyproject.toml` `requires-python = ">=3.12"`） |
| Web框架 | FastAPI >= 0.115 | 已建立，仅 `/health` `/ready` 端点（`backend/apps/family_api`） |
| 数据校验 | Pydantic v2 (>=2.7) | 已声明依赖，尚无业务模型使用 |
| ORM | SQLAlchemy 2 (>=2.0, async) | 已用于 `backend/platform/persistence`（`AsyncSession`/`async_sessionmaker`） |
| 迁移工具 | Alembic (>=1.13) | 已声明依赖，尚无 revision 生成（阻塞项见 `DATA_ARCHITECTURE.md` §1） |
| 数据库 | PostgreSQL（生产）+ SQLite/aiosqlite（测试） | 生产驱动 `asyncpg`，测试驱动 `aiosqlite`；当前均未接入真实数据库（`unit_of_work.py` 的 `ping()` 已写好但未在CI中对真实Postgres验证） |
| 缓存/队列 | Redis | **计划保留但当前 `pyproject.toml` 未声明依赖**，是本文档发现的技术债之一（见第6节） |
| 长流程编排 | Temporal | **同上，未声明依赖**，`backend/workflow_worker` 进程尚未创建任何代码 |
| HTTP客户端 | httpx (>=0.27) | 已声明为 dev 依赖（当前用于测试，非运行时对外调用——运行时对外调用只能经 Model Gateway，见 R7） |
| 测试框架 | pytest (>=8.2) + pytest-asyncio (>=0.24) | 已建立，`tests/` 下已有 14 个测试文件（架构测试7个+平台内核测试6个+family_api测试1个） |
| Lint | Ruff (>=0.6) | 已配置 `[tool.ruff]`，规则集 `E,F,I,UP,B,SIM` |
| 类型检查 | mypy | **`pyproject.toml` 当前未声明**，是技术债（见第6节） |
| 可观测性 | OpenTelemetry | **当前未声明依赖**，是技术债（见第6节） |
| 依赖管理 | uv + `pyproject.toml` | 已建立（`uv.lock` 存在于仓库根），R11强制唯一工具链 |

**技术债说明（不回避）**：`MIGRATION_PLAN_V2.md` 第0节承诺保留 Redis/Temporal/mypy/OpenTelemetry 作为目标技术栈的一部分，但当前 `pyproject.toml` 的 `dependencies`/`optional-dependencies` 均未声明这四项。这不是矛盾——Wave 1 的范围本身就只是"平台内核+FastAPI入口"（见 `MIGRATION_MANIFEST.yaml` 条目 `fastapi_runtime_entrypoint`/`platform_*`），Redis/Temporal 是 workflow_worker 进程和长流程能力（Batch 4起的21/90天计划节奏）才需要的依赖，mypy/OpenTelemetry 是尚未排期加入CI的治理项。记录在此，防止后续开发者误以为"目标技术栈"已经等于"当前依赖清单"。

## 2. 三进程划分：职责边界与通信方式

沿用 `MIGRATION_PLAN_V2.md` 第0节"三进程划分：`family-api`(业务) / `ai-runtime`(智能) / `workflow-worker`(长流程)"，本仓库实际目录名为 `backend/apps/family_api`、`backend/intelligence`、`backend/workflow_worker`（后两者尚未创建代码，见 `MASTER_BLUEPRINT.md` §5 现状核对表）。

### 2.1 职责边界

| 进程 | 职责 | 不做什么 |
|---|---|---|
| `family_api` | 业务权威状态的读写入口（HTTP）；承载 `backend/domains/*` 的 api/application 层；调用 `backend/platform/*` 平台内核完成鉴权/审计/幂等/事务 | 不直接调用模型供应商（R7）；不产生 AI 推断结果 |
| `ai_runtime` | Model Gateway、Context Engine、Agent Runtime、Human Gate、Provenance、Evaluation 各一份（R10唯一AI Runtime）；产出 `Perspective`/`Recommendation`/`Hypothesis`/`Draft` | **不得直接 import 业务域的 repository**（R9硬约束的架构落地）；不写业务权威状态；canonical 写入只能经业务域自己的 Named Action |
| `workflow_worker` | 长流程编排（21/90天计划节奏推进、服务预约SLA超时处理、通知重试）；由 Temporal 驱动 | 不是业务状态的第一权威来源，只是状态转换的调度器；状态本身仍落在业务域的表里 |

### 2.2 通信方式：Command / Query / Event / Port

进程间与域间通信严格限定为以下四种，禁止绕过（架构测试强制，见 `MIGRATION_PLAN_V2.md` 验收标准第2条"是否存在双写"）：

- **Command**：改变业务权威状态的请求（如 `SubmitAssessment`、`ConfirmGrowthHypothesis`），必须经由目标域自己的 Named Action 处理，产生 AuditEvent（R6）。
- **Query**：只读投影请求，可跨域读取（如 `CustomerServiceBookingProjection`），不产生副作用。
- **Event**：域内状态变化后发出的领域事件（Outbox模式，沿用矩阵001已验证的 Outbox+幂等消费者设计），供其它域/进程异步响应，不建立同步跨域直接调用。
- **Port**：域内 `application/ports` 定义的抽象接口，由 `infrastructure` 层实现。`ai_runtime` 消费业务域数据必须经由业务域暴露的 Query Port 或已发布的 Event，不允许 `from backend.domains.xxx.infrastructure.repository import XxxRepository` 这类跨域直接 import。

**禁止事项（架构测试待补）**：跨域直接 import repository；`ai_runtime` 直接持有业务域的 SQLAlchemy Session；业务域直接 import 供应商 SDK（R7，已有 `tests/architecture/test_no_direct_provider_calls.py`）。

## 3. 领域四层结构约定

沿用 `MIGRATION_PLAN_V2.md` 第0节的四层结构：

```text
backend/domains/<domain_name>/
  api/            {routes, requests, responses}
  application/    {commands, queries, handlers, ports}
  domain/         {entities, value_objects, policies, events, errors}
  infrastructure/ {sqlalchemy_models, repositories, projections}
```

### 3.1 真实例子：`backend/platform/*` 不是 domain，是 platform——区别在哪

Wave 1 已落地的 `backend/platform/identity`、`backend/platform/authorization`、`backend/platform/consent`、`backend/platform/audit`、`backend/platform/idempotency`、`backend/platform/persistence` **不遵循**上述四层结构，这不是遗漏，是设计上的刻意区分：

| 维度 | `backend/platform/*`（平台层） | `backend/domains/*`（域层，未来） |
|---|---|---|
| 是否有业务语义 | 否——`ActorContext`/`PolicyEngine`/`ConsentGate`/`AuditRecorder`/`IdempotencyKey`/`UnitOfWork` 都是**跨域共享的技术原语**，不认识 Family/GrowthNeed/ServiceCase 等业务概念 | 是——每个域认识且只认识自己的业务实体（如 `family` 域认识 `Family`/`Person`/`Consent`） |
| 是否分四层 | 否，每个平台子模块只是"一个概念一个/两个文件"（如 `consent/models.py` + `consent/gate.py`） | 是，强制 api/application/domain/infrastructure 四层 |
| 被谁依赖 | 被所有域依赖（`backend.platform.identity.context.ActorContext` 是 `backend.platform.authorization.policy.PolicyEngine` 的直接依赖，见 `policy.py:25`） | 域之间不允许互相直接依赖 repository，只能经 Port/Event |
| 典型代码证据 | `backend/platform/authorization/policy.py` 的 `PolicyEngine.check()`——不知道"预约"或"测评"是什么，只知道 `(actor, action, resource_type)` 三元组和 `human_only` 标记 | 未来 `backend/domains/assessment` 的 `application/commands/submit_assessment.py` 才知道"提交测评"的业务规则 |

一句话区分：**platform 层回答"任何域都会遇到的通用问题"（我是谁/我能不能做这个/这次写入有没有留痕/这次请求重复了没有/事务边界在哪），domain 层回答"这个特定业务概念该怎么运作"**。`backend/platform/persistence/unit_of_work.py` 的 docstring 明确写了这个判断的来源：源仓库从未有正式 UnitOfWork 类，只有 membership 域私有的 `commit()`/`_stage()` 手写约定——这正是"平台原语应该跨域共享而不是域内重造"这条设计原则要防止的具体故障模式。

### 3.2 AI Runtime 隔离规则（承接 R9/R10）

`backend/intelligence/*` 落地时同样不套用四层结构，但理由与 platform 层不同：AI Runtime 内部子模块（Model Gateway/Context Engine/Agent Runtime/Human Gate）本身没有"业务domain"意义上的持久化权威状态，它们的产出（Draft/Hypothesis/Explanation/Proposal）必须经由消费方业务域的 Named Action 才能变成权威状态——`may_mutate_business_state=false` 是 AI Runtime 每个子模块的硬约束（`MIGRATION_PLAN_V2.md` 第0节保留清单）。

## 4. 前端技术栈

| 前端 | 技术栈 | disposition | 现状 |
|---|---|---|---|
| `frontend/mobile` | Expo / React Native，TypeScript，`@tanstack/react-query` 等 | **MIGRATE**（project_owner_override 已推翻此前 KEEP_NON_PYTHON 判定："34个UI已经做得很好，需要把整个Mobile迁移过来"，见 `MIGRATION_MANIFEST.yaml` 条目 `frontend_mobile`） | 已实体迁入，34个UI屏幕文件全部存在于 `frontend/mobile/app/ui/UI-02.tsx` ... `UI-34.tsx`，另有 `(tabs)/`、`oauth/`、`dev/theme-lab.tsx` |
| `frontend/web` | 无组件框架、无 bundler，build 脚本仅 `tsc --noEmit` | **REVIEW_REQUIRED / BLOCKED** | 未迁入 AiFamily，`MIGRATION_MANIFEST.yaml` 明确"24个 spec 文件价值更多是后端路由的契约参照，不是可部署UI"——是否迁移待人类裁决 |

**阻塞动作（承接自 manifest）**：`frontend_mobile` 消费 ~40+ 后端路径 + 4个 `/auth/*` 端点，其中9+屏幕依赖 `/dev/*` 合成路由（源仓库 `dev-platform-surfaces.service.ts`/`dev-core-growth.service.ts`，disposition=ARCHIVE 但被真实消费，见 `MIGRATION_MANIFEST.yaml` 条目 `family_dev_surface_services`）。Python `family_api` 必须先满足 mobile 依赖的端点清单，否则 34 个屏幕中最多 24 个会因缺 `/dev/*` 而白屏——这条约束直接决定 Batch 1-3 的 API 设计优先级不能只按后端域的"重要性"排序，必须同时满足前端已经存在的调用面。

## 5. CI / 测试策略：五层测试体系

依据宪章 R14（架构测试强制）与 `MIGRATION_PLAN_V2.md` 第7节验收标准，测试体系分五层：

| 层 | 目录 | 用途 | 当前现状 |
|---|---|---|---|
| 架构测试 | `tests/architecture/` | 机械检验宪章可检验规则（R2/R3/R7/R11/R12/R13） | 已建立6个测试文件：`test_domain_registry.py`、`test_migration_manifest.py`、`test_no_direct_provider_calls.py`、`test_single_toolchain.py`、`test_no_layout_coupling.py`、`test_docs_truth_boundary.py`，另有 `conftest.py` |
| 单元测试 | `tests/platform/<module>/test_*.py` | 验证平台内核/域内业务规则的最小单元 | 已建立6个：identity/authorization/consent/audit/idempotency/persistence 各一个 |
| 集成测试 | `tests/apps/family_api/test_routes.py`（现状）；未来 `tests/domains/<domain>/integration/` | 验证跨模块协作（如 UnitOfWork+Repository+真实/内存数据库） | 已有1个（对 `/health` `/ready`），域集成测试尚不存在 |
| 契约测试 | 对应源仓库 `test_oracle_excluded_contract_specs`（`evals/subject-isolation`、`evals/authorization-planes`），target: `tests/architecture` | 验证跨租户/跨家庭隔离等安全契约不被打破，作为需求规格断言迁移，不作为覆盖率证明 | 未迁移，disposition=MIGRATE，status=PLANNED |
| 验收测试 | 每个Batch完成时的 e2e 验证，对照 `MIGRATION_PLAN_V2.md` 第7节五条验收标准 | 验证一个Batch范围内的业务闭环端到端可用 | Batch 1尚未开始，无验收测试 |

**测试纪律（承接R4伤疤教训）**：`governance/MIGRATION_MANIFEST.yaml` 记录的最大教训是 `membership` 域 2627行代码但零测试目录，其 docstring 声称的 `tests/conftest.py` 在磁盘上不存在——"文档声称测试存在但磁盘找不到"被 `MIGRATION_PLAN_V2.md` 第7节验收标准第4条显式列为不可接受的既往问题重演。任何域从 `NOT_STARTED` 变为 `ACTIVE` 必须同时在 `DOMAIN_REGISTRY.yaml` 登记测试路径（R4）。

## 6. 待人类架构师裁决/待补的技术债

1. **Redis/Temporal/mypy/OpenTelemetry 尚未声明为依赖**——`pyproject.toml` 只覆盖了 Wave 1 平台内核+FastAPI 所需的最小依赖集，`workflow_worker` 进程创建时（Batch 4 前后）必须补齐 Temporal+Redis；mypy/OpenTelemetry 接入 CI 的时间点未排期，建议不晚于 Batch 3（Family Core，第一个真正写业务权威状态的域）落地时补上，理由是那时开始才有"业务状态错误"和"生产可观测性缺失"的真实风险面。
2. **跨域 Port 契约的具体形态未设计**——第2节只给出通信方式的分类（Command/Query/Event/Port），尚无一份"哪些数据允许通过Query跨域读、哪些必须留在Event异步"的具体契约清单，这是 Batch 3（Family Core，平台内核原语与首个业务域交界处）落地时必须补的设计文档，不能靠"四种通信方式已经分类"就当作已完成。
3. **契约测试（`evals/subject-isolation`、`evals/authorization-planes`）迁移的排期未定**——`MIGRATION_MANIFEST.yaml` 只登记为 `status: PLANNED`，未指定属于哪个 Batch，建议不晚于 Batch 3（引入真正的租户/家庭隔离矩阵）之前完成迁移，否则 Batch 3 的隔离测试会重新发明源仓库 `family-scope.integration.spec.ts` 已经验证过的负例矩阵。
