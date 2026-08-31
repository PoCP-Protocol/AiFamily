---
id: BIZ-SCENARIO-CAPABILITY-BLUEPRINT-001
title: AiFamily 业务场景—能力—终端蓝图 V1
type: business
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-31
updated: 2026-08-31
canonical: false
supersedes: null
superseded_by: null
---

# AiFamily 业务场景—能力—终端蓝图 V1

> 本文件是 `FAMILY_GROWTH_PLATFORM_BLUEPRINT_V3.md` 的下一级分解候选，将战略蓝图转成业务场景、能力地图、核心对象、终端矩阵和阶段 Backlog。它吸收项目负责人提供的《AiFamily 业务场景与功能模块蓝图 V1.0》作为研究输入，但不是附件的原样复制，也不代表能力已经实现。正式成为执行基线前须经项目负责人、PMO、场景 DRI、Domain owner、Experience 和 QA 会签。

## 1. 设计顺序

AiFamily 不按“首页、课程、直播、社区、专家、我的”建设六个孤立产品。所有设计和开发必须遵循同一顺序：

```text
家庭发生了什么
  → 家长希望得到什么结果
  → 哪些角色共同完成
  → 产生或改变哪些业务对象
  → 需要复用哪些平台能力
  → 哪些终端承担哪些动作
  → 如何运行、失败、恢复和验收
```

功能模块是被场景调用的能力，不拥有用户结果。页面是场景在特定终端的呈现，不是产品架构的起点。

## 2. 统一业务语义

### 2.1 北极星对象

`FamilyNeed` 是跨测评、成长行动、知识、服务、关系连接和价值转化的上位业务起点。它不是无限家庭画像，也不立即要求新建第二个 Domain 或第二张事实表。正式建模前，必须由现有 Family/Growth/Assessment/Service owner 裁决它与 `GrowthIntent`、`GrowthNeed`、`ServiceCase`、`OrderIntent` 的引用关系。

最小上位契约至少表达：

- family/subject scope；
- purpose 与来源；
- Evidence refs；
- 家长确认、修正或拒绝 receipt；
- 当前状态、版本、复盘时间；
- 解决、未解决、暂停、升级、关闭与重新打开；
- Consent、可见范围、留存与删除引用。

候选生命周期为：

```text
DRAFT
  → CLARIFYING
  → GUARDIAN_CONFIRMED
  → ACTIVE
  → PAUSED
  → RESOLVED / WITHDRAWN / SUPERSEDED
```

每次状态迁移必须形成带 actor、tenant/family scope、Consent ref、Evidence refs、版本、时间、理由和幂等信息的 receipt。此生命周期是待 ADR 裁决的目标契约，不是立即创建 `FamilyNeed` Domain 或新表的授权。

### 2.2 核心结果链

```text
FamilyNeed
  → Evidence
  → Perspective / Understanding Draft
  → GuardianDecision
  → Goal
  → InterventionProposal
  → ActionPlan / ActionExecution
  → Observation / Reflection
  → Outcome
  → Escalation / Next Need
```

AI 可以帮助形成 Draft、知识依据、候选介入与复盘摘要，但不能越过 GuardianDecision 或具名专业复核直接改变高影响业务状态。涉及专业评估的结论由具名且具备相应资格的专业人员实质查看、修改、驳回或要求补充；Guardian 决定是否采用、共享、购买或进入行动。Guardian 确认不能替代专业复核，专业人员也不能泛化修改家庭权威事实。

### 2.3 “微行动”的升级定义

本蓝图不以“做一件小事”作为产品高度。正确概念是：

> **最小充分家庭成长介入（Minimum Sufficient Family Intervention）**

“最小”表示不向家庭施加超过当前需要的复杂度和服务强度；“充分”表示它必须足以验证一个关键假设、改善一个具体情境或为下一次专业判断提供 Evidence。它可以是一项家庭协定、一次结构化对话、一个环境调整、一段观察期或一次专业服务，不等同于打卡任务。

