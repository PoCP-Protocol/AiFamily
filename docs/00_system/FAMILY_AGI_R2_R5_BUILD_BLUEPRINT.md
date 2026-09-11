---
id: FAMILY-AGI-R2-R5-BUILD-BLUEPRINT-001
title: FAMILY AGI R2–R5 详细建设蓝图（原位收敛式改造）
type: build-blueprint
status: draft
version: 1.0
owner: chief-architect
created: 2026-09-11
canonical: false
supersedes: null
superseded_by: null
baseline_ref: infra/ci-postgres-isolation@7b20f83c
extends: docs/00_system/FAMILY_AGI_PLATFORM_TECHNICAL_ARCHITECTURE.md
relates-to: docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md, governance/ADR/ADR-0167-family-agi-runtime-architecture.md, governance/ADR/ADR-0158-agi-native-family-growth-platform.md
---

# FAMILY AGI R2–R5 详细建设蓝图（基于现有AiFamily平台的原位收敛式改造）

```text
⚠️ 同一条纪律：status: draft, canonical: false 指本蓝图的任务拆解待总架构师
逐项批准启动，且尚未走完docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2的
Research→Decision→Canonical晋升流程——不是"以下代码已经写了"，也不是
"内容不重要"。当前诚实进度见第十七节。

本文件跟前两份文档的关系：
docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md       = 战略定位（为什么）
docs/00_system/FAMILY_AGI_PLATFORM_TECHNICAL_ARCHITECTURE.md = 技术总架构（长什么样）
本文件（R2-R5建设蓝图）                                     = 怎么从现有代码走到那里
```

**核心判断，改变了前两份文档的实施方式**：不是按照理想架构重新造一套系统，
是把现有AiFamily**原位收敛式**长成Family AGI Platform。基于`infra/ci
-postgres-isolation@7b20f83c`实际读码确认：现有仓库已经不是"从0到1"，是
"已经有很多正确零件，缺一个统一AGI内核"——`agent_runtime`已有contracts/
authorization/durable runtime/gateway port/SQL AgentRun ledger；
`experience`已有三张持久化run/event/checkpoint表；`tool_runtime`已有
Action Outbox+accepted dispatch/worker/delivery；`context_engine`已有
family-growth port/outcome consumer/reflection/SQL store；`growth_graph`
已有projector/store；`principal`已是独立package；`FamilyNeed`已是正式
Domain Aggregate；`CourseContent`已具备发布/审核/Postgres repository。

## 一、总实施原则

```text
EXISTING PLATFORM → INVENTORY → SEMANTIC CONVERGENCE → ADAPTER
→ MIGRATION → DEPRECATION → DELETE DUPLICATION
```

**不是**：设计理想AGI架构 → 新建几十个package → 逐渐把旧系统遗忘。
核心思想：**Evolve AiFamily into Family AGI**，不另起炉灶，不新建第四套
Runtime，不重写已有Domain，不为了AGI名词重造已有能力。

## 二、现有AiFamily到什么程度（读码结论，非推测）

| 现有模块 | 已有基础 | R2-R5处置 |
|---|---|---|
| `agent_runtime/` | contracts/authorization/composition/durable_runtime/gateway_port/persistence/registry/runtime，`AgentRunPersistence`已正确限定为runtime metadata、不写Family/Growth业务事实 | **KEEP + EXPAND** |
| `model_gateway/` | provider路由等已实现 | **KEEP** |
| `experience/` | `experience_runs`/`experience_run_events`/`experience_run_checkpoints`三表，已强调"runtime ledger≠domain repository"，load/replay已要求tenant/family/subject scope | **KEEP + ADAPT** |
| `principal/` | contracts/router/runtime独立package | **KEEP + REWIRE** |
| `tool_runtime/` | runtime/contracts/action_outbox/accepted_dispatch/accepted_worker/accepted_delivery | **KEEP** |
| `human_gate/` | 既有实现 | **KEEP** |
| `context_engine/` | contracts/async_port/sql_store/family_growth_port/family_need_outcome_consumer/outcome_reflection/deletion | **KEEP + WORLD MODEL SOURCE** |
| `growth_graph/` | store/projectors/outbox_consumer | **KEEP + WORLD MODEL SOURCE** |
| `memory/store.py` | 既有实现 | **KEEP + WORLD MODEL SOURCE** |
| `backend/domains/family_need/` | 正式N1-N8 Domain Aggregate，非概念稿 | **KEEP AS DOMAIN TRUTH** |
| `backend/domains/product_intelligence/`（CourseContent） | DRAFT→UNDER_REVIEW→PUBLISHED→RETIRED完整生命周期+Human Review+EvidenceClaim+Repository | **KEEP + COMPILE TO SKILL** |
| `agi_vertical_runtime.py`/`agi_vertical_durable.py`/`agi_vertical_feedback.py`/`agi_growth_path_projection.py`/`agi_assessment_bridge.py` | 家庭业务语义正确，但独立执行路径需收敛 | **ABSORB → ADAPT → DELETE** |
| `EvaluationLedger` | 内存版，跟`AgentRunPersistencePort`语义重叠 | **DEPRECATE** |
| `path_orchestration`系列feature分支 | 契约设计可用，整体不合并 | **EXTRACT SEMANTICS ONLY**（ADR-0167已裁决） |

