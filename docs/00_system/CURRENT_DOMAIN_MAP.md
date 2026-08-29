---
id: SYS-DOMAIN-MAP-001
title: AiFamily Current Domain Map
type: system
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# 当前领域地图 (Current Domain Map)

> 本文件回答一个问题：**业务真相由哪些 Domain 管理，各自的边界在哪，现在真实到什么程度。**
> 它是 `governance/DOMAIN_REGISTRY.yaml`（机器可执行登记）的人类可读视图，冲突时以 YAML 与 `governance/MIGRATION_MANIFEST.yaml` 为准。

---

## 0. Status 词表（本文件唯一状态语言）

| Status | 定义 | 判据 |
|---|---|---|
| `NOT_STARTED` | AiFamily 内无任何代码 | canonical path 不存在或为空 |
| `MIGRATED_STRUCTURE_ONLY` | 代码在仓库内，但是空壳 / stub / 全 `NotImplementedError` | 有文件，无可用行为 |
| `MIGRATED_UNTESTED` | 有实质代码，**零验收测试** | 违反 R4，不得称为能力 |
| `MIGRATED_TESTED` | 有实质代码 + 可在 CI 真实运行的测试 | 满足 R4 |
| `PRODUCTION` | 已真正上线服务真实家庭 | 有生产运行记录 |

**当前没有任何一个 Domain 达到 `PRODUCTION`。** 前提条件（业务 API、数据库 baseline、远端 CI）全部缺失，见 `CURRENT_SYSTEM_BASELINE.md` §4。

**`MIGRATED_STRUCTURE_ONLY` / `MIGRATED_UNTESTED` 不是"接近完成"**，按 `governance/REPOSITORY_CONSTITUTION.md` R4（无测试不得称能力）与 R14（架构测试强制）的伤疤记录，它们等价于"能力不存在，但代码占了位置"。代码行数不是成熟度。

---

## 1. 状态总览

```text
MIGRATED_TESTED           1  (product_intelligence)
MIGRATED_UNTESTED         1  (membership)
MIGRATED_STRUCTURE_ONLY   3  (market_intelligence, product_strategy, growth_plan)
NOT_STARTED              14  (family, growth, assessment, journey, action, outcome,
                              service, teacher, institution, commerce, community,
                              identity*, consent*, tenancy)
PRODUCTION                0
```

`identity` / `consent` 标 `*`：它们的**平台内核部分**（`backend/platform/identity`、`backend/platform/consent`）已有真实代码与测试，但作为**业务域**（账号生命周期、OTP、会话、同意授予与撤回的完整业务流）未开始，见 §3.17 / §3.18。

---

## 2. 核心域 / 支撑域划分

