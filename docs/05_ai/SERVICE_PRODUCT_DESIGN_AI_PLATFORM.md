---
id: AI-SERVICE-DESIGN-PLATFORM-001
title: 服务产品设计 AI 平台总设计
type: specification
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# 服务产品设计 AI 平台总设计

> 本文件补齐“服务产品如何被设计、验证、发布、交付和持续改进”的平台能力。
> 它不是家庭端的另一个聊天 Agent，也不是把服务预约页面加上一个 AI 按钮；它是
> 面向产品、内容、教研、服务运营和质量角色的组件化设计工厂。所有 AI 结果仍然
> 遵守 `Fact ≠ Perspective ≠ Recommendation ≠ Action ≠ Outcome`，发布和业务事实
> 写入必须由业务域 Named Action 完成。

## 1. 研究结论：为什么必须单独建这一层

本轮核对了以下现有证据：

- `docs/01_strategy/source_materials/法咪莉教育战略白皮书_30页演讲汇报版.txt` 的 Slide 16
  明确提出“知识库 → 用户画像 → 成长规划 → 陪练执行 → 督导反馈 → 数据中台”，Slide 17
  将 Agent 绑定到真实任务，Slide 18/19 将家庭成长数据库和结构化采集定义为护城河。
- `docs/01_strategy/source_materials/家庭教育大模型平台科技公司项目合作方案.txt` 要求
  “底座工具 + Agent 应用 + 用户裂变”可跨赛道复用，并把知识库、会话存档和 Agent 迭代
  作为持续投入，而不是一次性上线功能。
- `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md` §8 已将 Service Blueprint Library、
  `primary_contradiction` 和 Growth Intervention Engine 定为独占区候选。
- 旧版 `backend/packages/contracts/product_factory.py` 曾有 `Component`、`Pattern`、
  `ProductDefinition` 的重复 schema，但它与 `product_intelligence` 域的 canonical
  实体重复，已在本轮清理删除；后续组件、Pattern 和 ProductDefinition 只能以
  `backend/domains/product_intelligence` 的实体/Port 为真相。组件兼容、工作流、资源、
  AI 用例、安全、成本、评估和 SLA 校验仍由设计工厂编译器负责。
- `backend/intelligence/design_copilot/compiler.py` 已列出 12 类编译检查，所有方法仍为
  `NotImplementedError`，且没有调用方；`simulation.py` 只有“模拟结果不能自证”的护栏，
  `run()` 尚未实现。
- `backend/domains/product_intelligence` 已有 MarketSignal、GrowthProblem、
  GrowthHypothesis、ContradictionModel、ValueArchitecture、GrowthStrategy、
  ProductConcept、ProductComponent、ProductPattern、ProductDefinition 等对象，
  但它们仍未形成“设计稿 → 可执行服务蓝图”的应用闭环。
- `backend/domains/service` 已有 Provider、Offering、Slot、Booking、ServiceRecord
  和服务查询/预约端点，属于“服务交付运行时”；它不能代替设计工厂，也不能被 AI 直接
  改写。
- `backend/domains/assessment/domain/knowledge_grounding.py` 与
  `docs/13_research/knowledge_compiled/*.json` 已证明知识资产可以被构建时 grounding，
  但当前只有静态快照和测评构念白名单，没有统一知识源、版本、许可、检索、审核、失效
  和删除链路。

因此现有系统缺的不是一个“服务推荐接口”，而是服务供给从经验变成可复用产品的中间层：

```text
业务问题/主要矛盾
  → 组件与模式选择
  → 服务产品设计稿
  → 服务蓝图与交付任务
  → 模拟验证/安全/成本/SLA检查
  → 人工评审与发布
  → 真实交付与质量证据
  → 知识、组件和蓝图迭代
```

## 2. 平台定位和边界

### 2.1 一句话定位

Service Product Design AI Platform（SPD-AI）是一个以知识和证据为输入、以组件和
Service Blueprint 为输出、以模拟和真人交付反馈为验证的服务产品设计操作系统。

