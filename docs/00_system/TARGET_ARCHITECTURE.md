---
id: SYS-TARGET-ARCH-001
title: AiFamily Target Architecture
type: system
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: docs/00_foundation/MASTER_BLUEPRINT.md (§1 全景图 / §3 独占区归属 / §4 FGCN 落位部分)
superseded_by: null
---

# 目标架构 (Target Architecture)

```text
⚠️ 读本文件前必须明白一件事：

status: current  指的是"这份目标态描述本身是当前正式的目标态"，
                 不是"这里画的东西已经建好了"。

本文件内容 = TARGET（目标态）
系统现状     = docs/00_system/CURRENT_SYSTEM_BASELINE.md

本文件里任何一个方框、实体名、Port，除 CURRENT_SYSTEM_BASELINE.md §1
明确列为 Implemented 的以外，都还不存在。
```

## 0. 本文件为何从 CURRENT_SYSTEM_BASELINE 拆出

原 `MASTER_BLUEPRINT.md`（后被重命名为 `CURRENT_SYSTEM_BASELINE.md`）混装了两类信息：系统全景/独占区归属/FGCN 落位（**目标态**）与现状核对表（**当前真相**）。按 `SYSTEM_MANIFEST.md` §6（Current Truth ≠ Specification）与 §4 的分区要求，一个名为 `CURRENT_SYSTEM_BASELINE` 的文件承诺的是"系统现在到底是什么"，把目标拓扑放在里面必然被误读为"已实现" —— 原文件自己在第 72 行不得不写"不要把这张全景图误读为已实现"，这是分区错误的症状，不是可以靠加警告解决的问题。

**处理方式**：目标态内容移入本文件（TARGET，回答"要建成什么"），`CURRENT_SYSTEM_BASELINE.md` 重写为纯现状四分区（回答"现在是什么"）。两份文件通过交叉引用绑定：本文件的每个目标元素在 CURRENT_SYSTEM_BASELINE 中都能找到对应的实现状态行。

本文件不是新的治理 SSOT，是既有治理文件（宪章 / MIGRATION_PLAN_V2 / manifest / 商业战略 V2 / UI 审计）在"系统全景"颗粒度上的整合视图。**与治理文件冲突之处以治理文件为准，须回来修订本文件。**

---

## 1. 目标系统全景图

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Frontend (TypeScript)                          [部分已存在]          │
│                                                                       │
│  frontend/mobile (Expo/React Native)  ← 代码已在仓库，后端未就绪     │
│    34 个 UI 屏幕 (UI-01 = app/(tabs)/index.tsx, UI-02..34 = app/ui/) │
│                                                                       │
│  Teacher Workspace / Institution Console / Operations Console         │
│    ← 全部 PLANNED_NO_CODE (见 CURRENT_PRODUCT_MAP.md §4)             │
│                                                                       │
│  frontend/web — REVIEW_REQUIRED / BLOCKED，未迁入，去向待裁决        │
└───────────────────────────┬───────────────────────────────────────┘
                             │ HTTP (Command / Query)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ backend/apps/family_api  (Python/FastAPI — 业务进程)  [骨架已存在]   │
