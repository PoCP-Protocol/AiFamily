# 04 — Python 目标差距分析 (Gap Analysis for Wave 1 Platform Kernel)

- **用途**: 本文档是 Wave 1（平台内核）的施工前置条件清单。列出从零建的每一项平台原语，标注 TS 侧是否有可参考实现、Python 侧当前现状（全部是"不存在，须新建"），以及依赖管理/运行时入口/数据库迁移工具三项跨切前置问题。
- **核心结论**：Python 侧全域 grep `ActorContext`/`TenantContext`/`UnitOfWork`/`DomainEvent` 等平台原语精确类名 = **0 命中**。计划假设的平台基础设施在 Python 侧完全不存在，Wave 1 不是"迁移"，是"第一次创建"。

---

## 1. 平台内核逐项差距

### 1.1 ActorContext / TenantContext

| 项目 | 内容 |
|---|---|
| TS 侧参考 | 无直接对应物。业务规则参考见 `auth`/`family-scope` 模块 |
| Python 侧现状 | **不存在**。唯一域内等价物：`backend/domains/membership/application/context.py:20-27` 的 `ActionContext` dataclass，但仅 `membership` 域私有，不是共享基础设施 |
| Wave 1 目标 | `backend/platform/identity`, `backend/platform/tenant` |
| 施工提示 | 不要直接把 `membership` 私有的 `ActionContext` 提升为共享类——它是为单一域设计的，字段集未必满足租户隔离所需的完整性（对比 `family-scope.integration.spec.ts` 的 6 层绑定链，`ActionContext` 大概率缺少 TenantFamilyBinding / TenantAccountMembership 层级的字段）。应从测试断言反推所需字段，而不是从现有代码抠字段。 |

### 1.2 Authorization Policy

| 项目 | 内容 |
|---|---|
| TS 侧参考 | `apps/api/src/modules/auth/family-authorization.policy.ts`（82 行，含未知角色 fail-closed 测试）、`family-scope.guard.ts` |
| Python 侧现状 | **不存在** |
| Wave 1 目标 | `backend/platform/authorization` |
| 施工提示 | 业务规则（角色→权限映射）要重译，来源见 `family-authorization.policy.ts`；验收标准见 `family-scope.integration.spec.ts`（TEST_ORACLE，6 层隔离矩阵逐层 DENY）。fail-closed 默认拒绝这一机制性质必须保留，是 TS 侧唯一值得直接借鉴的设计决策。 |

### 1.3 Consent

| 项目 | 内容 |
|---|---|
| TS 侧参考 | `specs/ontology/consent.schema.yaml`（schema 定义）、`apps/api/src/modules/family/grant-consent.integration.spec.ts`（交叉家庭拒绝矩阵，TEST_ORACLE） |
| Python 侧现状 | **不存在** |
| Wave 1 目标 | `backend/platform/consent` |
| 施工提示 | schema 可直接参照迁移，但"交叉家庭拒绝矩阵"的行为语义必须逐条对照 `grant-consent.integration.spec.ts` 验证，这是 family 域下游（Wave 3）强依赖的前置能力——consent 缺失会导致 family_core 的否定推断守卫（不得从 relationship 推断 consent）无法成立。 |

### 1.4 Audit

| 项目 | 内容 |
|---|---|
| TS 侧参考 | `AuditModule`（`audit.module.ts` 8 行 + `audit.service.ts` 22 行）——最小实现 |
| Python 侧现状 | **不存在** |
| Wave 1 目标 | `backend/platform/audit` |
| 施工提示 | TS 侧实现"值得参考但太薄"，不能直接照搬。`REPOSITORY_CONSTITUTION.md` R6 要求任何权威状态写入必须产生 `AuditEvent`，且至少记录 actor / tenant / action / resource / before / after / reason / correlation_id / timestamp 九个字段——TS 侧 22 行的 `audit.service.ts` 大概率没有覆盖全部九个字段，需要按 R6 的完整字段清单重新设计，不是简单翻译现有代码。 |

### 1.5 Idempotency

| 项目 | 内容 |
|---|---|
| TS 侧参考 | 无独立中间件/装饰器实现的记录 |
| Python 侧现状 | 只有字段级去重（`membership` infrastructure 的 `_by_idempotency_key`），无中间件/装饰器抽象 |
| Wave 1 目标 | `backend/platform/idempotency` |
| 施工提示 | 需要从零设计一个可复用的幂等性中间件/装饰器抽象，`membership` 域现有的字段级实现只能作为"这个域曾经怎么临时解决这个问题"的反面参考，不是可提升的组件。 |