每个介入必须写清：目标、依据、参与者、时间窗口、完成/停止条件、观察方法、风险、升级条件和 Outcome 解释边界。

## 3. 核心参与者与责任

| 角色 | 在场景中的核心责任 | 不应承担 |
|---|---|---|
| Parent / Guardian | 表达、授权、修正、确认、行动、购买和反馈 | 被动接受 AI 结论 |
| Child / Youth | 家庭成员、成长中心与受益者；按年龄与授权参与 | 营销、排名或公开拉新主体 |
| Family Growth Copilot | 理解、追问、知识检索、Draft、导航和复盘辅助 | 最终事实、诊断和高影响决策者 |
| Family Advocate | 维护旅程连续性、协调资源与跨服务交接 | 无边界持有全部家庭数据 |
| Teacher | 教育场景观察、协作、交付与反馈 | 查看未授权的完整家庭隐私 |
| Expert | 在专业范围内评估、复核、交付和升级 | 以平台声望替代证据与责任 |
| Organization | 管理供给、合同、服务和质量 | 获得未经家庭授权的明细 |
| Platform Operations | 内容、供给、服务、直播、质量和治理运营 | 直接改写家庭事实或结果 |

## 4. 八个家庭旅程场景

附件中的 S01–S12 是重要业务素材，但其中混合了旅程步骤、按需能力和长期投影。为避免把每一步建设成独立产品或事实源，本蓝图使用 `J0–J7` 描述家庭旅程；现有 `S1–S6` 继续作为 MVP 交付包。

### J0｜建立最小家庭访问上下文

- 触发：成人首次注册、受邀加入或重新进入。
- 核心动作：确认账户、家庭、成员关系与 Guardian 权限。
- 家庭结果：安全进入一个可回读的 Family Home，不强迫首次完成完整画像。
- 关键对象：Account、Family、FamilyMember、GuardianRelation、Consent。
- Receipt：`FamilyContextReceipt`。
- 反向路径：邀请失效、关系待确认、无家庭、权限不足、撤回。

### J1｜表达问题并形成可修正理解

- 触发：家长遇到具体困扰或收到可信观察。
- 核心动作：通过文字、语音或必要媒体表达一次事件，查看“事实、我的表达、平台理解、仍未知”，回答追问并修正。
- 家庭结果：形成 Evidence、FamilyNeedCandidate 和可编辑家庭理解地图。
- 按需能力：只有需要更多结构化 Evidence 时才调用轻量、专项或综合 Assessment；测评不是固定关卡。
- 关键对象：ProblemIntake、Evidence、ContextSnapshot、UnderstandingDraft、GuardianCorrection、AssessmentSession、DimensionProfile。
- Receipt：`NeedUnderstandingReceipt`。
- 反向路径：转录失败、模型/知识不可用、误解、评估版本过期、暂不保存或删除。

### J2｜确认需要并选择支持方向

- 触发：理解草案已经形成，或按需评估补充了 Evidence。
- 核心动作：家长确认、修正、拒绝、暂停或要求更多信息，并共同定义可观察目标。
- 家庭结果：确认后形成版本化 FamilyNeed/GrowthIntent；Goal 与后续方案只引用它，不重新推断一套需要。
- 关键对象：GuardianDecision、FamilyNeedRef、GrowthIntent、Goal、Baseline、TargetCondition。
- Receipt：`GuardianDecisionReceipt`、`FamilyNeedConfirmedReceipt`。
- 反向路径：成员意见不一致、目标过度、证据不足、暂停或重新打开。

### J3｜形成并确认最小充分介入

