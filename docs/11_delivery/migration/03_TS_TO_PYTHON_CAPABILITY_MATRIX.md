# 03 — TS → Python 能力映射矩阵 (Capability Matrix)

- **用途**: 本文档是 Wave 3+ 执行者的施工图。每一行回答四个问题：这个能力现在活在 TS 侧哪个文件、去哪个测试文件找验收标准、Python 侧目标位置在哪、disposition 是什么。
- **disposition 定义**（与 `governance/MIGRATION_MANIFEST.yaml` 一致）：
  - `MIGRATE` — 行为语义直接搬运，允许在 Python 侧重新实现但不改变契约
  - `REIMPLEMENT` — 只保留设计参考/规则参考，代码从零写，通常因为 TS 实现本身有架构问题不宜复制
  - `CONTRACT_ONLY` — 只搬语义/契约进文档或宪章，不搬代码
  - `ARCHIVE` — 不迁移，留作历史证据
  - `DELETE` — 不迁移，建议删除
  - `REVIEW_REQUIRED` — 需要人工裁决后才能定 disposition

---

## 1. NestJS 生产模块 → Python 目标

### 1.1 `auth` 模块

| 项目 | 内容 |
|---|---|
| 源文件 | `apps/api/src/modules/auth`（1546 行） |
| 关键子文件 | `family-authorization.policy.ts`（82行，含未知角色 fail-closed 测试）、`family-scope.guard.ts` |
| 运行时状态 | **真实**，连真实 Postgres（`identity_sessions`/`otp_challenges`/`accounts`/`tenants` 等表） |
| 测试覆盖 | 有，`family-scope.integration.spec.ts` 是完整的租户-家庭隔离矩阵测试（见第 3 节 TEST_ORACLE） |
| 已知替换点 | `OtpService` 的 `StubOtpSender` 是显式标注的替换点（非生产短信发送） |
| disposition | **MIGRATE**（identity 部分）+ **REIMPLEMENT**（authorization policy 部分，见下） |
| Python 目标 | `backend/platform/identity`（身份/会话），`backend/platform/authorization`（策略引擎） |
| 验收标准来源 | `apps/api/src/modules/auth/family-scope.integration.spec.ts` — 6 层绑定链（Account→Person→FamilyMembership→TenantFamilyBinding→TenantAccountMembership→Session）逐层 DENY 测试，是 Wave 1 平台内核的核心 TEST_ORACLE |
| 施工提示 | authorization policy 的**业务规则**要重译（角色→权限映射逻辑），但底层机制（fail-closed 默认拒绝）必须保留；不要把 TS 的 Guard/Decorator 装饰器模式直接映射成 Python，改用依赖注入式的显式检查函数 |

### 1.2 `family` 模块

| 项目 | 内容 |
|---|---|
| 源文件 | `apps/api/src/modules/family`（14091 行含 specs，核心 `family.service.ts` 2293 行） |
| 运行时状态 | **真实**，全仓库最大服务文件，60+ 路由，真实 Postgres（families/persons/consents 等） |
| 测试覆盖 | 有，e2e/integration/spec 全覆盖 |
| disposition | **REIMPLEMENT** |
| Python 目标 | `backend/domains/family` |
| 验收标准来源 | `family-core-integration.e2e-spec.ts`（M1-E2E-01/07/08：family→parent→child→relationship→lifestage→consent 全链路 + 否定推断守卫——不得从 relationship 推断 consent、不得从 birthdate 推断 lifestage）；`family.e2e-spec.ts`（E2E-M2-101~105：onboarding→perspective→profile→report→journey 全链路，含"确认 profile 产生零 AI/Model 事件"的否定断言） |
| **必须显式处理的子问题** | `dev-platform-surfaces.service.ts`（202行）与 `dev-core-growth.service.ts`（534行）自述 `data_source: 'SYNTHETIC_DEV_ONLY'`、`model_gateway: 'NOOP_NOT_INVOKED'`，含 24 张硬编码 UI 卡片，却挂在生产路由 `/:familyId/dev/*` 上，被 `apps/mobile` 的 9+ 个真实屏幕（UI-10/11/12/22/23/25/27/28/29）消费。**这两个服务本身 disposition = ARCHIVE（不作为业务代码迁移），但 Wave 3 重建 family 域时必须显式决定这些屏幕的新数据来源**，否则移动端切换后端后会白屏。这不是"清理了假数据"，是"制造了新的功能回归"，必须在同一 PR 内提供替代数据源或明确降级方案。 |

