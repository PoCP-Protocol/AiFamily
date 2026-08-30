---
id: IPD-PDM-PLM-COMPONENT-FACTORY-001
title: 家庭成长系统 IPD/PDM/PLM 组件与 AI 产品工厂
type: product
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# 家庭成长系统 IPD/PDM/PLM 组件与 AI 产品工厂 V1（Web UI）

> 本产品只交付 Web UI。它是产品经理、教研/服务设计师、AI 管理员、质量与运营人员使用的
> 产品工作台，不是移动端家庭应用。家庭端、教师端和商业端的渠道产品由后续独立项目消费
> 已发布的 ProductPackage/Blueprint 投影，本工作台不复制这些渠道页面。

## 1. 目标架构

家庭成长系统采用三套互补系统，而不是把所有东西塞进一个“课程后台”：

```text
IPD  产品决策系统   决定做什么、为谁做、为什么做、何时停止
 ↓
PDM  产品数据系统   管理组件、配置、版本、依赖、成本、能力和组合关系
 ↓
PLM  产品生命周期系统 管理试点、发布、运营、变更、复盘、退役
 ↓
Family / Journey / Service / Commerce 业务域执行并产生事实
```

21 天成长营、90 天成长计划只是 `ProductPackage` 的两种产品形态，不是两套特例代码。
后续家庭沟通、学习习惯、手机管理等产品复用同一组件库、技能库、蓝图和生命周期。Web UI
只负责设计、编译、试点和生命周期控制，不直接替代家庭业务渠道。

## 2. IPD、PDM、PLM 的职责边界

### Web UI 工作台分区

- **Product Studio**：机会、Charter、需求基线、概念候选和三区决策；
- **Component Library**：组件、Skill、Pattern、兼容矩阵、版本和使用关系；
- **AI Design Lab**：证据输入、候选生成、组合、解释、反例和评估；
- **Gate Board**：G0-G6 输入、证据、责任人、阻断项和决策历史；
- **Pilot Ops**：小批试点、分组、指标、guardrail、异常和人工升级；
- **PLM Console**：发布、暂停、回滚、变更、反馈、成本和退役。

Web UI 的每个按钮都必须映射到 Command/Query、权限、审计和验收测试；不能用静态卡片
伪装成产品已发布。

### IPD：跨职能产品开发

IPD 以真实家庭需求为起点，以 `ProductInitiative` 为决策根，先形成 `DemandFrame` 和
`RequirementHypothesis`，再用 `MarketInsight` 验证规模、替代、竞争与趋势，最后串起概念
候选、架构基线、验证和阶段 Gate。IPMT 决定投资与停止；PDT 负责设计和交付；领域 Owner
负责业务事实。市场洞察不能绕过需求直接生成产品。

最小 Gate：G0 机会、G1 概念、G2 计划、G3 开发冻结、G4 资格、G5 发布、G6 生命周期。

### PDM：产品数据与配置管理

PDM 管理可复用的产品构件：

- `GrowthComponent`：一个可组合的成长活动或服务能力；
- `SkillDefinition`：AI/人工完成一类工作的输入、输出、工具和边界；
- `PatternDefinition`：组件组合的结构、适用问题、阶段和依赖；
- `ProductPackage`：面向一个场景的产品组合，如 21 天或 90 天；
- `BlueprintVersion`：供 Journey/Service 执行的冻结配置；
- `KnowledgeBinding`、`PromptBinding`、`MetricDefinition`、`CostPolicy`、`SLAPolicy`。

PDM 不拥有家庭状态、订单、服务履约或成长结果；这些仍由业务域拥有。

### PLM：产品生命周期管理

PLM 管理 `Draft → Pilot → Qualified → Released → Paused → Retired`，并记录版本、试点、
质量、成本、反馈、变更和 EOL。每次变更都产生新的不可变版本，已执行的家庭计划引用原版本。

## 3. 组件库设计

### 3.1 组件不是内容卡片

一个可复用组件必须声明：