- 触发：FamilyNeed 已由家长确认。
- 核心动作：比较知识支持、AI 协作、结构化计划、成长顾问、教师、专家或机构候选，并确认行动方案或明确不行动。
- 家庭结果：选择一个强度适当、依据清楚、可停止和可升级的 InterventionProposal 与 ActionPlan。
- 关键对象：InterventionCandidate、EvidenceGrade、Applicability、EscalationRule、ActionPlan。
- Receipt：`InterventionDecisionReceipt`、`ActionPlanReceipt`。
- 反向路径：没有合适候选、家庭拒绝、资源不可用、需要人工设计。

### J4｜实践、观察与复盘

- 触发：介入开始、行动到期、家长主动记录或到达复盘点。
- 核心动作：说明实际发生了什么、什么有帮助、什么没有，并选择继续、调整、暂停、停止或升级。
- 家庭结果：形成 ActionExecution、Observation、PhaseReview 和可讨论的 OutcomeProjection，而不是单纯 `Completed=true`。
- 关键对象：ActionExecution、Observation、Barrier、Reflection、PhaseReview、OutcomeProjection。
- Receipt：`ObservationReceipt`、`PhaseReviewReceipt`。
- 反向路径：未尝试、部分完成、冲突加剧、无法归因、数据矛盾、长期无改善。

### J5｜升级可信专业服务

- 触发：家长主动请求，或 J2/J4 表明 AI/自助支持不足。
- 核心动作：查看服务边界、负责人、资质、时间、价格和 SLA，主动预约、接受履约并反馈。
- 家庭结果：获得一次有责任人、可追踪、可取消和可补救的真人帮助。
- 关键对象：EscalationRequest、ServiceCase、ProviderMatch、Booking、DeliveryRecord、Feedback、Remedy。
- Receipt：`EscalationReceipt`、`ServiceDeliveryReceipt`、`RemedyReceipt`。
- 反向路径：容量冲突、拒单、超时、取消、服务失败、退款或补救。

### J6｜发现和使用知识、内容与社会资源

- 触发：家长在 J1、J2、J4 或 J5 主动寻找补充帮助。
- 核心动作：按 FamilyNeed 或明确查询选择 Evidence、专家解释、家庭经验、活动、短视频、直播或方案。
- 家庭结果：获得来源清楚、可收藏、可加入、可退出的资源，并返回理解、行动、复盘或服务主链。
- 关键对象：KnowledgeItem、ExperienceCard、ContentVersion、Activity、LiveSession、Collection、Report。
- Receipt：`ResourceEngagementReceipt`。
- 反向路径：空态、撤回、审核失败、过期、越权、举报、媒体故障。
- 边界：这是跨旅程可选分支，不是 J5 之后的强制内容流。
- 个性化边界：基于家庭上下文的推荐必须引用已确认 FamilyNeed；通用知识、主题浏览和紧急帮助入口不得强制创建 FamilyNeed。
- 媒体边界：直播、录制与回放必须具备审核、举报、stop switch、版权/版本、删除 lineage 与事故补救；Media Runtime 不拥有 FamilyNeed、Consent 或审核事实。

### J7｜阶段结果与长期连续性

- 触发：阶段复盘、服务履约完成、Need 观察窗口到达或家庭主动回看。
- 核心动作：判断需要是否改善、未变化、恶化或仍未知，并选择关闭、重开或形成下一 Need。
- 家庭结果：家庭知道“有没有帮助、为什么、下一步怎么选”，拥有目的明确、可修正、可撤回的成长连续性。
- 关键对象：OutcomeMeasure、OutcomeObservation、FamilyFeedback、ExpertPerspective、GrowthTimeline、Milestone、NextFamilyNeed。
- Receipt：`NeedOutcomeReceipt`、`NeedClosureReceipt`。
- 反向路径：无法归因、成员意见不同、结果恶化、数据不足、长期记忆撤回。
- 边界：时间线是前序 receipt 的投影，不是第二套家庭事实系统。

## 5. 五个平台运营场景

平台运营场景使用 `O1–O5`，不与家庭旅程共用编号，避免把后台建设误报为家庭价值。

