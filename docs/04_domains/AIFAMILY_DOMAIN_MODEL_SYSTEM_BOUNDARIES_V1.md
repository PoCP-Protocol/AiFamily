---
id: DOMAIN-MODEL-BOUNDARY-002
title: AiFamily 领域模型与系统边界设计 V1
type: domain
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-31
updated: 2026-08-31
canonical: false
supersedes: null
superseded_by: null
---

# AiFamily 领域模型与系统边界设计 V1

> 本文件把业务场景与能力地图进一步转换为目标领域语义、系统协作和演进边界。它吸收项目负责人提供的《AiFamily 领域模型与系统边界设计 V1.0》作为研究输入，但不是附件的原样复制。当前领域真相仍以 `CURRENT_DOMAIN_MAP.md`、`DOMAIN_REGISTRY.yaml`、`CAPABILITY_REGISTRY.yaml` 和已接受 ADR 为准；本文件未获联合评审前不授权新增 Domain、目录、表、事件或部署服务。

## 1. 设计目标

本层回答：

1. 哪些业务语义必须有唯一 owner；
2. Aggregate 如何保持小而一致；
3. 哪些协作需要同步 Port，哪些使用 Event/Outbox；
4. 当前哪些模块在一个 Python 业务应用中运行；
5. AI Plane、业务事实、媒体运行时与读模型如何隔离；
6. 什么时候才值得拆成独立部署单元。

统一推导链为：

```text
J0–J7 家庭旅程 / S1–S6 全量 MVP
  → A–H 业务能力系统
  → Context ownership
  → Use Case / Aggregate / Policy
  → Command / Query / Event / Receipt
  → API / Read Model / UI
  → Code path / Test / Evidence
```

`Bounded Context ≠ Python package ≠ database schema ≠ microservice ≠ team`。四者可以在演进中逐步对齐，但不能因一张目标图就同时创建。

## 2. 核心业务命题

AiFamily 的核心不是用户、课程、直播或商城，而是：

> 一个家庭围绕一个已表达并可修正的需要，在具体上下文中选择适当介入，实践、观察、复盘，并决定继续、调整、暂停、升级或结束。

目标语义链为：

```text
Family / Guardian Context
  → Problem Intake / Evidence
  → Understanding Draft / Guardian Decision
  → FamilyNeed or GrowthIntent Reference
  → Goal
  → Intervention Proposal / Journey Plan
  → Action / Observation / Reflection
  → Outcome Assessment
  → Service Escalation / Next Need
```

这是一条跨 Context 旅程，不是一个 Aggregate Chain，也不是一张全局状态表。`FamilyNeed` 是战略上位候选对象；在 ADR 裁决前，现有 `GrowthIntent` 和各域 receipt 是实施可用语义，不得新建第二套 Need 事实源。

## 3. 目标 Context Portfolio

### 3.1 业务 Context

| Context | 主要职责 | 明确不拥有 | 当前目标落点 |
|---|---|---|---|
| Family | Family、成员、关系、生命阶段与家庭主体生命周期 | Account、Consent、成长状态、服务与订单 | `backend/domains/family`，当前边界待完成 |
| Growth | 已确认成长需要/意图、Goal 与成长状态引用 | AI Draft、Assessment 内部结果、Action 执行、Service 履约 | `backend/domains/growth`，正式建模待 ADR |
| Assessment | 工具版本、Session、Response、Evidence 与可修正解释 | 家庭总分、临床诊断、最终 Need/Goal | `backend/domains/assessment`，已有候选 |
| Journey | 阶段计划、家庭介入实例、节奏与 PhaseReview | 单次 Action 事实、独立 Outcome 结论、模板证据事实 | `backend/domains/journey`，已有候选 |
| Action | Action 生命周期、Execution、Barrier 与 Observation | Journey 规划、介入定义、Outcome | `backend/domains/action`，边界/实现待核验 |
| Outcome | 观察汇总、阶段结果、不确定性与 Closure 依据 | 打卡数冒充效果、跨家庭评分、因果自动断言 | `backend/domains/outcome`，待产品/ADR裁决 |
| Service | ServiceOffering、Booking、Delivery、SLA 与 Remedy | Provider 资质、家庭 Need、资金账 | `backend/domains/service`，已有候选 |
| Provider & Organization | Provider 身份、资格、准入、能力范围、机构关系和容量 | Booking/Delivery、Account 凭据、家庭数据 | 现有 `teacher`/`institution` 目标需 ADR 收敛 |
| Knowledge & Evidence | KnowledgeItem、Evidence Registry、Applicability、版本与介入依据 | Assessment Session、家庭 Outcome、媒体播放状态 | canonical owner 缺失 |
| Community & Resource | 受控经验、主题、活动、收藏、举报与资源发现 | 家庭内部关系、Knowledge Evidence、Live Runtime | canonical owner 缺失 |
| Commerce & Entitlement | Offer/Price、Order、Payment、Refund、Entitlement 与财务账 | 专业适配、Service Delivery、Contribution Evidence | `backend/domains/commerce`，目标边界待裁决 |