### 2.2 服务对象

- 产品负责人：定义目标家庭问题、价值假设、适用人群和商业约束。
- 教研/内容负责人：维护理论、方法、课程、话术和安全边界。
- 服务运营/管家负责人：定义交付角色、SLA、资源能力、升级和补偿规则。
- 专家/教师：提供组件、交付步骤、验收标准和不可适用条件。
- AI 治理/评估人员：维护知识、Prompt、Schema、评估集、风险和发布门槛。
- 平台运营：观察采用、返工、投诉、交付质量、成本和版本漂移。

家庭、孩子和服务接受者只消费已经发布且经过授权的服务产品；他们不直接编辑平台
主数据，也不承担服务产品发布责任。

### 2.3 不负责的事情

- 不替代 `backend/domains/service` 的预约、案件、任务、验收和贡献事实。
- 不替代 `backend/domains/product_intelligence` 的市场信号、问题、假设和策略权威。
- 不让 AI 直接发布产品、激活计划、预约服务、分派资源、验收交付或计算分账。
- 不把家庭成长结果、儿童特征或服务满意度汇总成家庭总分/家庭排名。
- 不把未成年人数据复制进共享知识库；家庭私有上下文和公共知识必须物理/权限隔离。

## 3. 分级业务流程架构

### L0：服务产品设计生命周期

```text
SP0 设计治理
  → SP1 问题与价值建模
  → SP2 组件/模式设计
  → SP3 服务产品编排
  → SP4 蓝图编译与验证
  → SP5 人工评审与发布
  → SP6 服务交付反馈
  → SP7 知识与产品学习
```

### L1-L2 场景闭环

#### SP-01 问题、价值和主要矛盾建模

1. 输入：市场信号、家庭需求摘要、测评证据、服务反馈、目标客群和约束。
2. 活动：形成 GrowthProblem、GrowthHypothesis、ContradictionModel、ValueArchitecture
   和 GrowthStrategy；AI 只能提出 Perspective/Hypothesis，不能确认事实。
3. 输出：经人工确认的问题包和 `primary_contradiction_ref`。
4. 规则：证据引用非空；至少两条互相有张力的假设才可形成 Contradiction；高风险主题
   必须进入人工闸门；不得生成儿童诊断、家庭总分或排名。
5. 结束：问题包 `APPROVED`，或被驳回/退回补证据。

#### SP-02 组件目录维护

1. 输入：教研方法、课程内容、服务步骤、角色能力、工具、资源、风险规则和历史质量证据。
2. 活动：建立 ComponentDefinition，声明输入/输出契约、适用范围、前置条件、禁用条件、
   资源需求、预计时长、成本和验证方式。
3. 输出：组件版本 `DRAFT → REVIEWED → PUBLISHED → RETIRED`，发布后不可原地修改。
4. 规则：组件必须有 owner、证据/来源、许可、适用年龄、数据用途和安全标签；AI 生成
   的组件只能是 Draft；组件不能携带某个家庭的私有事实。
5. 结束：组件可被 Pattern 或 ServiceProduct 引用；没有合规/质量证据则保持 Draft。

#### SP-03 模式与服务产品编排

1. 输入：已发布组件、服务角色、交付渠道、资源能力、价格/权益边界、目标矛盾和服务目标。
2. 活动：组合 PatternDefinition，形成 ServiceProductDefinition，声明阶段、任务、
   责任人、输入输出、人工触发、失败补偿和验收标准。
3. 输出：可编译的产品设计稿和依赖图。
4. 规则：组件版本必须存在且兼容；阶段必须可达且无死循环；每个任务有责任人和交付物；
   资源不足只能输出 `RESOURCE_GAP`，不能伪造可交付能力。
5. 结束：设计稿进入编译，或因依赖/资源/安全缺口退回。

#### SP-04 Service Blueprint 编译与验证

1. 输入：ServiceProductDefinition、组件/模式版本、主要矛盾、知识检索结果、服务目录、
   资源容量、SLA、成本预算和评估套件。
