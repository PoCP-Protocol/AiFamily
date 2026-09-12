---
id: ADR-0167
title: Family AGI Runtime 架构定位（Family Domain AGI Platform）
status: Accepted
date: 2026-09-10
updated: 2026-09-11
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

## 实施顺序

用户于 2026-09-11 确认本次范围为 R0 检查与 R2.1 最小变更。先完成
R0 Green Main → R2.1 Run Taxonomy → R2.2 Scope → R2.3 IntelligenceRun，
再推进模型执行收敛；R2 EXIT 全部通过后才能进入 R3 World Model。
Accepted 表示接受本 ADR 的架构边界，不表示 R0 或 R2 已通过验收。

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
- **`Principal`** = 用户面对的统一人格/Supervisor Experience，目标为只负责路由/解释/确认；当前仍有直接网关调用，须在 R2.4 接入 AgentRuntime，不能称为已收敛
- **`ToolRuntime`** = 唯一行动与外部工具边界（现状保留）

### 具体迁移方向

撤销旧版“EvaluationLedger 迁入 agent_runtime”的建议：它的 Guardian 修正与
认知 lineage 属于 IntelligenceRun，不属于 AgentRun。旧建议以 Git 历史保留，
不再作为实施指令。

- 复用 AgentRuntime 的技术执行状态机、权限、trace 与 Model Gateway port。
- 将 revise/reflect 的认知生命周期适配到 IntelligenceRun；家庭 payload 与
  capability grounding 留在 VerticalFamilyGrowthProfile。
- Guardian calibration、parent/revision/reflection lineage 归 IntelligenceRun。

### `path_orchestration` feature branch 处置

`feat/path-draft-persistence-clean`/`feat/path-orchestration-understand-gateway-adapter`/`feat/path-orchestration-knowledge-candidates`三条分支（对应PR#23/#25/#26）**不直接整体merge进main**。吸收其契约设计，归档分支本身：

- `FamilyPathContext` → 并入 Family World Model的context契约
- `PathDraft` → 并入 Plan/GrowthPath契约
- `PathFeedbackSignal` → 并入 Guardian Calibration（`VerticalFamilyGrowthRuntime.decide()`已有的机制）
- `PathDraftPersistencePort` → 提取可复用语义，经 IntelligenceRun persistence port
  适配已有 Experience ledger；不适配到已弃用的 EvaluationLedger
- `ContextDrivenPathDraftPlanner` → 降级为Candidate Pre-selector（确定性过滤层，不冒充Planner）

这不代表三个PR的工作被浪费——`GatewayBackedUnderstandAdapter`/`GatewayBackedCandidateExplanationAdapter`（真实Model Gateway调用+去标识化+知识检索/模型转写分离）这两个设计模式本身是对的，会被复用到Family Intelligence Loop的实现里，只是不再作为独立的`path_orchestration`package存在。

## R2.1：四级 Run Taxonomy（FAMILY-AGI-REORG-021）

本节参考已有定稿提交 `arch/r2-run-taxonomy@31410fe7`，结合当前代码补充可执行
护栏与未完成边界；未修改该协作者分支。基线为
`origin/main@7e3041b53b98f7fd847810ad2d87d590af753080`。

### CURRENT CODE TO REUSE

- `agent_runtime/contracts.py::AgentRun` 与 `persistence.py::AgentRunRecord`、
  `AgentRunRow`：技术执行记录，复用 `ai_agent_runs` 与 trace 表。
- `experience/runs.py`、`experience/run_store.py::SqlAlchemyExperienceRunStore`：
  已有 run/event/checkpoint 状态与持久化，复用 `experience_runs`、
  `experience_run_events`、`experience_run_checkpoints`。
- `agi_vertical_durable.py` 与生产装配中的 durable adapter 检查：已有迁移接缝，
  不能把“仍带内存 pipeline 的 durable wrapper”误报成“旧 runtime 已删除”。
- 现有 ToolRuntime、Human Gate、Domain Named Action：业务事实写入边界。

### CODE TO RETIRE

`backend/intelligence/agi_vertical_runtime.py::EvaluationLedger` = **DEPRECATED**。
不迁入 AgentRuntime，不升级为生产 canonical persistence。先适配、切换调用者、
验证，再删除；本次不删除仍被调用的实现。`experience/multimodal_eval.py` 的同名
EvaluationLedger Protocol 是评测接口，不是这个旧认知 ledger，不能按同名一并删除。

### NEW CODE

本次只新增 `tests/architecture/test_runtime_taxonomy.py`；不创建运行时模块。
R2.3 才实现 `agent_runtime/intelligence_runs.py` 与
`experience/intelligence_run_adapter.py`。**NO MIGRATION / NO NEW TABLE**。