### 3.2 非业务事实 Context

| 边界 | 职责 | 规则 |
|---|---|---|
| Platform Core | Actor/Tenant Context、Authorization、Consent、Audit、Idempotency、UoW/Persistence 原语 | 是多个 canonical 模块的横向集合，不是一个巨型 Platform Domain |
| Family Intelligence Runtime | Model Gateway、Context Assembly、Agent/Tool Runtime、typed Draft、Human Gate、Eval/Provenance | 只产生 Draft/Recommendation/Trace，不拥有业务权威状态 |
| Xiaojudeng Media | Creator/Channel、Live/Replay、MediaAsset、QoS 与媒体执行状态 | 独立产品/部署边界；不拥有 FamilyNeed、Consent、审核或 Service 事实 |
| Search / Analytics | 跨域只读索引、旅程/运营投影和分析 | 可重建，不成为第二事实源，不反向直写业务表 |
| Workflow Worker | 长流程 timer、retry、SLA 与 human-task orchestration | 通过 Port/Event 驱动具名业务命令，不自行创造业务决策 |

`Governance`、`Data`、`Operations` 是横向能力视图，不应被实现成一个拥有所有事实的 Context。Consent、Audit、Deletion、Moderation、AI Review 和 Incident 各自保留明确 owner 与接口。

## 4. 核心对象所有权

### 4.1 Family 与身份/授权

```text
Platform Identity owns: Account, Session, ActorContext, TenantContext
Family owns:            Family, FamilyMember, Relationship, LifeStage
Platform Consent owns:  ConsentGrant, purpose/scope/effective window/withdrawal
Family references:      guardian relation evidence and consent refs
```

儿童可以是 `FamilyMember` 而没有 `Account`。`GuardianRelation` 表达家庭/法律关系证据，`ConsentGrant` 表达特定 actor 对特定 purpose/scope 的有效同意；Relationship 不能自动推导 Consent。

Family Aggregate 候选只维护：family identity、状态、成员关系引用和生命周期不变量。不得塞入 Assessment、Order、Chat、Media 或 Service JSON。

### 4.2 Problem、Need、GrowthIntent 与 Case

| 概念 | 候选语义 | 关键边界 |
|---|---|---|
| ProblemIntake | 家长原始表达、事件与观察的版本化记录 | 原话/观察不是平台诊断事实 |
| UnderstandingDraft | AI/规则对输入的可编辑理解 | 属 Draft，确认前不改变 Growth 状态 |
| GuardianDecision | 确认、修正、拒绝、暂停或要求更多信息 | 通过具名 Command 记录 |
| GrowthIntent | 当前仓库已有的确认后交接对象 | 在 FamilyNeed ADR 前作为 canonical 候选承接 |
| FamilyNeed | 战略上位候选：跨阶段连续解决的家庭需要 | 不得静默复制 GrowthIntent/GrowthNeed |
| GrowthCase | 需要持续协调时的责任/连续性候选 | 是否独立 Aggregate 必须由 ADR 证明 |
| ServiceCase | 一次真人服务履约责任链 | 不能冒充 GrowthCase |

附件提出“Case 是第一中心对象”过早。平台第一锚点是 `tenant_id + family_id + subject_ref`，业务连续性再通过 `growth_intent_ref/family_need_ref`、`correlation_id` 和场景 receipt 建立。只有确实需要状态、owner、SLA、关闭/重开不变量的过程才建立 Case；Knowledge、Media、Assessment Definition 等不应被迫拥有 `case_id`。

跨 Context 关联使用不同语义的标识，不得混成通用 Case：