2. 活动：Schema、Component、Compatibility、Workflow、Resource、AI Use Case、
   Context、Safety、Human Gate、Cost、Evaluation、SLA 12 项检查；生成可执行的
   BlueprintDraft 和 SimulationPlan。
3. 输出：编译报告、错误/警告清单、模拟计划和蓝图草案。
4. 规则：任一阻断项失败不能进入评审；引用的 AI 用例必须在
   `governance/AI_USE_CASE_REGISTRY.yaml` 登记；知识引用必须可追溯到版本和许可；模拟
   数据只能证明工程正确性，不能自证真实有效性。
5. 结束：`COMPILE_PASSED` 进入人工评审，或 `COMPILE_BLOCKED` 返回设计稿。

#### SP-05 模拟、红队和人工评审

1. 输入：BlueprintDraft、合成家庭/交付情境、风险规则、评估集和历史失败案例。
2. 活动：运行正常、缺证据、资源不足、用户拒绝、人工超时、敏感主题、供应商不可用、
   交付返工和取消等情境；检查输出边界、引用、成本、SLA、补偿和可回放性。
3. 输出：SimulationRun、EvaluationRun、RedTeamFinding、HumanReviewTask。
4. 规则：模拟结果不能单独晋级；高风险必须人工确认；失败的 Safety/Contract/Workflow
   检查阻断发布；所有结果带 `data_class=SYNTHETIC` 和 provenance。
5. 结束：评审通过发布候选，或驳回/要求修改。

#### SP-06 发布、回滚与交付接线

1. 输入：通过评审的 BlueprintVersion、知识/Prompt/Schema 版本、资源准入、发布计划。
2. 活动：发布蓝图，建立 `ServiceBlueprintRelease`，同步 Service Catalog Projection；
   交付运行时只读取冻结版本；变更采用新版本并可灰度/回滚。
3. 输出：可被 `service` 域创建 ServiceCase/ServiceTask 的蓝图版本。
4. 规则：只有业务域/运营 Named Action 能发布；AI 只能创建发布建议；已创建案件绑定的
   蓝图版本不可被后续编辑覆盖；回滚不改变历史交付记录。
5. 结束：发布成功、回滚或暂停使用。

#### SP-07 交付反馈和持续学习

1. 输入：ServiceTask、DeliveryRecord、QualityReview、投诉/恢复、家长反馈、人工改写、
   采用/驳回、成本和 SLA 事实。
2. 活动：归因到组件、模式、蓝图、知识和 Agent；识别返工、空转、资源缺口和风险漂移；
   形成组件/知识/Prompt/Blueprint 的变更候选。
3. 输出：LearningAction、QualitySignal、ComponentImprovementDraft、KnowledgeFeedback。
4. 规则：反馈不直接改历史事实；不能把满意度当作家庭成长结果；任何新版本重新走编译、
   Safety、评估和人工发布闸门。
5. 结束：候选进入下一轮设计，或被归档。

## 4. 组件化产品模型

### 4.1 组件类型

```text
ComponentDefinition
├─ evidence / theory       理论和证据组件
├─ method / practice       方法与练习组件
├─ content / lesson        内容与课程组件
├─ interaction / script    互动与话术组件
├─ assessment / signal     测评/观察信号组件
├─ service_step / task     真人交付步骤组件
├─ role / capability       角色和能力组件
├─ tool / resource         工具和资源组件
├─ safety / policy         安全、合规和边界组件
└─ evaluation / metric     验收指标和评估组件
```

每个组件必须声明：`component_id`、`version`、`type`、`input_contract`、
`output_contract`、`preconditions`、`exclusions`、`required_roles`、`resource_requirements`、
`safety_policy`、`knowledge_refs`、`evidence_refs`、`cost_estimate`、`sla_impact`、owner 和状态。

### 4.2 Pattern 与 ServiceProduct

- `PatternDefinition` 是经过组合验证的组件模式，例如“21 天家庭沟通练习”或“专家评估→
  家庭任务→回访复盘”。Pattern 只引用版本化组件，不复制组件正文。