| 场景 | 业务结果 | 核心能力 | 对家庭主链的接口 |
|---|---|---|---|
| O1 供给准入与能力维护 | 合适且有责任的教师、专家和机构可被服务调用 | 准入、资质、能力、容量、质量、退出 | ProviderMatch、DeliveryRecord |
| O2 介入、知识与服务设计 | 每个产品都从 Problem/Outcome/Intervention 设计 | BlueprintVersion、知识包、价格、适用范围 | InterventionCandidate、ResourceOption |
| O3 协同交付与结算 | 多角色贡献按真实交付与验收确认 | Role、ContributionEvent、RevenueRule、Dispute | ServiceCase、DeliveryRecord、Outcome |
| O4 运营、质量与事件处理 | 家庭、服务、供给、内容、直播可运营和补救 | Growth/Service/Supply/Knowledge/Media/Quality Ops | 状态查询、具名动作、补救 |
| O5 平台可信运行 | Evidence、AI、权限、审计、删除和评测可追溯 | Evidence Governance、AI Registry、Audit、Deletion | 全链 provenance、policy 与 replay |

O1–O5 不能直接改写 FamilyNeed、Outcome 或 GuardianDecision；任何人工操作必须通过具名动作、权限和 Audit/Outbox 进入业务域。

## 6. 从 16 个模块到能力地图

十六个模块是一级能力簇，不应未经裁决直接创建十六个 Domain。

### System A｜Family Growth System

| 能力簇 | 支持场景 | 核心对象 | 近期策略 |
|---|---|---|---|
| Identity & Family | J0、全链 | Family、Member、Guardian | 复用 Platform/Family canonical |
| Problem & Case | J1–J7 | ProblemIntake、Case、FamilyNeedRef | 先定义上位引用，不新建重复事实源 |
| Assessment | J1 | ToolVersion、Session、DimensionProfile | 作为按需能力深化家庭理解地图 |
| Goal | J2 | Goal、Baseline、TargetCondition | 优先复用 Growth/Journey |
| Intervention | J3 | Candidate、Proposal、EscalationRule | 先做 projection/contract |
| Action | J3–J4 | Plan、Execution、Observation | 复用 Journey canonical |
| Follow-up & Outcome | J4、J7 | Reflection、PhaseReview、Outcome | 区分 Observation 与 Outcome |

### System B｜Family Service Network

| 能力簇 | 支持场景 | 核心对象 | 近期策略 |
|---|---|---|---|
| Service | J5 | Case、Booking、Delivery、Remedy | 复用现有 Service canonical |
| Provider Network | J5、O1 | Teacher、Expert、Organization、Capacity | 先做受控供给，不做开放市场 |
| Product & Service Studio | J3、J6、O2 | Offering、BlueprintVersion、Applicability | 先服务一个场景方案 |
| ACN Collaboration | J5、O3 | Role、Contribution、Allocation、Dispute | 先证明真实履约，再启用分配 |

### System C｜Family Knowledge & Media Network

| 能力簇 | 支持场景 | 核心对象 | 近期策略 |
|---|---|---|---|
| Knowledge & Evidence | J1、J3、J4、J6、O5 | KnowledgeItem、EvidenceGrade、SourceRef | 建一个主题知识包与引用链 |
| Community & Search | J6 | Query、ExperienceCard、Collection、Report | 受控主题、诚实空态、无无限流 |
| Xiaojudeng Media | J6 | ContentVersion、LiveSession、MediaAsset | 独立产品队列，经接口对接 |

### Shared｜Family Intelligence Runtime 与 Platform Core

| 能力簇 | 支持场景 | 核心对象/接口 | 近期策略 |
|---|---|---|---|
| Family AI | J1–J7 | Model Gateway、Context、Draft、Human Gate、Eval | Workflow-first、固定回放 |
| Operations & Governance | J0–J7、O1–O5 | Identity、Consent、Audit、Outbox、Deletion、Policy | 复用唯一平台底座 |

