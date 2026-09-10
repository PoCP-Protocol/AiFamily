---
id: ADR-0167
title: Family AGI Runtime 架构定位（Family Domain AGI Platform）
status: Accepted
date: 2026-09-10
owner: chief-architect
---

# ADR-0167：Family AGI Runtime 架构定位

## 决策

正式采纳用户提出的长期技术定位：**AiFamily = Family Domain AGI Platform**——
面向家庭成长领域的领域通用智能平台，而不是"很多AI功能拼起来的平台"。

**大模型是基础设施，不是核心**：不训练自研AGI大模型，模型经`Model Gateway`
可替换路由；AiFamily真正要建设的是模型之上的 **Family Intelligence
Runtime + Family World Model + Skill/Agent/Tool Network + Outcome
Learning System**。

## 与ADR-0158 / ADR-0162的关系（避免两份文档各说各话）

- **不取代**。ADR-0158记录的具体契约（`FamilyPathContext`/`PathDraft`/
  `PathFeedbackSignal`/`PathDraftPersistencePort`等）仍然有效，归入本ADR
  "Skill/Agent System"层下的一个具体实现（`path_orchestration`），本ADR
  只是给它一个更大的架构坐标，不改动其代码契约。
- ADR-0158的"唯一主线"（成人授权→家庭表达→AGI理解与因果假设→可修改方案→
  Guardian确认→低风险行动→结果回读→失败复盘）与本ADR的七步闭环
  （PERCEPTION→WORLD MODEL→GOALS→REASON&PLAN→ACT&COORDINATE→OBSERVE→
  LEARN）是**同一个闭环的两种表述**，以本ADR的七步闭环为准，ADR-0158的
  主线八段表格继续作为该闭环在"path_orchestration"这一具体切片上的落地
  追踪，不重复定义。
- ADR-0162的G0-G6生产就绪阶段门（证据等级纪律：fixture≠证据、内存
  ledger≠持久化证明等）作为**横切纪律**，适用于本ADR下所有子系统的推进
  ——本ADR定义"要建什么"，ADR-0162继续管"怎么证明建好了"。
- 本ADR新增的"Governed Autonomy"五级（回答→建议→生成计划→用户授权执行→
  低风险自主执行→专业监督）回答的是另一个正交问题——"允许AI自主到什么
  程度"，跟G0-G6"证明到了哪个阶段"并存，不是互相替代。

## Runtime 分层（简化版，完整版见用户原文档）

```
EXPERIENCE（App/Web/Voice/直播/设备）
RUNTIME（Perception/Understanding/Reasoning/Goal/Planner/Agent Loop/Reflection/Evaluation）
WORLD MODEL（Family Graph / Evidence Graph / Experience Graph / Service Graph / Skill Graph）
MEMORY（Working / Episodic / Semantic / Family State）
SKILL / AGENT SYSTEM（Assessment / Course / Coach / Expert / Community / Live / Navigator）
TOOL BUS（MCP / API / DB / Search / Payments / IoT）
AGENT NETWORK（A2A / External Agents）
MODEL GATEWAY（多provider路由，已有`backend/intelligence/model_gateway`）
SAFETY / GOVERNANCE / EVAL（Consent / Guardian / RBAC / Audit / Evals，已有多个域雏形）
```

## 五张世界模型图 —— 诚实现状核对（不是全部从零开始）

| 图 | 现状 |
|---|---|
| Family Graph | `Growth Graph`（PR#22刚接的hypothesis/action事件outbox）是雏形，远未到"state随时间演化"的完整家庭世界模型 |
| Evidence Graph | `backend/intelligence/knowledge/registry.py`（`KnowledgeRegistry`）是雏形——确定性发布/检索/证据等级门槛已具备，但内容为空（无真实审查知识） |
| Experience Graph | 未建立 |
| Service Graph | 未建立（`governance/CAPABILITY_REGISTRY.yaml`是平台自身能力登记，不是"谁擅长解决什么问题"的服务图） |
| Skill Graph | 刚起步——本轮`knowledge_candidate_source.py`+`candidate_explanation_adapter.py`是"检索到的知识→可执行候选"这一条窄切片，远未到完整Skill Package（课程=Human-readable Skill Package这个设计还未落地） |

## 五级AGI演进 —— 当前诚实定位