## 三、现有系统→Family AGI总改造关系

```text
agent_runtime           → Universal Agent Execution Kernel
experience               → IntelligenceRun Cognitive Ledger
principal                → Famili Principal / Supervisor UX
context_engine+growth_graph+memory+domain facts → Family World Model
family_need               → Core Demand Domain
growth/journey             → Goal / Plan / Action Truth
course_content             → Skill Source
tool_runtime               → Unique Action Bus
human_gate                 → Governed Action Boundary
agi_vertical_*              → Extract → Absorb → Delete
EvaluationLedger            → Deprecate
path_orchestration          → Extract useful semantics only
```

## 四、R2总目标：Runtime Convergence

R2不是加AGI功能，是解决"现在到底是谁在运行Family Intelligence"。R2完成后
必须只有`Family Intelligence → AgentRuntime → Model Gateway`一条路径，
以及`Cognitive Episode → IntelligenceRun`一个概念。

### R2.1 — Run Taxonomy（`FAMILY-AGI-REORG-021`）

**状态：已完成**——ADR-0167已在本会话前一阶段定稿并转为`Accepted`（"R2.1
定稿"一节），四级Run Taxonomy已冻结，`EvaluationLedger=DEPRECATED`的裁决
已写入。本蓝图确认这条裁决不需要重做，唯一待补的是ADR-0167提到的
architecture test：

```
tests/architecture/test_runtime_taxonomy.py
```

至少断言：AgentRun不得拥有guardian_calibration；AgentRun不得拥有
plan_revision lineage；IntelligenceRun不得拥有provider token
accounting；EvaluationLedger不得成为production wiring。**这个测试尚未
写**，是R2.1唯一剩余的交付物，不需要重新讨论架构语义。

### R2.2 — Unified Runtime Scope Contract（`FAMILY-AGI-REORG-022`）

**状态：按总架构师既定裁决暂缓，先处理R0 Green Blocker**（见ADR-0158）。
目标态记录：新增轻量value object package（建议`backend/platform/
identity_refs/`，或复用现有identity package合适位置）：`TenantRef/
FamilyScopeRef/SubjectRef/ActorRef`，先做**代码里的语义分离**，不立即
重命名数据库列。改造范围第一批：`agent_runtime/experience/principal/
tool_runtime/context_engine/memory/growth_graph/agi_vertical_*`，第二批
再扩展Domain adapters。新增ADR-0168（Runtime Identity & Scope
Contract），冻结`DomainFamilyId != FamilyScopeRef`。**跟本会话BLOCKER-001
发现的直接关系**：`service_cases`的`0070`迁移（family_id widen成
varchar）正是"真实身份模型缺失、用放宽类型约束暂时承载两种语义"的历史
产物，R2.2要正式把这两种语义拆开，不是继续加宽更多列。

### R2.3 — IntelligenceRun（`FAMILY-AGI-REORG-023`）

