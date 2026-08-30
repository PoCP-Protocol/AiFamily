---
id: IPD-AI-PRODUCT-FACTORY-001
title: AiFamily AI 产品工厂：21 天成长营与 90 天成长计划
type: product
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# AiFamily AI 产品工厂 V1（Web UI）

> 本产品只做 Web UI 工作台。21 天成长营、90 天成长计划是由工作台设计并发布的产品包，
> 不是本项目内置的移动端页面。Web UI 面向产品、教研、服务、质量、合规和运营角色。

## 1. 产品不是固定页面，而是平台生成的可验证产品包

21 天成长营、90 天成长计划，以及后续的家庭沟通、学习习惯、手机管理等产品，都由同一
个 `AI Product Factory` 设计。产品工厂接收市场证据、家庭需求、服务供给和约束，生成
带版本、成本、验证指标和发布条件的 `ProductPackage`，而不是直接生成一个页面。

```text
MarketSignal / VOC
  → Opportunity + GrowthProblem
  → AI Product Factory
  → ProductConcept candidates
  → ProductCharter + RequirementBaseline
  → ServiceBlueprint + DeliveryCapacity
  → Micro Pilot
  → Evidence / Outcome / Quality
  → Scale / Revise / Kill
```

这条链同时满足 IPD 的跨职能 Gate 和公开资料中常被归纳的 SHEIN 式“需求感知—小批测试—
快速迭代—数据回流”机制。这里借鉴的是反馈速度和供给编排原则，不假设或复制其私有算法、
供应商协议或经营数据。

## 2. 产品工厂输入与输出

### 输入

- `Opportunity`、`GrowthProblem`、已审核的证据引用和目标细分场景；
- 家庭授权的需求上下文、可用服务能力、教师/机构供给、时间和交付约束；
- 三区定位：同质区、优势区、独占区候选；
- 产品线、预算上限、风险等级、合规目的、留存期限和禁止事项；
- 历史产品试点的匿名化结果、质量事件、成本和反馈。

### 输出

`ProductPackage` 至少包含：

- `ProductCharter`：目标客户、问题、价值假设、范围内/范围外、Owner；
- `ProductConcept`：产品形态、持续时间、阶段结构、交付方式和替代概念；
- `RequirementBaseline`：稳定需求 ID、用户故事、验收测试、接口/事件、数据 Owner；
- `ServiceBlueprintVersion`：角色、触点、前后台动作、SLA、容量和补救路径；
- `ExperimentPlan`：小批范围、实验分层、主要指标、guardrail、停止/升级规则；
- `ReleaseBaseline`：冻结的内容、知识、模型、提示词、配置、迁移、Runbook 和回滚点。

AI 只能先产生 `Perspective / Insight / Hypothesis / Recommendation / Draft / HumanTask`。
事实、家庭计划、服务分派、价格、支付、对外发布必须由领域 Owner 和 Named Action 提交。

## 3. SHEIN 式机制在家庭成长产品中的翻译

| 机制 | 家庭成长平台实现 | 不能照搬的部分 |
|---|---|---|
| 需求感知 | MarketSignal、VOC、家庭主动反馈、服务人员观察 | 不采集与目的无关的儿童敏感信息 |
| 快速试款 | 生成多个 7/21 天产品候选，先做小范围试点 | 不用 AI 草案冒充真实成长效果 |
| 小批生产 | 受控家庭/服务组、明确授权、容量上限 | 不做公开儿童实验、不跨租户混用数据 |
| 实时回流 | 任务采纳、暂停/恢复、服务质量、主动反馈、成本 | 不以停留时长或金额合成家庭总分 |
| 快速补货 | 对有效产品生成新版本、扩展服务槽位和内容组件 | 扩大前必须经过 Gate、合规和容量检查 |
| 低效下架 | 低价值、质量差、成本失控的产品进入 RETIRED | 不静默删除历史证据，保留可审计版本 |

平台追求的是“学习速度”，不是无限上新。每个产品候选都有生命周期预算、最大试点规模、
停止条件和回滚方案。

## 4. 两类首发产品的产品族模型

### 4.1 21 天成长营（Micro Product）

定位：用较短周期验证一个具体成长假设，目标不是给家庭打分，而是帮助家庭完成一轮
“理解—尝试—反馈—调整”。

```text
Day 0  需求澄清与目标确认（家长主动确认）
Day 1-3 共同理解：解释假设、选择可暂停行动
Day 4-14 小步行动：每日/隔日行动，允许暂停和替代路径
Day 15-19 服务协同：必要时升级给教师/专家
Day 20-21 复盘：反馈、证据整理、下一步建议
```

必备字段：`hypothesis_id`、`duration_days=21`、行动节奏、暂停规则、人工升级条件、
成功指标、guardrail、服务容量、退出和删除路径。不得输出“完成即改善”的疗效承诺。

### 4.2 90 天成长计划（Scale Product）

定位：将已通过 21 天试点的产品能力扩展为三阶段产品，但每一阶段仍可独立暂停、复盘和
回滚。

```text
Phase A  Day 1-21  理解与启动
Phase B  Day 22-60 稳定行动与服务协同
Phase C  Day 61-90 迁移、复盘与下一周期决策
```