│                                                                       │
│   目标：承载全部业务域路由，守护事实与权限                            │
│   现状：仅 /health /ready，零业务路由                                 │
│                                                                       │
│   依赖 backend/platform/*  [六项已存在，有测试]                      │
│     identity(ActorContext/TenantContext) / authorization(PolicyEngine │
│     fail-closed) / consent(ConsentGate) / audit(AuditRecorder) /      │
│     idempotency(IdempotencyKey/Store) / persistence(UnitOfWork)       │
│                                                                       │
│   backend/domains/*  [5 个已迁入但均未接线，14 个尚不存在]           │
│     四层结构: api/ application/ domain/ infrastructure/               │
└───────┬───────────────────────────────────────┬───────────────────┘
        │ Port (同进程内接口，禁止跨域直接 import repository)         │
        ▼                                                             ▼
┌───────────────────────────┐               ┌─────────────────────────┐
│ backend/intelligence/      │  Event/Query   │ backend/workflow_worker/ │
│ (Python — 智能进程)         │◄──────────────►│ (Python — 长流程进程)     │
│   [仅 design_copilot 占位]  │               │   [完全不存在]            │
│                             │               │                          │
│ 目标组件(R10 各一份):        │               │ 21/90 天计划节奏、       │
│  model_gateway (唯一凭据    │               │ 服务预约 SLA、           │
│    读取点，R7 强制)          │               │ "AI 提议→人工确认→落库"  │
│  context_engine             │               │ 类跨时长流程              │
│  agent_runtime              │               │ Temporal 驱动             │
│  tool_runtime               │               │                          │
│  memory                     │               │                          │
│  prompt_registry            │               │                          │
│  schema_registry            │               │                          │
│  safety / human_gate        │               │                          │
│  evaluation / provenance    │               │                          │
│  trace / cost               │               │                          │
│                             │               │                          │
│ 独占区候选的推理侧驻留于此   │               │                          │
│ (见 §3)                     │               │                          │
└───────────────┬────────────┘               └───────────┬──────────────┘
                │ Port                                     │ Port
                └───────────────────┬─────────────────────┘
                                     ▼
                    ┌─────────────────────────────────────┐
                    │ PostgreSQL（按域分 schema）  [未建立] │
                    │ identity.* / tenancy.* / family.* /   │
                    │ consent.* / assessment.* / growth.* /  │
                    │ journey.* / action.* / outcome.* /     │
                    │ service.* / commerce.* / community.* / │
                    │ content.* / ai_runtime.*               │
                    └─────────────────────────────────────┘
```

**三进程划分的硬性理由**（不是部署偏好）：`docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.1 指出，`ai_runtime` 承载核心域智能、`family_api` 守护事实与权限、`workflow_worker` 承载"AI 提议→人工确认→落库"这类跨时长流程 —— **缺任何一个，AI 原生都不成立**。进程边界同时是 R9（AI 输出不得自动成为事实）的物理执行手段：`ai_runtime` 无权直接写业务权威表。

---

## 2. 三层价值网络：目标形态与已验证程度

三层划分沿用 `MIGRATION_PLAN_V2.md` §2 与商业战略 V2 §2。

**重要限定**：下表的"已验证程度"指的是**源仓库 NestJS 环境下的验证结果**（Evidence 层，来源矩阵001）。在 AiFamily 内没有任何一条链被 Python 后端点亮过。逐屏状态见 `CURRENT_PRODUCT_MAP.md`。

### 层1：AI 自服务层（测评 → 假设解读 → 今日任务）

| 环节 | UI | 源仓库验证程度 |
|---|---|---|
| 测评 | UI-02 | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` |
| AI 假设解读 | UI-03 | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` |
| 今日任务 | UI-09 | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` |

UI-02→UI-03→UI-09 是源仓库**唯一端到端真实打通**的链路。其生产路径仍是 NestJS，`PYTHON_READY` 状态在源仓库也只在 test/staging 生效。

**对 AiFamily 的含义**：Batch 1 的目标是**在 Python 里重新验证一条已被验证的业务语义**，不是从零设计业务规则。这是三区方法论下"两个维度同时最优"的判断结果（独占区雏形所在地 × 已端到端验证），不是排期直觉。

### 层2：人机协作层（21/90 天计划 + 专家咨询预约网络）

| 环节 | UI | 源仓库验证程度 |
|---|---|---|
| 名师专区/详情 | UI-19/20 | `BACKEND_READY` |
| 在线咨询预约 | UI-21 | `E2E_READY`（**取消入口完全不存在**） |
| 我的咨询和活动 | UI-24 | `E2E_READY` |
| 90 日计划入口 | UI-05 | `UI_READY_BACKEND_GAP`（phase-review 已接线；**pause 无前端入口且客户端 SDK 缺方法**） |
| 报告 | UI-04 | `UI_READY_BACKEND_GAP`（仅 LLM draft，无报告事实 DTO） |

SERVICE 预约子链（UI-19→UI-21→UI-24）是源仓库唯一验证过的**付费方向**闭环。PLAN 链里只有 UI-09 已验证，"计划本身"（UI-04/05）仍是 GAP —— 这个差异是 `MIGRATION_PLAN_V2.md` 把 SERVICE 提前到 Batch 2、PLAN 排到 Batch 4 的直接依据。

### 层3：生态放大层（会员/商城/社区/机构 B2B2C）

| 环节 | UI | 源仓库验证程度 |
|---|---|---|
| 邀请有礼/拼团 | UI-15/16 | `E2E_READY`（Named Action + fixture + 幂等 + **零外部 effect**，即无真实扣款） |
| 发布动态 | UI-26 | `E2E_READY`（模板白名单 + 零外发） |
| 商城首页/商品详情 | UI-13/14 | `UI_READY_BACKEND_GAP`（无正式 catalog DTO） |
| 积分商城 | UI-17 | `GATE_BOUNDARY`（**硬编码积分兜底值 `?? 1280`**） |
| 社区流 | UI-25/27/28 | `GATE_BOUNDARY` / `UI_READY_BACKEND_GAP` |
| 成长效果/榜单/海报/成果 | UI-08/11/12/29 | 全部 `GATE_BOUNDARY` —— **R9 红线，不迁移不重建** |

层3 内部完成度极不均匀，且分界线清晰：**"Named Action + fixture + 零外部 effect"模式的页面已 `E2E_READY`；一旦触及真实定价/支付/积分兑换就停在 `GATE_BOUNDARY`。** UI-17 的硬编码积分是明确反面案例（`AI_NATIVE_PRINCIPLES.md` §4 第 4 条）。

GROWTH 闭环（UI-08/11/12/29）**不是技术迁移问题，是产品边界问题** —— 见 §6 待裁决项 3。

---

## 3. 四个独占区候选：目标归属判断

商业战略 V2 §8.2 提出的四个独占区候选，在目标进程拓扑中的归属：

| 独占区候选 | 归属进程 | 归属理由 | AiFamily 现状 |
|---|---|---|---|
| **Family Context**（家庭持续数年的成长数字上下文） | `backend/intelligence/`（ai_runtime） | 本质是"读取经授权、与当前任务相关的最小上下文"，是 AI Runtime 消费侧的输入层，**不产生业务权威状态本身** | **完全空白**。源仓库审计确认 `FamilyMemoryDialogueRuntime` 未接入任何调用方，embedding/pgvector 完全不存在于代码。归属 intelligence 不代表已有实现 |
| **Family Growth Graph**（Context 结构化为时间序列图谱） | 数据结构 → `backend/domains/*` 持久化层；**查询/推理能力** → `backend/intelligence/` | 图谱实体（Family/Parent/Child/Relationship/GrowthNeed/Goal/Behavior/Intervention/Outcome/Evidence）是业务权威数据，必须由业务域按 R6 写入；但"按时间轴组织成可检索图谱"是读时能力，属 Context Engine 范畴 | **完全空白**。这是本文件**唯一存在的架构分歧点**，不是简单二选一，见 §6 待裁决项 2 |
| **Growth Intervention Engine**（给定 Context + GrowthNeed + 历史证据判断下一步） | `backend/intelligence/` | 定义本身就是"决策能力"而非"业务状态"：消费 `AssessmentInterpretationPort` 产出的 `hypotheses`/`action_candidates`，输出 `Perspective`/`Recommendation`，**永不直写业务权威状态**（R9 硬约束） | 雏形数据结构在源仓库存在，但缺 `primary_contradiction` 排序层。AiFamily 内零实现 |
| **Service Blueprint Library**（针对家庭主要矛盾的标准化谋略库） | 蓝图对象 → `backend/domains/service`；"匹配"能力 → `backend/intelligence/` | `ServiceBlueprintVersion`（DRAFT→REVIEWED→PUBLISHED→RETIRED，发布后冻结）是业务权威配置对象，按 R9/R6 只能由业务域管理；把家庭 `primary_contradiction` 接入蓝图匹配输入契约是 AI Runtime 侧逻辑，输出仍是 Recommendation | AiFamily 内零实现 |

**共同结论**：四个候选没有一个整体归属 AI Runtime 或整体归属业务域 —— **决策/推理/上下文检索归 AI Runtime，权威状态的持久化与写入归业务域**。这不是额外规则，是 R9 在架构拓扑上的直接投影。

**AI 原生要求**：`AI_NATIVE_PRINCIPLES.md` §1 规定"独占区候选必须 AI 原生"（五条判据全部答"是"），且 §3.3 明确 Family Context 与 Family Growth Graph 是 AI 原生的**地基而非可选增强**（判据 2 与判据 4 的载体）。因为它们完全空白，**它们是新建，不是优化**。

---

## 4. FGCN / ACN 协作网络：在目标架构中的位置

FGCN（Family Growth Collaboration Network）设计 —— 一客一案 / 一案一管家 / 一任务一责任人 / 一次交付一凭证 / 一个案件一次分配 / 配置先于执行 —— 已被商业战略 V2 §5 确认为**继续有效、不重写**的设计内容。

### 4.1 对应 Batch

| Batch | FGCN 形态 | 内容 |
|---|---|---|
| Batch 2 | **轻量 FGCN** | `TeacherProfile` / `ProviderProfile` / `BookingRequest` / `ServiceRecord` 四个核心对象（已验证的预约闭环） |
| Batch 7 | **完整 FGCN** | 多机构协作、贡献分配、影子结算（disposition = REIMPLEMENT） |

### 4.2 核心运行对象链的域归属

```text
ServiceBlueprintVersion → ServiceCase → ServiceTask → TaskAssignment
                        → ServiceContribution → AllocationStatement
```

- `backend/domains/service`：`ServiceBlueprintVersion` / `ServiceCase` / `ServiceTask` / `TaskAssignment` / `ServiceRecord`
- `backend/domains/teacher`（或并入 service，视 Batch 7 调研而定）：`Provider` / `ProviderProfile` / `Qualification` / `Admission`
- `backend/domains/institution`：`Organization`（B2B2C 机构侧，"**付款方 / 服务接受者 / 数据访问者必须分离**"这一治理原则的落点）
- 贡献确认与分配（`ServiceContribution` / `AllocationStatement`）：**service 域内部子模块，不是独立 domain**。其核心不变量是"**三笔账必须分开**"（增长账 / 服务贡献账 / 资金结算账）；P0 阶段用"影子贡献单位"，**不接真实支付**

### 4.3 明确排除

**C2C 自由市场模式**（教师直接对家庭开店接单）被商业战略 V2 §3 明确排除，与"客户由平台服务，不归属任何教师、机构或推荐人"的战略原则直接冲突，**不得在实现 FGCN 时引入**。

---

## 5. 目标态与现状的绑定关系

| 目标元素 | 现状 | 权威来源 |
|---|---|---|
| `backend/apps/family_api`（业务进程） | 骨架存在，仅 `/health` `/ready` | `CURRENT_SYSTEM_BASELINE.md` §1 |
| `backend/platform/*`（内核六项） | 全部存在且有测试 | `CURRENT_SYSTEM_BASELINE.md` §1 |
| `backend/domains/*`（业务域） | 5 迁入 / 1 有测试 / 14 未开始 | `CURRENT_DOMAIN_MAP.md` |
| `backend/intelligence/*`（智能进程） | 仅 `design_copilot` 占位（全 `NotImplementedError`） | `CURRENT_AI_MAP.md` |
| `backend/workflow_worker/*`（长流程进程） | **不存在** | `CURRENT_SYSTEM_BASELINE.md` §4 |
| PostgreSQL 按域分 schema | **未建立**，58 个 SQL 尚未线性化为 Alembic baseline | `CURRENT_SYSTEM_BASELINE.md` §4 |
| 四个独占区候选 | 全部空白 | `CURRENT_AI_MAP.md` §4 |
| Teacher / Institution / Operations 端 | 全部 `PLANNED_NO_CODE` | `CURRENT_PRODUCT_MAP.md` §4 |

**任何声称"目标架构某部分已实现"的说法，必须能在上表右侧栏找到支撑，否则视为不实断言**（`SYSTEM_MANIFEST.md` §6）。

---

## 6. 待人类架构师裁决（本文件不自行拍板）

1. **`frontend_web` 的最终去向** —— `MIGRATION_MANIFEST.yaml` 判定 `REVIEW_REQUIRED / BLOCKED`。全景图把它画为"存在但状态待定"，不假设会被迁移或废弃。
2. **Family Growth Graph 的归属分歧** —— §3 给出的"数据归业务域、查询归 intelligence"是方向性归属，不是最终接口设计。是否需要一个专门的只读投影层跨越两个进程，需要更细的 Port 契约设计。
3. **GROWTH 闭环（UI-08/11/12/29）的产品侧去向** —— 技术侧无法自行决定这类 `GATE_BOUNDARY` 页面是下线还是等产品设计补齐依据后重新打开。这直接影响 Batch 8 的删除范围与 §2 层3 未来的完成度描述方式。
4. **`growth_plan` stub 与 `journey` 域的关系** —— 二者语义重叠，Batch 4 前必须裁决，否则违反 R2（唯一领域真相）。见 `CURRENT_DOMAIN_MAP.md` §7。
5. **平台 `identity` 与业务身份域的边界** —— `DOMAIN_REGISTRY.yaml` 有两条条目共用 `backend/platform/identity`，构成 R2 模糊地带。

## 7. 与其它文档的关系

| 文档 | 分工 |
|---|---|
| `CURRENT_SYSTEM_BASELINE.md` | 系统**现状**（Implemented / In Progress / Planned / Not Implemented 四分区）。本文件与它冲突时，**现状以它为准** |
| `CURRENT_PRODUCT_MAP.md` | 产品/端的真实状态与 34 UI 逐屏清单 |
| `CURRENT_DOMAIN_MAP.md` | Domain 边界（Owns / Does Not Own）与真实成熟度 |
| `CURRENT_AI_MAP.md` | AI 能力版图与成熟度 |
| `CURRENT_TECHNOLOGY_BASELINE.md` | 进程内部技术选型、分层约定、测试策略 |
| `docs/07_data/`（数据架构） | 表 / schema / 图谱字段的具体设计 |
| `docs/05_ai/AI_ARCHITECTURE.md` | AI Runtime 的详细规格（Agent 定义、三层画像、Intervention Engine 设计） |
| `docs/05_ai/AI_NATIVE_PRINCIPLES.md` | **上位约束**，本文件与它冲突时以它为准 |
| `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` | Batch 划分与 disposition 分类法 |
