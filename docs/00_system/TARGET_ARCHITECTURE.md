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

## 0.1 平台八层组织架构（**先读本节，再读 §1**）

> 本节 2026-08-29 新增。此前本文件只有 §1 的**进程拓扑**（代码住在哪个进程、哪个域），
> 缺一张回答「为什么建这个、它为家庭创造什么」的组织视图，于是整个架构无法被一眼读懂。
> 采纳依据：project-owner 定调 **Family Growth Intelligence OS**，裁决记录见 **ADR-0015**。
> **本节不新增任何目标元素**，只是把已有元素按价值链重新组织；§1 的进程拓扑完全不变。

### 八层

```text
┌──────────────────────────────────────────────────────────────────┐
│ 1  FAMILY EXPERIENCE      家长 │ 孩子 │ 家庭 │ 教师 │ 专家 │ 机构   │
├──────────────────────────────────────────────────────────────────┤
│ 2  VALUE EXPERIENCE       Emotional → Action → Growth → Economic  │
│                           → Trust                                 │
├──────────────────────────────────────────────────────────────────┤
│ 3  FAMILY GROWTH INTELLIGENCE          ★ 护城河在这一层            │
│    Context │ State │ Problem │ Contradiction │ Value Architecture │
│    │ Strategy │ Intervention │ Evidence                           │
├──────────────────────────────────────────────────────────────────┤
│ 4  PRODUCT INTELLIGENCE   Signal │ Insight │ Opportunity │ 三区    │
│                           │ Pattern │ FPDL │ Compiler             │
├──────────────────────────────────────────────────────────────────┤
│ 5  SERVICE INTELLIGENCE   Blueprint │ Case │ Workflow │ FGCN       │
│                           │ AI + Human 三级协作                    │
├──────────────────────────────────────────────────────────────────┤
│ 6  AI RUNTIME             ← AI 只在这一层                          │
│    L1 能力声明 │ L2 编排推理 │ L3 网关 │ L4 供应商适配              │
├──────────────────────────────────────────────────────────────────┤
│ 7  DATA PLATFORM          PostgreSQL │ Redis │ Object │ Vector     │
│                           │ Event/Outbox │ Trace                   │
├──────────────────────────────────────────────────────────────────┤
│ 8  MODEL LAYER            GPT │ Claude │ Gemini │ DeepSeek │ 本地   │
│                           │ 多模态                                 │
└──────────────────────────────────────────────────────────────────┘
```

### 这张图的三个承重判断

**① `Model` 在最底层，不在最上层。**
模型是可替换件。因此供应商更替是**路由问题**（第 6 层 L4），不是架构问题。
这直接缓解 ADR-0005「需要接受的风险」记录的两条：不得转委托约束可能限制供应商选型、
判据 1 使可用性风险集中于模型供应链。

**② Agent 不是平台中心。**
核心资产是第 3 层的 Context / State / Problem / Contradiction / Strategy / Evidence /
Long-Term Memory；**Agent 是执行这些资产的智能劳动者**。
推论：`backend/intelligence/` 当前几乎全空**不构成致命缺口**，而是正常的建设顺序——
因为护城河本就不在第 6 层。这一句同时消解了 `CURRENT_AI_MAP.md` §7 记录的张力
（平台自称 AI 原生，而 AI 层是全系统最空的一层）。

**③ 第 3~5 层是业务智能，不是 AI Runtime 的一部分。**
它们的**权威状态归业务域**，只有「推理与检索」归第 6 层。
这不是额外规则，是 R9 在分层上的投影（详见 `docs/04_domains/DOMAIN_ARCHITECTURE.md` §3 逐行映射）。

### 两张图怎么一起读

```text
本节（八层）    回答「为什么建这个、它为家庭创造什么」   —— 组织视图
§1（进程拓扑）  回答「代码住在哪个进程、哪个域」          —— 实现视图
两张图都要在。任何一张单独存在都会导致误读：
  只有八层 → 不知道东西写在哪，价值链变成 PPT
  只有拓扑 → 不知道为什么要建，AI 变成目的本身
```

