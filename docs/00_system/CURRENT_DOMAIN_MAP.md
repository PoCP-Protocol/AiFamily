---
id: SYS-DOMAIN-MAP-001
title: AiFamily Current Domain Map
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

# 当前领域地图 (Current Domain Map)

> 本文件回答一个问题：**业务真相由哪些 Domain 管理，各自的边界在哪，现在真实到什么程度。**
> 它是 `governance/DOMAIN_REGISTRY.yaml`（机器可执行登记）的人类可读视图，冲突时以 YAML 为准。
> 本次全文重写（2026-09-10），核心原则："当前真相不与历史混写"——正文只描述现在为真的状态，历史演变放到 §7 History，不再以追记/脚注方式贴在旧段落上。

---

## 0. Status 词表（本文件唯一状态语言，与 `DOMAIN_REGISTRY.yaml` 一致）

| Status | 定义 |
|---|---|
| `NOT_STARTED` | canonical path 不存在或为空 |
| `MIGRATED_STRUCTURE_ONLY` | 有文件，但是空壳 / stub / 全 `NotImplementedError` |
| `MIGRATED_UNTESTED` | 有实质代码，零验收测试（违反 R4，不得称为能力） |
| `MIGRATED_TESTED` | 有实质代码 + 可在 CI 真实运行的测试（满足 R4） |
| `RETIRED_CANONICAL_CONFLICT` | 曾迁入，因与另一 canonical 实体重复（违反 R2）被降级退役 |
| `PRODUCTION` | 已真正上线服务真实家庭 |

**当前没有任何一个 capability 是 `PRODUCTION`。**

---

## 1. 状态总览（本次重写实测，来源：`governance/DOMAIN_REGISTRY.yaml` 全表 + `backend/domains/` 目录实查，2026-09-10）

`DOMAIN_REGISTRY.yaml` 中按 `canonical_path` 去重后的业务/内部工具 capability：

```text
MIGRATED_TESTED              action, assessment, auth_identity(identity),
                              commerce_product_catalog, commerce_order_intent_dev,
                              family_need_orchestration, growth_intent_confirmation(growth),
                              journey, membership, product_intelligence(+course_content
                                +improvement_candidate+family_experience_signal),
                              service_booking, service_fgcn_collaboration
MIGRATED_STRUCTURE_ONLY       docs_governance_enforced_subset
MIGRATED_UNTESTED             packages_contracts_provenance
RETIRED_CANONICAL_CONFLICT    product_strategy, market_intelligence, growth_plan_python_stub
NOT_STARTED                   family_core(family), database_schema, packages_contracts_ts,
                              docs_business_domain_language, orchestration_core, principal_core
PRODUCTION                    0
```

**目录存在但不在 `DOMAIN_REGISTRY.yaml` 中登记**：`backend/domains/loyalty_points`（有 api/application/domain/infrastructure 四层代码，本次未逐文件核实其测试覆盖，也未在 registry 找到对应 `capability` 行——记为**登记缺口**，见 §5）。

**目录不存在（本次逐一 `test -d` 核实，2026-09-10）**：`backend/domains/{teacher,institution,community,tenancy,outcome}` 均为 `absent`。这五个在 §3 中仍标 `NOT_STARTED`，且与登记表一致（`community`/`teacher`/`institution`/`tenancy`/`outcome` 本身在 `DOMAIN_REGISTRY.yaml` 中也没有条目——即"未登记 = 未开始"，两个来源互相印证）。

---

## 2. 核心域 / 支撑域划分

