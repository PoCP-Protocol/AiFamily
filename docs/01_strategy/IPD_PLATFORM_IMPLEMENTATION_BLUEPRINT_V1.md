---
id: IPD-PLATFORM-IMPLEMENTATION-001
title: AiFamily IPD 平台实现蓝图
type: strategy
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# AiFamily IPD 平台实现蓝图 V1

本蓝图把 IPD（Integrated Product Development）从管理口号转成可执行的平台设计。它补充
`AIFAMILY_IPD_PRODUCT_SYSTEM_REDESIGN_V1.md` 的产品线和 Gate 定义，重点回答：平台要保存
什么、谁可以作决定、AI 在每个阶段做什么、以及如何从当前代码渐进迁移。

## 1. 设计结论

平台的主对象不再是页面或单次 AI 对话，而是一个可版本化的 `ProductInitiative`：

```text
ProductInitiative
  ├─ MarketEvidence / VOC
  ├─ RequirementBaseline
  ├─ ConceptSet → SelectedConcept
  ├─ ArchitectureBaseline
  ├─ VerificationPlan / VerificationRun
  ├─ PilotRun
  ├─ ReleaseBaseline
  └─ LifecycleDecision / ChangeRequest
```

已有业务域仍然是事实 Owner。IPD 对象只管理产品与研发决策、版本和证据，不复制
`family`、`journey`、`service`、`commerce` 或 `community` 的业务事实。当前产品设计链
`MarketSignal → CustomerInsight → Opportunity → GrowthProblem → GrowthHypothesis →
GrowthStrategy → ProductConcept` 继续保留，新增对象以引用和快照方式接入。

## 2. IPD 阶段与平台能力映射

| 阶段 | Gate | 平台输入 | 平台输出 | 当前落点 |
|---|---|---|---|---|
| 市场管理 | G0/MM | 市场信号、VOC、竞争替代 | `ProductInitiative`、机会假设 | `market_insight`、`product_intelligence` |
| 概念决策 | G1/CDCP | MRD、三区判断、概念候选 | `ProductCharter`、入选概念 | `ProductConcept` + AI Runtime |
| 计划决策 | G2/PDCP | PRD、依赖、成本、合规计划 | `RequirementBaseline`、版本范围 | 待新增 IPD application |
| 开发决策 | G3/ADCP | 架构、代码、事件、迁移、测试 | `ArchitectureBaseline`、候选发布 | `ProductDefinition`、`ServiceBlueprintVersion` |
| 资格决策 | G4/LDCP | 集成、性能、安全、AI Eval、删除演练 | `VerificationRun`、`PilotRun` | compiler/simulation 逐步补齐 |
| 发布决策 | G5/GA | 灰度、SLO、回滚、运营准备 | `ReleaseBaseline`、发布事件 | workflow worker + release projection |
| 生命周期 | G6 | 经营结果、质量、反馈、成本 | `LifecycleDecision`、`ChangeRequest` | analytics/outbox projection |

Gate 是决策记录，不是审批按钮。每个 Gate 必须保存 `decision_id`、输入版本、证据引用、
决策人/团队、结论、阻断项、有效期和回滚动作；没有 Gate 证据只能停留在草案或开发态。

## 3. 核心对象与不变量

### 3.1 ProductInitiative

`id`、租户范围、产品线、目标客户/付款方/使用者、问题陈述、Owner、生命周期状态和当前
Gate。一个 Initiative 可有多个概念，但同一时间只能有一个 `SelectedConcept`。

### 3.2 RequirementBaseline

保存稳定需求 ID（`IPD-{product}-{capability}-{feature}-{operation}`）、用户故事、验收测试、
数据 Owner、接口/事件、范围外清单、依赖和版本。冻结后不可原地编辑，只能产生新版本。
UI-01~UI-34 仅作为渠道投影标识，不得作为业务主键。

### 3.3 ArchitectureBaseline

保存应用边界、领域 Owner、数据对象、事件、适配器、环境、SLO、安全/合规约束和成本假设。
必须明确 `backend/intelligence` 只经 Model Gateway，不直接持久化业务事实；业务域不直连
模型供应商。

### 3.4 VerificationRun / PilotRun / ReleaseBaseline

验证运行记录测试矩阵、输入版本、环境、结果、失败和重放信息；试点运行记录范围、实验分组、
guardrail、人工升级和回滚；发布基线冻结代码、迁移、配置、模型/知识版本、Runbook、SLO
和回滚点。发布对象不拥有业务事实，只引用其版本。

## 4. 状态机与 Gate 规则

```text
DRAFT → G0_READY → G1_READY → G2_READY → IN_DEVELOPMENT
      → G3_READY → QUALIFIED → PILOT → RELEASED
      → LIFECYCLE_REVIEW → RELEASED | RETIRED
```