**状态：未开始，依赖R2.2**。目标态：只新增`backend/intelligence/
agent_runtime/intelligence_runs.py`（不新建`intelligence_run/`独立
package），核心对象`IntelligenceRun/IntelligenceRunState/
IntelligenceRunLineage/IntelligenceRunCheckpoint/IntelligenceRunReplay/
IntelligenceRunPersistencePort`；persistence adapter新增`backend/
intelligence/experience/intelligence_run_adapter.py`，关系链
`IntelligenceRunPersistencePort → ExperienceIntelligenceRunAdapter →
SqlAlchemyExperienceRunStore → experience_runs/experience_run_events/
experience_run_checkpoints`——**硬约束：NO NEW TABLE**，复用现有三表。
IntelligenceRun拥有`family_scope_ref/subject_refs/world_state_ref/
evidence_refs/unknown_refs/guardian_decisions/guardian_calibration/
goal_ref/plan_ref/reflection_refs/parent_intelligence_run_id/
revision_lineage`；**不拥有**`token usage/provider retry/raw provider
response`（这些属于AgentRun/GatewayAttempt）。Replay必须`ZERO MODEL
CALL/ZERO TOOL CALL/ZERO DOMAIN MUTATION`。

### R2.4 — Single Model Execution Path（`FAMILY-AGI-REORG-024`）

**状态：未开始**。目标：`Principal/Vertical AGI/Assessment AI/Coach/
Planner/Reflection → DurableAgentRuntime/AgentRuntime → ModelGateway`。
`PrincipalRuntime`改为"build AgentTask/Profile→AgentRuntime.execute()"，
不再是independent inference runtime；`agi_vertical_runtime.py`不重写，
拆出`VerticalFamilyGrowthProfile`承载家庭领域payload/policy，模型执行
迁给AgentRuntime。新增architecture guard
`tests/architecture/test_model_execution_boundary.py`（AST/import
scan），生产intelligence路径不允许direct provider SDK/direct
generate_structured/direct ModelGateway execution，除`agent_runtime`/
`model_gateway`基础设施本身。

### R2.5 — AgentRun ↔ IntelligenceRun Link（`FAMILY-AGI-REORG-025`）

**状态：未开始，依赖R2.3+R2.4**。新表`ai_intelligence_run_agent_links`
（`tenant_id/family_scope_ref/intelligence_run_id/agent_run_id/
sequence/step_ref/relation/created_at`，约束
`UNIQUE(tenant_id,agent_run_id)`+`UNIQUE(tenant_id,intelligence_run_id,
sequence)`）。`relation`示例：`UNDERSTAND/EVIDENCE_SYNTHESIS/
GOAL_PROPOSAL/PLAN/REFLECTION/REPLAN`。**禁止**继续往`ai_agent_runs`塞
`plan_id`/guardian decision/reflection lineage/world state。

### R2.6 — Absorb Vertical Runtime（`FAMILY-AGI-REORG-026`）

**状态：未开始**。不直接删除现有`agi_vertical_*`文件，走
`EXTRACT → ADAPT → SWITCH CALLER → TEST → DEPRECATE → DELETE`：
`agi_vertical_runtime→VerticalFamilyGrowthProfile+common AgentRuntime`；
`agi_vertical_durable→IntelligenceRun Adapter`；`agi_vertical_feedback
→Guardian Calibration/Evaluation`；`agi_growth_path_projection→World
Model source projection`；`agi_assessment_bridge→Assessment World Model
Source Adapter`。最终`backend/intelligence/`顶层不再堆大量`agi_*.py`。

### R2 EXIT GATE（全部满足才能进R3，缺一项禁止）

```
[ ] one production model execution path
[ ] AgentRun = technical execution
[ ] IntelligenceRun = cognitive episode
[ ] EvaluationLedger zero production caller
[ ] Principal no direct model execution
[ ] Vertical Runtime no direct gateway
[ ] unified scope contract
[ ] IntelligenceRun durable replay
[ ] Guardian lineage durable
[ ] replay has zero model/tool/domain side effect
[ ] cross-tenant/family fail closed
[ ] Main CI GREEN
```

## 五、R3总目标：Family World Model

R3不建设新的业务事实库，解决"在当前时刻，AGI基于已有真实数据，应该怎样
理解这个家庭"。

### R3.1 — World Model Contract（`FAMILY-AGI-REORG-030`）

