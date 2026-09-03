---
id: AIFAMILY-IPD-001
title: AiFamily 按 IPD 重构的产品系统与研发运营蓝图
type: strategy
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# AiFamily 按 IPD 重构的产品系统与研发运营蓝图 V1

> 本文件把 AiFamily 从“34 个 UI + 若干后端域”重新组织为可持续经营的产品系统。
> IPD（Integrated Product Development）在这里不是增加审批，而是把市场、客户需求、
> 产品包、研发、验证、发布和生命周期放进同一条可追溯链路。

## 1. 为什么必须重构

当前四级功能分解书已经盘点出 9 个一级域、24 个二级能力群、58 个三级功能和 79 个四级
操作，但 4 级操作中“已实现可用”只有 11 项（13.9%）；PLAN、SERVICE、COMMUNITY 和
AI Runtime 仍有大量功能只有 UI 或骨架。继续逐屏补 UI 会产生三个问题：

1. **客户价值断裂**：页面很多，但每个页面没有明确的市场问题、目标客户和可验收价值。
2. **研发优先级漂移**：技术组件先行，主链、依赖、质量门禁和发布责任不清晰。
3. **数据无法复利**：事件、特征、推荐和交易没有统一的产品版本、实验假设与结果闭环。

因此，34 个 UI 必须降级为渠道投影；产品包、需求基线、版本和发布证据才是研发主线。

## 2. IPD 总体闭环

```text
市场管理 MM
  → VOC/场景/竞争证据
  → 产品机会与 MRD
  → 概念评审 CDCP（立项/否决）
  → 产品包/PRD/Charter
  → 计划评审 PDCP（范围/架构/成本/质量）
  → 跨职能 PDT 开发
  → 技术/业务/安全/合规验证
  → 发布评审 LDCP（灰度/回滚/运营准备）
  → GA 上线与经营
  → 生命周期复盘、版本演进或 EOL
```

每一个 Gate 都必须有输入、决策人、退出条件和证据。没有通过 Gate 的能力只能标记为
`CONCEPT`、`IN_DEVELOPMENT` 或 `PLANNED`，不能用静态页面或合成数据冒充已上线。

## 3. 产品线重组

### 3.1 六条产品线

| 产品线 | 目标客户/付款关系 | 核心问题 | 第一版产品包 | 主要事实 Owner |
|---|---|---|---|---|
| P1 Family Growth Core | 家庭；B2C | 家庭不知道从哪里开始，也无法持续行动 | 测评理解 → 假设确认 → 21/90 天旅程 → 今日行动 | family / assessment / journey |
| P2 Service Collaboration | 家庭、教师、机构；B2C/B2B2C | 个性化服务难组织、难交付、难验收 | FGCN 案件、任务、分派、交付、质量与补救 | service |
| P3 Commerce Relationship | 家长/付款方；主动表达服务需要后 | 课程、会员、产品和权益关系割裂 | 商品、会员、订单、支付、权益和退款 | commerce / membership |
| P4 Community Trust | 家庭与经审核伙伴；C2C 受控 | 经验无法安全分享，公开传播缺少撤回 | 私密动态、模板发布、审核、申诉、删除 | community / rights |
| P5 Principal & AI Runtime | 家庭、运营、服务人员 | AI 输出缺少上下文、溯源、人工边界 | Context、Principal、Model Gateway、Draft、Human Gate、Eval | intelligence / platform |
| P6 Platform & Operations | 内部运营、研发、合作伙伴 | 版本、实验、指标、事故和环境不一致 | Catalog、Feature、Experiment、Analytics、Release、Audit | platform / operations |

P1 是首要产品线，不是因为其他产品不重要，而是因为它产生后续服务、商业和长期关系所
需的真实需求证据。P2/P3/P4 不得绕过 P1 的情绪与成长闸门直接放大交易。

### 3.2 产品包（Product Package）标准

每个产品包必须有一份冻结的 `ProductCharter`，至少包括：

- 目标细分客户、付款方、使用者、数据访问者和服务受益者；
- 一个可验证的客户问题与场景，不以“增加页面”作为目标；
- MRD/VOC 证据、竞争替代、三区判断（同质/优势/独占）；
- PRD 需求集合、范围外清单、依赖、容量、成本和风险；
- 端到端业务流程、领域 Owner、数据对象、应用模块和外部适配器；
- 版本目标、质量指标、实验假设、灰度策略、回滚点和 EOL 条件。

## 4. 需求体系：从四级功能书升级为 IPD 需求基线

### 4.1 需求层级映射

```text
L1 业务域       → Product Line / 产品线
L2 能力群       → Capability / 能力包
L3 功能         → Feature / 可交付特性
L4 操作         → User Story + Command/Query + Acceptance Test
UI-01~UI-34     → 渠道投影标识，不是需求主键
```

