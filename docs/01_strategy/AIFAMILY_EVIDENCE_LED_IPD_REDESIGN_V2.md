---
id: AIFAMILY-IPD-002
title: AiFamily 证据驱动的 IPD/PDM/PLM Web 平台重设计
type: strategy
status: draft
version: 0.2
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# AiFamily 证据驱动的 IPD/PDM/PLM Web 平台重设计 V2

## 0. 设计纪律：先证据，再决策

本版本纠正前一版可能出现的主观推断。所有设计内容分为三类：

### A 类：已验证事实

- 仓库正式后端是 Python/FastAPI/SQLAlchemy/PostgreSQL，AI Runtime 位于
  `backend/intelligence/`；
- `product_intelligence` 是产品概念、组件、Pattern、ProductDefinition 和三区评估的
  canonical 领域；`market_intelligence` 已降级为退役空壳；
- 现有三区理论定义为同质区、优势区、独占区候选；
- 现有 ProductComponent/ProductDefinition 字段已扩展为可承载教育产品规格，并有契约测试；
- 当前主要代码链是 MarketSignal → CustomerInsight → Opportunity → GrowthProblem →
  GrowthHypothesis → GrowthStrategy → ProductConcept；
- 当前 Web 产品工作台尚未形成完整业务 API、组件 Catalog API、Gate 持久化和 PLM 发布闭环。

### B 类：已明确的产品约束

- 本产品只做 Web UI 工作台；
- 21 天成长营、90 天成长计划必须由平台设计出来，而不是写死为页面；
- AI 要覆盖洞察、设计、组合、验证和迭代，不能被限制为末端摘要；
- 家庭教育产品必须遵守同意、最小必要、人工复核、不可自动写事实和未成年人商业边界；
- 产品三区理论必须进入 IPD/PDM/PLM 决策，而不是只做展示标签。

### C 类：待验证假设

- 某个竞品是否提供长期家庭上下文、真人协同或个性化计划；
- 家庭是否愿意连续参与 21 天或 90 天产品；
- 哪些指标能预测家庭主动采纳和服务质量；
- 哪些组件能形成真正难复制的独占区候选资产；
- 21 天到 90 天的升级比例、成本和安全阈值。

C 类内容不得直接进入 `ProductCharter` 的成功事实，只能进入 `Hypothesis` 和
`ExperimentPlan`，直到有可引用证据。

## 1. 产品定位：Web 产品设计与经营操作系统

Web UI 面向产品经理、教研/服务设计师、AI 管理员、质量、合规和运营人员，提供六个工作台：

1. **Demand Studio**：家庭需求、客户之声、服务问题和需求假设；
2. **Market Insight**：需求的外部验证、竞争替代、趋势和机会分析；
3. **Product Studio**：Charter、概念候选、三区决策和需求基线；
4. **Component/Skill Library**：组件、Skill、Pattern、兼容矩阵和版本；
5. **Pilot & Gate Board**：编译、验证、小批试点、Gate 证据和决策；
6. **PLM Console**：发布、暂停、回滚、反馈、变更、成本和退役。

该产品不是家庭端 App，也不直接写 Family、Journey、ServiceCase、Order 或 Outcome 事实。

## 2. 需求优先的 IPD 主链

```text
家庭需求 / 客户之声 / 服务问题
  → DemandFrame（需求边界、角色、场景、痛点、证据）
  → RequirementHypothesis（要解决什么、如何验收）
  → MarketInsight（规模、替代、竞争、趋势、支付关系验证）
  → Opportunity（是否值得投资）
  → ConceptSet（多个产品概念）
  → ProductPackage（组件 + Skill + Blueprint + 成本/SLA）
  → Micro Pilot（7/21 天小批验证）
  → Scale Product（90 天扩展产品）
  → Lifecycle（SCALE / REVISE / KILL）
```

市场洞察服务于需求，不制造需求。若需求没有可信来源，AI 只能生成待访谈问题，不能直接
生成正式产品。

## 3. 竞品分析：成为证据管道，不是主观排名

### 3.1 竞品范围

每个竞品必须先标记类别，不允许把不同商业模型混在一张排名表里：

- **家庭教育内容/课程产品**：内容库、课程计划、学习路径；
- **家庭成长/亲子关系产品**：家庭目标、互动、计划、陪伴或咨询；
- **AI 教育/陪练产品**：生成式辅导、对话、评估或个性化练习；
- **真人服务网络**：教师/专家、预约、交付、质量和补救；
- **平台基础设施**：内容生产、实验、推荐、供应和生命周期工具；
- **替代方案**：线下咨询、家长社群、短视频、搜索和自建表格。

SHEIN 不作为家庭教育直接竞品，而作为“高频需求感知、小批测试、快速回流、滚动扩展”
的产品运营机制参考；任何具体供应链、算法或经营数字都必须另取一手证据。

### 3.2 竞品证据卡

Web 工作台中的每个竞品都必须有一张不可变版本证据卡：

```text
competitor_id / category / region / observed_at
target_customer / payer / core_problem / product_duration
component_model / human_service / ai_role / experiment_loop
pricing_or_access / retention_signal / safety_boundary
source_refs / evidence_quality / confidence / analyst
```

证据质量分为 `PRIMARY`（官方产品、条款、帮助文档、监管披露）、`SECONDARY`（可信行业
研究）和 `UNVERIFIED`（待核验访谈/推测）。只有 PRIMARY/SECONDARY 且有时间戳的字段，
才能影响 G0/G1 决策；`UNVERIFIED` 只能生成研究任务。

### 3.3 竞品比较维度

平台不计算“综合竞品分”，也不按竞品排名。比较的是可验证维度：