```text
component_id / version / owner / zone
purpose / target_scenario / duration
inputs / outputs / preconditions / contraindications
roles / actions / evidence_refs / knowledge_refs
service_capacity / sla / unit_cost_assumption
metrics / guardrails / pause_rule / rollback_rule
required_skills / allowed_tools / human_gate_policy
```

只写“亲子沟通课程”或“每日打卡文案”的卡片不是组件；无法声明输入、输出、责任、验收和
失败处理的内容不得进入发布目录。

### 3.2 组件分类

| 类型 | 例子 | 主要 Owner |
|---|---|---|
| Understanding | 需求澄清、假设解释、冲突复述 | product_intelligence + AI Runtime |
| Action | 今日行动、家庭对话、复盘提示 | journey |
| Service | 教师会话、专家答疑、机构交付 | service |
| Evidence | 反馈采集、观察记录、质量检查 | growth/service |
| Orchestration | 21 天节奏、90 天阶段、暂停/恢复 | product + journey |
| Governance | 同意、人工升级、删除、回滚 | platform + compliance |
| Commerce | 家长主动购买、会员权益、退款 | commerce |

组件库按产品三区理论分层，而且分区会改变 IPD Gate、PDM 配置和 PLM 投资，不是展示标签：

| 产品区 | 产品设计重点 | PDM 组件策略 | PLM 决策规则 |
|---|---|---|---|
| 同质区 | 快速满足基本需求、稳定交付 | 复用标准组件，严格控制成本和变体 | 低成本试点；无差异即淘汰或外采 |
| 优势区 | 在家庭场景和服务协同上形成明显优势 | 组合 AI Skill、服务蓝图和质量策略 | 以采纳、交付质量和复购意向决定扩展 |
| 独占区候选 | 建立难复制的上下文、关系和方法资产 | 沉淀受治理知识、成长图谱、干预和蓝图 | 允许长期投入，但必须持续验证可复制性和安全性 |

三区评估必须引用 `product_intelligence` 现有 `ProductZoneAssessment` 与策略版本；产品
工厂不另造评分算法。一个产品包可以同时含三类组件，但必须声明主导区、各区比例、护城河
假设和退出条件。进入独占区候选不等于天然正确，只代表值得验证和投资。

### 3.3 三区驱动的组件准入

- 同质区组件：必须有稳定输入输出、成本上限、替代方案和标准 SLA；
- 优势区组件：必须绑定至少一个家庭场景假设、服务责任人和质量指标；
- 独占区候选组件：必须绑定证据/知识版本、删除策略、回放能力、长期反馈指标和 IPMT 投资
  决策，且不可把家庭或儿童数据用于跨家庭画像或商业排名。

## 4. Skill 化：把“如何完成工作”变成可组合能力

`SkillDefinition` 是平台内的一等对象，不等同于某个模型 Prompt，也不等同于某个 UI 页面。

```text
SkillDefinition
  ├─ skill_id / version / owner
  ├─ purpose / input_schema / output_schema
  ├─ required_context / knowledge_bindings
  ├─ allowed_tools / forbidden_tools
  ├─ quality_evals / safety_policy / human_handoff
  └─ status: DRAFT | REVIEWED | PUBLISHED | RETIRED
```

首批技能：

- `discover_family_problem`：把授权证据整理为问题与机会视角；
- `explain_growth_hypothesis`：解释假设并提出可暂停行动；
- `compose_growth_product`：组合组件形成 21/90 天产品草案；
- `compile_service_blueprint`：检查组件、服务容量、SLA 和风险；
- `design_micro_pilot`：设计小批试点、指标、guardrail 和停止条件；
- `interpret_pilot_feedback`：解释反馈，生成 SCALE/REVISE/KILL 建议；
- `prepare_lifecycle_change`：生成版本变更、迁移和回滚草案。

每个 Skill 经 Model Gateway 调用，必须带 provenance、上下文快照、知识版本和评估结果；
Skill 默认只产生 Draft/Recommendation/HumanTask，不直接写业务事实。

## 5. AI 产品工厂如何生成 21 天和 90 天产品

### 5.1 设计阶段

AI 从 Opportunity、GrowthProblem、已审核证据、组件库、技能库、服务容量和约束中生成
多个候选，而不是只生成一个“最佳答案”：