介于 **AGI-0（AI Assistant）与AGI-1（Family Copilot）之间**：
- 有真实模型调用（`GatewayBackedUnderstandAdapter`/`GatewayBackedCandidateExplanationAdapter`），但没有Family World Model、没有跨会话Memory、没有Goal Engine、没有Hierarchical Planner
- `path_orchestration`目前只是"读取一次context→打分→返回候选"，不构成AGI-1要求的"家庭画像+Memory+测评+课程+Tool Calling"完整闭环

## 不做的事（范围边界，不是留白）

- 不训练自研AGI大模型
- 不一次性搭建全部Runtime目录骨架（`family-intelligence-runtime/`下29个子目录）——空目录本身就是骨架冒充能力，是本ADR明确要避免的反面案例；目录结构按需在AGI-1目标驱动下逐个长出真实内容
- MCP/A2A暂不接入——本ADR记录方向（工具/多Agent协作走标准协议，不自建私有集成），实际接入时机等有真实的第三方Agent协作需求出现

## 下一步

邀请Codex在此ADR下回应/反驳——本ADR直接决定`path_orchestration`及其后续切片的架构坐标，不是单方面的技术决策。当前具体推进目标：把AGI-0→AGI-1的差距（Family World Model的最小雏形、跨会话Memory）列为下一个可验证增量，而不是继续在"回答变得更聪明"这个维度上打磨。

## 修订（2026-09-10）：Runtime Convergence——从愿景架构到收敛决策

用户第三轮架构诊断指出：本ADR原版本停留在"愿景蓝图"层面，没有解决一个更紧迫的真实问题——**当前仓库存在三套完全独立、无复用关系的"智能执行"实现**，且都被诚实核实过（`Explore` agent读代码验证，非猜测）：

| Runtime | 入口方法 | 数据模型 | 端口数 | 多步/循环能力 |
|---|---|---|---|---|
| `backend/intelligence/agent_runtime/runtime.py` (`AgentRuntime`) | `execute()` | `AgentRun` | 1 (`AgentExecutionPort`) | 无——严格单步：调一次网关拿一个DRAFT就结束 |
| `backend/intelligence/agi_vertical_runtime.py` (`VerticalFamilyGrowthRuntime`) | `run()`/`revise()`/`reflect()` | `EvaluationLedgerEntry` | 4（Context/Knowledge/Feedback/Gateway） | 有链式（`revise()`内部递归调用`run()`，靠`parent_run_id`追踪），但不是真正的Plan/Step/Goal循环——没有这些class存在 |
| `backend/intelligence/principal/runtime.py` (`PrincipalRuntime`) | `draft()` | `PrincipalDraft` | 无独立port，直接用gateway/router | 无——单步 |

三者互不import、互不复用，各自实现了一遍"调用模型拿结构化输出"的骨架。这是真实的架构债，不是这份ADR初版愿景描述掩盖过的问题。

### 决策：Single Family Intelligence Kernel，不新建第四套

**不新建`backend/intelligence/family_agi_runtime/`或任何新顶层package**——继续扩展`backend/intelligence/agent_runtime/`，把它从"单步执行原语"升级为收纳通用循环能力的位置。四个角色正式冻结：

- **`AgentRuntime`** = 单步、受权限约束的结构化执行原语（现状保留，不改语义）
- **Family Intelligence Loop**（新增，位置待定为`agent_runtime/`下的模块，不是新package）= 长期目标/规划/执行/观察/反思/重规划——**目前不存在**，`VerticalFamilyGrowthRuntime`的`revise()`/`reflect()`是这个角色的唯一真实雏形，将被迁移改造为这个角色的实现，不是被推翻重写
- **`Principal`** = 用户面对的统一人格/Supervisor Experience，只负责路由/解释/确认，不做Goal/Plan（现状已经符合这个定位，不用大改）
- **`ToolRuntime`** = 唯一行动与外部工具边界（现状保留）

### 具体迁移方向（供后续实施ADR/PR细化，本次不动代码）

> **RETRACTED HYPOTHESIS（2026-09-10 R2.1定稿撤销，见下方"R2.1定稿"一节）**：
> 下面这条"把EvaluationLedger迁进agent_runtime"的建议已被总架构师正式撤销，
> 不是当前架构事实。保留在此仅供理解调研过程，**不得被后续人员引用为决策
> 依据**。正式裁决见本文档"R2.1定稿"一节的"EvaluationLedger最终裁决"。

调研确认的可迁移边界（历史记录，已撤销）：

