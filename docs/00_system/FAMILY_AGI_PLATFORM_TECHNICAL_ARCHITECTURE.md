---
id: FAMILY-AGI-PLATFORM-TECHNICAL-ARCHITECTURE-001
title: FAMILY AGI PLATFORM 技术总架构
type: target-architecture
status: draft
version: 1.1
owner: chief-architect
created: 2026-09-11
canonical: false
supersedes: null
superseded_by: null
extends: docs/00_system/TARGET_ARCHITECTURE.md
relates-to: docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md, governance/ADR/ADR-0167-family-agi-runtime-architecture.md, governance/ADR/ADR-0158-agi-native-family-growth-platform.md, docs/00_system/FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md
---

# FAMILY AGI PLATFORM 技术总架构

```text
⚠️ 读本文件前必须明白一件事（跟docs/00_system/TARGET_ARCHITECTURE.md同一条纪律）：

status: draft, canonical: false   指的是"这份技术架构本身待总架构师最终确认，
                      尚未走完docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2的
                      Research→Decision→Canonical晋升流程"，
                      不是"这里画的东西已经建好了"，也不是"内容不重要"。

本文件内容 = TARGET（目标态），是docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md
战略定位的技术实现层，不是当前代码的能力声明。

系统现状 = docs/00_system/CURRENT_SYSTEM_BASELINE.md
本文件里任何一个方框、实体名、Port，除CURRENT_SYSTEM_BASELINE.md明确列为
Implemented以外，都还不存在。当前诚实进度见第十节。
```

**跟`docs/00_system/TARGET_ARCHITECTURE.md`的关系**：本文件不取代它——
`TARGET_ARCHITECTURE.md`定义的八层组织架构/三层价值网络/独占区/FGCN-ACN
协作网络继续是权威的**整体系统**目标架构。本文件是它的**AGI智能内核**
子专题深化——`TARGET_ARCHITECTURE.md`里的Domain层（`backend/domains/*`）
对应本文件的`P4 DOMAIN TRUTH PLANE`，两者是同一套系统在不同专题视角下的
描述，字段/Port命名冲突时以后续实施ADR裁决为准，本文件不单方面覆盖既有
Port契约。

**定位**：AGI-native Family Intelligence Platform。**核心特征**：感知、
理解、规划、行动、学习、评估、受控进化。**基本需求单位**：Family。
**第一切入口**：Child Growth。**长期目标**：Family Intelligence
Infrastructure。战略层定义见`docs/01_strategy/FAMILY_AGI_PLATFORM_
BLUEPRINT.md`，本文件回答"这套定位在代码里怎么落地"。

## 一、技术总纲

Family不采用"传统业务平台+若干AI功能"，采用：

```text
Family World Model 驱动认知
        +
  Goal / Plan 驱动运行
        +
  Skill 驱动能力组合
        +
Tool / Human 驱动现实行动
        +
  Outcome 驱动学习
        +
  Eval 驱动改进判断
        +
Governance 驱动受控进化
```

平台从根本上是一个**Closed-loop Intelligence System**：`Sense →
Understand → Model → Reason → Plan → Act → Observe → Evaluate → Learn
→ Evolve`。

## 二、七大技术Plane（正式冻结）

```text
P1 EXPERIENCE PLANE          用户、家庭与智能系统的持续交互
        ↓
P2 FAMILY INTELLIGENCE PLANE 理解、世界模型、推理、目标、计划、Agent
        ↓
P3 ACTION & RESOURCE PLANE   Skill/Tool/Human Gate/社会资源
        ↓
P4 DOMAIN TRUTH PLANE        Family/Person/Growth/Journey/Service/
                              Identity/Consent/Assessment/Action
        ↓
P5 OUTCOME & LEARNING PLANE  Observation/Outcome/Reflection/Pattern
        ↓
P6 EVALUATION & EVOLUTION PLANE  Eval/Gap/Improvement/Candidate
        ↓
P7 GOVERNANCE & CONTROL PLANE    Safety/Consent/Audit/Release/Rollback
```

七个Plane不是七套独立平台，共同组成一个运行内核。P4对应`TARGET_
ARCHITECTURE.md`已有的Domain层各域；P7横切全部Plane，不是流水线上的一环，
是常驻治理层（跟ADR-0162 G0-G6横切纪律定位一致）。

## 三、P1 — Experience Plane