- `ServiceProductDefinition` 是面向一个问题/主要矛盾的产品设计稿，包含目标客群、价值
  叙事、适用/排除条件、Pattern、阶段、任务、角色、资源、SLA、成本和评估套件。
- `ServiceBlueprintVersion` 是供 `service` 交付域执行的冻结蓝图。它是设计稿编译后的
  业务配置，不是 AI 生成的事实；发布由服务域 Named Action 完成。
- `ServiceCase`、`ServiceTask`、`DeliveryRecord` 和 `ServiceContribution` 只承载真实
  交付事实；运行时不得反向修改设计稿。

### 4.3 编译器的 12 项检查

现有 `ProductCompiler` 的 12 个检查应实现为同一个可重放的 `CompileRun`，不允许 UI 自己
拼校验：

```text
schema → component → compatibility → workflow → resource → ai_use_case
context_boundary → safety → human_gate → cost → evaluation → sla
```

每项检查输出 `PASS / WARN / BLOCK`、规则版本、输入版本、证据引用、解释和修复建议。
编译器只读设计投影和目录，不直接写 `service` 交付事实。

## 5. 知识库架构

### 5.1 知识分层

```text
K0 来源层       论文、法规、课程、专家材料、服务记录、评估案例
K1 文档层       文档/章节/附件/版权/适用范围/失效日期
K2 语义层       Claim、Theory、Method、Practice、Contraindication、SafetyRule
K3 组件层       KnowledgeComponentBinding、BlueprintPatternBinding
K4 检索层       Chunk、EmbeddingRef、Index、RetrievalPolicy
K5 运行层       GroundedContext、Citation、KnowledgeFeedback、LearningAction
```

### 5.2 知识资产类型

- 理论与研究：说明机制、证据等级、跨文化限制和开放问题。
- 方法与练习：步骤、剂量、适用年龄、观察信号、禁忌和失败模式。
- 服务交付知识：角色职责、话术、SLA、验收标准、补偿和升级路径。
- 组件/蓝图知识：组件组合条件、互斥关系、资源依赖和历史质量。
- 治理知识：法规、同意、留存、删除、儿童安全、发布规则。
- 运行反馈知识：经过脱敏/聚合的失败案例、人工改写、评估结果和版本影响。

现有 `docs/13_research/knowledge_compiled/*.json` 属于 K0/K1 的构建时快照；
`knowledge_grounding.py` 属于测评构念的 K2/K5 适配器。它们是可复用资产，但还不能
替代统一的 Knowledge Registry、版本状态机、检索服务和删除作业。

### 5.3 知识生命周期

```text
INGESTED → PARSED → CHUNKED → GROUNDED → REVIEWED → PUBLISHED → RETIRED
```

每个版本必须有 source、license、owner、scope、age_range、jurisdiction、evidence_grade、
safety_tags、expires_at、retention_class、provenance 和 reviewer。发布后不可原地修改；
知识失效或许可证撤销时，检索索引、缓存、EmbeddingRef、评估副本和引用投影必须可定位、
可删除并产生完成证明。

### 5.4 检索与 grounding 规则

1. 检索先按 tenant、purpose、主体、年龄、data_class、scope 和有效期过滤，再做关键词/
   向量/结构化条件的混合排序。
2. 共享知识库不得写入家庭私有事实；家庭 Context 只在授权请求内与公共知识临时合并。
3. 每次检索返回 `knowledge_version`、`chunk_id`、`claim_id`、evidence_grade 和引用范围；
   模型自报的引用不可信，必须在 Registry 白名单中复核。
4. 无足够 grounding 时输出 `INSUFFICIENT_EVIDENCE` 或转人工，不用通用文案填空。
5. 向量索引可以使用 PostgreSQL/pgvector，但必须先通过租户隔离、主体删除、留存、重建
   和故障恢复测试；不能把不可删除的外部向量库作为前提。

## 6. AI 智能能力与 Agent 对齐