### 每层的 canonical 文档（避免在本文件重复维护）

| 层 | 详细规格在 |
|---|---|
| 2 价值层四层价值的落地形态 | ADR-0015 §1（**家庭侧永不出现分数**，三层只表达方向，唯 Economic 可量化） |
| 3 领域边界与跨域契约 | `docs/04_domains/DOMAIN_ARCHITECTURE.md` |
| 3 只读投影与 Evidence | ADR-0010（`graph_projection.*`，投影 role 只授 `SELECT`） |
| 6 AI Runtime 四层与两道横切门 | `docs/05_ai/AI_ARCHITECTURE.md` §6–§10 |
| 6 目标态前瞻能力 | `docs/05_ai/AI_PLATFORM_FORWARD_ARCHITECTURE.md`（`canonical: false`） |
| 7 分域 schema 与派生数据删除 | `docs/07_data/DATA_ARCHITECTURE.md` |
| 平台内核实际契约 | `docs/06_platform/*`（6 项，从代码反向记录） |

### 诚实的成熟度（八层里五层没有代码）

```text
1 Family Experience    34 屏已迁入，可工作数 = 0（无后端）
2 Value Experience     ABSENT   Value Architecture 属 T-18，未开工
3 Growth Intelligence  ABSENT   仅 hypotheses/action_candidates 雏形，缺 primary_contradiction
4 Product Intelligence ★ 唯一有真代码 + 测试的智能层
5 Service Intelligence ABSENT   Batch 2 六个端点全部 MISSING
6 AI Runtime           L3 网关 + L4 适配器存在；L1/L2 ABSENT
7 Data Platform        Postgres + Alembic baseline + outbox 表已落地；
                       relay / projection ABSENT（见 T-20）
8 Model Layer          经 L4 接入
```

**八层中只有第 4 层与第 6 层的下半截是实的。** 这不是本节的缺陷，是本节要如实记录的事——
按 R4，「设计过」不等于「已实现」，一张完整的分层图最容易被误读为「平台已具备这些层」。

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

## 6. 曾待人类架构师裁决的 5 项 —— 已于 2026-08-29 全部裁决

**本节已从「待裁决清单」转为「裁决索引」。** 裁决记录在 ADR，本节只做指向；
**ADR 的 Decision 段是权威，本节的一句话摘要不是**。每份 ADR 的 Enforcement 段都如实标注了
它当前是否有机械执行者 —— **有 ADR 不等于已落地**，落地任务见
`docs/11_delivery/TASK_BACKLOG.md` T-19。