### 1.6 Persistence / UnitOfWork

| 项目 | 内容 |
|---|---|
| TS 侧参考 | 无直接对应的正式 UnitOfWork 抽象记录 |
| Python 侧现状 | `membership/infrastructure/sqlalchemy_repository.py` 的 `commit()`/`_stage()` 是手写约定，非正式 UnitOfWork 类 |
| Wave 1 目标 | `backend/platform/persistence` |
| 施工提示 | 同样不要直接提升 `membership` 的手写约定，应设计标准的 UnitOfWork 模式（`__enter__`/`__exit__` 或显式 `commit`/`rollback` 生命周期），并让 `membership`、`family` 等域统一依赖它，避免重复各域各写一套"手写约定"的问题再次出现。 |

### 1.7 Model Gateway

| 项目 | 内容 |
|---|---|
| TS 侧参考 | `packages/ai-gateway/src/index.ts`（894 行）——唯一真实网关实现，Routing/Timeout/Admission/FailClosed/Provenance/HumanGate 均真实存在；另参考 `packages/principal-ai/src/index.ts`、`packages/principal-runtime/src/index.ts` |
| 违规先例（必须避免重演） | `apps/api/src/modules/orchestration/llm-gateway/family-llm-gateway.service.ts:58-63` 业务服务内部裸 `new OpenAICompatibleAiGateway`，绕过 DI、绕过 fail-closed 工厂、绕过审计——这是 `REPOSITORY_CONSTITUTION.md` R7/R14 的核心伤疤 |
| Python 侧现状 | **不存在**，任何对应物 |
| Wave 1 目标 | `backend/intelligence/model_gateway` |
| 施工提示 | 架构与策略常量作为设计参考重译，**不搬 TS 运行时代码**。必须同 PR 配套 `tests/architecture/test_no_direct_provider_calls.py`（R14 要求），确保"禁止业务模块直连供应商"这条策略不会像 TS 侧一样写成常量却没有代码强制执行。三种历史接入模式（`principal.module.ts` 的 DI+fail-closed 最严、`family-model-gateway.provider.ts` 的双 env 门控、`llm-gateway` 的裸 new 违规）应统一收敛为唯一一种，参照最严格的 fail-closed 工厂模式。 |

### 1.8 FastAPI Runtime Entrypoint

| 项目 | 内容 |
|---|---|
| TS 侧参考 | 不适用（这是 Python 运行时问题，NestJS 的入口模式仅供思路参考） |
| Python 侧现状 | **不存在**。全仓库零个 `FastAPI()`/`uvicorn.run()`/`include_router()` 首方调用；唯一 `APIRouter`（`product_intelligence/api/routes.py`）自述"Not mounted into any app yet" |
| Wave 1 目标 | `backend/apps/family_api` |
| 施工提示 | Python 侧从未有过运行时入口，这是第一次创建，不存在"迁移"的语义，只有"新建"。建立入口后第一件事应是挂载 `product_intelligence` 的现有 router，验证端到端可用性。 |

---

## 2. 依赖管理现状（跨切前置问题 1）

- **现状**: 全仓库零个 `pyproject.toml`/`requirements*.txt`/lock 文件。两个 venv 存在于磁盘但无对应 manifest，依赖集只能靠翻 `site-packages` 的 `.dist-info` 反推。
- **不可移植产物**: `apps/ai-runtime/.venv/Lib/site-packages/_editable_impl_family_ai_runtime.pth` 硬编码绝对路径 `D:\family-ai\50_开发_dev\apps\ai-runtime\src`，换机即失效。
- **AiFamily 侧现状**: 已用 uv + `pyproject.toml` 建立（`MIGRATION_MANIFEST.yaml` 条目 `dependency_management`, `status: DONE`），对应 `REPOSITORY_CONSTITUTION.md` R11。
- **Wave 1 施工前置**: 每个新建的 `backend/platform/*` 子包在创建时必须同步声明进 `pyproject.toml` 的可安装包结构，禁止依赖 cwd/`sys.path` 注入解析导入（R12），这是源仓库 `backend/domains/*` 全部违反的问题（`from packages.contracts.evidence import Provenance` 这类裸顶层导入必须钉在 `50_开发_dev/backend` 才能跑）。

