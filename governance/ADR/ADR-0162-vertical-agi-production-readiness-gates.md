---
id: ADR-0162
title: 垂直家庭成长 AGI 生产就绪阶段门
status: Proposed
owner: chief-architect
created: 2026-09-09
updated: 2026-09-09
---

# ADR-0162：垂直家庭成长 AGI 生产就绪阶段门

## 决策摘要

垂直家庭成长 AGI 不以“有一个生成接口”作为完成标准，而以一条可回放、可拒绝、可删除、可跨进程恢复的家庭成长闭环作为交付对象：

```text
家庭表达 / AssessmentResponse
  → ContextObservation
  → Perspective Draft
  → Guardian Calibration
  → Confirmed FamilyNeed
  → GrowthPath / Action Proposal
  → Outcome / Reflection
```

每一阶段必须通过对应的真实证据后才能进入下一阶段。开发组合、合成模型、内存账本和页面测试只能证明契约，不得升级为生产能力声明。

## 背景

当前仓库已经具备以下可复用基础设施：

- `backend/intelligence/model_gateway`：统一模型调用边界；
- `Context Engine` 与 `Growth Graph` 的 durable adapter；
- `DurableVerticalLedgerAdapter`：复用 Experience Ledger 保存 Draft、Guardian Decision、删除和回放；
- `/families/{family_id}/growth/ai-drafts`：canonical vertical HTTP surface；
- Web 首页到理解草案、校准和成长方向的浏览器路径。

但这些能力曾分别在开发组合、真实 PostgreSQL adapter、旧 Experience API 和浏览器 fixture 中出现，容易形成“局部通过、整体未接线”的错觉。因此需要一个独立的生产就绪判断框架，约束后续实现和汇报。

## 决策

### 1. 单一生产组合根

生产环境只能通过一个显式 `ProductionVerticalFamilyGrowthComposition` 安装 vertical runtime。该组合必须同时绑定：

1. 同一 `async_sessionmaker` 创建的 Context Broker 与 Experience Ledger；
2. 经过 Model Gateway admission 的模型实现；
3. 已发布且有适用范围的 Knowledge Registry；
4. 当前身份、Consent、Tenant/Family scope resolver；
5. Guardian Decision、Audit、Outbox 和删除语义；
6. 可被新进程重新构造的 scope factory。

组合根不得从环境变量偷偷制造 fallback，也不得把 `EvaluationLedger` 或开发 Context 作为生产依赖。

### 2. 阶段门

| 阶段 | 名称 | 必须证明 | 未通过时的状态 |
|---|---|---|---|
| G0 | 语义冻结 | `Fact / Perspective / Recommendation / Action` 分离；无家庭总分、排名、诊断 | `BLOCKED` |
| G1 | 原语可运行 | UNDERSTAND、MATCH_KNOWLEDGE、DESIGN_PATH、REFLECT 通过统一 Port | `EXPERIMENT` |
| G2 | Durable Draft | PostgreSQL 保存 Draft、provenance、context ref、knowledge ref，并能新会话 replay | `EXPERIMENT` |
| G3 | Guardian Calibration | ACCEPT、EDIT、REJECT、DEFER 幂等持久化；下一轮能读取校准 lineage | `EXPERIMENT` |
| G4 | Composition Root | production/staging/test 的显式组合均绑定 durable Context、Ledger、Consent 和 Gateway | `CANDIDATE` |
| G5 | 产品闭环 | 同一浏览器与同一 ref 完成表达→理解→校准→成长方向；两个家庭产生可解释差异 | `CANDIDATE` |
| G6 | 发布评审 | V-01～V-10 全部 hard gate 通过，含失败恢复、删除、跨 scope 拒绝和重启回读 | `RELEASE_CANDIDATE` |

只有 G6 可以进入生产评审；通过单元测试或 fixture 不得跳过阶段门。

### 3. 证据优先级

证据按以下顺序解释：

1. 同一 commit/ref 的真实 HTTP + PostgreSQL + 新进程 replay；
2. 同一 commit/ref 的浏览器行为和网络请求记录；
3. adapter / application 单测；
4. schema、ADR、registry 文档。

低等级证据不能替代高等级证据。特别是：

- 内存 ledger 不能证明跨进程持久化；
- 页面显示不同不能证明家庭上下文不同；
- fixture provider 不能证明真实模型供应商已接通；
- 旧 Experience API 通过不能证明 canonical vertical API 已接线。

### 4. 长期学习闭环

Guardian 的修改、拒绝、暂停和结果反馈都是版本化 evidence，不直接改写 Family Fact。下一轮生成必须显式携带：

- `feedback_refs`；
- `context_snapshot_ref`；
- `knowledge_ref` / `knowledge_version`；
- `lineage_ref`；
- `guardian_decision_ref`（如有）。

任何缺少上述 lineage 的输出都只能保持 `DRAFT`，不能被呈现为已确认成长方向。

## 验收矩阵

实现工作包必须至少提供以下 artifact：

| Artifact | 内容 |
|---|---|
| HTTP log | request、response、idempotency、scope、错误码 |
| SQL snapshot | Draft、Context、Decision、Feedback、Audit/Outbox 行 |
| restart proof | 进程 A 写入、进程 B 回读的命令与结果 |
| browser proof | URL、关键 DOM 状态、网络请求、console 错误 |
| negative proof | 跨家庭、撤回 Consent、删除、重复提交、Provider failure |
| provenance proof | model/prompt/schema/knowledge/context 的可追溯引用 |

缺少任一 hard gate 时，汇报必须使用 `BLOCKED`、`EXPERIMENT` 或 `CANDIDATE`，不得使用“已完成生产能力”。

## 与现有设计的关系

- 本 ADR 约束并细化 `ADR-0158` 的生产方式，不改变其“GrowthPath 是产品主对象”的决策。
- `docs/11_delivery/AGI_VERTICAL_EVALUATION_SPEC.md` 的 V-01～V-10 是本 ADR 的验收明细；本 ADR 只规定阶段门和证据等级。
- 本 ADR 不新增 Domain、事实库、Identity、Consent、Audit 或 Model Gateway。
- 34 个旧 UI 继续作为兼容入口；新增体验必须由同一 `GrowthPathNode` contract 呈现。

## 当前判断

截至本 ADR 创建时：

- G0～G3 已有代码和测试证据；
- G4 有显式 composition contract，但默认生产启动接线仍未完成；
- G5 已有浏览器黄金路径，但双家庭 durable 差异和完整 V-01～V-10 artifact 尚未齐全；
- G6 未通过，因此本 ADR 保持 `Proposed`，不宣称生产就绪。