服务产品设计平台复用既有 `operations_assistant` 作为内部执行 Agent，并增加两个不可
直接写业务的执行 profile：

- `service_product_architect`：问题→组件→Pattern→ServiceProductDefinition 草案。
- `knowledge_steward`：知识登记、grounding、许可/失效检查和反馈归因草案。

两个 profile 不是新的家庭端业务主体；它们必须通过 Agent Runtime 和 Model Gateway，
只能调用只读目录、编译、模拟、评估和人工任务工具。

新增 AI 用例：

```text
SPD-01 service_problem_synthesis       → ProblemPerspective / Hypothesis
SPD-02 component_composition           → ComponentCompositionDraft
SPD-03 service_product_blueprint_draft → ServiceProductDraft
SPD-04 blueprint_compile_explanation   → CompileReport / HumanTask
SPD-05 service_simulation_plan         → SimulationPlan
SPD-06 knowledge_grounded_design_advice→ DesignRecommendation
SPD-07 blueprint_release_readiness     → ReleaseRecommendation / HumanTask
SPD-08 delivery_feedback_learning      → LearningActionDraft
```

这些结果全部登记在 `governance/AI_USE_CASE_REGISTRY.yaml`，初始状态为 `PLANNED`，
任何高影响输出需要产品/教研/运营等指定责任人确认。AI 不得直接发布蓝图、修改已发布
组件、改变价格/权益、预约/分派服务或验收交付。

## 7. 应用架构和接口边界

### 7.1 应用模块

```text
ServiceProductDesignApplication
├─ ProblemWorkbench          问题/矛盾/价值建模
├─ ComponentCatalog          组件和模式目录
├─ ProductComposer           服务产品编排
├─ BlueprintCompiler         12 项检查和编译报告
├─ SimulationLab              合成场景、红队和回放
├─ KnowledgeWorkbench         知识登记、grounding 和版本
├─ ReviewAndRelease           人工评审、发布、灰度、回滚
└─ LearningWorkbench          交付反馈、质量和版本改进
```

### 7.2 进程边界

- `family_api`：产品设计工作台 API、身份/权限、Named Action、人工评审和服务目录投影。
- `ai_runtime`：Context Broker、Knowledge Retrieval、Agent Profile、Compiler/Simulation
  推理、Model Gateway、Safety、Provenance；默认只读设计投影。
- `workflow_worker`：编译、模拟、评估、索引、删除、发布、回滚和反馈归因等长任务。
- `service` 域：接收已发布 BlueprintVersion，创建 ServiceCase/Task 并记录交付事实。

### 7.3 关键 API/命令

```text
POST /ops/service-products/designs
POST /ops/service-products/designs/{id}/compose
POST /ops/service-products/designs/{id}/compile
POST /ops/service-products/designs/{id}/simulate
POST /ops/service-products/designs/{id}/submit-review
POST /ops/service-products/designs/{id}/publish
POST /ops/service-products/releases/{id}/rollback
POST /ops/knowledge/sources
POST /ops/knowledge/versions/{id}/review
POST /ops/knowledge/versions/{id}/publish
POST /ops/service-products/feedback/attribute
```

所有写命令必须带 `idempotency_key`、`correlation_id`、actor、reason 和审计；AI 只能调用
对应的 Draft/Preview/Simulation/Review Task 端点，不能绕过应用层访问 ORM。

## 8. 数据对象、表和关系总览

本专项的对象分为三组：

1. 设计主数据：`service_product_components`、`service_product_patterns`、
   `service_product_definitions`、`service_blueprint_versions`、`service_product_releases`。
2. 知识主数据：`knowledge_sources`、`knowledge_documents`、`knowledge_versions`、
   `knowledge_chunks`、`knowledge_claims`、`knowledge_component_bindings`、
   `knowledge_embeddings`、`knowledge_review_tasks`。
3. 设计/验证业务数据：`design_compile_runs`、`design_compile_findings`、
   `simulation_runs`、`simulation_cases`、`design_evaluation_runs`、
   `design_human_reviews`、`service_product_feedback_links`、`design_learning_actions`。