### 6.1 Current / Target / Missing Owner 快照

以下状态只用于防止目标蓝图被误写成现有能力；正式 Current Truth 仍以 L0 canonical 文档和 Registry 为准。

| 能力簇 | 状态判断 | 近期边界 |
|---|---|---|
| Identity & Family | Mixed | Platform identity/consent 有基础，完整 Family 聚合与真实场景接线待核验 |
| Problem & Case / FamilyNeed | Missing Owner / Decision | 先裁决 FamilyNeed 与 GrowthNeed/GrowthIntent/Case 的映射 |
| Family AI | Foundation Current / Business Target | Model Gateway 有基础，Context、Clarification、Human Gate 与业务接线未闭合 |
| Assessment | Candidate | 已有局部纵切片；真实 Identity/Consent/PG 与完整体验待闭合 |
| Goal / Intervention | Target / Boundary Decision | Goal 优先归 Growth，Plan 归 Journey；AI proposal 不成为事实源 |
| Action / Follow-up / Outcome | Journey In Progress / Outcome Missing | Action、Observation、PhaseReview、Outcome 需明确分工 |
| Service | Candidate | 预约与履约有候选；真实主线和生产依赖未闭合 |
| Provider Network | Missing Owner | Teacher/Expert 共享 Provider 主体与资质模型，避免两个市场 |
| Knowledge & Evidence | Partial / Missing Owner | Evidence、KnowledgeReference、Content 必须分层 |
| Community & Search | Not Started | Search 作为跨域只读投影，不拥有内容事实 |
| Xiaojudeng Media | Independent / Missing interface owner | 媒体事实归小橘灯，AiFamily 持有 FamilyNeed/Consent/Service 引用 |
| Product/Service Studio 与 ACN | Partial Target | 先服务一个已验证场景，复杂分配与结算后置 |
| Operations & Governance | Core Partial / Ops Missing | 不建巨型治理域；运营台使用各域投影与受控命令 |

任何 `Current` 或 `Candidate` 都不等于完整产品、主线或生产能力；没有代码、可运行场景和真实环境证据时必须继续标 `Target`、`Not Started` 或 `Missing Owner`。

## 7. 核心对象所有权原则

下面是目标业务语义，不是新增表清单：

```text
Family / GuardianRelation / Consent
FamilyNeedRef / ProblemCase
Evidence / KnowledgeReference / ContextSnapshot
AssessmentSession / DimensionProfile / UnderstandingDraft
GuardianDecision / Goal / InterventionProposal
ActionPlan / ActionExecution / Observation / Reflection / Outcome
EscalationRequest / ServiceCase / Booking / DeliveryRecord / Remedy
ResourceOption / ContentVersion / Activity / LiveSession
Offering / OrderIntent / Entitlement
```

建模前必须回答：现有 canonical owner 是否已经拥有该语义；能否用字段、projection、receipt 或引用增量完成；是否需要 ADR；谁负责删除和回读。名字相似不能成为复制对象的理由。

### 7.1 事件与 receipt 标准

事件表达“发生过什么”，receipt 是跨场景和跨系统的稳定交接凭证。首批候选包括：

- `FamilyNeedExpressed` / `NeedUnderstandingReceipt`；
- `GuardianDecisionRecorded` / `FamilyNeedConfirmedReceipt`；
- `AssessmentSubmitted`；
- `GoalConfirmed`；
- `InterventionDecisionReceipt` / `ActionPlanReceipt`；
- `ObservationReceipt` / `PhaseReviewReceipt`；
- `NeedOutcomeReceipt` / `NeedClosureReceipt`；
- `EscalationReceipt` / `ServiceDeliveryReceipt` / `RemedyReceipt`；
- `KnowledgeReferenced` / `ResourceEngagementReceipt`；
- `ContributionRecorded` / `OrderIntentConfirmed`。