任何逆向移动都产生 `ChangeRequest`，不允许静默回写历史版本。Gate 规则采用纯函数编译，
至少检查：

- 需求是否有客户证据、Owner、验收测试、数据权限和范围外清单；
- 概念是否有替代方案、三区定位、价值假设、成本与停止条件；
- 架构是否有领域 Owner、事件/接口契约、租户边界、迁移和回滚；
- 验证是否覆盖 happy path、拒绝、删除、跨租户、重放、性能和 AI Eval；
- 发布是否有灰度、监控、人工升级、Runbook、回滚和环境等价证据。

## 5. 跨职能决策模型

| 决策 | 负责团队 | 必须咨询 | AI 可做 | AI 不可做 |
|---|---|---|---|---|
| 做不做 | IPMT | PDT、财务、合规 | 汇总证据、比较机会、提出建议 | 私自立项或停止产品 |
| 做什么 | Product Owner/PDT | 领域 Owner、UX、客户代表 | 生成 MRD/PRD 草案、发现冲突、排序需求 | 把猜测写成需求事实 |
| 怎么做 | 架构/工程 PDT | AI、数据、安全、运营 | 生成方案、接口草案、测试矩阵、风险清单 | 绕过领域 Owner 写业务事实 |
| 能否发布 | Release Owner + Gate 评审 | QA、合规、运营、IPMT | 编译证据、解释失败、推荐灰度 | 自主发布、付款、改价、改政策 |

AI 可在整个 IPD 链路高自治地完成检索、聚类、分析、方案生成、优先级排序、验证设计和
结果解释。AI 输出统一标记为 Perspective、Insight、Hypothesis、Recommendation、Draft
或 HumanTask；涉及事实变更、预算、价格、政策、对外承诺和发布的动作必须经 Named Action
与相应 Owner。这样限制的是高影响写入，不是限制 AI 的分析能力。

## 6. 三区方法论的 IPD 化

- **同质区**：优先复用标准组件和现成服务；AI 负责差距扫描、质量监控和成本比较。
- **优势区**：围绕家庭场景、服务交付和情绪/成长节奏形成可验证组合；AI 负责场景合成、
  服务蓝图、实验分层和反馈解释。
- **独占区候选**：由证据驱动寻找难以复制的知识、关系和交付能力；AI 负责发现信号、生成
  假设、设计验证并持续更新置信度，但是否投资由 IPMT 决定。

三区标签进入 `ProductCharter` 与 `RequirementBaseline`，不能只留在营销文档里；每个独占区
候选都必须有验证指标、保护边界和失败后的退出策略。

## 7. 分阶段实施

### IPD-P0：基线与对象目录

登记产品线、能力、Use Case、Domain Owner 和指标；冻结术语；禁止复活已退役的
`market_intelligence` 领域或直接搬运旧仓库实现。

### IPD-P1：需求基线与 Gate Compiler

在 `product_intelligence` 旁新增 IPD application/contracts，先实现不可变的需求版本、
证据引用、Gate 纯函数和决策审计；不先建大而全的 UI。

### IPD-P2：概念到架构

把 `ProductConcept`、`ProductDefinition`、`ServiceBlueprintVersion` 以版本快照接入
ArchitectureBaseline；为每个组件补 Domain Owner、接口契约、SLO、成本和回滚信息。

### IPD-P3：验证、试点与发布

将 compiler/simulation 从桩替换为可重放的 VerificationRun；由 workflow worker 编排
试点和 ReleaseBaseline，所有外部动作通过 Named Action。

### IPD-P4：生命周期经营

接入 Outbox/Analytics Projection、Feature/Experiment、服务质量和商业结果；用
`LifecycleDecision` 驱动继续、缩小、重做、迁移或 EOL。

## 8. 首个可交付纵向切片

首版只选 Family Growth Core：`UI-02 → UI-03 → UI-05 → UI-09`。G0-G2 先完成 MRD、Charter、
需求基线和架构基线；G3-G5 再完成 Assessment/Journey/Action 的正式 API、事件、审计、
验证和灰度。支付放大、公开社区推荐、儿童商业画像、家庭总分/排名不属于该切片。

验收标准：任何 L4 操作都能追溯到需求、Command/Query、领域 Owner、测试、事件、版本和
发布状态；AI 草案不能伪装成事实；发布可停止、降频、撤回和回滚。

## 9. 当前差距与完成定义

当前平台已具备市场洞察、产品概念/定义、服务蓝图、AI Model Gateway、知识登记和部分
编译检查，但还没有完整的 RequirementBaseline、Gate 决策持久化、VerificationRun、PilotRun
和 ReleaseBaseline。故本次设计完成不等于 IPD 已上线；只有 P0-P3 代码、测试、审计和环境
等价证据完成后，才可将 ADR-0035 从 `proposed` 提升为正式运行规则。