**C01 Famili Principal**：负责长期关系/自然语言交互/情绪价值/对话连续性/
解释/家庭导航/确认/提醒，**不得拥有**独立Planner/独立模型调用路径/独立
业务真相/独立记忆真相。运行路径必须是`Famili Principal → Family
Intelligence Kernel`——这是ADR-0167已冻结的Principal边界（"不得拥有独立
Model Gateway路径"）在体验层的重申，不是新规则。

**C02 Multimodal Family Interaction**：Text/Voice/Image/Video/Document/
Assessment/Realtime Avatar统一转化为`Observation/Evidence/Expression/
Intent`，而不是不同业务真相——多模态只是输入/表达形式。

**C03 Dynamic Family Experience**：前端不是固定菜单驱动，而是
`FamilyWorldState + Current Goal + Current Plan + Current Need +
Pending Action → Experience Composer`，输出可信组件（`NeedCard/GoalCard/
PlanCard/ActionCard/OutcomeCard/AssessmentCard/ExpertCard/LiveCard/
SkillCard/GuardianConfirmCard`）。原则：**AGI决定展示什么，不自由生成
任意UI**。

**C04 Family Timeline**：统一展示"发生了什么/为什么发生/我们做了什么/
结果怎么样/现在正在解决什么/下一步是什么"，是长期陪伴体验的基础。

## 四、P2 — Family Intelligence Plane：六个系统

### S01 Family Understanding System

把家庭的自然表达转化为结构化、带证据、不确定性的理解。输入：
Conversation/Assessment/Observation/Feedback/Historical Action/Service
Result/Professional Input。输出：`FamilyNeedCandidate/Evidence/Unknown/
Hypothesis/RiskSignal/WorldModelUpdateProposal`。必须区别`FACT/
OBSERVATION/INFERENCE/HYPOTHESIS/PROPOSAL`——**禁止LLM推测直接变成
DomainFact**，这是INV-01（第十二节）的直接来源。

### S02 Family Need System

`FamilyNeed`是一级对象——补充`docs/00_system/FAMILY_NEEDS_PLATFORM_
TARGET_MODEL.md`已有的N0-N8定义，本节给出目标态的具体字段：

```text
FamilyNeed
  need_id / tenant_ref / family_scope_ref
  expressed_need / normalized_need
  related_subjects
  context_refs / evidence_refs / unknowns
  hypotheses
  risk_level
  status
  goal_refs / plan_refs / resource_refs
  outcome_refs
  created_at / updated_at
```

生命周期：`EXPRESSED → UNDERSTANDING → CLARIFIED → GOAL_PROPOSED →
ACTIVE → RESOLVING → IMPROVED/RESOLVED/ESCALATED`。核心理念：**平台管理
的是需求，而不是流量**——这是`FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`
"N1不替家庭定义需求"纪律的对象化实现，字段名以后续实施ADR为准，跟已有N0-N8
的`FamilyNeed`/`NeedSignal`/`NeedProfile`等对象需要一次映射对齐，不是
平行发明第二套。

### S03 Family World Model