每个 receipt 至少包含：

```text
receipt_id
event_type
aggregate_type / aggregate_id
tenant_id / family_id
actor_id / actor_role
source_version
occurred_at
correlation_id
idempotency_key
consent_ref
audit_ref
payload_hash
```

receipt 字段与 owner 是目标契约，必须经相邻场景和 Platform owner 会签；不得在各场景中分别发明不兼容格式。

## 8. 终端矩阵

### 8.1 家庭端

| 入口 | 用户问题 | 主要场景 |
|---|---|---|
| Today | 今天最值得关注和完成什么 | J3、J4、J5、J7 |
| Ask Famili | 我家刚发生了什么，平台如何理解 | J1、J2 |
| Discover | 哪里有相关知识、经验、活动和直播 | J6 |
| Growth | 我们的需要、计划、观察和结果如何变化 | J1–J4、J7 |
| Family | 谁属于家庭、谁能看什么、服务与权益在哪里 | J0、J5、J7 |

首页首屏优先承接“说说家里最近发生的一件事”和“继续上一次行动/复盘”。课程、直播、专家和商品按已确认需要渐进出现，不做六宫格产品货架。

### 8.2 专家端

`待接单 → 阅读授权材料 → 判断适配性 → 接受/转介 → 服务方案 → 服务交付 → 记录观察 → Outcome → 补救/随访`。首页优先展示今天需要负责的家庭、SLA 和风险，而不是课程、直播或收入入口。

### 8.3 教师端

围绕“收到协作请求 → 查看必要教育上下文 → 提交具体观察 → 参与目标或介入 → 反馈执行情况 → 家校复盘”；只显示 Guardian 授权且完成任务所必需的 Education Context，不建设儿童行为积分中心。

### 8.4 机构端

围绕“供给准入 → 服务配置 → 家庭服务请求 → 分派责任人 → 容量与 SLA → 履约 → 质量异常 → 补救 → 结算”；机构购买服务能力不等于取得家庭数据，首页优先展示履约风险和待补救事项。

### 8.5 运营端

使用 Need、Intervention、Service、Supply、Knowledge、Media、Quality/Governance 中心组织后台，不回到 Banner/文章/用户的传统 CMS 结构。运营核心问题是“哪个家庭旅程断了、谁负责恢复”。

## 9. 三层编号与映射

| 全量 MVP 场景 | 本蓝图旅程阶段 | 说明 |
|---|---|---|
| S1 首次被理解 | J0–J2 | 建档、表达、理解、按需评估与 Need 确认 |
| S2 成长循环 | J3、J4、J7 | 介入、行动、观察、复盘和 Outcome |
| S3 知识与 AI | 横跨 J1–J4，并支持 J6 | 是协作能力，不是孤立聊天入口 |
| S4 专业服务 | J5、J7 | 服务升级、履约、反馈和补救 |
| S5 家庭关系 | J6、J7 | 受控经验、活动、关系连接与长期连续性 |
| S6 价值转化 | J2、J3、J5、J6，及 O2/O3 | 从确认需要到方案、权益、交易和履约 |

三层编号各司其职：`J0–J7` 描述家庭旅程，`S1–S6` 描述 MVP 交付包，`O1–O5` 描述平台运营场景。项目排期只使用 S1–S6 作为主键，避免同一团队同时被三套编号调度。

## 10. P0/P1/P2 产品化路线

### P0｜Golden Family Journey

目标：证明一个家庭可以从问题进入，到获得理解、选择介入、行动并完成首次复盘。

```text
J0 家庭访问
  → J1 表达问题、可编辑理解与按需评估
  → J2 确认 FamilyNeed/Goal
  → J3 选择最小充分介入
  → J4 实践、观察与首次复盘
  → J7 形成阶段结果与下一决定
```