- 需求覆盖：解决的家庭问题和排除的问题；
- 产品结构：单次内容、短周期计划、长期计划、服务协同；
- 组件复用：是否有可观察的模块、阶段、版本和组合；
- AI 自治：AI 做分析、生成、执行还是只做摘要；
- 反馈闭环：是否可观察到小批试验、指标回流和版本迭代；
- 交付能力：真人角色、容量、SLA、质量和补救；
- 家庭权益：暂停、退出、删除、解释和人工复核；
- 商业关系：付款方、受益人、推荐方式和未成年人边界；
- 证据强度：来源、时间、可重复观察和未知项。

输出是 `CompetitorEvidence`、`GapHypothesis` 和 `ExperimentRequest`，不是一句“我们比
竞品更好”。

## 4. 产品三区理论的执行化

三区分类由现有 `product_intelligence` 三区评估与策略版本产生，Web UI 只展示可追溯结果。

| 区域 | IPD 立项 | PDM 组件 | PLM 经营 |
|---|---|---|---|
| 同质区 | 证明基本需求、替代方案和成本可接受 | 复用、标准化、少变体 | 快速试点；无差异即停止或外采 |
| 优势区 | 证明家庭场景、服务或交付有可重复优势 | 组合 AI Skill、服务、质量和蓝图 | 按采纳、质量、成本和复购意向扩展 |
| 独占区候选 | 证明存在长期可积累且合规的资产假设 | 上下文、知识、关系、干预、蓝图和反馈 | 长期投资，但持续检查可复制性、删除和安全 |

产品包必须声明主导区、三区组件构成、竞争证据、优势假设和退出规则。区域可迁移，但每次
迁移都要有新证据和 Gate 决策；不允许因为 AI 使用了某个模型就声称进入独占区。

## 5. 家庭教育产品工厂

### 5.1 ProductPackage

`ProductPackage` 是 Web UI 设计的最小发布单元，绑定：

- 一个 `DemandFrame` 和至少一个需求假设；
- 市场/竞品证据卡及其时间戳；
- 一个主导三区和可解释的价值假设；
- 组件、Skill、Pattern、Blueprint 的版本引用；
- 21 天或 90 天的阶段、暂停、人工升级和退出规则；
- 服务容量、SLA、成本假设、指标、guardrail 和停止条件；
- 验证、试点、发布和回滚版本。

### 5.2 产品生成

AI 在 Model Gateway 上生成多个候选：不同周期、服务密度、组件组合和成本假设。组合器只
连接契约兼容的组件；编译器检查输入/输出、责任、容量、合规、版本和回滚。AI 生成的是
Draft/Recommendation，IPMT/PDT 选择概念并提交 Gate。

### 5.3 21 天与 90 天关系

- 21 天是需求假设的 Micro Product，用于验证理解、行动、反馈和服务协同；
- 90 天是已经通过 7/21 天验证的组件和蓝图的 Scale Product；
- 90 天新增组件必须重新进入小批试点，不能用长期周期绕过验证；
- 任何结果只能作为 Outcome 证据或 Perspective，不能自动生成诊断、排名或成长结论。

## 6. PDM 组件与 Skill 设计

组件必须有输入、输出、前置、禁用、角色、证据、知识、容量、SLA、成本、指标、guardrail、
暂停、回滚、Skill 和人工闸门引用。Skill 必须有 input/output schema、工具白名单、知识绑定、
评估集、版本和人工交接。

首批组件：需求澄清、假设解释、目标确认、今日行动、暂停/恢复、反馈采集、周复盘、教师
升级、服务预约、质量验收、21 天编排、90 天编排。

首批 AI Skill：发现家庭问题、解释假设、组合成长产品、编译服务蓝图、设计小批试点、
解释试点反馈、准备生命周期变更。

## 7. PLM 生命周期

```text
DRAFT → REVIEWED → PILOT → QUALIFIED → RELEASED
  ↑                    ↓          ↓
  └──── REVISE ←───────┴── PAUSE / ROLLBACK
                         ↓
                       RETIRED
```

生命周期事件必须引用产品版本、组件版本、Skill/知识/模型版本、指标快照、操作者和决策
证据。已执行家庭计划永远引用原冻结版本；新设计只能创建新版本。

## 8. Web UI 的第一条真实闭环

第一条闭环不是“展示一个 21 天计划”，而是：

1. 产品人员在 Demand Studio 录入一个家庭需求和来源；
2. AI 生成需求澄清问题和市场/竞品研究任务；
3. 研究结果进入证据卡，形成需求与市场洞察基线；
4. AI 生成多个 21 天产品候选，标记三区和未知项；
5. 编译器检查组件、Skill、容量、风险、指标和回滚；
6. Gate Board 由责任人作出 GO/NO-GO；
7. Pilot Ops 创建受控小批试点；
8. PLM Console 依据反馈生成 SCALE/REVISE/KILL 建议和下一版本草案。

## 9. 开发优先级与验收

- **P0**：DemandFrame、CompetitorEvidence、ProductPackage、Component/Skill Catalog 契约；
- **P1**：Web Demand Studio、Market Insight、Product Studio 只读/草案流程；
- **P2**：组件兼容编译器、三区 Gate、AI 候选组合；
- **P3**：Pilot Ops、PLM 事件、反馈投影、SCALE/REVISE/KILL；
- **P4**：与 Journey/Service 的已发布 Blueprint 投影接线。

完成定义：给定一个有来源的家庭需求，平台能生成带竞品证据、三区定位、组件/Skill 版本、
验收指标和停止条件的 21 天产品候选；通过 Gate 后能创建受控试点，并在试点结束后生成可
审计的 90 天升级、改版或停止建议。没有这些证据，Web UI 只能显示为 Draft。