建议使用稳定需求 ID：`IPD-{product}-{capability}-{feature}-{operation}`，例如：
`IPD-P1-JOURNEY-ACTION-CHECKIN`。UI 编号保留用于视觉和渠道回归，但不得承担业务事实、
接口语义或版本主键。

### 4.2 IPD 文档包

1. **MRD（Market Requirements Document）**：市场问题、客户分群、VOC、替代方案、商业机会。
2. **Product Charter**：产品边界、价值假设、目标指标、Owner、预算和 Gate 退出条件。
3. **PRD（Product Requirements Document）**：用户故事、规则、异常、权限、同意、文本和多模态需求。
4. **System Requirement Baseline**：服务/API、事件、数据对象、性能、可靠性、安全与环境等价。
5. **Solution/UX Design**：信息架构、交互状态、视觉令牌、可访问性、空态和错误态。
6. **Quality & Compliance Plan**：测试矩阵、删除/留存、Human Gate、红队、可观测性和回滚。
7. **Launch & Lifecycle Plan**：灰度、运营手册、SLO、培训、客户支持、版本冻结和 EOL。

需求只有同时绑定产品包、版本、Owner、验收测试和发布状态后，才算进入研发基线。

## 5. 跨职能团队与决策权

### 5.1 组织角色

- **IPMT（集成产品管理团队）**：决定产品组合、投资优先级、Gate 结论和停止/继续。
- **PDT（产品开发团队）**：产品经理、教研/领域专家、UX、架构、研发、数据、质量、合规、运营和财务。
- **领域 Owner**：拥有 Family、Assessment、Journey、Service、Commerce、Community 等事实与 Named Action。
- **Platform/AI Owner**：拥有 Identity、Consent、Audit、Outbox、Context、Model Gateway、Feature、Experiment。
- **Release Owner**：对版本清单、环境等价、灰度、回滚和上线后指标负责。

### 5.2 决策边界

- IPMT 决定“做什么、为谁做、何时停止”；不能绕过领域 Owner 直接改事实。
- PDT 决定“怎么做、如何验证”；不能把未验证方案写成当前真相。
- AI 可以生成 Perspective、Recommendation、Draft 和 HumanTask；不得替代业务确认。
- 财务指标可以进入商业经营分析；不得成为家庭排名或儿童推荐的隐式奖励函数。

## 6. Gate 与交付证据

### G0 市场机会 Gate（MM）

- 输入：客户问题、VOC、市场/竞争证据、目标分群、替代方案。
- 通过条件：问题可验证，有明确客户和业务价值，非单纯 UI 或模型炫技。
- 输出：MRD、机会 ID、假设、初始指标和 PDT。

### G1 概念 Gate（CDCP）

- 输入：MRD、三区判断、概念方案、风险、商业模型和数据边界。
- 通过条件：产品 Charter 被 IPMT 接受；范围外、红线和停止条件明确。
- 输出：ProductCharter、产品包版本 `v0.x`。

### G2 计划 Gate（PDCP）

- 输入：PRD、系统需求基线、架构/UX、依赖、成本、质量与合规计划。
- 通过条件：每个 L4 操作有 Command/Query、Owner、数据归属和验收测试；无孤立按钮。
- 输出：`RELEASE_PLAN`、资源承诺、版本范围和风险登记。

### G3 开发冻结 Gate（ADCP）

- 输入：代码、迁移、事件/接口契约、测试、监控和数据工厂。
- 通过条件：主链可运行；AI/支付/消息/模型均经适配器；迁移可回滚；不破坏既有 WIP。
- 输出：候选发布版本、变更清单、测试报告。

### G4 资格 Gate（LDCP）

- 输入：集成/E2E、性能、安全、删除、跨租户、可重放、环境等价和人工演练证据。
- 通过条件：关键路径达到 SLO；高风险动作有 Human Gate；失败可恢复；合成数据不冒充真实效果。
- 输出：`QUALIFIED` 或带阻断项的 `REJECTED`。

### G5 发布/经营 Gate（GA）

- 输入：灰度结果、指标、告警、客服与运营准备、回滚演练。
- 通过条件：小流量指标达到目标且 guardrail 未越界；可停止、降频、撤回和回滚。
- 输出：发布版本、实验分组、运营 Runbook、上线审计。

### G6 生命周期 Gate

- 每个版本必须有复盘、已知缺陷、成本/质量/客户价值变化和下一版决策。
- 低价值、不可维护或违反战略边界的能力进入 `RETIRED`/`EOL`，不得无限堆积。

## 7. 与五层架构的重新对齐

### 7.1 业务架构

业务主线从“页面清单”改为：市场机会 → 家庭需求 → 解决方案 → 交付 → 验收 → 关系/商业
结果。六条产品线是价值承载者；Family/Journey/Service/Commerce/Community 是事实边界。

### 7.2 流程架构

每个产品包同时绑定两条流程：