新增`backend/intelligence/world_model/`，初期只有四个文件
（`__init__.py/contracts.py/assembler.py/sources.py`）——**禁止一次建**
`graph/reasoner/ontology/causal/simulation/digital_twin/`这类空目录。
核心对象：`FamilyWorldStateSnapshot/WorldStateSection/
WorldStateEvidenceRef/WorldStateUnknown/WorldStateContradiction/
WorldStateConfidence`，Snapshot性质：immutable/scope-bound/as_of-bound/
evidence-grounded。数据来源复用`context_engine/growth_graph/memory/
assessment/family_need/journey/growth-action/service`，**不是复制
数据**。

### R3.2 — World Model Sources（`FAMILY-AGI-REORG-031`）

定义`WorldModelSource`协议（`async def project(scope, as_of) →
WorldModelFragment`）。Adapters：`ContextEngineSource/GrowthGraphSource/
MemorySource/AssessmentSource/FamilyNeedSource/GrowthActionSource/
JourneySource/ServiceSource`。现有`agi_assessment_bridge.py`吸收成为
`AssessmentSource`；`agi_growth_path_projection.py`吸收成为Growth/Plan
projection source——这正是R2.6"Absorb"的具体落点，两个任务序号需要
协同排期，不是各自独立。

### R3.3 — Assembler（`FAMILY-AGI-REORG-032`）

Assembler只做Collect/Normalize/Merge/Detect contradictions/Build
unknowns/Attach evidence/Freeze snapshot，**不做**LLM diagnosis/自动写
domain/永久family labeling。

### World Model不能成为第二套Truth

```
Domain Table → Projection → FamilyWorldStateSnapshot   （正确）
Domain Table → Copy all data to new world_model_* tables （禁止）
```

V1原则：**World Model primarily projection, not canonical
persistence**。可以缓存，但缓存必须rebuildable/versioned/disposable。

### R3.4 — Evidence / Unknown / Contradiction（`FAMILY-AGI-REORG-033`）

所有关键认知支持`value/evidence_refs/confidence/freshness/
contradictions/unknowns`——这是本蓝图对`FAMILY_AGI_PLATFORM_
TECHNICAL_ARCHITECTURE.md`第四节S03/第十三节Evidence/Unknown体系的
逐字段落地，两文档字段名须保持一致。

### R3.5 — LearningSignal Contract V0（`FAMILY-AGI-REORG-034`）