P0 必须具备：Family/Guardian、Problem/Evidence、理解 Draft、轻量 Assessment、Goal、InterventionProposal、Action、Observation、Reflection/Outcome，以及相应 Consent、Audit/Outbox、Idempotency、Deletion 和真实 HTTP/PG 回读。

最小充分介入示例不是“今晚做一件小事”，而是：

> 在未来七天重构晚间学习启动机制：家长与孩子共同明确开始时间、第一步和求助方式；记录三次启动过程，复盘冲突强度、启动耗时和双方感受。若三次均无法启动或冲突升级，则暂停当前方案并升级专业支持。

### P1｜AI 到真人的连续服务

在 P0 上增加 Family Advocate、Teacher/Expert、ProviderMatch、Booking、ServiceCase、DeliveryRecord、SLA、反馈、取消与补救；同时让一个知识包和一个小橘灯已审核资源能通过 FamilyNeed 对接，不成为独立入口。

### P2｜平台网络与规模化

增加受控家庭关系网络、Product & Service Studio、机构、ACN 协同、B2B2C、完整权益/交易、运营中心和更丰富的 Knowledge/Media Network。P2 扩展网络，但不能改变 FamilyNeed 驱动和家庭结果优先。

## 11. 阶段验收

### P0 可运行场景

- 正向：家长表达真实问题，修正平台理解，完成必要评估，确认 Need，选择介入，执行并复盘。
- 拒绝：家长拒绝理解 Draft，不形成 Goal 或 Plan。
- 撤回：Consent 撤回后停止处理，相关引用与派生数据进入删除流程。
- 越权：跨 family 不泄露对象是否存在。
- 故障：AI、知识、数据库或通知不可用时不渲染成功，保留可恢复点。
- 重启：新会话和服务重启后能回读同一 receipt、行动与复盘。

### P1 可运行场景

- 家长主动升级真人服务，知道服务范围、责任人、价格和 SLA；
- 容量冲突、取消、履约失败和投诉有清楚补救；
- 专业人员只能读取任务所需的授权上下文；
- 服务 Outcome 回到同一 FamilyNeed。

### P2 可运行场景

- 家长在受控主题中搜索、收藏、参加活动或举报；
- 方案、权益、交易、退款和履约可回读；
- 机构与多角色协作不复制家庭事实；
- 内容、社区、直播和商品撤回后，所有引用同步失效。

## 12. 产品与项目指标

一级指标：被理解感、修正成功率、Need 确认质量、介入关联度、首次复盘质量、Outcome 改善/未知比例、成人帮助感、服务履约与补救、恢复成功率、信任损耗。

领先指标：问题表达完成、行动尝试、观察记录、复盘到达、知识引用查看、人工接管成功。

经营指标：转化、续用、服务毛利、履约成本、退款和 GMV。经营指标必须与家庭结果联读，不能反向驱动儿童画像、过度介入或注意力优化。

## 13. 任何新功能的五问

1. 它解决哪个 FamilyNeed？
2. 它处于家庭成长旅程哪个阶段？
3. 它是否改善理解、介入、行动、复盘或服务履约？
4. 它产生什么可观察 Outcome 或新的 Evidence？
5. 它是否增强家庭的长期连续性与信任？

回答不清楚的功能，不进入主产品主链。

## 14. 从蓝图进入实施的条件

本文件获批后，每个阶段还必须形成：

- 场景闭环 PRD；
- capability/owner/pathspec 映射；
- 对象状态与 API/事件/receipt contract；
- 家庭端与专业端逐屏流程；
- 正反场景测试和环境同构计划；
- Current/Target/Missing Owner 状态表；
- Sprint Backlog 与可展示 artifact 标准。

在这些输入未闭合前，不得把本蓝图中的 8 个家庭旅程、5 个运营场景、16 个能力簇或三个系统直接翻译成新增 Domain、数据库表或团队数量。