### 1.3 `model` 模块

| 项目 | 内容 |
|---|---|
| 源文件 | `apps/api/src/modules/model/family-assessment-model.provider.ts`（23 行） |
| 运行时状态 | 目录名为 `modules/model` 但根本不是 Nest module，只是裸 provider；default 走确定性 fallback，真实路径靠双 env 开关 |
| 测试覆盖 | 未在浓缩发现中提及有专门测试 |
| disposition | **REVIEW_REQUIRED**（`status: BLOCKED`） |
| Python 目标 | 待裁决，可能并入 `backend/intelligence/model_gateway` 或独立评估域 |
| 验收标准来源 | 待补充——因为 disposition 未定，暂无施工标准 |
| 施工提示 | 在裁决前不要假设它的双 env 开关逻辑值得保留；23 行的裸 provider 大概率应被 Model Gateway 的统一路由取代，而不是单独迁移 |

### 1.4 `orchestration` 模块

| 项目 | 内容 |
|---|---|
| 源文件 | `apps/api/src/modules/orchestration`（5519 行） |
| 运行时状态 | 真实，明确设计为不写 Growth 权威表（仅写自己的 non-canonical 表，见 `orchestration.repository.ts:106` 注释） |
| disposition | **MIGRATE** |
| Python 目标 | `backend/platform/orchestration` |
| 已知违规子问题 | `orchestration/llm-gateway/family-llm-gateway.service.ts:58-63` 在 domain service 内部裸 `new OpenAICompatibleAiGateway`，违反代码自身声明的 `AI_GATEWAY_POLICY.business_module_direct_provider_call = 'forbidden'`（见 `packages/ai-gateway/src/index.ts:544-560`）。此条已单独登记为 `orchestration_llm_gateway_violation`，`disposition: REVIEW_REQUIRED`，`blocking_action`: REIMPLEMENT 时必须走 R7 的 Model Gateway，不得重复此违规 |
| 施工提示 | 迁移主体逻辑时，**必须**把 `family-llm-gateway.service.ts` 的直连模式替换为通过 `backend/intelligence/model_gateway` 调用，这是 `REPOSITORY_CONSTITUTION.md` R7/R14 明确要求架构测试强制拦截的模式，不能只在 code review 里口头把关 |

### 1.5 `principal` 模块

| 项目 | 内容 |
|---|---|
| 源文件 | `apps/api/src/modules/principal`（2337 行） |
| 运行时状态 | 真实，连真实 Postgres（`principal_*` 表），明确不写 Growth 权威状态，DI 工厂 fail-closed 最严格（三种模型网关接入模式中最严的一种，见 `principal.module.ts:19-34`） |
| disposition | **MIGRATE** |
| Python 目标 | `backend/intelligence/principal` |
| 验收标准来源 | `*.livecheck.ts`（命名故意避开 `.spec.ts` 使其不被 CI 收集，是真实外部调用的手动烟雾测试，非生产代码，但对验证真实供应商连通性有价值）——登记为 `principal_livecheck_scripts`, `disposition: TEST_ORACLE` |
| 施工提示 | fail-closed 工厂模式是三种模型网关接入方式里最严格的一种，应作为 Python 侧 Model Gateway 客户端封装的默认参考范式，而不是 `family-model-gateway.provider.ts` 的双 env 门控模式（见 R10 伤疤：三套互不相同的接入模式并存本身就是问题） |

### 1.6 `waf` 模块