不等R8才想学习，现在就冻结`ExpectedObservation/MeasurementWindow/
SuccessCriteria/FailureCriteria/StopCriteria/EscalationCriteria/
LearningEligibility`契约字段。**R3只定义contract，不建设Population
Learning**——这跟`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第十七节"Learning
Contract必须从早期就进入系统"是同一条纪律的具体任务编号化。

### R3 DB边界

原则上**NO NEW CANONICAL FAMILY FACT TABLE**。如确实需要snapshot
cache，必须先过ADR。默认用existing sources + rebuildable projection。

新增ADR-0169（Family World Model = Evidence-grounded Projection），
冻结：`WorldModel != DomainTruth`/`Memory != WorldModel`/`Hypothesis !=
Fact`/`Unknown is first-class`。

### R3 Golden E2E

输入真实Assessment+FamilyNeed+最近Action Outcome+Memory，生成
`FamilyWorldStateSnapshot`；进程重启后rebuild，重要字段语义一致；同时
证明不同family scope无法读取。

## 六、R4总目标：Family Need → Goal → Plan

FamilyNeed已存在，**不重新建FamilyNeed aggregate**。

### R4.1 — FamilyNeed Intelligence Bridge（`FAMILY-AGI-REORG-040`）

`backend/domains/family_need`保持canonical domain；新增intelligence
adapter（放入`world_model/sources`）。AI可以interpret need/identify
unknowns/propose clarification/propose hypothesis，但**FamilyNeed事实
生命周期仍由domain管**。

### R4.2 — Goal Model（`FAMILY-AGI-REORG-041`）

必须冻结`GoalProposal ≠ GuardianDecision ≠ GrowthIntent`：AI生成
GoalProposal，家庭确认GuardianDecision，业务承诺GrowthIntent。**AI永远
不能让GoalProposal直接变成业务Goal**——这是INV-05类边界（AI不能直接创造
业务事实）在Goal对象上的具体实现。

### R4.3 — Primary Contradiction（`FAMILY-AGI-REORG-042`）

不是哲学概念硬编码，实际含义："当前阶段最值得优先解决、且最可能改变结果的
核心张力"（例如表面"孩子不愿学习"，核心矛盾候选"父母控制强度×孩子自主
需求"）。必须输出evidence/uncertainty/alternatives，**不是诊断标签**。

### R4.4 — Planner V1（`FAMILY-AGI-REORG-043`）

`WorldState → Policy Candidate Filter → 5-20 candidates → Reasoning
Planner → PlanDraft`。Deterministic Layer负责Consent/Age/Risk/
Prerequisite/Contraindication/Availability/Region/Resource
Constraint；Reasoning Layer负责priority/sequence/why/expected
observation/uncertainty/alternative/replan trigger——跟
`FAMILY_AGI_PLATFORM_TECHNICAL_ARCHITECTURE.md`S04两层Planner
设计一致，本节是具体任务化。

### R4.5 — Plan / PlanStep（`FAMILY-AGI-REORG-044`）

核心`Plan/PlanStep/PlanRevision`，Plan必须版本化`Plan v1→Outcome→
Reflection→Plan v2`。每个Step至少有`goal_ref/skill_requirement/
action_requirement/expected_observation/completion_condition/
stop_condition/replan_condition`。

### R4.6 — Reflection & Replan（`FAMILY-AGI-REORG-045`）

直接复用现有`context_engine/outcome_reflection.py`以及
`agi_vertical_runtime`的reflect/revise语义，但把通用认知生命周期迁入
统一IntelligenceRun。Reflection输出which hypothesis strengthened/
weakened、what failed、what changed、what new unknown appeared，然后
才Replan。

### R4 DB边界：Draft ≠ Truth

不能为方便把所有Plan存进`experience_runs`的JSON。原则：Model Draft →
IntelligenceRun checkpoint；Guardian Accepted Plan → canonical
Growth/Plan Domain。

新增ADR-0170（Goal / Plan Authority Boundary），冻结：AI proposes /
Guardian decides / Domain records / Outcome may trigger replan。

### R4 Golden E2E

Golden Scenario："孩子越来越不愿意和我说话，一说学习就吵架"，跑
`Expression→FamilyNeed→WorldState→Evidence→Unknown→Hypothesis→Primary
Contradiction→GoalProposal→Guardian edit→Guardian confirm→
GrowthIntent→Plan v1`，要求进程重启后Plan+Guardian lineage可恢复。

## 七、R5总目标：Product Capability → Growth Skill

R5解决"Planner有了计划以后，到底拿什么能力去解决问题"——答案不能永远是
"让LLM临时想"，必须建立Skill Runtime。

### R5.1 — GrowthSkillSpec（`FAMILY-AGI-REORG-050`）

新增`backend/intelligence/skills/`（只建`__init__.py/contracts.py/
registry.py`三个文件）。核心：`GrowthSkillSpec/SkillApplicability/
SkillContraindication/SkillOutcomeContract/SkillEscalationRule`。字段
（跟`FAMILY_AGI_PLATFORM_BLUEPRINT.md`第十八节一致）：`skill_id/
version/title/problem_types/goal_types/applicability/
contraindications/evidence_level/knowledge_refs/intervention_logic/
lesson_refs/action_templates/tool_refs/human_role_refs/
expected_observations/outcome_metrics/success_criteria/
failure_criteria/stop_rules/escalation_rules/learning_signals`。

### R5.2 — CourseContent Compiler（`FAMILY-AGI-REORG-051`）

**不是迁移/删除CourseContent**：`Product Intelligence CourseContent →
GrowthSkillCompiler → GrowthSkillSpec`。CourseContent继续拥有
authoring/review/publication/evidence governance；Skill Runtime只消费
`PUBLISHED`内容——现有发布生命周期和Human Gate必须继续复用，不重建。

### R5.3 — Skill Registry（`FAMILY-AGI-REORG-052`）

支持register/version/publish/retire/find_by_problem/find_by_goal/
filter_by_age/filter_by_risk。**V1不上**向量数据库/Graph database/
LLM-only skill discovery——structured deterministic registry。

### R5.4 — Skill Selection（`FAMILY-AGI-REORG-053`）

`PlanStep → Deterministic Eligibility Filter → Skill Candidates →
Reasoning Ranker → Selected Skill`，必须fail closed：
contraindication/age mismatch/consent missing/risk too high。

### R5.5 — Skill Execution（`FAMILY-AGI-REORG-054`）

统一`Skill → ActionProposal → ToolRuntime → Policy → HumanGate →
NamedAction`。**Skill不能**直接写数据库/直接预约老师/直接改Plan/直接
支付。

### R5.6 — First Learnable Skill（`FAMILY-AGI-REORG-055`）

不一次编译全部课程，第一个Skill是"亲子沟通降温"，必须包括
applicability/exercise/family action/AI coaching/expected outcome/
stop rule/escalation。

### R5 Golden E2E

完整跑`FamilyNeed→Goal→PlanStep→Skill Candidates→Skill Selected→
Action Proposed→Guardian Confirm→ToolRuntime→NamedAction→Outcome`，
然后准备进入R6：`Bad Outcome→Reflection→Replan→Different Skill/
Action`。

## 八、R2-R5完整package演化图

R2-R5结束后，真正新增的顶层`backend/intelligence/`package只有两个：
**`world_model`**（R3）和**`skills`**（R5），不是二三十个package：

```
backend/intelligence/
├── agent_runtime/     # 保留，升级（新增intelligence_runs.py）
├── model_gateway/     # 保留
├── principal/         # 保留，降级为Experience/Supervisor
├── experience/        # 保留，成为IntelligenceRun持久化底座
│                       # （新增intelligence_run_adapter.py）
├── context_engine/    # 保留
├── growth_graph/       # 保留
├── memory/             # 保留
├── world_model/         # R3新增
├── skills/               # R5新增
├── tool_runtime/          # 保留
├── human_gate/            # 保留
├── knowledge/              # 保留
└── safety/                  # 保留
```

## 九、数据库总原则

**R2-R5不允许"AGI架构一升级，数据库表数量暴涨"**：R2允许新增
`ai_intelligence_run_agent_links`一张表，其余以复用为主；R3默认0张新
canonical表（World Model是projection）；R4只在已有Goal/Growth/Plan
Domain缺少真正authoritative entity时，经ADR才新增；R5 Skill Registry
V1可以code/config backed，先不必须建数据库。

## 十、测试金字塔与证据规则

每个R阶段统一四层：`L1 Contract Unit / L2 Architecture Boundary / L3
Real PostgreSQL Integration / L4 Golden Family E2E`。例如R4：Unit=Plan
invariants；Architecture=Planner cannot mutate domain；Postgres=
Guardian confirmation durable；Golden=Need→Goal→Plan→restart→replay。

**证据规则**（沿用本会话R0.5建立的AGENT-EVIDENCE纪律，ADR-0167已冻结）：
`Agent report != Evidence`，正式证据优先级`git diff > actual code >
test exit code > Postgres verification > CI`。每个R2-R5任务的完成报告
必须包含：`TASK_ID/FILES_CHANGED/INVARIANTS_PROVEN/TESTS_RUN/
REAL_POSTGRES_RESULT/ARCHITECTURE_GUARD_RESULT/GOLDEN_E2E_RESULT/
KNOWN_GAPS/COMMIT_SHA`。

## 十一、分支策略与三个月实施节奏

**分支策略**：每个任务one capability/one branch/small diff/green
tests/merge/delete branch（例如`arch/r2-run-taxonomy`/
`feat/r2-runtime-scope`/`feat/r2-intelligence-run`/
`refactor/r2-model-path`/`feat/r3-world-state`/`feat/r4-goal-plan`/
`feat/r5-growth-skill`），**不建立**跨几个月的单一巨型分支。

**推荐节奏**（供总架构师排期参考，不是本蓝图自动生效的日程）：

```
Month 1  R0 Green Main / R2.1 Run Taxonomy / R2.2 Scope / R2.3 IntelligenceRun
         → 智能Runtime身份与运行语义统一