按 `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1 划分，决定 AI 原生要求作用于谁：

| 类型 | Domain | AI 原生要求 |
|---|---|---|
| **核心域** | assessment, growth, journey, action, outcome | **必须** AI 原生 |
| **优势域** | service, teacher, institution, community | **应当** AI 原生（FGCN 设计指导） |
| **支撑域** | identity, consent, tenancy, commerce | **不要求** AI 原生 |
| **内部工具域** | product_intelligence, membership, loyalty_points | 面向平台自身运营，不直接服务家庭 |

注：`product_strategy`、`market_intelligence`、`growth_plan`（Python stub）已被 registry 判定 `RETIRED_CANONICAL_CONFLICT`（与 `product_intelligence` / `journey` 的 canonical 实体重复，违反 R2），不再作为独立域列入本表。

---

## 3. Domain 逐条登记（本次以 `DOMAIN_REGISTRY.yaml` 状态为唯一权威，逐条核对磁盘目录是否存在）

### 3.1 family — `NOT_STARTED`
- **Canonical Code Path**: `backend/domains/family`（registry `family_core` 条目 canonical_path 指向该路径，status = `NOT_STARTED`，与本次磁盘核实一致——该目录不在 `ls backend/domains` 的实际输出中）
- **Purpose**: 家庭主体本身：`Family`、`Person`、`FamilyMembership`、`Relationship`、`LifeStage`
- **Does Not Own**: 账号凭据（→ identity）；同意记录（→ consent）；成长状态（→ growth）

### 3.2 growth — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/growth`（目录存在，含 `application/`、`infrastructure/`）
- **Registry capability**: `growth_intent_confirmation`
- **Purpose**: `GrowthIntent` 的确认与成长状态演进
- **Does Not Own**: 家庭总分/排行（R9 永久红线，字段不存在）；每日行动执行（→ action）

### 3.3 assessment — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/assessment`（目录存在，含 api/application/domain/infrastructure 四层）
- **Purpose**: 版本化测评工具、会话、作答、证据、`GrowthHypothesis`
- **Does Not Own**: 不拥有 Fact——Hypothesis 是 Perspective，需家庭确认后才生成 growth 域的 GrowthIntent

### 3.4 journey — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/journey`（目录存在，四层俱全）
- **Purpose**: 21/90 天成长旅程阶段划分、节奏推进、阶段复盘
- **Does Not Own**: 单任务执行状态（→ action）；效果判定（→ outcome）

### 3.5 action — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/action`（目录存在，四层俱全）
- **Purpose**: 每日成长行动生命周期：开始/暂停/继续/取消/完成、打卡、反思
- **Does Not Own**: 打卡 ≠ Outcome（R9）；不拥有计划结构（→ journey）

### 3.6 outcome — `NOT_STARTED`
- **Canonical Code Path**: `backend/domains/outcome`（本次 `test -d` 核实：**不存在**；`DOMAIN_REGISTRY.yaml` 中亦无对应 capability 条目）
- **Purpose**: 成长效果的四层区分与证据化记录
- **Does Not Own**: 任何跨家庭比较、榜单、总分、勋章等级（R9）

### 3.7 service — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/service`（目录存在）
- **Registry capabilities**: `service_booking`、`service_fgcn_collaboration`（`backend/domains/service/fgcn`）
- **Purpose**: 服务供给与履约网络：蓝图、案件、任务、分派、服务记录、预约、贡献与结算
- **Does Not Own**: 教师个人档案（→ teacher）；机构主体（→ institution）；蓝图匹配推理（→ intelligence，输出仍是 Recommendation）

### 3.8 teacher — `NOT_STARTED`
- **Canonical Code Path**: `backend/domains/teacher`（本次核实：不存在，registry 无对应条目）
- **Purpose**: 教师/专家/供给方主体：档案、资质、准入
- **Does Not Own**: 预约与履约（→ service）；客户归属——客户由平台服务，不归属任何教师/机构/推荐人（战略原则）

### 3.9 institution — `NOT_STARTED`
- **Canonical Code Path**: `backend/domains/institution`（本次核实：不存在，registry 无对应条目）
- **Purpose**: B2B2C 机构主体与多机构协作
- **Does Not Own**: 家庭数据本身——付款方/服务接受者/数据访问者必须分离

### 3.10 commerce — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/commerce`（目录存在）
- **Registry capabilities**: `commerce_product_catalog`、`commerce_order_intent_dev`
- **Purpose**: 商品目录、订单、支付、会员权益、积分
- **Does Not Own**: 服务履约（→ service）；**不得向未成年人做自动化决策商业营销**（法定绝对禁止）

### 3.11 community — `NOT_STARTED`
- **Canonical Code Path**: `backend/domains/community`（本次核实：不存在，registry 无对应条目）
- **Purpose**: 家庭之间的互助与内容流
- **Does Not Own**: 公开画像、等级事实、跨家庭排序（R9）