- **迁到`agent_runtime`成为通用能力**：`EvaluationLedger`（append/decision/read/replay/delete，跟family语义无关，是纯粹的日志/重放基础设施）；`revise()`/`reflect()`的框架逻辑（除payload构造外都通用）；`_lineage_ref()`（内容无关的稳定ID生成）
- **留在家庭特定层，降级为`VerticalFamilyProfile`配置对象**：`family_need_id`/`path_id`/`family_id`/`context_snapshot_ref`/`guardian_calibration`/capability grounding检查——这些字段在`agi_vertical_runtime.py`里出现86次，是真正的家庭业务语义，不该被抽象掉

### `path_orchestration` feature branch 处置

`feat/path-draft-persistence-clean`/`feat/path-orchestration-understand-gateway-adapter`/`feat/path-orchestration-knowledge-candidates`三条分支（对应PR#23/#25/#26）**不直接整体merge进main**。吸收其契约设计，归档分支本身：

- `FamilyPathContext` → 并入 Family World Model的context契约
- `PathDraft` → 并入 Plan/GrowthPath契约
- `PathFeedbackSignal` → 并入 Guardian Calibration（`VerticalFamilyGrowthRuntime.decide()`已有的机制）
- `PathDraftPersistencePort` → 改造成`EvaluationLedger`的adapter，不是独立持久化层
- `ContextDrivenPathDraftPlanner` → 降级为Candidate Pre-selector（确定性过滤层，不冒充Planner）

这不代表三个PR的工作被浪费——`GatewayBackedUnderstandAdapter`/`GatewayBackedCandidateExplanationAdapter`（真实Model Gateway调用+去标识化+知识检索/模型转写分离）这两个设计模式本身是对的，会被复用到Family Intelligence Loop的实现里，只是不再作为独立的`path_orchestration`package存在。

### 本次未决事项（诚实标注，非本次会话解决范围）

- 具体的代码迁移（把`agi_vertical_runtime.py`的通用部分真的搬进`agent_runtime/`）是下一个PR的工作，本次修订只锁定方向，不动代码
- `VerticalFamilyProfile`的确切字段/接口设计需要在实施PR里定稿，本ADR只给出迁移边界的判断依据
- status继续`Proposed`——这是架构级决策，需要codex/总控确认后才能`Accepted`，不由本次会话单方面拍板

### Claude 补充发现（2026-09-10）：迁移比预想的更复杂，暂停代码动手，先记录

尝试开始最小的迁移步骤（把`EvaluationLedger`搬到`agent_runtime`）时，发现两个此前判断不够精确的问题：

1. **`EvaluationLedgerEntry`本身不是"跟family语义无关的通用infra"**——它内嵌`family_need_id`/`path_id`必填字段。真正通用的只是`EvaluationLedger.append/read/replay/delete`四个方法（这四个方法确实只依赖`entry.run_id`，是duck-typing式的通用）；`decision()`方法绑定`GuardianDecision`（同样family-specific），不能一起搬。

2. **更重要的发现**：`backend/intelligence/agent_runtime/`下已经存在一套**真实SQL持久化**的`AgentRunPersistencePort`+`DurableAgentRuntime`（真实表`ai_agent_runs`，`create/start/succeed/fail/append_trace/replay`完整生命周期），跟`agi_vertical_runtime.py`自己发明的**内存版**`EvaluationLedger`在语义上高度重叠——都是"记录一次AI执行+支持重放"，只是一个持久化、一个不持久化。这本身就是本ADR想解决的"三套并行执行语义"问题的一个更深层子问题：**不只是执行入口重复，连持久化/记录机制也重复发明了一遍**。

`AgentRunPersistencePort`目前没有`guardian_calibration`/`parent_run_id`链式追踪这类认知修正语义，跟`VerticalFamilyGrowthRuntime`要的"guardian校准→revise→reflect"链条不是同一层次的东西（一个是执行状态机，一个是认知修正链）。**是否能/该把两者合并，需要认真设计，不是简单的文件搬移**。

**暂停这条代码迁移线**，不在没有设计评审的情况下继续写可能被推翻的迁移代码。这个发现补充进ADR-0167，等codex/总控一起判断：(a) 两套持久化机制要不要合并，(b) 如果合并，`AgentRunPersistencePort`需要加哪些字段/方法才能承载guardian calibration链，(c) 如果不合并，两者的边界该怎么正式划清楚（避免第三次有人再发明第三套）。

## R2.1 定稿（2026-09-10）：四级Run Taxonomy，`Proposed → Accepted`