```text
family_id / subject_ref   安全与家庭作用域
family_need_ref           业务原因，可选
aggregate_id              当前 Context 的事实身份
receipt_ref               稳定业务交接
correlation_id            一次跨系统旅程追踪
causation_id              某事件/命令由什么触发
```

### 4.3 Assessment

Assessment Aggregate 候选：

```text
AssessmentTool / AssessmentVersion
  → AssessmentSession
      → AssessmentResponse
      → AssessmentEvidence
      → DimensionInterpretation
```

`AssessmentVersion` 冻结题目、维度、解释规则、适用范围和版本。Session 引用 family/subject/purpose 与可选 need/case ref。输出是 Evidence、DimensionInterpretation、Unknown 与风险草案，不是家庭总分、诊断或不可修正的“官方结果”。

Assessment 不固定处在 Guardian Confirmation 之后：证据充分时可以跳过；证据不足时可在理解、介入或复盘阶段按目的调用。它发布 `AssessmentEvidenceRecorded`/receipt，而不是要求 Growth 直接读取内部表。

### 4.4 Goal、Intervention、Journey、Action 与 Outcome

| 语义 | 候选 owner | 说明 |
|---|---|---|
| Goal / Baseline / TargetCondition | Growth | 家长确认的方向与观察条件 |
| InterventionDefinition/Version | Knowledge/Product Studio 候选 owner | 通用方法、Evidence、适用/不适用与版本 |
| InterventionProposal | Intelligence 产 Draft，Growth/Journey 接受或拒绝 | Draft ≠ 业务决定 |
| Family-specific InterventionPlan | Journey | 具体家庭的目标、节奏、阶段和升级条件 |
| ActionAssignment/Execution | Action | 具体执行、障碍和观察 |
| Reflection/PhaseReview | Journey | 家庭对阶段经历的复盘与下一决定 |
| OutcomeAssessment | Outcome 候选 | 改善/未变/恶化/未知、证据充分性和替代解释 |

不在本文件中创建独立 `intervention` Domain。先尊重 ADR-0012 对计划语义归 Journey 的裁决，并由后续 ADR 判断“通用 Intervention Definition”应属于 Knowledge、Product/Offering 还是新 Context。

### 4.5 Service、Provider、Organization、Commerce 与 Collaboration

```text
Provider/Organization       Service                     Commerce
qualification/admission  → offering/booking/delivery → order/payment/refund
capability/capacity         SLA/remedy/feedback         entitlement/ledger
```

- `Account` 是登录身份；`Provider` 是可提供服务的业务主体/角色；
- `OrganizationMembership` 表达 Provider 与机构关系，不把机构塞进 Provider JSON；
- Availability 可以由 Service 读取 Provider 的发布容量，但不能重载为 Live slot；
- ContributionEvent 首先归 Service 协同交付；Allocation/Settlement 属 Commerce/Finance；
- Service Outcome 回到同一 Growth reference，但完成履约不自动关闭 FamilyNeed；
- 复杂 ACN 不在 P0 创建独立 Context，只有真实多角色履约证明边界稳定后再评估拆分。

### 4.6 Knowledge、Community 与 Media

```text
Evidence            KnowledgeItem          FamilyExperience       MediaAsset
professional basis  reviewed explanation   family account         runtime object
```

四者不能合并为 `Content`。Knowledge/Evidence 管来源、版本、适用与限制；Community 管成人可见的经验/活动/互动；小橘灯管媒体执行和 QoS。跨边界使用 immutable/versioned ref；撤回、下架或删除后相关 Search、Collection、Recommendation 和 Replay 投影同步失效。

## 5. Aggregate 与生命周期原则

P0 不以“先设计几十个 Aggregate Root”为目标。优先守住以下小聚合/责任边界：

```text
Family
AssessmentSession
GrowthIntent / FamilyNeed candidate
JourneyPlan
ActionExecution
ServiceBooking / DeliveryRecord
Order / Entitlement (S6窄闭环)
```

不采用附件中的单一线性状态机：

```text
NEW → UNDERSTANDING → CONFIRMED → ASSESSED → ... → RESOLVED
```

它错误地强制 Assessment、Service 和 Media 服从同一步骤，并会让所有团队争抢一个 Case 枚举。每个 Aggregate 维护自己的小生命周期：