### 3.12 product_intelligence — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/product_intelligence`
- **Registry capabilities**: `product_intelligence`、`course_content`、`improvement_candidate`、`family_experience_signal`（四条均 `MIGRATED_TESTED`，均落在同一 canonical_path）
- **Purpose**: 平台自身产品智能（内部工具域），并已扩展出去标识化跨家庭信号能力（`family_experience_signal`/`improvement_candidate`）
- **Does Not Own**: 家庭成长假设（→ assessment 的 `GrowthHypothesis`，同名不同物）

### 3.13 membership — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/membership`
- **Purpose**: 会员分层与分层跃迁不变量管理
- **Does Not Own**: score/rank/level 字段（`FORBIDDEN_TIER_FIELD_TOKENS` 不变量，与 R9 同向）；支付订单（→ commerce）
- 说明：registry 状态已是 `MIGRATED_TESTED`（本次核对 registry 原文第 273-275 行），不同于本文件历史版本记录的"零测试目录/MIGRATED_UNTESTED"状态——测试缺口已被后续工作补齐，具体测试文件列表本次未逐一枚举核实。

### 3.14 loyalty_points — 登记缺口（磁盘有代码，registry 无条目）
- **Canonical Code Path**: `backend/domains/loyalty_points`（本次 `ls` 确认存在，含 api/application/domain/infrastructure 四层）
- **说明**: 本次在 `DOMAIN_REGISTRY.yaml` 全文 grep `loyalty` **零命中**。按 R2 判据（"canonical_path 下若存在代码，必须能追溯到本文件的一行登记"），这是需要补登记的缺口，不属于本文件可单方裁定的状态；本文件不猜测其测试覆盖，标记为**未核实（待补登记）**。

### 3.15 market_intelligence — `RETIRED_CANONICAL_CONFLICT`
- **Canonical Code Path**: `backend/domains/market_intelligence`（目录存在，仅 `README.md`/`__init__.py`/`domain/`）
- 与 `product_intelligence` 域同名 canonical 实体（`MarketSignal`/`SignalCluster`）重复，违反 R2，已降级退役。禁止新增实现。

### 3.16 product_strategy — `RETIRED_CANONICAL_CONFLICT`
- **Canonical Code Path**: `backend/domains/product_strategy`（目录存在，四层俱全但仅 fake repository，无真实持久化）
- 与 `product_intelligence` 域同名 canonical 实体（`GrowthProblem`/`Opportunity`）重复，违反 R2，已降级退役。

### 3.17 growth_plan（Python stub） — `RETIRED_CANONICAL_CONFLICT`
- **Canonical Code Path**: `backend/domains/growth_plan`
- 单文件错误类型空壳，语义已按 ADR-0012 并入 journey。旧目录删除仍需 project-owner 二次确认，暂保留但禁止新增实现。

### 3.18 identity（业务域） — `MIGRATED_TESTED`
- **Canonical Code Path**: `backend/domains/identity`（目录存在，四层俱全）
- **Registry capability**: `auth_identity`
- **Purpose**: 账号、会话、登录、OTP 挑战、租户上下文的业务流
- 说明：本文件历史版本称业务域部分 `NOT_STARTED`，仅平台内核（`backend/platform/identity`）有代码——此说法已不成立：`backend/domains/identity` 目录本次确认存在，registry `auth_identity` 条目 status = `MIGRATED_TESTED`。平台内核部分（`backend/platform/identity`，capability `platform_actor_tenant_context`）同样是 `MIGRATED_TESTED`，二者是不同 canonical_path 上的两条独立登记，不是同一状态的两次重复描述。

### 3.19 consent（业务域） — `NOT_STARTED`
- **Canonical Code Path**: 业务域部分未见独立 `backend/domains/consent` 目录；平台内核部分 `backend/platform/consent`（capability `platform_consent`）status = `MIGRATED_TESTED`
- **Purpose**: 家庭同意的授予、范围、撤回
- **Does Not Own**: 不得由 relationship 推断 consent；同意 ≠ 授权