不是新业务数据库，是对现有家庭事实/记忆/行为/上下文的**Read-only
Intelligent Projection**：`FamilyWorldStateSnapshot`，特征：immutable/
time-bound/evidence-grounded/scope-aware/confidence-aware/replayable。
结构：`IdentityState/RelationshipState/DevelopmentState/NeedState/
GoalState/PlanState/ActionState/OutcomeState/ResourceState/RiskState/
PreferenceState/UnknownState`。每个State必须支持`as_of/evidence_refs/
confidence/contradictions/freshness`，不是只有`value`——这是
`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第四节`Unknowns`层和第二十六节
`World Model Confidence`的具体schema化。

### S04 Goal & Planning System

核心对象分开：`GoalProposal ≠ GuardianDecision ≠ GrowthIntent`。流程：
`FamilyWorldState → Need → Primary Contradiction → GoalProposal →
Guardian Confirmation → GrowthIntent → PlanDraft → Plan`。Planner采用
两层：**Deterministic Policy Layer**（处理Consent/Age/Risk/
Availability/Prerequisite/Contraindication/Region/Policy）+
**Reasoning Planner**（处理优先级/因果假设/策略组合/时间安排/行动顺序/
备选方案/解释）——跟ADR-0167已有判断（`ContextDrivenPathDraftPlanner`
一类确定性打分层不冒充Planner）一致，是它在Goal/Plan完整流程里的位置
确认。

### S05 Agent Runtime

必须保持唯一生产执行路径：`Principal / Planner / Assessment AI / Coach
/ Reflection / Resource Intelligence / Evolution Intelligence →
AgentRuntime → Model Gateway`。**不允许**出现`Principal→Gateway`/
`Planner→Vendor SDK`/`Skill→Model API`这类绕过路径——任何生产模型执行
必须经过AgentRuntime，这是INV-02（第十二节）的来源，也是ADR-0167"不新建
第四套runtime、扩展现有`agent_runtime/`"裁决在执行路径唯一性上的具体
约束。

### S06 Model Gateway

Foundation Model可替换，支持provider routing/model routing/structured
output/fallback/timeout/retry/token accounting/cost accounting/
provenance/latency/safety policy。运行对象`GatewayAttempt`——**它不等于
`AgentRun`**（见ADR-0167四级Run Taxonomy，下节复述其在本架构里的位置）。

## 五、四级运行对象（复述ADR-0167已冻结定义，标注本架构里的具体形态）

```text
GatewayAttempt → AgentRun → IntelligenceRun → NamedAction / DomainFact
```

`GatewayAttempt`=一次模型网络调用；`AgentRun`=一次有限的技术Agent执行；
`IntelligenceRun`=一次完整的家庭智能认知过程，可能包含多个AgentRun/多次
人类交互/多次Evidence更新/多次Guardian修改/Reflection/Replan；
`DomainFact`=真实世界业务事实，只有Domain Service/Named Action/
Authorized Human Action才能写入。**IntelligenceRun是未来AGI的核心运行
单位**——例如一次`IR-1001`可能包含：Need="孩子不愿沟通"，WorldState v42，
AgentRuns=[understanding, evidence, planner]，Guardian edits=1，
Goal=改善沟通安全感，Plan=v3，Outcome=partial，Reflection=当前行动强度
偏高，Replan=Plan v4——这比"保存一次LLM response"高一个数量级，是本架构
区别于普通LLM应用日志的关键。

## 六、P3 — Action & Resource Plane

### S07 Skill Runtime

所有解决问题能力统一成`GrowthSkillSpec`（字段见`FAMILY_AGI_PLATFORM_
BLUEPRINT.md`第十八节，本文件不重复列出，两文件字段定义须保持一致，出现
分歧以后续实施ADR为准）。课程未来不是独立系统孤岛，而是`CourseContent →
GrowthSkillCompiler → GrowthSkillSpec`。GrowthSkill是"可学习能力"：
`Problem + Context + Intervention Logic + Action + Outcome + Learning
Contract`，未来支持`Skill v1 → Outcomes → Evaluation → Skill v1.1`。

### S08 Tool Runtime

唯一Action Bus：`Planner → Skill → ToolRuntime → Policy Gate → Human
Gate → PendingNamedAction → NamedAction → Domain`。Tool可包括send
reminder/book expert/create activity/schedule check-in/generate
report/open service case/create task/send parent confirmation。
**LLM不得直接执行现实动作**——这是INV-03（第十二节）的来源。

### S09 Family Resource Network

资源对象统一为`Resource`（类型：AI Skill/Teacher/Expert/Institution/
Course/Live Session/Community/Camp/Activity/School Resource/
Professional Service/Public Resource），不是传统资源目录。匹配逻辑：
`FamilyNeed × FamilyPattern × Goal × PlanStage × ResourceCapability ×
Availability × HistoricalOutcome → ResourceRecommendation`。

**Family ACN**：复杂需求可能由多个角色协同完成（`Famili Principal →
Planner → {Parent Coach, Teacher, Psychologist, AI Coach,
Community}`），未来记录Need discovery/Planning/Trust/Delivery/Outcome
各环节的contribution，形成可配置分工分账——不是简单销售佣金系统，跟
`family-allocation-platform-mechanisms`历史资产的FGCN角色分账判断
一致，本节是它在ACN多角色协同场景下的扩展。

## 七、P4 — Domain Truth Plane

核心原则：**Intelligence is not Truth**。必须明确`Family World Model
≠ Family Domain Database`。Domain Truth负责Family/Person/Guardian/
Consent/Assessment/Journey/GrowthIntent/Plan/Action/Service/Resource/
Transaction/Outcome Fact——对应`backend/domains/*`各域现状，本架构不
新建平行的domain层。

**Identity & Scope**（必须在R2优先解决，见第十四节Gate）：
`DomainFamilyId ≠ FamilyScopeRef`，两者不能继续混用；统一四个Runtime
Ref：`TenantRef/FamilyScopeRef/SubjectRef/ActorRef`；真实业务对象是
`DomainFamilyId/DomainPersonId`。**这正是本会话R0.5 BLOCKER-001调研中
实际观察到的问题的正式架构回应**——`service_cases`历史迁移
（`0070_service_cases_scope_refs_string`）把`family_id`从uuid+FK widen成
opaque string varchar，本质是在真实身份模型缺失的情况下，用"放宽类型
约束"暂时承载了两种不同语义（真实Family UUID vs 运行时opaque scope
slug）。R2.2 Scope Contract要做的，是把这两种语义正式拆开，不再靠"把
UUID列widening成String"这种兼容性妥协来长期承载两种身份语义。

**Authorization Decision Point**：所有敏感读取遵循`Identify Resource →
Resolve Subject → Assert Tenant → Assert Family Scope → Assert
Consent/Purpose → Read Sensitive Evidence`。**不得**让SQL把无权限记录
过滤没了、导致Application误认为NOT_FOUND——`FORBIDDEN != NOT_FOUND`，
这正是本会话已修复的consent withdrawal P0 bug（`backend/domains/
assessment/infrastructure/sqlalchemy_repository.py`，commit
`7e3041b5`）的一般化原则，本节把那次具体修复升级为架构级不变量，防止
同类bug在其它域重演。

## 八、P5 — Outcome & Learning Plane

### S10 Outcome System

Action创建时必须定义`ExpectedObservation/MeasurementWindow/
SuccessCriteria/FailureCriteria/StopCriteria/EscalationCriteria/
LearningEligibility`（即`LearningSignal`，见`FAMILY_AGI_PLATFORM_
BLUEPRINT.md`第二十五节）。`Action → Observation → Outcome`。Outcome
不是"用户点了完成"，是"真实世界发生了什么变化"。分类至少：`POSITIVE/
PARTIAL/NO_CHANGE/NEGATIVE/UNKNOWN`，同时记录`confidence/evidence/
observation_window/source`。

**Reflection Engine**：回答"为什么有效/无效？哪个假设被支持/推翻？计划
哪里需要调整？需要更多Evidence吗？"，输出`Reflection`，**不直接改
Plan**。**Replan**必须明确`Plan v1 → Outcome → Reflection → Plan v2`，
保留`why_changed/evidence_refs/outcome_refs/previous_plan_ref`——这将
成为Family AGI的第一黄金能力（见第十三节Golden AGI Test）。

### Learning Plane四级（复述`FAMILY_AGI_PLATFORM_BLUEPRINT.md`
第十三节，标注跨家庭学习的合规前置条件）

`L1 Family Adaptation`（单家庭个性化学习）/`L2 Population Outcome
Learning`（跨家庭统计与模式）/`L3 Capability Learning`（Skill/Planner
优化）/`L4 Platform Evolution`（系统发现自己缺什么能力）。**L2绝不能
直接读取所有家庭数据**——必须经过`Consent → Purpose → Eligibility →
Minimization → Aggregation/De-identification → Policy`，形成
`LearningEligibleOutcome`才能进入群体级学习，这是`FAMILY_AGI_PLATFORM_
V1_BLUEPRINT.md`第三十三节"绝不能走向家庭监控平台"红线的具体门禁点。

**Family Pattern Library**：长期形成`Pattern`，但定义为**Probabilistic
Pattern**，不是Permanent Label——例如`{high-parent-control,
high-child-autonomy, communication-conflict, confidence: 0.67}`不能
变成"这个家庭就是控制型家庭"这类固化标签。

## 九、P6 — Evaluation & Evolution Plane

### S11 Evaluation Platform

任何智能能力必须**Eval-by-Default**：`Benchmark/Golden Cases/
Regression Cases/Safety Cases/Adversarial Cases/Outcome Cases`。例如
`Planner v7 vs v8`须比较Goal acceptance/Plan completion/Outcome
improvement/Safety/Escalation/Cost/Latency。Evaluation Dataset来源：
Synthetic Cases/Curated Expert Cases/Historical Replay/Anonymized
Outcome Cases/Regression Incidents/Safety Red-team Cases，全部必须
版本化。

### S12 Family Evolution Engine

组成（跟`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第三十节E1-E7一一对应）：
`Performance Observer → Failure Pattern Miner → Capability Gap
Detector → Improvement Designer → Evaluation Factory → Evolution
Governance → Release Controller`。链路：`Observe → Detect Gap →
Explain → Generate Candidate → Evaluate → Govern → Release → Observe
Again`。

**CapabilityGap**是一级对象：`gap_id/capability/evidence_refs/
affected_family_patterns/failure_rate/severity/hypothesis/
possible_solution_types/priority`。**ImprovementCandidate**类型：
`PromptCandidate/SkillCandidate/PlannerPolicyCandidate/AgentCandidate/
ToolCandidate/ResourceStrategyCandidate`——**`Candidate != Production
Capability`**，这是INV-05（第十二节）的直接来源。

**Self-Evolution权限分级**（复述`FAMILY_AGI_PLATFORM_BLUEPRINT.md`
第三十一节表格，此处仅标注对应的自动化程度）：`E0/E1`可高度自动化评估；
`E2`必须Release Gate；`E3`需Architecture+Safety Review；`E4`需Human
Approval；`E5`（未成年人/医疗/重大决策边界）**禁止系统自行发布**——
这条跟第七节"敏感权限判断"是同一类不可协商边界在Evolution Engine场景
下的复述。

## 十、P7 — Governance & Control Plane

AGI越强，这一层越重要。统一治理：Consent/Purpose Limitation/Minor
Protection/Tenant Isolation/Family Isolation/Policy/Human Gate/Audit/
Provenance/Deletion/Safety/Evaluation Gate/Release Gate/Rollback。
原则：**Greater Intelligence → Stronger Governance**。

**Governed Autonomy**：系统自治程度根据Risk/Data Sensitivity/Action
Reversibility/Financial Impact/Child Impact/Health Impact/External
Side Effect动态决定——例如"推荐一篇文章"自动、"调整学习计划草案"自动
提出、"预约老师"需Guardian确认、"心理高风险处理"强制人工、"改变数据
用途"禁止自动。这是`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第九节既有
Governed Autonomy五级在具体动作粒度上的举例，不是新增一套分级。

## 十一、十二大核心子系统与四十项核心能力地图

```text
S01 Family Understanding    S07 Skill Runtime
S02 Family Need             S08 Tool Runtime
S03 Family World Model      S09 Family Resource Network
S04 Goal & Planning         S10 Outcome Learning
S05 Agent Runtime           S11 Evaluation Platform
S06 Model Gateway           S12 Evolution Engine
```

治理（P7）作为跨系统Control Plane，不是第十三个孤立业务系统。

**四十项核心能力地图**（分组，供后续任务拆解引用编号，不代表四十项等
优先级，优先级见第十四节R2-R10映射）：

```text
A. Experience       01 Principal Conversation / 02 Multimodal Input /
                    03 Dynamic Experience / 04 Family Timeline /
                    05 Guardian Confirmation
B. Understanding    06 Intent Understanding / 07 FamilyNeed Detection /
                    08 Evidence Extraction / 09 Unknown Detection /
                    10 Hypothesis Generation
C. World Model      11 WorldState Assembly / 12 Temporal State /
                    13 Confidence / 14 Contradiction Tracking /
                    15 State Replay
D. Goal / Plan      16 Primary Contradiction / 17 Goal Proposal /
                    18 Goal Confirmation / 19 Plan Generation / 20 Replan
E. Skills / Agents  21 AgentRuntime / 22 Skill Registry /
                    23 Skill Selection / 24 Skill Execution / 25 AI Coach
F. Action/Resources 26 ToolRuntime / 27 HumanGate / 28 NamedAction /
                    29 Resource Matching / 30 Collaborative Service
G. Outcome/Learning 31 Observation / 32 Outcome Measurement /
                    33 Reflection / 34 Family Adaptation /
                    35 Population Learning
H. Evolution/Gov    36 Capability Gap Detection / 37 Improvement
                    Candidate / 38 Evaluation Factory / 39 Controlled
                    Release / 40 Rollback & Safety Governance
```

## 十二、五条核心Architecture Invariants（代码评审强制检查项）

```text
INV-01  Family Domain Truth 与 AI 推理结果严格分离。
INV-02  所有生产模型调用必须经过 AgentRuntime → Model Gateway。
INV-03  所有现实动作必须经过 ToolRuntime → Governance/Human Gate → NamedAction。
INV-04  所有成长干预必须具备 Outcome / Learning Contract。
INV-05  所有平台自我进化必须经过 Eval + Governance + Release Gate。
```

任何设计违反其中一条，都不能进入主线——这五条是本文件对既有分散纪律（ADR-
0167 Principal边界/NamedAction边界、`AI_NATIVE_PRINCIPLES.md`生成式
纪律、本次consent bug教训、ADR-0162 Gate纪律）的统一压缩，供后续代码
评审直接引用编号，不需要每次重新展开论证。

## 十三、核心数据对象总表 / 禁止的重复对象 / Memory定位 / Replay原则

**核心数据对象**（目标态，后续实施ADR逐一定稿，字段名以最终ADR为准）：

```text
TenantRef / FamilyScopeRef / SubjectRef / ActorRef
FamilyNeed
Evidence / Unknown / Hypothesis
FamilyWorldStateSnapshot
GoalProposal / GuardianDecision / GrowthIntent
Plan / PlanStep
GrowthSkillSpec
Resource / ResourceCapability
ActionProposal / PendingNamedAction / NamedAction
Observation / Outcome / Reflection
GatewayAttempt / AgentRun / IntelligenceRun
LearningSignal / FamilyPattern
CapabilityGap / ImprovementCandidate / EvaluationRun / ReleaseDecision
```

**不应该新增的重复对象**（禁止清单，直接对应ADR-0167已经处理过的"三套
并行智能执行"教训，不要重演）：第二套WorldState/第二套Planner Runtime/
第二套Run Ledger/第二套Agent Runtime/第二套Action Bus/第二套Memory
Truth/第二套Consent Gate。任何新概念首先回答"能不能扩展现有内核"，不能
默认新建subsystem。

**Memory的定位**：Memory只负责"过去发生过什么、系统应该记住什么"；
World Model负责"现在应该如何理解这个家庭"；Outcome负责"行动以后发生了
什么"；Learning负责"这些Outcome意味着什么"。四者不能混。

**Experience Run / Agent Run的收敛**（复述ADR-0167已冻结的裁决，
Logical convergence, NOT physical table merge）：现有`ai_agent_runs`/
`ai_agent_traces`继续承担AgentRun Technical Ledger；现有
`experience_runs`/`experience_run_events`/`experience_run_checkpoints`
演化承担IntelligenceRun Cognitive Ledger；不合并物理表，逻辑上统一。

**Replay是AGI必须具备的基础能力**：AgentRun Replay回答"当时模型调用
发生了什么"，不得重新调用模型；IntelligenceRun Replay回答"当时系统基于
什么WorldState、得到什么Evidence、Guardian修改了什么、为什么生成这个
Plan、为什么后来Replan"，同样`ZERO MODEL SIDE EFFECT`。

**自我学习不是在线乱更新模型**：短中期优先WorldState Update/Skill
Versioning/Planner Policy Evolution/Retrieval Improvement/Resource
Matching/Prompt Improvement/Outcome Intelligence，不是立即持续
Fine-tune基础模型——Foundation Model始终保持可替换（`FAMILY_AGI_
PLATFORM_V1_BLUEPRINT.md`第二十九节"Learning Asset ≠ Foundation
Model"的技术实现约束）。

**技术基础设施原则**：V1-V2阶段`Python + FastAPI + SQLAlchemy +
PostgreSQL`足够，暂时不因"未来AGI"自动引入Neo4j/Kafka/Temporal/Redis/
Vector DB cluster/Kubernetes微服务爆炸，只有明确瓶颈出现才引入。
PostgreSQL长期承担Domain Truth/Run Ledger/WorldModel source facts/
Plan/Skill Metadata/Outcome/Evaluation Metadata/Governance/Resource
Network；向量能力未来如需要，先benchmark pgvector，不是直接新引入数据库
——跟本会话R0.5全程"不擅自引入新基础设施、先证明必要性"的纪律完全一致。

## 十四、R2-R10映射与R2实际优先顺序

```text
R2   Runtime Foundation      统一执行/统一身份范围/统一Run taxonomy
     任务: GatewayAttempt/AgentRun/IntelligenceRun/DomainFact,
           TenantRef/FamilyScopeRef/SubjectRef/ActorRef
     完成标准: one model execution path / one scope contract / one action path

R3   Family World Model      FamilyWorldStateSnapshot/Assembler/Sources/
                              Evidence/Unknown/Confidence/Temporal State
                              + LearningSignal Contract V0

R4   Goal & Planning         FamilyNeed/GoalProposal/GuardianDecision/
                              GrowthIntent/Plan/Planner；每个Plan必须定义
                              Expected Outcome

R5   Growth Skill Runtime    GrowthSkillSpec/Skill Registry/Skill Compiler/
                              Skill Selection；21天成长营/课程内容逐渐编译
                              成Skill

R6   Long-Horizon Loop       跑通Need→Goal→Plan→Action→wait→Outcome→
                              Reflection→Replan

R7   Dynamic Experience      Experience Component Registry/Dynamic
                              Composer/Principal Experience/Family Timeline

R8   Outcome Learning        Outcome System/Learning Signals/Reflection/
                              Population Pattern/Outcome Intelligence

R8.5 Evaluation Platform     Benchmark/Golden Case/Replay Dataset/
                              Regression/Safety Eval

R9   Resource Intelligence   Resource Network/Outcome-aware Matching/
                              Human Service/ACN Collaboration

R9.5 Evolution Engine        Capability Gap/Improvement Candidate/
                              Eval Factory/Release Candidate

R10  Controlled Multi-Agent  specialized agents/agent collaboration/
     AGI                     external agents/A2A + Governed Self-Evolution
                              （最后才发展，不是V1.1近期范围）
```

**R2实际优先顺序**（不是一次写大量AGI代码，严格顺序）：`R0 Main Green
→ R2.1 Run Taxonomy → R2.2 Runtime Scope Contract → R2.3
IntelligenceRun → R2.4 Single Model Execution Path → R2.5 AgentRun↔
IntelligenceRun link → R2.6 Absorb Vertical Runtime`。R2.1已按ADR-0167
完成`Proposed→Accepted`（见该ADR"R2.1定稿"一节）；R2.2及以后按总架构师
此前裁决"暂缓，先清R0 Green Blocker"（见ADR-0158对应记录），本文件不
改变这个已生效的排序决定，只提供R2.2启动后的技术路线图。

**R3前必须通过的架构Gate**：`Principal没有直连Model Gateway / Vertical
Runtime没有独立模型通路 / EvaluationLedger无production caller /
AgentRun与IntelligenceRun语义分开 / DomainFamilyId与FamilyScopeRef不混
/ Replay无模型副作用 / HumanGate durable / Consent fail-closed / Main
Green`——缺一项，禁止进入World Model冻结阶段。这条Gate跟R0/R2的既定
排序（"先R0 Green再R2.2"）完全一致，是它的具体检查清单化。

**FamilyNeed作为R3/R4之间的桥梁**：`R3 World Model understands family
→ R3.5 FamilyNeed V1 → R4 Goal/Plan resolves need`。FamilyNeed是World
Model与Goal/Plan之间最重要的业务桥梁。

## 十五、第一Golden Vertical与FAMILY AGI V1真正的MVP

**继续选Parent-Child Communication**（理由：高频/高情绪价值/结果可
观察/风险相对可控/家庭变量明显/适合Action/适合Replan/可以引入Human
Resource）。Golden Need示例："孩子越来越不愿意跟我说话，一谈学习就吵
架。"

**Golden Vertical必须覆盖整个内核**，不是Demo页面：`Expression →
Understanding → FamilyNeed → Evidence → Unknown → WorldState →
Hypothesis → GoalProposal → GuardianConfirm → Plan → Skill → Action →
Outcome → Reflection → Replan`，最终再接Human Resource。

**FAMILY AGI V1真正的MVP不是"100个功能"，是"1个FamilyNeed+1条完整智能
闭环+真实Outcome+真实Replan"**——这是本文件对"什么算做完了V1"这个问题
最重要的产品判断，跟`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第三十五节
Golden E2E一的验收标准是同一件事的两种表述。

**自我进化V1不宜过早自动化**：Evolution Engine第一阶段可以是`AI
Discover / AI Design / AI Evaluate / Human Release`，即系统自动发现
问题、自动提出候选、自动跑Eval，但人决定是否发布——这是当前最合理状态，
以后再逐级提高自治程度，对应第九节Self-Evolution权限分级里`E0/E1`先行、
更高级别逐步开放的节奏。

## 十六、Intelligence Improvement Rate与三个最终飞轮

复述并确认`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第二十一节已定义的
**IIR（Intelligence Improvement Rate）**指标——衡量Need Understanding
Quality/Goal Acceptance/Plan Completion/Outcome Improvement/Replan
Effectiveness/Human Escalation Accuracy/Resource Matching Quality/
Safety Regression Rate，比较Today vs 30天前 vs 90天前，平台必须能够
证明自己真的在变得更好。

**三个最终飞轮**（对应`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第十六节
Loop A/B/C的战略表述在架构图上的落地）：`Family Growth Flywheel`（Need
→Plan→Action→Outcome→Better Family State）、`Intelligence Flywheel`
（Outcomes→Learning→Better Skill/Planner→Better Outcomes）、
`Resource Network Flywheel`（More Needs→More Resources→Better
Matching→Better Outcomes→More Families）——三者最终互相加强。

## 十七、总架构最终形态图

```text
                      FAMILY
                        │
                        ▼
                FAMILI PRINCIPAL
                        │
                        ▼
           FAMILY INTELLIGENCE KERNEL
                        │
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
 UNDERSTAND         WORLD MODEL        PLANNER
       │                │                │
       └──────────────┬─┴────────────────┘
                      ▼
                  FAMILY NEED
                      │
                      ▼
                GOAL / PLAN
                      │
                      ▼
             AGENT / SKILL RUNTIME
                      │
                      ▼
                TOOL RUNTIME
                      │
                      ▼
             POLICY / HUMAN GATE
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
         AI         FAMILY       RESOURCE
          │           │            NETWORK
          └───────────┼────────────┘
                      ▼
                   ACTION
                      │
                      ▼
                   OUTCOME
                      │
                      ▼
                 REFLECTION
                      │
             ┌────────┴─────────┐
             ▼                  ▼
          REPLAN             LEARNING
             │                  │
             ▼                  ▼
        WORLD MODEL       OUTCOME INTELLIGENCE
                                │
                                ▼
                        EVOLUTION ENGINE
                                │
                                ▼
                           EVALUATION
                                │
                                ▼
                         GOVERNANCE GATE
                                │
                                ▼
                        NEW CAPABILITY
```

## 十八、FAMILY AGI的最终技术定义与五阶段终局

FAMILY AGI不是"一个会回答家庭问题的大模型"，而是"一个拥有持续家庭世界
模型，能够理解家庭需求，制定目标与动态计划，调用AI与社会资源执行现实
行动，从真实Outcome中学习，并通过Evaluation和Governance持续提升自身
能力的长期智能系统"。因此`Family AGI ≠ Model`，是`World Model +
Reasoning + Planning + Agents + Skills + Actions + Resources +
Outcomes + Learning + Evaluation + Governed Evolution`。

**五阶段终局**：①AI helps families → ②AI understands families → ③AI
coordinates resources for families → ④AI learns what works for
families → ⑤The platform continuously improves how society serves
families。最终价值不只是服务一个家庭，是通过数百万/数千万家庭的长期
实践，在隐私、安全和治理边界内不断学习"怎样才能真正让家庭变得更好"——
这是本文件的长期技术使命，跟`FAMILY_AGI_PLATFORM_BLUEPRINT.md`
第三十七节最终战略定义是同一个判断的技术层复述。

## 十九、当前诚实进度（对照本文件目标态）

跟`docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md`第三十八节的
判断一致（本节不重复评估同一批能力，只补充本文件特有的、更细粒度的
技术对象层面的进度）：

- **十二大核心子系统**：S05 Agent Runtime、S06 Model Gateway有真实实现
  （`backend/intelligence/agent_runtime/`、`backend/intelligence/
  model_gateway/`）；S01/S02/S03/S04/S07/S08/S09/S10/S11/S12均未建成
  或仅有雏形（S08 Tool Runtime/S09 Resource Network的FGCN P0雏形除外，
  已在既有记忆记录中确认）。
- **四级Run Taxonomy**：ADR-0167已`Accepted`，是唯一已完成"架构语义
  冻结"的部分；`AgentRunPersistencePort`+`DurableAgentRuntime`是
  AgentRun层唯一有真实SQL持久化的实现；`IntelligenceRun`层完全没有
  物理落地，`ExperienceIntelligenceRunAdapter`一类的收敛adapter尚未
  实施。
- **五条Architecture Invariants（第十二节）**：INV-01/02/03对应的
  边界（AI推理与Domain Truth分离、AgentRuntime唯一执行路径、
  ToolRuntime唯一Action Bus）在现有代码里**部分成立**——`Model
  Gateway`确实是唯一模型调用路径，但`VerticalFamilyGrowthRuntime`是否
  完全经过`AgentRuntime`还是保有独立执行逻辑，需要专门的代码审计才能
  下结论，本文件不代为断言，标注为待验证项。INV-04/05（Learning
  Contract、Evolution Gate）完全未建成。
- **R2-R10路线**：仅R2.1（Run Taxonomy）完成，R2.2及以后按总架构师
  既定裁决暂缓，先处理R0 Green Blocker（见ADR-0158）。R3-R10全部是
  目标态，没有任何一项已开始实施。

**这份技术总架构的作用**：为R2.2及以后的具体实施ADR/PR提供统一坐标和
对象命名参照，避免各域各自发明一套World Model/Planner/Run Ledger——
本身不是立即要执行的任务清单。是否要按此文件启动R2.2实施，以及具体先
从哪个子系统（建议S03 Family World Model或S02 Family Need，见第十四
节R3/R3.5顺序）开始，需要总架构师在R0 Green Main达成后单独决策。