Month 2  R2.4 Single Model Path / R2.5 Run Links / R2.6 Vertical Absorption
         / R3.1 WorldState / R3.2 Sources
         → Family AGI第一次拥有统一执行内核和统一家庭状态视图

Month 3  R3 Evidence/Unknown / R4 Goal / R4 Planner / R4 Dynamic Plan
         / R5 SkillSpec
         → 开始形成真正的Need→Goal→Plan→Skill智能链
```

## 十二、现有代码处置矩阵（汇总，供任务拆解直接引用）

见第二节表格——本节不重复，只强调：处置动作只有KEEP/KEEP+EXPAND/
KEEP+ADAPT/KEEP+REWIRE/ABSORB→DELETE/DEPRECATE/EXTRACT SEMANTICS ONLY
七种，**没有"推倒重写"这个选项**，任何任务如果发现需要推倒重写某个现有
模块，必须先停下来单独评审，不能作为R2-R5常规任务的一部分。

## 十三、五条工程禁令

```
禁令1  禁止新建第四套Runtime。
禁令2  禁止为了World Model复制Domain Truth。
禁令3  禁止LLM Draft直接成为Domain Fact。
禁令4  禁止Skill绕过ToolRuntime执行现实动作。
禁令5  禁止以"未来AGI需要"为理由提前引入复杂基础设施。
```

跟`FAMILY_AGI_PLATFORM_TECHNICAL_ARCHITECTURE.md`第十二节五条
Architecture Invariants是同一层纪律在"建设过程"维度上的对应表述——
Invariants是"代码长什么样才对"，本节禁令是"过程中不要犯的五个具体错误"。

## 十四、R2-R5后的质变判断

R2-R5的目标不是完成四个新子系统，是完成四次质变：

```
R2  从"多个AI执行点"          → "一个Family Intelligence Runtime"
R3  从"散落的家庭数据"        → "一个Evidence-grounded Family World State"
R4  从"回答家庭问题"          → "围绕真实Need形成Goal与动态Plan"
R5  从"课程/模型临时解决问题" → "可治理、可组合、可学习的Growth Skills"
```

然后才进入R6（Outcome→Reflection→Replan）/R7（Dynamic Family
Experience）/R8（Outcome Learning）/R9（Family Resource Network
Intelligence）/R10（Governed Self-Evolving AGI）——这五个阶段的目标态
定义见`FAMILY_AGI_PLATFORM_TECHNICAL_ARCHITECTURE.md`第十四节
R2-R10映射，本蓝图不重复。

## 十五、新增硬规则：所有后续开发指令必须先答两个问题

**从本蓝图开始，任何具体开发任务的指令，必须先写清楚"CURRENT CODE TO
REUSE"与"CODE TO RETIRE"，再写"NEW CODE"**——这是防止Codex/开发人员
在不了解现有代码的情况下，为新架构重新发明Runtime/Ledger/Planner/
Context/Action Bus的强制前置检查。这条规则本身不需要额外的ADR，直接
作为本蓝图和后续所有R2-R5任务工单的固定格式要求生效。

## 十六、当前排期状态（跟已生效裁决保持一致，不擅自改变）

第一开发动作**不是**直接建World Model，是先把
`R0 Green Main → R2.1 Run Taxonomy → R2.2 Scope → R2.3 IntelligenceRun`
做扎实——这是总架构师此前已经裁决且仍然生效的顺序（见ADR-0158
"R2.2及以后暂时不准启动，先处理两个R0 Green Blocker"）。ADR-0167本身
记录的"三套执行语义并存"以及`EvaluationLedger`判断需要修正，正是R2必须
先于R3的原因。本蓝图的R3-R5任务拆解是提前准备好的路线图，不代表这些
任务已经排期启动。

## 十七、当前诚实进度

- **R2.1**：已完成，ADR-0167已`Accepted`。**唯一剩余交付物**：
  `tests/architecture/test_runtime_taxonomy.py`尚未编写。
- **R2.2-R2.6、R3、R4、R5**：全部未开始，均为目标态任务拆解。
- **R0 Green Main**：未达成——两个Blocker（`FAMILY-R0-BLOCKER-001`
  数据库漂移诊断已完成待Strategy B3执行审批；`FAMILY-R0-BLOCKER-002`
  已修复，见`fix/r0-green-main-closure`分支）状态见ADR-0158最新记录。
- **本蓝图列出的所有ADR编号**（ADR-0168/0169/0170）均**尚未创建**，是
  为对应R阶段预留的编号占位，不是已存在的文档。

**下一步建议**（供总架构师排期，本蓝图不擅自启动）：按第十六节已生效的
顺序，下一个可以启动的具体任务是补齐R2.1的architecture test，其余任务
等R0 Green Main达成、且总架构师批准R2.2启动后再逐项排期。