总架构师拍板：不再继续争论"是否物理合并两套持久化机制"，改用一个更清晰的**四级模型**，明确每一级的职责边界和"不得拥有什么"，逻辑收敛、物理不强合并。本节是ADR-0167从`Proposed`转为`Accepted`的定案内容，覆盖第17节验收问题的全部14个答案。

### 四级Run模型（正式冻结）

```text
GatewayAttempt
       ↓
AgentRun
       ↓
IntelligenceRun
       ↓
NamedAction / DomainFact
```

**GatewayAttempt** —— 回答"某次provider/model网络调用发生了什么"。拥有：provider、model、latency、token usage、retry、timeout、provider response/error metadata。这是`Model Gateway`调用记录层，不是业务执行记录层。

**AgentRun** —— 回答"一次有边界的技术Agent执行发生了什么"。拥有：run lifecycle、agent/use-case、request/trace、technical execution status、model draft、execution error。**不得拥有**：Guardian calibration、cognitive parent lineage、plan revision lineage、reflection lineage、Family business truth。这是纯技术执行状态机层——现有`AgentRunPersistencePort`+`DurableAgentRuntime`（真实SQL表`ai_agent_runs`）正是这一层的正确归属，保持不变。

**IntelligenceRun** —— 回答"Family Intelligence一次完整认知事件是怎么演化的"。允许包含：0..N个AgentRun、evidence refs、world-state refs、human interaction、guardian edits、reflection、replan lineage、revision lineage。可以跨越model call/human wait/resume/多次bounded execution。这是`VerticalFamilyGrowthRuntime`的`revise()`/`reflect()`、`GuardianCalibration`、认知修正链条的正确归属——**不是**AgentRun的扩展字段，是独立的上一层概念。

**NamedAction / DomainFact** —— 回答"现实业务状态真正改变了什么"。必须通过`ToolRuntime`+Policy+Human Gate+Named Action+Domain Service产生。**AI cognition不能直接创造业务事实**——这是ADR-0158主线里"Guardian确认→低风险行动"这一步的架构对应物，不是新概念，是给已有纪律一个在Run Taxonomy里的正式位置。

### EvaluationLedger最终裁决：DEPRECATED，不迁移，长期删除

撤销第126-136节的迁移建议（"将EvaluationLedger搬进agent_runtime"）——**这个建议本身被撤回，标记为RETRACTED HYPOTHESIS，不是架构事实，保留在文档里仅供后续人员理解调研历史，不得引用为决策依据**。

正式裁决：`EvaluationLedger` = **DEPRECATED**。可以暂时存在于test fixture、实验兼容性、迁移桥接场景，但**不得成为生产环境的canonical persistence**。长期方向是删除。它携带的Family特定认知语义（`GuardianCalibration`、parent cognitive lineage、reflection/replan lineage）归**IntelligenceRun**，不归AgentRun——这就是为什么不能简单"搬进agent_runtime"：AgentRun这一层的职责边界明确排除了这些语义，搬进去等于把两层职责混在一起，重新制造这次要解决的问题。

### ExperienceRun与IntelligenceRun：逻辑收敛，非物理合表

```text
IntelligenceRunPersistencePort
        ↓
ExperienceIntelligenceRunAdapter
        ↓
AsyncExperienceRunLedger
        ↓
existing experience_* tables
```

现阶段**不新建IntelligenceRun数据库表**，尤其禁止把`experience_runs`和`ai_agent_runs`合并成一张巨表——那正是本ADR最初想解决的"三套并行执行语义"问题的反面重演，只是从"三套并行"变成"一张过载表"，同样错误。

### Principal边界

```text
Family Principal
      ↓
AgentRuntime / Family Intelligence Kernel
      ↓
Model Gateway
```

Principal**禁止**拥有独立的Model Gateway调用路径——不允许成为第二个planner、第二个execution runtime、第二个ledger。Principal只负责：persona、conversation、routing、explanation、confirmation UX。这是对本ADR第98行"Principal现状已经符合这个定位"的正式冻结，不是新约束，是把既有事实写成硬规则。

### R2.1验收问题（第17节）逐条作答