---

## 3. FastAPI 入口现状（跨切前置问题 2）

- **现状**: 不存在。见第 1.8 节。
- **Wave 1 施工前置**: 在写任何域代码之前，先建立一个最小可运行的 `backend/apps/family_api` 入口（哪怕只挂载健康检查路由），并配套一个可在本地/CI 跑起来的启动脚本。理由：源仓库最大的教训之一是"5 个 Python 域目录存在但全部无运行时入口"——如果 AiFamily 重复这个顺序（先写域代码，入口留到最后），会重演同样的"代码存在但从未被验证过真的能跑起来"的风险。

---

## 4. 数据库迁移工具选型问题（跨切前置问题 3）

- **现状**: `database/migrations` 下 58 个手写 SQL 文件（0001-0058），经 `tools/migrate.mjs` 顺序应用，非 TypeORM/Prisma/Alembic 风格。
- **已知缺陷（必须先解决才能生成 Alembic 首个 revision）**:
  1. **4 组文件名重号**：`0022`/`0023`/`0024`/`0053` 各有两个不同内容的文件。在生成 Alembic revision chain 前，必须先确定这 4 组重号文件的真实应用顺序（哪个先被 `schema_migrations` 表记录为已应用，哪个是后来试图重新利用同一编号的第二次尝试），否则 Alembic 生成的 revision 图会与真实历史数据库状态不一致。
  2. **死列共存**：`growth_profiles` 表存在两代列——`0003` 引入的 `subject_type`/`subject_ref_id` 被 `0007` 追加的 `profile_scope`/`subject_person_id` 取代，但旧列**未被删除**。生成 Alembic baseline 前必须决定：保留旧列做兼容读（并在 Python ORM 模型中显式标注为 deprecated），还是先在源仓库补一个删除旧列的迁移再对齐。
- **Wave 1 施工前置**: `MIGRATION_MANIFEST.yaml` 条目 `database_schema` 的 `blocking_action` 已明确写出："Alembic 首个 revision 生成前必须先解决 4 组重号并决定死列去留"。这是一个**必须先做人工历史考古**才能继续的任务，不能靠自动化工具直接从当前 schema 反推出干净的 Alembic 历史——因为 4 组重号意味着"当前 schema 状态"本身可能有歧义（取决于两个同编号文件谁最后生效）。
- **建议顺序**:
  1. 先查 `schema_migrations` 追踪表的真实记录，确定重号文件的实际应用胜出者
  2. 对比两个重号文件内容，确认败者版本的改动是否已被后续迁移覆盖或从未生效
  3. 决定 `growth_profiles` 死列去留
  4. 以上确定后，才能用 `alembic revision --autogenerate` 生成 Python 侧的首个 baseline revision

---

## 5. Wave 1 施工前置条件清单（汇总检查表）

在开始写任何 Wave 1 平台内核代码之前，以下条件应逐一确认：

- [ ] `pyproject.toml` 已建立并声明可安装包结构（`status: DONE`，已完成）
- [ ] 数据库迁移的 4 组重号已完成人工考古，确定线性顺序
- [ ] `growth_profiles` 死列去留已决定
- [ ] 最小 FastAPI 入口已建立（哪怕只有健康检查路由）
- [ ] `tests/architecture/test_no_direct_provider_calls.py`（R7/R14）与 Model Gateway 同 PR 落地，不能只写网关不写强制测试
- [ ] `tests/architecture/test_no_layout_coupling.py`（R12）已能拦截裸顶层导入模式
- [ ] ActorContext/TenantContext 字段集已从 `family-scope.integration.spec.ts` 的 6 层绑定链反推完整，而非从 `membership` 私有 `ActionContext` 抠字段
- [ ] Audit 字段集已对照 R6 的九字段要求（actor/tenant/action/resource/before/after/reason/correlation_id/timestamp）设计，而非照搬 TS 侧 22 行的最小实现
- [ ] **`docs_current_baseline_CONTRADICTION` 已获得人工裁决**（见报告 02 第 9 条）——若源仓库既有 Python-only 迁移计划与本次 AIFAMILY-000 是同一决定，Wave 1 的范围可能需要重新框定，此项应在其他前置条件之前优先处理

以上前置条件中，最后一项（三份矛盾基线文档的裁决）不是纯技术问题，但会直接影响 Wave 1 的范围与优先级判断，因此被列入本清单而非仅停留在报告 02。