关系约束：

- `ServiceProductDefinition → ServiceBlueprintVersion` 为 1:N；蓝图编译时冻结设计和组件版本。
- `ServiceBlueprintVersion → ServiceCase` 为 1:N；ServiceCase 只保存 blueprint snapshot ref，
  不反向更新设计对象。
- `ComponentDefinition → PatternDefinition → ServiceProductDefinition` 为 1:N；引用版本
  不复制正文，组件退役不影响历史蓝图。
- `KnowledgeVersion → KnowledgeChunk → KnowledgeClaim` 为 1:N；Claim 可被组件/蓝图绑定，
  绑定必须保留版本和用途。
- `KnowledgeVersion → KnowledgeEmbedding` 为 1:N；Embedding 删除必须受主体/许可证/留存作业
  控制并产生完成证明。
- `DesignCompileRun → DesignCompileFinding` 为 1:N；`SimulationRun → SimulationCase`
  为 1:N；评估失败阻断发布。
- `ServiceTask/QualityReview/Feedback → ServiceProductFeedbackLink` 为 N:1 归因关系；归因
  只能产生改进候选，不能覆盖原始交付事实。

物理 schema、字段、索引、删除级联和 PostgreSQL revision 详见配套
`docs/07_data/SERVICE_PRODUCT_DESIGN_KNOWLEDGE_DATA_ARCHITECTURE.md`。

## 9. 环境等价和安全边界

开发、测试、生产必须暴露相同的工作台、编译器、模拟器、知识审核、发布、回滚、人工闸门、
错误码和状态机。测试环境只替换合成设计资料、Fake/Deterministic Model Provider、索引
数据和外部服务适配器，不能删除编译失败、知识失效、人工超时、回滚、删除和审计路径。

设计平台尤其要防止三类泄漏：

1. 设计人员把家庭私有上下文复制到公共组件/知识库。
2. AI 将研究摘要或模拟结果伪装成已验证服务效果。
3. 通过“推荐组件/推荐专家”间接形成未成年人画像驱动商业营销。

## 10. 当前实现与缺口

### 已有可复用基础

- `product_intelligence`：问题、假设、矛盾、价值、策略、产品组件/模式/定义的领域对象和
  部分持久化/测试。
- `service`：供给、服务产品（Offering）、时段、预约、服务记录和投影的交付运行时。
- `design_copilot`：12 项编译检查和模拟晋级护栏的结构占位。
- `product_intelligence` 域实体/Port：Component、Pattern、ProductDefinition 的唯一
  业务真相；禁止恢复已删除的 `backend/packages/contracts/product_factory.py` 重复入口。
- `assessment/knowledge_grounding.py` + 9 份 compiled JSON：静态 grounding 资产。
- `model_gateway`、`context_engine`：受治理的生成边界和内存上下文原语。

### 尚未实现的核心能力

- Component Catalog/Pattern Catalog 的统一版本、兼容矩阵、资源和租户权限。
- ServiceProductDefinition→ServiceBlueprintVersion 的真实编译器和 12 项检查执行器。
- 合成情境生成、SimulationLab、红队、评估集和发布阻断。
- Knowledge Registry、文档解析/chunk/claim、混合检索、Embedding 生命周期和删除证明。
- 设计工作台 API、人工评审/发布/回滚及与 `service` 域的正式接线。
- 设计反馈归因、组件质量指标、版本漂移和学习动作。
- SPD AI 用例的 Prompt/Schema/Knowledge 运行时版本与 `AI_USE_CASE_REGISTRY` 实际加载。

## 11. 分阶段落地

- **SP-P0 契约冻结**：登记 SPD-01～08、组件类型、蓝图状态机、知识元数据、12 项编译
  检查、环境等价和人工责任；不写模型供应商代码。
- **SP-P1 设计主数据**：实现 Component/Pattern/ServiceProductDefinition 的 PostgreSQL
  表、版本和兼容校验；把 `ProductCompiler` 从占位改成纯确定性检查器。