| # | 原开放项 | 裁决 | ADR |
|---|---|---|---|
| 1 | `frontend_web` 的最终去向 | **应用 ARCHIVE 不迁入**；但其 24 个 spec 文件收割为 `TEST_ORACLE`，作为 T-04 的**第二契约来源**（两来源不一致处即契约的真实歧义点）。原 `REVIEW_REQUIRED` 的证据（无组件框架、无 bundler、build 只是 `tsc --noEmit`）说明它从来不是可部署前端，而是一批伪装成前端的后端契约 | ADR-0013 |
| 2 | Family Growth Graph 的归属分歧 | **写入真相归业务域聚合，Graph 不是一个域**（登记为域会造出第二个成长真相，直接违 R2）。AI 侧唯一合法通路 = 独立只读投影 schema `graph_projection.*`（outbox → projector 构建）+ `GrowthGraphQueryPort`。**投影角色只授 `SELECT`**，使「AI 不能写业务真相」成为**数据库权限层的事实**而非代码约定。**不新建第四个进程**，projector 由 `workflow_worker` 承载。⚠ 整条链建立在尚不存在的机制上（`DomainEvent` 全域 grep 0 命中），ADR 明确规定在 outbox 存在前**一行代码都不该写** | ADR-0010 |
| 3 | GROWTH 闭环（UI-08/11/12/29）的产品侧去向 | **保留文件，当前形态不得挂生产路由。** 重启判据：能在**不呈现家庭总分 / 排名 / 等级**的前提下表达「成长样态」。排在 Batch 4 之后。含产品面判断，project-owner 可 override；但 R9 红线本身不可 override | ADR-0014 §5 |
| 4 | `growth_plan` stub 与 `journey` 域的关系 | **`growth_plan` RETIRE，语义并入 `journey`**（采纳 registry `r2_overlap_risk` 的选项 a）。决定性证据：该 stub 仅 38 行错误类型，而其中的错误码字面量本身就是 `journey_plan_not_draft` / `journey_phase_review_not_due` —— **这不是边界模糊，是一个能力被起了两个名字**。⚠ 删目录需 project-owner **二次确认**（同类删除刚发生过一次并被回滚，见 `TASK_BACKLOG.md` §0.1 偏离 #3） | ADR-0012 |
| 5 | 平台 `identity` 与业务身份域的边界 | **先纠正一个误读：这不是 R2 违规。** `DOMAIN_REGISTRY.yaml:43-49` 的 `r2_boundary_note` 已写明「两个*不同* capability 有意共享一个目录属 manifest 级决定；R2 禁止的是同一 capability 指向两个真实位置」。裁决的是那个已登记的开放项：平台层**永久限定**为无业务生命周期的值对象；业务身份落 `backend/domains/identity`、租户聚合落 `backend/domains/tenancy`；**删除 manifest 里根本不存在的 `backend/platform/tenant` target**。趁 `auth_identity` 仍是 `NOT_STARTED`，这是零成本改登记的最后时刻 | ADR-0011 |

### 6.1 裁决过程中新发现的、原清单没有的边界问题

| 发现 | 处置 |
|---|---|
| **`/auth/*` 四个端点寄居 `backend/domains/assessment/api.py`**，token 存在进程内 dict —— 身份能力住在 assessment 域内，是比「两条登记共享目录」严重得多的真实越界，而它不在任何开放裁决清单里 | ADR-0011 §4：`backend/domains/identity` 建立时迁出；迁出前须在代码里标注临时寄居 |
| **assessment 域不使用 `ActorContext` 也不使用 `PolicyEngine`**，`is_ai` 密封缝完全没接上 —— **没有任何东西阻止一个 AI actor 确认一个假设**，且它靠一个叫 `actor_id` 的 `str` 参数骗过了现有护栏的启发式 | ADR-0014 §Context 2 + `TASK_BACKLOG.md` T-17 |
| **`ModelDraft` 的封印有四处实测泄漏**（`status` 可被 `dataclasses.replace` 改写、`Literal` 运行时不校验、`output` 是可变别名、property 可被子类覆盖） | ADR-0014 §2 规格 + `TASK_BACKLOG.md` T-16 |
| **R9 打分护栏有类名维度漏洞**：原判据要求字段名**同时**命中主体词与打分词，因此 `emotional_value_score` 与 `class FamilyValueScore{emotional: float}` **都能完全通过** | 已补 `tests/architecture/test_r9_value_layer_boundary.py`，已验证会咬人 |

### 6.2 新增的上位组织架构（2026-08-29）

project-owner 定调 **Family Growth Intelligence OS**：平台围绕**家庭价值创造链**组织，
而非围绕 AI 能力清单或课程/测评清单；**`Model` 是最底层不是最上层**；
**Agent 不是平台中心** —— 核心资产是 Context / State / Problem / Contradiction /
Strategy / Evidence / Long-Term Memory，Agent 是执行它们的智能劳动者。

采纳记录与价值层三条边界裁决（家庭侧永不出现分数、State 建模为观察而非属性、
七引擎不建目录）见 **ADR-0015**。

**本文件与那张价值链骨架是两张不同的图，两张都要在。**
本文件回答「代码住在哪个进程、哪个域」；价值链回答「为什么建这个、它为家庭创造什么」。
目标态的 AI 侧展开见 `docs/05_ai/AI_PLATFORM_FORWARD_ARCHITECTURE.md`
（`status: draft` / `canonical: false`，六项成熟度全部为 `ABSENT` / `PARTIAL`）。

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