90 天计划只能引用已通过小批验证的组件、知识和服务蓝图版本。新组件必须先以 7/21 天
试点进入产品族，不能因为进入长期计划就跳过验证。

## 5. AI 产品设计闭环

### 5.1 Discover：发现机会

AI 在 Model Gateway 上对证据、VOC 和反馈做去重、聚类、趋势、矛盾和机会排序，生成
`OpportunityRecommendation`。证据引用必须来自已发布知识/证据包，禁止凭空生成市场事实。

### 5.2 Design：生成产品候选

AI 同时生成多种持续时间、交付方式和成本假设，比较同质/优势/独占区定位，并编译为
`ProductConcept` 草案。生成必须带模型、提示词、上下文快照、知识版本和置信度。三区不是
展示标签，而是资源策略：同质区优先速度和成本，优势区优先服务质量和场景采纳，独占区候选
优先长期证据资产与可复制性验证。

### 5.3 Simulate：验证可交付性

确定性编译器检查需求覆盖、服务容量、SLA、风险、合规、数据目的、事件契约、回滚和成本。
AI 可生成反例、边界场景和红队用例；模拟结果不能替代真实家庭试点。

### 5.4 Pilot：小批试点

由 workflow worker 创建受控试点，记录授权范围、分组、版本、人工责任人、指标、guardrail
和回滚动作。AI 负责实时解释信号、发现异常、提出调参建议，但不自动扩大样本或改变家庭事实。

### 5.5 Decide：扩展、改版或停止

IPMT/PDT 依据 `PilotRun` 输出做三选一：

- `SCALE`：冻结新版本，增加服务容量或开放范围；
- `REVISE`：保留证据，生成新 Concept/Blueprint/Experiment 版本；
- `KILL`：停止试点，撤下入口，保留审计记录和失败原因。

决策还要记录三区迁移结果：同质区只有证明场景采纳、服务质量或交付效率的可重复优势后，
才可进入优势区；优势区只有证明优势来自可治理、可复用且不侵犯隐私的知识/关系/蓝图资产，
才可进入独占区候选。安全、合规、容量或客户价值 guardrail 触发时，任何区域都必须
`REVISE` 或 `KILL`。

## 6. 产品工厂的最小数据对象

```text
ProductPackage
  ├─ charter_id / concept_id / requirement_baseline_id
  ├─ blueprint_version_id / verification_plan_id
  ├─ pilot_policy_id / release_baseline_id
  ├─ target_scenario / duration_days / zone
  ├─ delivery_capacity / unit_cost_assumption
  ├─ success_metrics / guardrails / stop_conditions
  └─ status: DRAFT | PILOT | QUALIFIED | RELEASED | RETIRED
```

对象只管理产品决策和版本，不拥有 Family、Journey、ServiceCase、Order 或 Outcome 事实。
Web UI 只展示这些事实的授权投影，不在前端复制写模型。
这些事实仍由对应业务域写入，产品工厂通过端口读取只读投影，并通过事件订阅结果。

## 7. Gate 规则

- **G1 概念**：至少 3 个候选方案、一个明确问题、证据引用、三区定位和失败条件；
- **G2 计划**：21 天产品的每个 L4 操作都有需求、Owner、接口和验收测试；90 天产品的每个
  阶段都有退出条件、容量和暂停规则；
- **G3 开发**：产品组件、知识、提示词、模型和服务蓝图均可追溯、可重放；
- **G4 资格**：通过功能、服务容量、安全、删除、跨租户、AI Eval 和人工升级测试；
- **G5 发布**：小流量开放、guardrail 未越界、运营和回滚 Runbook 已演练；
- **G6 生命周期**：以客户价值、质量、成本和安全结果决定扩展、改版或停止。

任何 Gate 不通过，产品仍是 Draft/Pilot，不得在前端显示为正式可用成长计划。

## 8. 开发顺序

1. **P0 产品目录与契约**：登记 ProductPackage、Duration、Experiment、Gate 和状态机；
2. **P1 AI 设计器**：经 Model Gateway 生成 21 天/90 天候选和完整 provenance；
3. **P2 编译与试点**：接入 design_copilot、workflow worker、Human Gate、Outbox；
4. **P3 真实闭环**：接入 Journey/Service/Outcome 只读投影，建立 SCALE/REVISE/KILL 决策；
5. **P4 产品族扩展**：从成长营扩展到家庭沟通、学习习惯等场景，复用同一产品工厂。

首个验收目标不是“有一个 21 天页面”，而是：给定一组已授权证据，平台能生成两个候选
产品包，完成 Gate、创建受控试点、接收反馈，并生成可审计的新版本或停止决策。

## 9. 约束

- 不做家庭总分、家庭排名或儿童商业画像；
- 不让 AI 输出自动成为家庭事实、服务订单、付款或发布状态；
- 不让 AI Runtime 直接访问业务仓储或模型供应商；
- 不使用停留时长、金额等单一指标作为家庭成长价值或 AI 奖励函数；
- 不把“产品生成能力已开发”与“21 天/90 天真实效果已证明”混为一谈。