| 项目 | 内容 |
|---|---|
| 源文件 | `apps/api/src/modules/waf/waf-domain.service.ts`（261 行） |
| 运行时状态 | 死代码（纯内存 Map，零路由引用，唯一消费者是自己的 spec 文件） |
| disposition | **ARCHIVE** |
| Python 目标 | 无 |
| 施工提示 | 不要迁移。若未来需要类似能力，从零设计，不要以此为参考起点（详见报告 02 第 1 条）。 |

---

## 2. Python 域 → Python 目标（域内重建/补测）

### 2.1 `product_intelligence`

| 项目 | 内容 |
|---|---|
| 源路径 | `backend/domains/product_intelligence`（21 文件 / 1492 行） |
| 结构 | domain/application/infrastructure/api/tests 五层俱全 |
| 测试覆盖 | 有（唯一有测试的 Python 域），含 `test_hypothesis_validation_guardrail.py`——真实 TEST_ORACLE：AI actor 不能验证 hypothesis |
| 运行时状态 | `api/routes.py` 自述"未挂载"；无 Postgres 集成测试（只有 SQLite）；代码自称 V0.1 |
| disposition | **MIGRATE**（`status: APPROVED_PENDING_REVIEW`） |
| 与计划的偏差 | 计划称其"已具备生产条件"，实测为 V0.1、路由未挂载、无 Postgres 集成测试——仍判定为 MIGRATE，但**完成定义必须包含补测试与挂载**，不能直接照搬现状当作完成 |
| Python 目标 | `backend/domains/product_intelligence`（同名，位置不变） |
| 验收标准来源 | `backend/domains/product_intelligence/tests/test_hypothesis_validation_guardrail.py` |

### 2.2 `membership`（最大单点风险）

| 项目 | 内容 |
|---|---|
| 源路径 | `backend/domains/membership`（2627 行，五域中最大） |
| 结构 | `domain/policies.py` 含真实不变量（`assert_tier_transition_legal` 等） |
| 测试覆盖 | **零测试目录**。`sqlalchemy_repository.py:8-9` docstring 声称的 `tests/conftest.py` 在磁盘上不存在——文档与代码矛盾 |
| 关键护栏声明未被强制 | `policies.py:24-28` 的 `FORBIDDEN_TIER_FIELD_TOKENS`（禁止 `score`/`rank`/`level` 字段）注释自称"由 guardrail test 强制"，该测试不存在 |
| disposition | **REVIEW_REQUIRED**（`status: BLOCKED`） |
| blocking_action | 必须先写出 `FORBIDDEN_TIER_FIELD_TOKENS` 的 guardrail test，再决定 MIGRATE vs REIMPLEMENT |
| 与计划的偏差 | 计划完全没提到此域。它比 `product_intelligence` 代码量更大、不变量更真实，但零测试——是审计中发现的最大单点风险 |
| Python 目标 | 待定（`backend/domains/membership`，条件是先通过 blocking_action） |
| 施工提示 | 不要因为代码"看起来完整"（含真实策略层、真实仓储）就跳过补测试直接判 MIGRATE。这正是 `REPOSITORY_CONSTITUTION.md` R4 的核心伤疤案例：代码行数不是成熟度，文档声明的测试不算测试 |

### 2.3 `product_strategy`

| 项目 | 内容 |
|---|---|
| 源路径 | `backend/domains/product_strategy`（159 行） |
| 结构 | 仅 domain + ports + fake repository，无真实持久化，无测试 |
| disposition | **REIMPLEMENT** |
| Python 目标 | `backend/domains/product_strategy` |
| 施工提示 | 现有代码只是骨架级参考，重写时不必受其结构约束 |

### 2.4 `market_intelligence`

| 项目 | 内容 |
|---|---|
| 源路径 | `backend/domains/market_intelligence`（52 行） |
| 结构 | 仅 `domain/entities.py` + `errors.py`，空目录占位 api/application/infrastructure |
| disposition | **ARCHIVE**（`status: NOT_MIGRATING`） |
| Python 目标 | 无 |