```text
UnderstandingDraft: DRAFT → EDITED / REJECTED / CONFIRMED
AssessmentSession:  OPEN → SUBMITTED / EXPIRED / WITHDRAWN
FamilyNeed target:  CONFIRMED → ACTIVE / PAUSED / RESOLVED / WITHDRAWN
JourneyPlan:        DRAFT → ACCEPTED → ACTIVE → PAUSED / COMPLETED / CANCELLED
ActionExecution:    PLANNED → ACTIVE → COMPLETED / BLOCKED / CANCELLED
ServiceBooking:     REQUESTED → CONFIRMED → CANCELLED / EXPIRED / DELIVERED
Order:              DRAFT → CONFIRMED → PAID / CANCELLED / REFUNDING / REFUNDED
```

允许迁移、actor、拒绝原因、恢复和重开由各域规格定义。`FamilyJourneyProjection` 将这些状态投影成家长能理解的“正在理解、等待确认、正在实践、等待复盘、需要帮助、已结束”，但不拥有状态迁移权。

`FamilyNeed target` 只有在 ADR 接受后才成为可实现状态机；若现有 `GrowthIntent` 最终被裁决为一次 Guardian decision receipt，则不得给它复制同样的生命周期。

## 6. 跨 Context 协作规则

### 6.1 可同步调用

同一 `family_api` 进程内，当前请求必须立即得到确定答案时，可通过 Application Port 同步调用：

- actor/tenant/family scope 与 authorization 判定；
- purpose-specific Consent 有效性；
- 创建 Command 前读取稳定 reference/eligibility；
- 用户提交后返回同一 Aggregate 的结果；
- 价格、权益和可用性等必须当场验证的 Query。

同步调用只能依赖公开 application/contract，不得 import 其他 Context 的 repository、ORM entity 或内部 domain service。

### 6.2 必须使用 Event/Outbox 或异步工作流

- 跨 Context 状态传播和读模型更新；
- AI Draft、转写、索引、通知、评测等可重试任务；
- Service SLA、Follow-up、到期、删除传播等长流程；
- Search/Analytics/Today projection；
- 小橘灯媒体状态与 AiFamily 业务引用同步；
- 任何不能在一个 Aggregate 事务内原子完成的副作用。

业务事实与 canonical Audit/Outbox 在本地事务内原子写入；跨 Context 消费至少一次、幂等、可重放、可进入 DLQ/人工补救。禁止用跨域数据库事务制造伪原子性。

### 6.3 Command、Event 与 Receipt

```text
Command  请求具名 actor 改变一个 Aggregate
Event    该 Aggregate 已发生的事实
Receipt  跨场景稳定交接凭证，引用事实、版本与审计
Query    不改变事实的读取
```

事件名不能预先宣布尚未发生的业务结果。例如 AI 只能产生 `EscalationRecommended` Draft；家长/具名责任链确认后，业务域才能产生 `EscalationRequested`。

AI Runtime 内部可以执行模型、工具和输出准入，但高影响业务事实的晋升权继续由 ADR-0014 所定义的 Platform `PolicyEngine`、领域规则与具名 Command 共同约束；不得在 Intelligence 内创建第二套拥有最终业务裁决权的 Policy/Human Gate。

## 7. API、Application 与代码结构

当前采用现有仓库结构，不创建附件中的第二套 `aifamily/` 根目录：

```text
backend/apps/family_api/       # composition root / HTTP API
backend/domains/<context>/
  api/                         # transport adapter
  application/                 # use case / port / orchestration
  domain/                      # aggregate / policy / event
  infrastructure/             # repository / external adapter
backend/platform/<capability>/ # shared platform primitives
backend/intelligence/          # AI plane
backend/workflow_worker/       # target long-running workflows
backend/packages/contracts/    # small cross-boundary contracts only
```

纯容器目录不增加 `__init__.py`。Controller/route 只负责输入、认证上下文、调用 use case 与输出映射，不编写跨域业务流程。跨场景编排放 Application Service/Workflow；业务不变量留在 Aggregate/Policy。

每项功能必须可追溯：

```text
Scenario → Context → Use Case → Aggregate/Policy
→ Command/Query → Event/Receipt → API → Read Model/UI → Test/Metric
```

## 8. Read Model 与产品表面

读模型解决跨域展示，不重组写模型：