1. **GatewayAttempt是什么** —— provider/model网络调用记录，见上。
2. **AgentRun是什么** —— 有边界的技术Agent执行记录，见上。
3. **IntelligenceRun是什么** —— Family认知事件演化记录，见上。
4. **DomainFact是什么** —— 经ToolRuntime+Policy+Human Gate产生的业务事实，见上。
5. **GuardianCalibration属于哪里** —— IntelligenceRun。
6. **Reflection lineage属于哪里** —— IntelligenceRun。
7. **Provider latency属于哪里** —— GatewayAttempt。
8. **Model draft属于哪里** —— AgentRun。
9. **NamedAction的authoritative truth属于哪里** —— NamedAction/DomainFact层本身，经ToolRuntime产生，不由AgentRun或IntelligenceRun直接写入业务表。
10. **EvaluationLedger未来是什么状态** —— DEPRECATED，长期删除，不迁移进agent_runtime。
11. **experience_runs是否删除** —— 不删除，作为IntelligenceRun的物理载体之一（经adapter），逻辑收敛非物理合表。
12. **ai_agent_runs是否扩成认知总账** —— 不扩，保持AgentRun的纯技术执行状态机边界，认知语义归IntelligenceRun另外的物理载体。
13. **Principal能否直接调用ModelGateway** —— 不能，必须经AgentRuntime/Family Intelligence Kernel。
14. **是否允许新增第四种runtime ledger** —— 不允许；四级模型（Gateway/Agent/Intelligence/DomainFact）是封闭集合，新需求应归入四级中的某一级，不新增第五个平行概念。

### 本次会话新增：Application Factory Configuration Isolation（源自R0.5 Case02事故）

R0.5 Case02（`docs/06_platform/R0_5_ORDER_DEPENDENCY_FINDINGS.md`）的最终根因——`create_app()`同进程内第二次调用继承了第一次调用遗留的module-global repository——揭示了一个比"漏了一行reset"更重要的架构原则，正式写入本ADR作为R2及以后所有Runtime组件的强制约束：

**`APP-FACTORY-ISOLATION`**：Application composition must not depend on previous application instances。`create_app()`每一次调用都必须形成完整、自洽、与此前app实例无关的依赖配置——production→test、test→production、production DB-A→production DB-B、dev→test、test→dev，全部必须成立。禁止"因为上一个create_app()调用碰巧配置过，这个全局就保持配置状态"的隐式继承。

这条原则对Family AGI的意义远大于一个Course repository——**Family AGI后续会有AgentRuntime/IntelligenceRun/WorldModel/Planner/Memory/HumanGate/SkillRuntime这些状态化组件**。如果它们也采用mutable module-global wiring（跟`course_routes.py`现在的`_repository`/`_gate`/`_release_baseline_store`模式一样），后果不再是"测试连错数据库"，而是**一次测试/请求里建立的Family A/Tenant A/Runtime A，被下一次App实例意外继承**——对多租户和未成年人数据边界是严重得多的问题。

**因此：R2开始的新Kernel/Runtime组件禁止新增mutable module-global dependency singleton。** 优先转向App-scoped dependency、Router factory、FastAPI dependency override、`application.state`、显式composition object。`course_routes.py`现有模式（`_repository`/`_course_system_repository`/`_gate`/`_release_baseline_store`四个全局，虽然已有`clear_course_content_wiring()`统一清理函数，但当前组合路径没有保证每次app构建都完整调用它）作为历史遗留登记为`APP-WIRING-STATE-002`（"Remove mutable module-global infrastructure wiring"），不在R2.1范围内改，只冻结方向、不追溯重写现有代码。

### 三条治理原则正式写入

- **RUNTIME-OWNERSHIP**：Every runtime stateful resource must have an explicit owner。
- **APP-FACTORY-ISOLATION**：见上，Application composition must not depend on previous application instances。
- **AGENT-EVIDENCE**：Agent narrative is not execution evidence。验收永远优先`git diff`/真实source/test exit code/CI结果，agent自述只是claim，不是evidence——源自本会话13个并行Agent中7个提交虚假完成报告的真实事故（`governance/ADR/ADR-0158-agi-native-family-growth-platform.md`记录），在此正式升级为R2及以后所有任务的验收纪律，不再只是ADR-0158里的一段事故记录。

### status变更：`Proposed → Accepted`

上述14个验收问题已逐条给出唯一答案，四级Run模型、EvaluationLedger裁决、ExperienceRun/IntelligenceRun收敛方式、Principal边界、三条治理原则均已冻结。本ADR正式从`Proposed`转为`Accepted`。R2.2（Unified Runtime Scope Contract）的具体实施留给下一个ADR/PR，本次修订只锁定架构语义，不动production runtime/schema/migration代码，符合R2.1的范围边界。