### 2.5 `growth_plan`（Python stub）

| 项目 | 内容 |
|---|---|
| 源路径 | `backend/domains/growth_plan`（37 行） |
| 结构 | 单文件，仅错误类型枚举，注释称"mirroring journey-plan.service.ts"但无实体 |
| disposition | **ARCHIVE**（`status: NOT_MIGRATING`） |
| Python 目标 | 无 |
| 施工提示 | 若未来需要 growth plan 能力，应从 TS 侧的 `journey-plan.service.ts`（若存在于 orchestration 或其他模块）找参考，不要以这个 37 行 stub 为起点 |

---

## 3. TEST_ORACLE 索引（完整清单）

以下测试文件是 Wave 3+ 验收标准的权威来源，disposition 均为 `TEST_ORACLE`（即：不作为业务代码迁移，但其断言必须在 Python 侧重新验证等价行为）：

| 测试文件 | 覆盖范围 | 关键断言 |
|---|---|---|
| `apps/api/src/modules/family/family-core-integration.e2e-spec.ts` | M1-E2E-01/07/08 | family→parent→child→relationship→lifestage→consent 全链路 + 否定推断守卫（不得从 relationship 推断 consent、不得从 birthdate 推断 lifestage） |
| `apps/api/src/modules/family/family.e2e-spec.ts` | E2E-M2-101~105 | onboarding→perspective→profile→report→journey 全链路，含"确认 profile 产生零 AI/Model 事件"的否定断言 |
| `apps/api/src/modules/auth/family-scope.integration.spec.ts` | 6 层租户隔离矩阵 | Account→Person→FamilyMembership→TenantFamilyBinding→TenantAccountMembership→Session 逐层 DENY 测试 |
| `apps/api/src/modules/principal/*.livecheck.ts` | 真实供应商连通性 | 命名避开 `.spec.ts` 故意不被 CI 收集，是手动烟雾测试 |
| `backend/domains/product_intelligence/tests/test_hypothesis_validation_guardrail.py` | AI actor 权限边界 | AI actor 不能验证 hypothesis |
| `evals/subject-isolation/subject-isolation.contract.spec.ts` | subject 隔离规格 | 未被收集，仅作规格参考（见报告 02 第 3 条） |
| `evals/authorization-planes/authorization-planes.contract.spec.ts` | 授权平面规格 | 同上 |

---

## 4. 矩阵总览（一页图）

| TS/Python 能力 | 行数 | 测试 | 挂载运行时 | disposition | Python 目标 |
|---|---|---|---|---|---|
| auth (identity部分) | 1546 | 有 | 是 | MIGRATE | backend/platform/identity |
| auth (authorization部分) | 82(policy) | 有 | 是 | REIMPLEMENT | backend/platform/authorization |
| family | 14091(含specs) | 有 | 是 | REIMPLEMENT | backend/domains/family |
| model | 23 | 无明确记录 | 是(裸provider) | REVIEW_REQUIRED | 待定 |
| orchestration | 5519 | 有 | 是 | MIGRATE | backend/platform/orchestration |
| orchestration_llm_gateway直连违规 | 6行(58-63) | 无 | 是(违规) | REVIEW_REQUIRED | 并入model_gateway |
| principal | 2337 | 有(livecheck) | 是 | MIGRATE | backend/intelligence/principal |
| waf | 261 | 有(仅自测) | 否(死代码) | ARCHIVE | 无 |
| product_intelligence | 1492 | 有 | 否(未挂载) | MIGRATE(需补测) | backend/domains/product_intelligence |
| membership | 2627 | **无** | 否 | REVIEW_REQUIRED(BLOCKED) | 待定 |
| product_strategy | 159 | 无 | 否 | REIMPLEMENT | backend/domains/product_strategy |
| market_intelligence | 52 | 无 | 否 | ARCHIVE | 无 |
| growth_plan | 37 | 无 | 否 | ARCHIVE | 无 |