- **SP-P2 知识库最小闭环**：来源→版本→chunk/claim→审核→发布→检索→Citation；先复用
  现有 compiled JSON，禁止把家庭私有数据纳入公共知识。
- **SP-P3 蓝图编译与模拟**：接入 Context/Knowledge/Model Gateway，生成 BlueprintDraft、
  CompileRun、SimulationRun 和 HumanTask；所有结果仍是 Draft。
- **SP-P4 发布和服务交付接线**：人工发布 ServiceBlueprintVersion，`service` 域按冻结版本
  创建案件/任务，回收 Quality/Delivery/Feedback。
- **SP-P5 学习和跨赛道复制**：以脱敏交付证据更新组件、知识和蓝图候选；新领域只替换知识
  包和组件，不复制一套 AI Runtime。

## 12. 完成定义

服务产品设计 AI 平台只有同时满足以下条件，才能称为可用：

1. 一个服务产品可从问题/主要矛盾追溯到组件、知识、蓝图和评估版本。
2. 编译器 12 项检查可重复执行、可解释、可阻断，并有人工修复路径。
3. 知识引用可验证，许可/失效/删除能级联到 chunk、embedding、缓存和评估副本。
4. 模拟结果和 AI 草案不会自动发布或写入服务交付事实。
5. 发布蓝图被服务案件冻结引用，回滚不改历史交付记录。
6. 交付反馈可以归因到组件/知识/蓝图版本，并形成新版本候选而非直接覆盖。
7. dev/test/prod 使用相同工作流、状态机、闸门、错误码和功能路径。
8. 所有高风险设计、儿童相关内容、服务分派和对外承诺都有明确的人类责任人。

## 13. 法咪莉校长：服务产品设计 AI 的统一入口

服务产品设计 AI 不应以“另一个聊天机器人”的形式存在。它是法咪莉校长在运营、产品、
教研和服务设计场景下的内部工作 profile：校长保持统一的 Soul、价值和安全边界，
profile 决定上下文、工具和输出 schema。

```text
问题/主要假设
  → Principal/service_product_architect
  → Product Intelligence + 三区证据
  → Component/Pattern Catalog
  → ServiceProductDefinition Draft
  → Compiler 12 checks
  → Simulation / Red Team / Eval
  → Human Publish Gate
  → ServiceBlueprintVersion
  → ServiceCase / ServiceTask
  → Quality / Contribution / Feedback
```

### 13.1 校长在设计工厂中的职责

| 阶段 | 校长可做 | 校长不可做 |
|---|---|---|
| 发现 | 总结市场信号、家庭需要和不确定性 | 把样本推断成家庭事实 |
| 设计 | 建议组件、模式、知识引用和服务步骤 | 直接发布产品或蓝图 |
| 编译 | 解释 12 项检查、指出冲突和缺失 | 绕过失败 finding |
| 模拟 | 生成合成情境、风险/成本/SLA 建议 | 把模拟结果当成疗效或真实 Outcome |
| 发布 | 准备评审包、回滚说明和人工作业 | 自动发布、自动分派或自动改价 |
| 学习 | 归因质量反馈并形成下一版本候选 | 覆盖历史交付事实或分佣事实 |

### 13.2 与家庭端校长的统一性

家庭端 profile 使用 `family_understanding`、`growth_planning`、`action_coaching`、
`delivery_reflection`；设计端使用 `service_product_architect`；知识治理使用
`knowledge_steward`；运营端使用 `operations_insight`。所有 profile 都通过同一个
`backend/intelligence/model_gateway`，并携带 `soul_version`、`prompt_version`、
`schema_version`、`knowledge_refs` 和 `provenance`。

这份设计完成后，仍不能声称服务产品设计 AI 已上线：当前 `design_copilot` 的编译器和
模拟器仍是结构占位，Principal/Agent/Knowledge Runtime 仍需按
`docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md` 的 Wave 0～4 实施。