1. **客户价值流程**：N0-N8 家庭需求闭环、E0-E4 情绪到经济闸门；
2. **研发运营流程**：MM → CDCP → PDCP → ADCP → LDCP → GA → 生命周期。

客户流程节点没有对应产品需求、接口、事件、测试和运营责任时，不能进入版本基线。

### 7.3 数据架构

新增/冻结以下 IPD 数据对象：`MarketRequirement`、`ProductCharter`、`ProductRequirement`、
`ReleaseBaseline`、`MetricDefinition`、`Experiment`、`ExperimentAssignment`、
`FeatureSignal`、`QualityReport`、`LifecycleDecision`。它们是产品与研发治理事实，不能
取代业务域事实，也不能把 Projection 当写模型。

### 7.4 应用架构

应用层调整为：

- `ProductManagementApplication`：MRD、Charter、PRD、版本和 Gate；
- `ExperienceApplication`：候选、推荐、反馈、特征、实验和渠道投影；
- `GrowthApplication`：Assessment/Journey/Action/Outcome Named Action；
- `ServiceCollaborationApplication`：FGCN 案件、任务、交付和质量；
- `CommerceRelationshipApplication`：订单、支付、会员、权益；
- `OperationsGovernanceApplication`：指标、实验、发布、事故和复盘；
- `SharedApplicationKernel`：identity、authorization、consent、idempotency、transaction、audit、outbox。

### 7.5 技术架构

保留并继续建设事件驱动、Outbox、Analytics Projection、Feature Store、Experiment、
Principal、Context Engine、Model Gateway 和可观测性。技术组件必须由产品包和 Gate 驱动，
不能脱离客户场景独立扩张。

## 8. 指标体系

### 8.1 客户价值指标

- 首次被理解时间、测评完成率、假设确认率；
- 21/90 天行动采纳、暂停后恢复、家庭主动反馈；
- 服务交付准时率、验收率、返工/补救率；
- 家庭留存和关系质量的授权反馈。

### 8.2 技术与产品质量指标

- API p95、错误率、Outbox 延迟、Projection Lag、Feature Freshness；
- 推荐候选覆盖、策略拒绝率、实验分流一致性、回滚时间；
- 删除可验证性、跨租户拒绝率、人工升级闭环率。

### 8.3 商业经营指标

- 主动服务意向率、订单转化、续费、退款、毛利、履约成本和合作伙伴贡献。

停留时长和金额都可以采集并进入相应指标域，但必须带目的、粒度、同意、版本和环境；
不合成家庭总分、不做家庭/儿童排名，不把单一指标作为推荐或 AI 奖励目标。

## 9. 首个 IPD 版本：P1-V1 Family Growth Core

### 范围

`UI-02 → UI-03 → UI-05 → UI-09`：测评执行、假设解释与确认、旅程计划预览/确认、今日
行动、暂停/恢复、反馈和可重放投影。

### 必须交付

1. `IPD-P1-ASSESSMENT-*`、`IPD-P1-JOURNEY-*` 需求基线与 Product Charter；
2. Family/Consent/Assessment/Journey/Action 的正式 API、Named Action、事件、审计和 Outbox；
3. ExperienceGateway、Curator、Feature/Experiment 和 Analytics Projection 接入只读投影；
4. UI-02/03/05/09 的加载、空态、错误、拒绝、确认、暂停和删除状态；
5. SQLite 快速合同测试 + PostgreSQL 集成测试 + Web/E2E + 环境等价报告；
6. G4 之前不得把合成数据、AI Draft 或静态 UI 标记为真实成长结果。

### 暂不纳入

真实支付放大、跨家庭公开推荐、儿童营销、家庭排名、多 Agent 自主执行和无限期记忆。
这些不是“删功能”，而是必须由独立产品包、合规边界和发布 Gate 决策。

## 10. 后续产品版本

- **P1-V2**：21/90 天节奏、复盘、Outcome 证据、Feature Store 在线读取；
- **P2-V1**：FGCN ServiceCase/Task/Assignment/Delivery/Quality/Recovery；
- **P3-V1**：Product/Membership/Order/Payment/Entitlement，接商业闸门；
- **P4-V1**：Community 私密发布、人工审核、申诉、撤回与删除；
- **P5/P6**：Principal Release Bundle、AI Eval、ExperimentOps、AnalyticsOps、全球 Cell。

## 11. 执行纪律

- 任何新 UI 先补 MRD/Charter/PRD 映射，再写代码；
- 任何新增业务事实先登记 Domain Owner 和数据对象，再建表/接口；
- 任何 AI 能力先登记 Use Case、工具、知识、Schema、风险和 Human Gate；
- 任何发布必须有版本、迁移、测试、审计、回滚和环境等价证据；
- 每个版本结束后做 IPD 复盘，未达目标就缩范围、重做或停止，而不是继续堆功能。