| Read Model | 组合内容 | 主要表面 |
|---|---|---|
| `FamilyTodayProjection` | 待确认、Action、Follow-up、Booking、Resource | Today |
| `NeedUnderstandingView` | 原始表达、理解 Draft、Evidence、Unknown、修正 | Ask / S1 |
| `FamilyGrowthJourneyView` | Goal、Plan、Action、Observation、Review、Outcome | Growth / S2 |
| `ResourceDiscoveryView` | Knowledge、Experience、Activity、Live refs | Discover / S3/S5 |
| `ServiceJourneyView` | Offering、Provider、Booking、Delivery、Remedy | S4 |
| `ValueDecisionView` | Offering、Price、Entitlement、Order/Cancel/Refund | S6 |

Read model 可由事件重建；查询层只读。家庭端不显示 `Case`、`Aggregate`、`receipt`、`provenance` 等工程语言。

## 9. 运行时与部署边界

### 9.1 当前目标形状

```text
Web / Mobile
    │
    ▼
family_api / BFF
    │ application ports
    ├─ Business Modular Monolith
    │   Family / Assessment / Growth / Journey / Action / Outcome
    │   Service / Provider / Knowledge / Community / Commerce
    ├─ Platform Core primitives
    │
    ├─event/query─→ ai_runtime
    └─outbox──────→ workflow_worker

Xiaojudeng Media Runtime ──adapter/event──→ AiFamily
Search / Analytics       ←──rebuildable projections
PostgreSQL               ←──owned tables/schemas, no cross-context writes
```

业务 Modular Monolith、AI Runtime 和 Workflow Worker 的三进程目标沿用 `TARGET_ARCHITECTURE.md`。当前磁盘实况不等于三者都已完整实现；Current Truth 见第 11 节。

### 9.2 拆分独立服务的条件

只有同时出现清晰数据 owner，并满足下列至少两项时才提拆分 ADR：

1. 扩缩容或资源模型明显不同；
2. 发布节奏持续冲突；
3. 故障隔离/SLA 不同；
4. 独立团队长期拥有完整能力；
5. 外部复用/API 产品化有真实需求；
6. 性能与数据生命周期需要独立治理。

潜在顺序是 Media、AI Runtime、Search、Notification、对外 Assessment；Family/Growth/Journey 在边界稳定前保持同一业务应用。拆进程不等于复制 Identity、Consent、Audit、Deletion 或业务账本。

## 10. P0 / P1 / P2 架构路线

### P0｜全量 MVP 的 Modular Monolith

- Golden Loop：Family context→表达/理解→按需 Assessment→确认 GrowthIntent/Need→Goal/Plan→Action/Observation→Reflection/Outcome；
- S3：一个 Knowledge/Evidence 主题包进入 typed AI Draft；
- S4：一个 Provider/Offering→Booking→Delivery→Feedback/Remedy；
- S5：一个审核资源/活动→加入/收藏→退出/举报；
- S6：一个 Offer→OrderIntent；若宣称交易闭环，则还必须有 sandbox Payment→Entitlement→Cancel/Refund；
- 同一 API/DTO/状态机在 development/test/production 形状一致，只替换数据、adapter、凭据和容量；
- 不创建独立 Intervention、Collaboration、Governance 巨型 Context。

### P1｜AI + 真人连续服务

- Provider/Organization、资格/准入、Matching、SLA、Remedy 深化；
- Intervention/Offering Definition 的 canonical owner 经 ADR 固化；
- Human Handoff、Workflow Worker、Knowledge Runtime 和 Outcome Analytics 形成闭环；
- 根据负载决定 AI Runtime 的物理独立程度，不改变 Draft/Fact 边界。

### P2｜网络与独立基础设施

- 小橘灯完整 Media、Search、Analytics 独立扩展；
- Community、机构/B2B2C、复杂 Commerce 与多角色协作；
- 真实 Contribution/Settlement 证明后再评估 Collaboration Context；
- Family/Outcome Graph 先作为读投影，不预设图数据库或独立事实源。

## 11. Current Truth / Candidate / Target