按 `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1（判据 1 的推论）划分。这个划分决定 AI 原生要求作用于谁：

| 类型 | Domain | AI 原生要求 |
|---|---|---|
| **核心域** | assessment, growth, journey, action, outcome | **必须** AI 原生 |
| **优势域** | service, teacher, institution, community | **应当** AI 原生（用 FGCN 设计指导，不重新发明） |
| **支撑域** | identity, consent, tenancy, commerce | **不要求** AI 原生。把 AI 塞进支撑域是另一种错误（R7/R9 正是防这个） |
| **内部工具域** | product_intelligence, product_strategy, market_intelligence, membership, growth_plan | 面向平台自身产品运营，不直接服务家庭 |

---

## 3. Domain 逐条登记

### 3.1 family

| 字段 | 内容 |
|---|---|
| **Purpose** | 家庭这一主体本身：家庭实体、成员（家长/孩子）、成员间关系、生命阶段。是所有其它域的主体锚点 |
| **Canonical Code Path** | `backend/domains/family` |
| **Canonical Doc Path** | `docs/04_domains/family/`（尚未建立） |
| **Owns** | `Family`、`Person`、`FamilyMembership`、`Relationship`、`LifeStage` |
| **Does Not Own** | 账号与登录凭据（→ identity）；同意记录（→ consent）；租户绑定（→ tenancy）；成长状态（→ growth）。**不得从 relationship 推断 consent，不得从 birthdate 推断 lifestage** —— 这两条否定断言来自源仓库 `family-core-integration.e2e-spec.ts`（M1-E2E-01/07/08），是迁移的验收口径 |
| **Upstream** | identity（谁在操作）、tenancy（属于哪个租户） |
| **Downstream** | 几乎全部域 |
| **Status** | `NOT_STARTED` |
| **依据** | `MIGRATION_MANIFEST.yaml` → `family_core`，disposition = REIMPLEMENT，status = PLANNED。源仓库 `family.service.ts` 2293 行是全仓库最大服务文件、60+ 路由、e2e 覆盖完整，但按 R1/R12 必须在 Python 重写，不是搬运。排期 Batch 3 |

### 3.2 growth

| 字段 | 内容 |
|---|---|
| **Purpose** | 家庭成长的权威状态：成长需要、成长意图、成长状态演进 |
| **Canonical Code Path** | `backend/domains/growth` |
| **Canonical Doc Path** | `docs/04_domains/growth/`（尚未建立） |
| **Owns** | `GrowthNeed`、`GrowthIntent`、`GrowthState`、`GrowthProfile` |
| **Does Not Own** | **家庭总分与家庭排行 —— 永不拥有，因为它们不存在**（R9 红线：`legacy_profile.family_score` → RETIRE，`legacy_profile.ranking` → RETIRE）。也不拥有 AI 假设（→ assessment 的 Hypothesis 只是 Perspective）、每日任务执行（→ action）、效果结论（→ outcome） |
| **Upstream** | family、assessment |
| **Downstream** | journey、action、outcome |
| **Status** | `NOT_STARTED` |
| **依据** | 未在 `DOMAIN_REGISTRY.yaml` 登记为独立条目。`MIGRATION_PLAN_V2.md` Batch 4 覆盖 GrowthIntent/GrowthPlan。注意源仓库 `growth_profiles` 表存在两代列并存（0003 的 `subject_type`/`subject_ref_id` 被 0007 的 `profile_scope`/`subject_person_id` 追加替代但未删除），迁移时必须决定死列去留 |

### 3.3 assessment

| 字段 | 内容 |
|---|---|
| **Purpose** | 版本化测评：工具、会话、作答、证据，以及基于证据的 AI 假设（Hypothesis）与家庭确认 |
| **Canonical Code Path** | `backend/domains/assessment` |
| **Canonical Doc Path** | `docs/04_domains/assessment/`（尚未建立） |
| **Owns** | `AssessmentTool`(versioned)、`AssessmentSession`、`AssessmentResponse`、`Evidence`、`GrowthHypothesis` |
| **Does Not Own** | **不拥有 Fact**。Hypothesis 是 `Perspective`，非事实非诊断（R9）；只有家庭执行 `CONFIRM_GROWTH_HYPOTHESIS` 后才生成 growth 域的 `GrowthIntent`。也不拥有评分与诊断结论（`legacy_assessment_score.score` → HISTORICAL_EVIDENCE，非 GrowthState） |
| **Upstream** | family、consent（ASSESSMENT 同意）、intelligence（Hypothesis 生成） |
| **Downstream** | growth（经确认后）、journey |
| **Status** | `NOT_STARTED` |
| **依据** | 未在 `DOMAIN_REGISTRY.yaml` 单列。这是 `MIGRATION_PLAN_V2.md` **Batch 1** 的目标域（三区方法论两维度同时最优：独占区雏形所在地 + 唯一端到端已验证链路）。源仓库 UI-02/UI-03 的 `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` 是行为规格来源，不是可搬运的 Python 代码 |

### 3.4 journey

| 字段 | 内容 |
|---|---|
| **Purpose** | 21/90 天成长旅程：阶段划分、节奏推进、阶段复盘 |
| **Canonical Code Path** | `backend/domains/journey` |
| **Canonical Doc Path** | `docs/04_domains/journey/`（尚未建立） |
| **Owns** | `Journey`、`JourneyPhase`、`PhaseReview`、`GrowthPlan` |
| **Does Not Own** | 单个任务的执行状态（→ action）；效果判定（→ outcome）；长流程调度机制本身（→ workflow worker 基础设施，不是业务域） |
| **Upstream** | growth（GrowthIntent）、intelligence（计划草案，Draft only） |
| **Downstream** | action、outcome、service |
| **Status** | `NOT_STARTED` |
| **依据** | `MIGRATION_PLAN_V2.md` Batch 4。已知前端缺口：UI-05 的 pause 入口连客户端 SDK 方法都没有 —— 但该计划明确排除"先补前端 pause 按钮"作为 Python 迁移的前置阻塞项 |

### 3.5 action

| 字段 | 内容 |
|---|---|
| **Purpose** | 每日成长行动的持久化生命周期：开始/暂停/继续/取消/完成、打卡、反思 |
| **Canonical Code Path** | `backend/domains/action` |
| **Canonical Doc Path** | `docs/04_domains/action/`（尚未建立） |
| **Owns** | `GrowthAction`、`GrowthActionCompletionFact`、`CheckIn`、`Reflection` |
| **Does Not Own** | **打卡 ≠ Outcome**（R9：`legacy_checkin` → TRANSFORM，打卡 ≠ `GrowthActionCompletionFact` ≠ Outcome，M014）。不拥有效果结论（→ outcome）、不拥有计划结构（→ journey） |
| **Upstream** | journey |
| **Downstream** | outcome |
| **Status** | `NOT_STARTED` |
| **依据** | 源仓库 UI-09 是 `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV`（真实 PostgreSQL 状态机 + 重启回读 + 幂等 + Audit/Outbox + AI 不调用），行为规格完整可作为验收口径 |

### 3.6 outcome

| 字段 | 内容 |
|---|---|
| **Purpose** | 成长效果的四层区分与证据化记录 |
| **Canonical Code Path** | `backend/domains/outcome` |
| **Canonical Doc Path** | `docs/04_domains/outcome/`（尚未建立） |
| **Owns** | `Outcome`（分层：过程/行为/关系/状态） |
| **Does Not Own** | **不拥有任何跨家庭比较、榜单、总分、勋章等级**（R9）。不得把过程指标（打卡数）写成成长效果 |
| **Upstream** | action、journey |
| **Downstream** | 家庭私有回顾视图 |
| **Status** | `NOT_STARTED` |
| **依据** | 对应 UI-08/11/12/29 全部 `GATE_BOUNDARY`。`MIGRATION_PLAN_V2.md` §3 处置为 **不迁移、不重建**，§8 列为待人类裁决项 —— 这是产品边界问题，不是技术迁移问题。**本域在产品侧裁决前不得开工** |

### 3.7 service

| 字段 | 内容 |
|---|---|
| **Purpose** | 服务供给与履约网络：服务方案蓝图、案件、任务、分派、服务记录、预约 |
| **Canonical Code Path** | `backend/domains/service` |
| **Canonical Doc Path** | `docs/04_domains/service/`（尚未建立） |
| **Owns** | `ServiceBlueprintVersion`（DRAFT→REVIEWED→PUBLISHED→RETIRED，发布后冻结）、`ServiceCase`、`ServiceTask`、`TaskAssignment`、`ServiceRecord`、`BookingRequest`、`AvailabilitySlot`、`ServiceOffering`、`ServiceContribution`、`AllocationStatement` |
| **Does Not Own** | 教师个人档案与资质（→ teacher）；机构主体（→ institution）；真实资金结算（P0 阶段为"影子贡献单位"，不接真实支付）。**蓝图与家庭 primary_contradiction 的匹配推理不属本域**（→ intelligence，输出仍是 Recommendation） |
| **Upstream** | family、consent（SERVICE 同意）、journey |
| **Downstream** | commerce（若涉付费）、outcome |
| **Status** | `NOT_STARTED` |
| **依据** | `MIGRATION_PLAN_V2.md` **Batch 2**（从 V1 Batch 5 提前）。源仓库 UI-19→UI-21→UI-24 是唯一验证过的付费方向闭环。FGCN 核心运行对象链 `ServiceBlueprintVersion → ServiceCase → ServiceTask → TaskAssignment → ServiceContribution → AllocationStatement` 全部落在本域。"三笔账必须分开"（增长账/服务贡献账/资金结算账）是本域内部核心不变量 |

### 3.8 teacher

| 字段 | 内容 |
|---|---|
| **Purpose** | 教师/专家/供给方主体：档案、资质、准入 |
| **Canonical Code Path** | `backend/domains/teacher` |
| **Canonical Doc Path** | `docs/04_domains/teacher/`（尚未建立） |
| **Owns** | `TeacherProfile`、`ProviderProfile`、`Qualification`、`Admission` |
| **Does Not Own** | 预约与履约（→ service）；机构归属（→ institution）；**客户归属 —— 客户由平台服务，不归属任何教师、机构或推荐人**（战略原则，C2C 自由市场模式被明确排除，不得在实现 FGCN 时引入） |
| **Upstream** | identity、institution |
| **Downstream** | service |
| **Status** | `NOT_STARTED` |
| **依据** | `MIGRATION_PLAN_V2.md` Batch 7（disposition = REIMPLEMENT）。Batch 2 的"轻量 FGCN"会先建 `TeacherProfile`/`ProviderProfile` 两个核心对象；是否最终并入 service 域视 Batch 7 调研而定（`resource` 域候选） |

### 3.9 institution

| 字段 | 内容 |
|---|---|
| **Purpose** | B2B2C 机构主体与多机构协作 |
| **Canonical Code Path** | `backend/domains/institution` |
| **Canonical Doc Path** | `docs/04_domains/institution/`（尚未建立） |
| **Owns** | `Organization`、机构-教师隶属、机构侧数据访问范围 |
| **Does Not Own** | 家庭数据本身（**付款方 / 服务接受者 / 数据访问者必须分离** —— 机构付钱不等于机构可读家庭数据，这是本域最重要的治理不变量）；租户隔离机制本身（→ tenancy） |
| **Upstream** | tenancy |
| **Downstream** | teacher、service |
| **Status** | `NOT_STARTED` |
| **依据** | `MIGRATION_PLAN_V2.md` Batch 7。源仓库无对应 domain，无 `organization` 表 |

### 3.10 commerce

| 字段 | 内容 |
|---|---|
| **Purpose** | 商品目录、订单、支付、会员权益、积分 |
| **Canonical Code Path** | `backend/domains/commerce` |
| **Canonical Doc Path** | `docs/04_domains/commerce/`（尚未建立） |
| **Owns** | `Catalog`、`Product`、`Order`、`Payment`、`Entitlement`、`PointsLedger`、`Invite`、`GroupBuy` |
| **Does Not Own** | 会员分层的内部运营模型（→ membership 内部工具域，两者边界待 Batch 6 明确）；服务履约（→ service）。**不得向未成年人做自动化决策商业营销**（《未成年人网络保护条例》第 24 条第 3 款，法定绝对禁止） |
| **Upstream** | identity、family、service |
| **Downstream** | 无（终端） |
| **Status** | `NOT_STARTED` |
| **依据** | `MIGRATION_PLAN_V2.md` Batch 6，且带**前置条件**：迁移前必须先清理 UI-17 的硬编码积分兜底值 `?? 1280`，并明确未成年人商业场景权限规则。价格/权益必须服务端派生，客户端不得传价格 |

### 3.11 community

| 字段 | 内容 |
|---|---|
| **Purpose** | 家庭之间的互助与内容流 |
| **Canonical Code Path** | `backend/domains/community` |
| **Canonical Doc Path** | `docs/04_domains/community/`（尚未建立） |
| **Owns** | `Post`、`Feed`、`CommunityProfile` |
| **Does Not Own** | **不拥有公开画像、等级事实、跨家庭排序**（R9）；不拥有真实外发能力（当前受控为零外发） |
| **Upstream** | family、identity |
| **Downstream** | 无 |
| **Status** | `NOT_STARTED` |
| **依据** | `MIGRATION_PLAN_V2.md` Batch 7。排期靠后但依 `SYSTEM_MANIFEST.md` §2 的"家庭与家庭之间的关系"定位**不是可砍功能**；`MIGRATION_PLAN_V2.md` §8 列为待裁决项（是否在 Batch 7 前先开始调研） |

### 3.12 product_intelligence

| 字段 | 内容 |
|---|---|
| **Purpose** | 平台自身的产品智能：产品假设的形成与验证（内部工具域，不直接服务家庭） |
| **Canonical Code Path** | `backend/domains/product_intelligence` |
| **Canonical Doc Path** | `docs/04_domains/product_intelligence/`（尚未建立） |
| **Owns** | 产品假设（Hypothesis）与其验证流程对象 |
| **Does Not Own** | 家庭成长假设（→ assessment 的 `GrowthHypothesis`，两者同名不同物，不得混用） |
| **Upstream** | market_intelligence（理论上） |
| **Downstream** | product_strategy（理论上） |
| **Status** | **`MIGRATED_TESTED`** |
| **依据** | `MIGRATION_MANIFEST.yaml` → `product_intelligence`，disposition = MIGRATE，status = APPROVED_PENDING_REVIEW。源仓库唯一有测试的 Python 域（21 文件 / 1492 行，domain/application/infrastructure/api/tests 五层俱全）。AiFamily 内 6 个测试通过，含真实 TEST_ORACLE `test_hypothesis_validation_guardrail.py`（AI actor 不能验证 hypothesis）。**遗留缺口**：`api/routes.py` 未挂载到任何 app；仅 SQLite 测试，无 Postgres 集成测试；源自称 V0.1。计划曾称其"已具备生产条件"，实测不成立 |

### 3.13 membership

| 字段 | 内容 |
|---|---|
| **Purpose** | 会员分层与分层跃迁的不变量管理（内部工具域） |
| **Canonical Code Path** | `backend/domains/membership` |
| **Canonical Doc Path** | `docs/04_domains/membership/`（尚未建立） |
| **Owns** | 会员分层（Tier）、分层跃迁合法性策略、幂等键去重 |
| **Does Not Own** | **不得拥有任何 score / rank / level 字段** —— 这是其 `domain/policies.py` 的 `FORBIDDEN_TIER_FIELD_TOKENS` 声明的不变量，与 R9 同向。也不拥有支付与订单（→ commerce） |
| **Upstream** | identity、commerce |
| **Downstream** | commerce |
| **Status** | **`MIGRATED_UNTESTED`** ← **本仓库最大单点风险** |
| **依据** | `MIGRATION_MANIFEST.yaml` → `membership`，含 `project_owner_override`（2026-08-29 project-owner 指示"保险起见，先把所有 Python 代码都迁移过来"，推翻此前 REVIEW_REQUIRED/BLOCKED）。2627 行，五个 Python 域中最大，`domain/policies.py` 含真实不变量（`assert_tier_transition_legal` 等）。**零测试目录**：`infrastructure/sqlalchemy_repository.py:8-9` 的 docstring 声称"Tests run this same class against an in-memory SQLite engine (`tests/conftest.py`)"，该 `tests/` 目录在源仓库磁盘上不存在；`policies.py:24-28` 的 `FORBIDDEN_TIER_FIELD_TOKENS` 注释自称"由 guardrail test 强制"，**该测试在源仓库与 AiFamily 中都不存在**。override 明确要求：迁移必须原样带着这个已知缺口，**不得在迁移过程中假装测试已存在**。解锁路径：先写出 `FORBIDDEN_TIER_FIELD_TOKENS` 的 guardrail test。**并发 WIP**：`tests/domains/membership/` 已出现另一会话编写的会员周期验收测试，但其中 2 个用例当前失败，且**不覆盖** guardrail —— 状态仍为 `MIGRATED_UNTESTED`，详见 `CURRENT_SYSTEM_BASELINE.md` §2.2 |

### 3.14 market_intelligence

| 字段 | 内容 |
|---|---|
| **Purpose** | 市场情报（内部工具域） |
| **Canonical Code Path** | `backend/domains/market_intelligence` |
| **Canonical Doc Path** | 无 |
| **Owns** | （名义上）市场信号实体 |
| **Does Not Own** | 一切实际行为 |
| **Upstream** | — |
| **Downstream** | — |
| **Status** | **`MIGRATED_STRUCTURE_ONLY`** |
| **依据** | `MIGRATION_MANIFEST.yaml` → `market_intelligence`，含 `project_owner_override`（"先迁移全部 Python 代码，推翻 ARCHIVE 判定；**迁移后仍是空壳状态，不假装已完整**"）。**52 行**，仅 `domain/entities.py` + `errors.py`，`api`/`application`/`infrastructure` 是空目录占位。零测试 |

### 3.15 product_strategy

| 字段 | 内容 |
|---|---|
| **Purpose** | 产品策略（内部工具域） |
| **Canonical Code Path** | `backend/domains/product_strategy` |
| **Canonical Doc Path** | 无 |
| **Owns** | （名义上）策略实体 + ports |
| **Does Not Own** | 真实持久化 —— 只有 fake repository |
| **Upstream** | product_intelligence |
| **Downstream** | — |
| **Status** | **`MIGRATED_STRUCTURE_ONLY`** |
| **依据** | `MIGRATION_MANIFEST.yaml` → `product_strategy`，disposition = REIMPLEMENT。**159 行**，仅 domain + ports + fake repository，无真实持久化，无测试。原 `domain/entities.py:17` 的注释直接在讨论 `50_开发_dev/backend/` 这个物理布局（R12 违规），迁入时已修复（属 6 处 R12 路径耦合修复之一） |

### 3.16 growth_plan

| 字段 | 内容 |
|---|---|
| **Purpose** | 成长计划（Python stub；语义目标域是 journey，见 §3.4） |
| **Canonical Code Path** | `backend/domains/growth_plan` |
| **Canonical Doc Path** | 无 |
| **Owns** | 仅错误类型枚举 |
| **Does Not Own** | 实体模型、任何计划行为 |
| **Upstream** | — |
| **Downstream** | — |
| **Status** | **`MIGRATED_STRUCTURE_ONLY`** |
| **依据** | `MIGRATION_MANIFEST.yaml` → `growth_plan_python_stub`，含 `project_owner_override`（"迁移后仍是错误类型 stub，**不假装已有实体模型**"）。**单文件 37 行**，注释称"mirroring journey-plan.service.ts"但无实体。**注意 R2 风险**：本 stub 与未来的 `backend/domains/journey` 语义重叠，Batch 4 开工前必须裁决二者关系，否则构成"一个能力两个实现位置"的违宪状态 |

### 3.17 identity

| 字段 | 内容 |
|---|---|
| **Purpose** | 账号、会话、登录、租户上下文 |
| **Canonical Code Path** | `backend/platform/identity`（平台内核部分，**已存在**）；业务域部分尚无位置 |
| **Canonical Doc Path** | `docs/06_platform/`（尚未建立细目） |
| **Owns** | 平台内核部分：`ActorContext`、`TenantContext`。业务域部分（未开工）：`Account`、`IdentitySession`、`OtpChallenge` |
| **Does Not Own** | 家庭成员语义（→ family：`Person` 是家庭成员，`Account` 是登录主体，二者不是同一对象）；授权判定（→ `backend/platform/authorization`） |
| **Upstream** | tenancy |
| **Downstream** | 全部域 |
| **Status** | 平台内核 = `MIGRATED_TESTED`（`backend/platform/identity` 有代码 + `tests/platform/identity/test_context.py`）；**业务域 = `NOT_STARTED`** |
| **依据** | `DOMAIN_REGISTRY.yaml` 有两条指向同一 canonical_path：`platform_actor_tenant_context`（REIMPLEMENT）与 `auth_identity`（MIGRATE，源 `apps/api/src/modules/auth` 1546 行、真实 Postgres `identity_sessions`/`otp_challenges`/`accounts`/`tenants`）。**这两条共用 `backend/platform/identity` 是一处需要复核的 R2 边界模糊**：平台原语与业务身份域是否应共处一个 canonical path。`OtpService` 的 `StubOtpSender` 是唯一显式标注的替换点。4 个 `/auth/*` 端点是 Mobile 的硬依赖，当前全部缺失 |

### 3.18 consent

| 字段 | 内容 |
|---|---|
| **Purpose** | 家庭同意的授予、范围、撤回 |
| **Canonical Code Path** | `backend/platform/consent`（内核部分，**已存在**） |
| **Canonical Doc Path** | `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`（约束级） |
| **Owns** | 内核部分：`ConsentGate`。业务域部分（未开工）：`Consent` 记录、scope（ASSESSMENT / SERVICE / …）、撤回历史 |
| **Does Not Own** | **不得由 relationship 推断 consent**（源仓库 M1-E2E-07/08 否定断言）。不拥有授权策略判定（→ authorization）；同意 ≠ 授权 |
| **Upstream** | family、identity |
| **Downstream** | assessment、service、intelligence（Context 读取必须经同意） |
| **Status** | 平台内核 = `MIGRATED_TESTED`（`tests/platform/consent/test_gate.py`）；**业务域 = `NOT_STARTED`** |
| **依据** | `MIGRATION_MANIFEST.yaml` → `platform_consent`，REIMPLEMENT。参考实现：`specs/ontology/consent.schema.yaml`、`grant-consent.integration.spec.ts`（交叉家庭拒绝矩阵，TEST_ORACLE）。硬约束：**同意撤回必须即时生效** |

### 3.19 tenancy

| 字段 | 内容 |
|---|---|
| **Purpose** | 多租户隔离：租户主体与"账号-家庭-租户"绑定链 |
| **Canonical Code Path** | `backend/domains/tenancy` 或 `backend/platform/tenant`（**未定，两处都不存在**） |
| **Canonical Doc Path** | 无 |
| **Owns** | `Tenant`、`TenantFamilyBinding`、`TenantAccountMembership` |
| **Does Not Own** | 机构业务语义（→ institution：租户是隔离边界，机构是业务主体，二者不等价） |
| **Upstream** | 无（最上游） |
| **Downstream** | 全部域 |
| **Status** | `NOT_STARTED` |
| **依据** | `MIGRATION_MANIFEST.yaml` → `platform_actor_tenant_context` 的 target 列出 `backend/platform/tenant`，但该目录在磁盘上**不存在**（只有 `backend/platform/identity` 被实现，`TenantContext` 落在 identity 内）。TEST_ORACLE 已就位：源仓库 `family-scope.integration.spec.ts` 是 6 层绑定链（Account→Person→FamilyMembership→TenantFamilyBinding→TenantAccountMembership→Session）逐层 DENY 测试。**已发现文档漂移**：manifest 的 target 与实际落点不一致，需一次 registry 校正 |

---

## 4. 已存在但不是业务 Domain 的代码

以下位于 `backend/` 下但不承载业务真相，登记在此以防被误当 Domain：

| 路径 | 性质 | 状态 |
|---|---|---|
| `backend/platform/authorization` | 平台内核：PolicyEngine（fail-closed） | 有代码 + `tests/platform/authorization/test_policy.py` |
| `backend/platform/audit` | 平台内核：AuditRecorder（R6 载体） | 有代码 + `tests/platform/audit/test_recorder.py` |
| `backend/platform/idempotency` | 平台内核：IdempotencyKey / Store | 有代码 + `tests/platform/idempotency/test_keys.py` |
| `backend/platform/persistence` | 平台内核：UnitOfWork / SqlAlchemyUnitOfWork | 有代码 + `tests/platform/persistence/test_unit_of_work.py` |
| `backend/packages/contracts` | 跨域共享原语（`Provenance` / `evidence`），被 4 个域以 `backend.packages.contracts.*` 绝对包路径导入 | `MIGRATED_PENDING_REVIEW`。manifest 原写 target = `backend/platform/persistence`，2026-08-29 已对齐为实际路径 |
| `backend/apps/family_api` | FastAPI 运行时入口 | 真实可运行，仅 `/health` `/ready` + `tests/apps/family_api/test_routes.py` |
| `backend/intelligence/design_copilot` | AI 侧占位 | `MIGRATED_STRUCTURE_ONLY`：`ProductCompiler` / `DesignSimulator` 每个方法都是 `NotImplementedError`，零调用方、零测试。见 `CURRENT_AI_MAP.md` |

## 5. 尚不存在的 Domain 边界能力（跨域基础设施缺口）

| 缺口 | 影响 |
|---|---|
| **数据库 schema** | 58 个源 SQL 迁移（0001-0058）尚未线性化为 Alembic baseline；4 组文件名重号（0022/0023/0024/0053）必须先解决。**没有一个 Domain 能拥有持久化真相** |
| **Family Context** | 完全空白。源仓库审计确认 `FamilyMemoryDialogueRuntime` 未接入任何调用方，embedding/pgvector 不存在。见 `CURRENT_AI_MAP.md` |
| **Family Growth Graph** | 完全空白。其数据结构应归业务域持久化层、查询/推理能力归 intelligence —— 这一归属分歧是 `TARGET_ARCHITECTURE.md` 的待裁决项 |
| **domain events / outbox** | 源仓库全域 grep `DomainEvent` 精确类名 = 0 命中。跨域协作机制尚无 Python 实现 |

## 6. 上游依据

- `governance/DOMAIN_REGISTRY.yaml`（R2 执行；注意其注释仍称"本表全部 status = NOT_STARTED"，已与磁盘实况漂移，见 §7）
- `governance/MIGRATION_MANIFEST.yaml`（R3 执行；含 3 处 `project_owner_override`）
- `governance/REPOSITORY_CONSTITUTION.md` R2 / R4 / R6 / R9 / R12
- `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` §3–§6
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1（核心域 / 支撑域划分）

## 7. 本文件发现的文档漂移（需后续校正动作）

1. **`DOMAIN_REGISTRY.yaml` 严重滞后**：其头部注释声明"Wave 0 阶段：本表全部 status = NOT_STARTED，不含任何业务代码"，且所有 Wave 1/Wave 2 条目仍写 `status: NOT_STARTED` —— 但磁盘上 `backend/platform/*` 六项、`backend/apps/family_api`、5 个 `backend/domains/*` 都已有代码。按 R2 的机器执行语义（"canonical_path 下若存在代码，必须能追溯到本文件的一行登记"），登记行存在但 status 失真，需一次 registry 状态刷新。
2. **`tenancy` 的 canonical path 与 manifest target 不一致**：manifest 写 `backend/platform/tenant`，实际不存在，`TenantContext` 落在 `backend/platform/identity` 内。
3. **`identity` 有两条 registry 条目共用同一 canonical_path**（`platform_actor_tenant_context` + `auth_identity`），平台原语与业务身份域的边界需明确，否则构成 R2 模糊地带。
4. **`growth_plan` stub 与未来 `journey` 域语义重叠**，Batch 4 前必须裁决，否则违反 R2。
5. **`DOMAIN_REGISTRY.yaml` 缺 3 个已迁入域的登记**：`market_intelligence` 与 `growth_plan` 在 manifest 中有条目、代码已在磁盘，但 `DOMAIN_REGISTRY.yaml` 中无对应行（`product_strategy` 有）。按 R2 判据这是需要补登记的缺口。