### 四级职责

```text
GatewayAttempt → AgentRun → IntelligenceRun → NamedAction / DomainFact
```

箭头表示记录与治理层次，不表示自动写入；一次 IntelligenceRun 可关联 0..N 次
AgentRun，一次 AgentRun 可关联多次 GatewayAttempt（例如重试）。

- **GatewayAttempt**：provider/model、网络延迟、token accounting、retry/timeout、
  provider response/error metadata。原始供应商响应不是认知状态。
- **AgentRun**：有边界的技术执行，拥有 request/agent/use-case、生命周期、trace、
  ModelDraft 与技术错误。可以保留 draft provenance 中已有的 usage 元数据，
  但不能拥有 guardian_calibration、认知 parent、plan_revision 或 reflection lineage。
- **IntelligenceRun**：认知事件，拥有 scope/subject refs、world-state/evidence/unknown
  refs、Guardian decisions/calibration、goal/plan refs、reflection refs、parent 与
  revision lineage。不得拥有 provider token accounting、provider retry 或 raw response。
  记录业务对象引用不等于拥有业务对象；接受后的 Plan 仍由 canonical Domain 保存。
- **NamedAction / DomainFact**：事实归 Domain；AI 现实动作经 ToolRuntime、Policy、
  所需 Human Gate 与 Named Action，审计随业务事务写入。认知结果不能自动成为事实。

### IntelligenceRun 持久化与重放

```text
IntelligenceRunPersistencePort
  → ExperienceIntelligenceRunAdapter
  → SqlAlchemyExperienceRunStore
  → existing experience run/event/checkpoint tables
```

保留现有 caller-owned transaction 与完整 scope 校验，不复制另一套 ledger。
R2.3 的 replay 必须 ZERO MODEL CALL / ZERO TOOL CALL / ZERO DOMAIN MUTATION，
并证明 Guardian edit/resume/reflection/replan lineage、跨 scope 拒绝及重启恢复。
本次仅冻结这些要求，未实现或验证 IntelligenceRun replay。

### 已落护栏与迁移债务

架构测试检查 AgentRun 的实际 dataclass 字段和 ORM 列，禁止认知字段混入技术记录；
检查现有认知载体的字段，并扫描今后新增的 IntelligenceRun 类型，禁止独立持有
provider accounting。ModelDraft 内原有 provenance 不属于新增的认知 accounting 字段。
扫描器的反例测试覆盖禁止字段与 import alias，避免只在当前文件上得到空的绿灯。

EvaluationLedger 禁止新增生产依赖；当前生产装配的一个 import + 参数类型仍是
显式迁移债务，护栏按基线冻结这两处引用，任何新增引用失败。另一个行为测试
要求生产装配拒绝把 EvaluationLedger 当作 durable ledger。
**这不等于 zero production caller**：旧 Vertical pipeline 仍使用它。
R2.3/R2.6 必须删除剩余依赖及护栏内的对应债务项后，才能通过 R2 EXIT。

字段扫描与依赖扫描不是任意动态 Python 行为的证明，也不证明 JSON payload 的
完整隔离、授权、真实 PostgreSQL、重启或生产路由可用；这些由后续集成验证覆盖。

### R0 检查与验收边界

2026-09-11 查询 main 的 CI run `34467544915`，对应上述基线：迁移、lint、
architecture steps 成功；全量测试 **17 failed, 2714 passed, 18 skipped**，
product_intelligence 域内测试步骤未执行。证据：
https://github.com/PoCP-Protocol/AiFamily/actions/runs/34467544915 。

失败包括跨 event loop 资源、失效数据库引用、family UUID、缺审计表及过期 Human
Task 等表现；仅凭 CI 摘要不能归为同一根因。已有 `fix/r0-green-main-closure`
与 `infra/ci-postgres-isolation` 工作线，本次不混入其修复，不声称它们已合入。
**R0 = BLOCKED；R2 整体验收未通过。**

Accepted 仅冻结 taxonomy 与退役方向。R2.1 最小变更不运行数据库迁移，
真实 PostgreSQL 与 Golden E2E 本次未运行；不得用本次架构测试替代 R2 EXIT。

### 后续实施纪律

每个任务先写 CURRENT CODE TO REUSE、CODE TO RETIRE，再写 NEW CODE。
状态资源必须有显式 owner；新 runtime 依赖按 app/composition 实例持有，不能新增
mutable module-global dependency singleton。应用装配不能依赖上一次 create_app()
留下的配置。执行证据优先于 Agent 叙述。