| 边界 | 当前判断 | 证据/限制 |
|---|---|---|
| Platform Core | Current foundation | `backend/platform/{identity,authorization,consent,audit,idempotency,persistence}` 有代码/测试；完整账号、家庭和跨场景原子链仍不等于完成 |
| Family | Target / Missing implementation owner | `backend/domains/family` 的正式聚合与真实应用接线未形成完整能力 |
| Assessment | Candidate / partially mounted | 有 Session/Response/Hypothesis/GrowthIntent、SQLAlchemy/PG候选；默认开发接线与完整真实身份仍有限制 |
| Growth | Target / boundary decision | FamilyNeed、Problem/Case、Goal 的 canonical 映射未裁决 |
| Journey | Candidate / not full main journey | 有 JourneyPlan/FamilyPractice/PracticeRecord/PhaseReview 与持久化候选；不能冒充 Outcome |
| Action / Outcome | Target / decision required | 现有代码、Registry 和产品语义需重新核验；Outcome 不得由 PhaseReview 或打卡替代 |
| Service | Candidate | Provider/Offering/Availability/Booking/Record 有代码测试；SLA/Remedy、真实家庭身份与生产依赖未闭合 |
| Provider/Organization | Target / Missing Owner | teacher/institution 目标路径存在于规划，统一主体与资格/准入边界未接受 |
| Knowledge/Evidence | Partial contracts / Missing Owner | Evidence contract、Assessment grounding 与研究材料存在，不等于 Knowledge Runtime/Evidence Registry |
| Community/Media | UI/SQL/history evidence only | 页面/helper或 baseline SQL 不等于 canonical backend 或 Media Runtime；小橘灯独立候选另行汇报 |
| Commerce/Collaboration | Adjacent/Target | ServiceOffering、Membership/Product Intelligence 或历史 SQL 不能冒充交易/ACN 闭环 |
| AI Runtime | Gateway foundation / business workflow missing | Model Gateway 有测试；Context/Agent/Human Gate/Eval 与业务调用链未完整闭合 |
| Workflow/Search/Analytics | Target | 不因目标架构存在就宣称部署单元可用 |

本仓库仍存在 L0、Registry、Manifest 与磁盘实况的状态漂移；任何实施计划必须引用具体 branch/commit/main/artifact/real-environment evidence，不得仅引用本表。

当前需要单独登记、不能由本文件顺手修复的漂移至少包括：`family_api/main.py` 与 `CAPABILITY_REGISTRY.yaml` 的部分头部说明仍称没有业务路由/API，但代码已存在 Assessment、Membership、Service 挂载；Model Gateway、Assessment 与数据库迁移在 Registry/Manifest 中也存在不同代际状态。局部 Outbox 写入已经存在，但 dispatcher、消费游标、重放和 DLQ 尚不能确认为完整 Event Backbone。

## 12. 必须先行的 ADR / Owner 裁决

1. `FamilyNeed`、`GrowthNeed`、`GrowthIntent`、Problem 与 GrowthCase 的关系；
2. GuardianRelation 与 ConsentGrant 的引用和生命周期；
3. Goal、Intervention Definition/Proposal、JourneyPlan 与 Action 的所有权；
4. Reflection、Observation、PhaseReview 与 OutcomeAssessment 的边界；
5. Provider/Teacher/Expert、Organization 与 Service 的统一主体模型；
6. Knowledge/Evidence 与 Assessment Evidence 的边界；
7. Offering、Booking、Order、Entitlement、Contribution 与 Settlement 的三账关系；
8. Community/Content 与小橘灯 Media 的审核、Consent、删除和事件接口；
9. Event/Receipt 最小合同、schema/version、retention 与 owner；
10. 哪些 Target Context 在 P0 只是 projection/module，哪些获准成为独立 canonical Domain。

## 13. 进入详细规格的条件

每个 S1–S6 场景进入开发规格前必须形成：

- 用户触发、用户结果、退出与恢复；
- Context/owner/aggregate/command/query/event/receipt 映射；
- 同步 Port 与异步 Event 边界；
- API/DTO/read model/UI flow；
- 当前代码复用、废弃和 migration 清单；
- development/test/production 的同形 contract；
- 正向、拒绝、撤回、越权、冲突、重启、故障与删除测试；
- 单一 DRI、接口 owner、窄 pathspec 和可展示 artifact。

下一份可执行设计应以 Golden Loop 为主干，同时为 S3–S6 保留真实窄闭环，不再按十个对象或十二个 Context 分成互不相干的团队。建议首先详细定义：

```text
Problem Intake
  → Understanding Draft / Clarification
  → Guardian Correction / Confirmation
  → GrowthIntent or FamilyNeed receipt
```

但该切片不能自行创造 `Case`、`FamilyNeed` 或新状态机；须先完成第 12 节的对象映射裁决，并复用已有 Assessment/GrowthIntent 与 Platform contracts。