### 3.20 tenancy — `NOT_STARTED`
- **Canonical Code Path**: `backend/domains/tenancy` 不存在；`backend/platform/tenant` 亦不存在。`TenantContext` 实际落在 `backend/platform/identity` 内（capability `platform_tenancy`，registry status = `MIGRATED_STRUCTURE_ONLY`，见原文第 115-117 行）
- **Purpose**: 多租户隔离：`Tenant`、`TenantFamilyBinding`、`TenantAccountMembership`

---

## 4. 平台内核（非业务 Domain，均 `MIGRATED_TESTED`，本次核对 registry 原文逐条确认）

| capability | canonical_path |
|---|---|
| platform_actor_tenant_context | backend/platform/identity |
| platform_locale_context | backend/platform/localization |
| platform_authorization_policy | backend/platform/authorization |
| platform_consent | backend/platform/consent |
| platform_audit | backend/platform/audit |
| platform_idempotency | backend/platform/idempotency |
| platform_persistence_uow | backend/platform/persistence |
| platform_mtls_transport | backend/platform/security |
| platform_notification | backend/platform/notification |
| model_gateway | backend/intelligence/model_gateway |
| fastapi_runtime_entrypoint | backend/apps/family_api |
| ai_human_gate | backend/intelligence/human_gate |
| vertical_family_growth_ai_runtime | backend/intelligence/agi_vertical_runtime.py |
| test_oracle_excluded_contract_specs | tests/architecture |

`platform_tenancy`（backend/platform/identity）= `MIGRATED_STRUCTURE_ONLY`；`design_copilot`（backend/intelligence/design_copilot）= `MIGRATED_STRUCTURE_ONLY`；`packages_contracts_provenance`（backend/packages/contracts）= `MIGRATED_UNTESTED`；`orchestration_core`（backend/platform/orchestration）与 `principal_core`（backend/intelligence/principal）= `NOT_STARTED`；`database_schema`（database/migrations）与 `packages_contracts_ts`（contracts/schemas）= `NOT_STARTED`。

---

## 5. 本次发现的登记缺口（不是历史遗留，是本次核实结果）

1. **`loyalty_points`**：磁盘有完整四层代码，`DOMAIN_REGISTRY.yaml` 全文无 `loyalty` 命中，缺登记行。
2. registry 头部注释仍留有历史校正记述文字（描述 2026-08-29 前的漂移状态）——这段文字本身是历史记录，不影响本文件当前判定，但读者应以 §1 本次总览表为准，不要把 registry 文件头部的旧叙述当作当前状态。

---

## 6. 上游依据

- `governance/DOMAIN_REGISTRY.yaml`（本次全表核对，2026-09-10）
- `backend/domains/` 磁盘目录列表（本次 `ls` 实查，2026-09-10）
- `governance/REPOSITORY_CONSTITUTION.md` R2 / R4 / R9
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1（核心域 / 支撑域划分）

---

## 7. History（历史演变记录，不代表当前状态）

- **2026-08-29**：`DOMAIN_REGISTRY.yaml` 头部曾声明"Wave 0 阶段，全表 NOT_STARTED"，随后同日发现该声明已与磁盘代码漂移，进行过一次状态校正。
- **2026-09-04**：本文件曾以"§0.1 现状核实追记"的补丁形式记录 growth/assessment/journey/action/service 已是 `MIGRATED_TESTED`，但未改写 §1/§3 正文表格，导致正文长期保留"NOT_STARTED"的过期数字与追记并存。本次（2026-09-10）重写已把追记内容合并进正文，不再保留补丁式追记。
- **product_strategy / market_intelligence / growth_plan**：曾经历"ARCHIVE → project-owner override 推翻 ARCHIVE 迁移全部代码 → 发现与 product_intelligence/journey 的 canonical 实体重复 → RETIRE"的多轮裁决，最终状态见 §3.15-§3.17。
- **membership**：曾因源仓库文档字符串虚假声称测试存在（`tests/` 目录实际不存在）被标记为"本仓库最大单点风险"（`MIGRATED_UNTESTED`）。本次核对 registry 显示其当前状态已是 `MIGRATED_TESTED`；具体是哪次提交补齐了测试、测试覆盖是否已包含 `FORBIDDEN_TIER_FIELD_TOKENS` 的 guardrail test，本次未逐一核实，留待下次深入校验。