```text
候选 A：21 天低服务密度，验证行动采纳
候选 B：21 天高陪伴密度，验证服务协同
候选 C：90 天三阶段，复用已通过的 21 天组件
```

候选之间比较客户价值、交付复杂度、成本、风险、证据强度和三区位置，由 IPD Gate 选择。

### 5.2 组合阶段

组合器根据输入输出契约和前置条件连接组件，形成 `PatternDefinition`；编译器检查：

- 组件输入是否满足前一组件输出；
- 每个阶段是否有明确责任人、行动、验收和暂停路径；
- 服务容量、SLA、成本和合规边界是否可交付；
- 所有 AI 技能是否有 Use Case、工具、知识和人工责任人；
- 21 天/90 天是否引用了正确的版本和可回滚蓝图。

### 5.3 试点与扩展

产品发布不是一次性上线，而是：

```text
7 天探索试点 → 21 天验证产品 → 90 天规模产品
       ↑              ↓              ↓
   反馈/质量/成本 ← PLM 生命周期 ← 版本变更
```

试点结果只能生成证据和改版建议，不能自动把 AI 判断写成成长结果。扩大范围必须经过新的
Gate，并检查服务容量、同意范围和未成年人保护约束。

## 6. PDM 与现有代码的映射

不新增平行的 canonical 业务域：

- `backend/domains/product_intelligence`：产品概念、组件、Pattern、ProductDefinition 的业务事实；
- `backend/intelligence/knowledge`：知识/证据包的登记与只读编译；
- `backend/intelligence/model_gateway`：所有模型调用；
- `backend/intelligence/design_copilot`：编译、模拟、设计建议；
- `backend/intelligence/human_gate`：人工确认和 Named Action；
- `backend/domains/journey`、`service`、`commerce`：按已发布蓝图执行并拥有业务事实；
- `workflow_worker`：长流程试点、发布、回滚和生命周期任务。

IPD/PDM/PLM application/contracts 应作为治理与产品配置层，不能让 AI Runtime import 业务
repository，也不能让设计对象绕过领域 Owner 直接创建 ServiceCase、Order 或家庭事实。

## 7. 首批组件库

第一批不追求数量，先建立可验证的 12 个组件：

1. 需求澄清；2. 假设解释；3. 家庭目标确认；4. 今日行动；5. 行动暂停/恢复；6. 反馈采集；
7. 周复盘；8. 教师升级；9. 服务预约；10. 质量验收；11. 21 天阶段编排；12. 90 天阶段编排。

21 天产品至少组合 1–8；90 天产品复用 1–8，并按阶段增加 9–12。每个组件都有独立版本、
Owner、验收测试、成本和回滚规则。

## 8. 开发切片与完成定义

### Slice A：组件与技能目录

建立 PDM contracts、版本状态机、兼容性检查和只读 Catalog API；登记首批组件/技能。

### Slice B：AI 组合器

经 Model Gateway 生成候选组件组合，输出 ProductPackage Draft；加入 provenance 和评估。

### Slice C：IPD Gate Compiler

将 Charter、RequirementBaseline、Blueprint、PilotPlan 和 ReleaseBaseline 编译成 Gate 证据。

### Slice D：PLM 试点与生命周期

接入 workflow worker、Outbox、Analytics Projection、Human Gate，形成 SCALE/REVISE/KILL。

完成定义不是“组件表存在”，而是：平台能用同一组件库生成 21 天和 90 天两个产品包，分别
通过编译检查，创建受控试点，读取反馈并产出可审计的新版本或停止决策。

## 9. 硬约束

- 组件库是产品主数据，不是硬编码 UI 卡片集合；
- Skill 是可评估、可版本化的工作能力，不是散落 Prompt；
- AI 可以设计和优化产品，但不能自动发布、付款、改价、改政策或写成长事实；
- 不做家庭总分、家庭排名、儿童诊断或未成年人自动化商业营销；
- 同一业务能力只保留一个 canonical Owner；不复活 `market_intelligence` 退役实现。
