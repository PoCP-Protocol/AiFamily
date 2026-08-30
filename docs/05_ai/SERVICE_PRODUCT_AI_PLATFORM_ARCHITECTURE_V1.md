---
id: AI-SERVICE-PRODUCT-ARCHITECTURE-002
title: 三区方法论服务产品 AI 平台架构设计 V1
type: specification
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# 三区方法论服务产品 AI 平台架构设计 V1

> 本设计是在 2026-08-30 对系统真相文档、治理登记和当前代码反向核对后的设计稿。
> 它先冻结边界和第一条可交付切片，不把尚未实现的能力描述成已完成能力。正式升格
> 为 canonical 前，需要产品、服务、AI 治理和合规负责人评审本文件及 ADR-0029。

## 1. 设计结论

服务产品 AI 平台（SPD-AI）不是家庭端聊天功能，而是把“家庭问题/主要矛盾”转成
“可验证、可交付、可复用服务产品”的内部设计与治理工作台。平台的核心闭环是：

```text
三区证据 → 问题与主要矛盾 → 组件/模式 → 服务产品定义
       → 确定性编译 → 合成模拟/红队 → 人工发布
       → Service 运行时冻结消费 → 交付质量反馈 → 新版本候选
```

三个边界必须同时成立：

1. `product_intelligence` 是产品设计真相；`service` 是交付事实真相。
2. `backend/intelligence` 可以完成从证据整理、洞察、机会排序到验证方案的完整分析闭环，
   产物仍以 Perspective、Insight、Hypothesis、Recommendation、HumanTask 表达，不直接写业务事实。
3. 发布、回滚、服务案件创建、任务分派、验收和权益动作都必须通过业务域 Named Action 与人工闸门。

## 2. 三区方法论如何变成产品决策规则

| 区域 | 平台策略 | AI 角色 | 交付门槛 |
|---|---|---|---|
| 同质区 | 复用成熟能力，控制成本，不建设独有复杂度 | 只做检索、摘要和草案 | 通过通用安全/合规检查即可 |
| 优势区 | 围绕真人 + AI 协同把响应、履约、质量做深 | AI 可完成洞察、机会排序、方案编排和运营分析；高影响动作由人确认 | 必须有责任人、SLA、人工接管和质量证据 |
| 独占区候选 | 累积 Family Context、Growth Graph、Intervention Engine、Blueprint Library | AI 主动发现、组合并验证能力候选，人工确认对外承诺 | 必须可追溯、可版本化、可删除、可回放，且模拟不能冒充疗效 |

服务产品平台只承接优势区和独占区候选的设计能力。同质区能力可以作为组件被引用，
但不应成为平台的战略数据沉淀或模型训练目标。`primary_contradiction_ref` 是从
“问题”进入“方案”的必填设计输入；它不是家庭评分，也不是诊断结论。

## 3. 当前真实状态与目标状态

### 3.1 已存在且可复用

- `backend/domains/product_intelligence/domain/entities.py`：已有
  `GrowthProblem`、`GrowthHypothesis`、`ContradictionModel`、`ValueArchitecture`、
  `GrowthStrategy`、`ProductConcept`、`ProductComponent`、`ProductPattern`、
  `ProductDefinition`、`ServiceBlueprintVersion`。
- `backend/domains/product_intelligence`：已有应用命令/查询、内存与 SQLAlchemy 适配器、
  矛盾审核/主矛盾约束以及产品分区评估能力。
- `backend/domains/service`：已有 Provider、Offering、Slot、Booking、ServiceRecord
  和服务查询/预约路径；它可作为蓝图发布后的运行时消费方。
- `backend/intelligence/principal`：已有服务产品能力路由、`service_product_architect`
  与 `operations_assistant` 角色约束及高风险人工复核标记。
- `backend/intelligence/model_gateway`、`context_engine`、`experience`：已有模型边界、
  上下文和运行时原语，可供后续 AI 草案编排复用。
- `governance/AI_USE_CASE_REGISTRY.yaml`：已登记 discovery、composition、compile、
  simulation、knowledge stewardship 五类服务产品 AI 用例，均为非变更型且要求人工闸门。

### 3.2 仍是骨架或缺口

- `backend/intelligence/design_copilot/compiler.py` 的 12 个检查仍为
  `NotImplementedError`，没有真实调用方。
- `backend/intelligence/design_copilot/simulation.py` 的 `SimulationLab.run` 未实现；现有
  护栏只能保证模拟结果不能直接晋级为真实效果。
- `ProductComponent`、`ProductPattern`、`ProductDefinition` 当前字段还不足以承载完整
  输入/输出契约、资源、SLA、成本、安全和评估绑定。
- 没有统一的知识源、Claim、许可、检索、失效、删除和反馈登记；现有
  `docs/13_research/knowledge_compiled/*.json` 只能作为构建时快照。
- 没有服务产品工作台 API、Blueprint Release、CompileRun、SimulationRun 或设计反馈投影。

因此本设计不宣称“平台已落地”，而是把下一步开发拆成可验收切片。

## 4. 目标架构

```text
┌──────────────────────────────────────────────────────────────┐
│ Operations Console / Product Workbench                       │
│ discovery · compose · compile · simulate · review · release  │
└──────────────────────────────┬───────────────────────────────┘
                               │ governed commands/queries
┌──────────────────────────────▼───────────────────────────────┐
│ Principal + AI Runtime                                       │
│ consent → context → safety → soul → route → knowledge        │
│ → agent/tool → model_gateway → schema/provenance → human gate│
│ 输出：Draft / Recommendation / HumanTask；不得写事实          │
└──────────────┬───────────────────────────┬───────────────────┘
               │ design projection         │ frozen release
┌──────────────▼─────────────┐   ┌─────────▼──────────────────┐
│ product_intelligence       │   │ service                    │
│ problem/contradiction/     │   │ provider/offering/booking/ │
│ concept/component/pattern/ │   │ service case/task/delivery │
│ definition/blueprint truth │   │ facts                       │
└──────────────┬─────────────┘   └─────────┬──────────────────┘
               │                           │ quality/feedback facts
               └──────────────┬────────────┘
                              ▼
                 CompileRun / SimulationRun / Evaluation
                 / Feedback / LearningCandidate projections
```

`service` 不读取未发布设计稿，也不允许运行中的 ServiceCase 反向修改设计定义。
发布时复制不可变的 `ServiceBlueprintVersion` 引用和校验和；后续设计变更只能创建新版本。

## 5. 领域与主数据归属

### 5.1 产品设计真相（`product_intelligence`）

沿用现有实体作为唯一业务归属，并补齐字段而不另建平行 Domain：

- `GrowthProblem`：问题陈述、来源证据、适用边界。
- `GrowthHypothesis`：可证伪假设及证据；可选 `primary_contradiction_ref`。
- `ContradictionModel`：至少两条有张力的已审核假设；主矛盾选择必须可审计。
- `GrowthStrategy` / `ValueArchitecture`：策略和四层价值叙事，不产生家庭总分。
- `ProductConcept`：目标问题、客群、价值和排除条件。
- `ProductComponent`：版本化组件；声明 input/output、前置/禁用、角色、资源、安全、
  知识、成本、SLA、评估和 owner。
- `ProductPattern`：只引用已发布组件版本，声明组合顺序、兼容矩阵和失败路径。
- `ProductDefinition`：面向一个主要矛盾的服务产品设计稿，绑定阶段、任务、责任人、
  资源、SLA、成本、评估和人工触发。
- `ServiceBlueprintVersion`：编译后的冻结执行配置；发布状态和 checksum 不可原地覆盖。

### 5.2 交付事实（`service`）

Provider、Offering、Slot、Booking、ServiceCase、ServiceTask、DeliveryRecord、QualitySignal
等只记录真实供给与交付。它们引用 `blueprint_version_id`，但不复制设计正文，不接受 AI
直接写入，不因设计稿更新而改变历史案件。

### 5.3 平台治理事实

Consent、Authorization、Audit、Idempotency、Persistence 仍由 `backend/platform` 负责。
编译、模拟、发布命令必须串起同一 `correlation_id`，并在真实事务中落审计；现状中
`AuditRecorder.flush()` 尚未持久化，这属于发布生产流量前的阻断缺口。

## 6. 生命周期与状态机

```text
Design: DRAFT → REVIEW → COMPILE_BLOCKED | COMPILE_PASSED
       → SIMULATION_REVIEW → APPROVED → PUBLISHED → RETIRED

Component/Pattern: DRAFT → REVIEWED → PUBLISHED → RETIRED
Blueprint Release: CANDIDATE → CANARY → ACTIVE → PAUSED/ROLLED_BACK
Compile finding: PASS | WARN | BLOCK
```

状态迁移规则：

1. AI 只能创建或更新 Draft/Recommendation/HumanTask；不能执行 `PUBLISHED`、`ACTIVE`、
   `ROLLED_BACK` 等业务状态迁移。
2. 任一 `BLOCK` finding、缺失人工责任人、缺失许可/证据或高风险主题未设人工闸门时，
   不得进入发布评审。
3. 回滚只改变当前 Release 指针，不删除历史蓝图、已生成的服务事实或 AI 输出。
4. 发布、回滚和蓝图绑定均使用 Named Action、幂等键和审计事件。

## 7. 确定性编译器契约

`ProductCompiler` 应从“领域实体依赖”改为输入不可变设计投影的 Protocol，放在
`backend/intelligence/design_copilot`，不直接 import `product_intelligence` 或模型供应商。
每次编译生成一个可重放的 `CompileRun`：

```text
schema → component → compatibility → workflow → resource → ai_use_case
context_boundary → safety → human_gate → cost → evaluation → sla
```

每个 finding 至少包含：`check_id`、`severity`（PASS/WARN/BLOCK）、`rule_version`、
`input_versions`、`evidence_refs`、`explanation`、`repair_hint` 和 `provenance`。

最小阻断矩阵：

- schema/component/compatibility/workflow：结构、引用或可达性失败即 BLOCK；
- resource/cost/sla：超预算或无容量时 BLOCK，边界值可 WARN；
- ai_use_case/context_boundary/safety/human_gate：未登记、越权、未成年人敏感数据
  越界或缺人工责任人即 BLOCK；
- evaluation：没有可执行评估集只能 WARN，禁止输出疗效结论；高风险评估失败即 BLOCK。

编译器只读设计投影和治理策略，不写 ServiceCase，不改变知识发布状态。

## 8. AI 用例与人工闸门

以 `governance/AI_USE_CASE_REGISTRY.yaml` 为唯一登记入口：

| 用例 | 输入 | 输出 | 闸门 |
|---|---|---|---|
| `service_product_discovery` | GrowthProblem、MarketSignal、ProductZoneAssessment | 概念 Draft | 产品/教研负责人审核 |
| `service_product_composition` | 概念、组件、模式、KnowledgeClaim | 定义 Draft | 产品负责人审核 |
| `service_product_compile` | 定义、组件、治理规则 | CompileRun Draft | 产品 + 服务负责人审核 |
| `service_product_simulation` | 蓝图 Draft、合成情境、成本/SLA策略 | Recommendation | 产品 + 服务负责人审核 |
| `knowledge_stewardship` | 来源、许可、Claim、失效规则 | Claim Draft | 知识 owner 审核 |

所有用例强制经过 Principal 路由、Context 最小化、Safety、Model Gateway、结构化输出、
Provenance 和 Human Gate。禁止：自动发布、自动分派、家庭排名/总分、儿童诊断、未经授权
的家庭数据进入共享知识库、把合成模拟当真实效果证明。

### 8.1 商业洞察的高自治模式

商业洞察不把 AI 限制为摘要器。对运营侧的 `MarketSignal`、公开研究、服务质量和成本
投影，AI 可以连续完成：信号去重与聚类、趋势/异常检测、客户分群、矛盾发现、机会排序、
GrowthHypothesis 生成、验证动作设计、结果解释和下一轮洞察调度。这个分析闭环可以自动
运行，减少人工逐条搬运信息的低价值工作。

边界只放在“改变系统事实或产生不可逆承诺”的瞬间：AI 仍必须输出带
`evidence_refs` 和完整 provenance 的 Draft/Recommendation；将洞察确认、产品立项、
预算投入、价格/政策修改、服务发布等动作写入 canonical 状态时，必须由业务域 Named
Action 执行并留下责任人、版本和审计记录。换言之，**放开分析自治，保留事实提交治理**，
而不是把 AI 降级成只能写摘要的助手。

## 9. 知识与数据合规设计

知识资产采用 `Source → DocumentVersion → Chunk → Claim → Binding → Retrieval` 链路，
每个 Claim 必须带来源、许可、适用范围、证据等级、失效日期和删除引用。家庭私有
Context、服务记录和儿童敏感数据不写入共享 K0-K4 知识库；仅在授权的 family scope 内
作为运行时上下文使用。

所有 AI 设计输入记录 purpose、data_class、consent_ref、tenant_id、retention_policy_ref
和 provenance。删除/撤回必须级联到原文、转写、Chunk、Embedding、缓存、评估副本和反馈
投影；未成年人商业画像和自动化营销绝不属于本平台能力。

## 10. API 与事件（设计契约）

运营工作台建议使用 `/ops/service-products` 命名空间：

- `POST /designs`、`POST /designs/{id}/compose`：创建/编排 Draft；
- `POST /designs/{id}/compile`：生成 CompileRun；
- `POST /blueprints/{id}/simulate`：只接受合成情境；
- `POST /reviews/{id}/approve|reject`：建立人工决定；
- `POST /releases`、`POST /releases/{id}/rollback`：由 Named Action 发布/回滚；
- `GET /catalog`：只返回已发布且当前有效的服务产品投影。

核心事件：`ProductDesignDrafted`、`CompileRunCompleted`、`SimulationCompleted`、
`BlueprintApproved`、`BlueprintReleased`、`BlueprintRolledBack`、`DeliveryFeedbackRecorded`、
`LearningCandidateCreated`。事件必须带 tenant、actor、correlation、provenance 和版本引用。

## 11. 分阶段开发与验收

### SP-P0：契约冻结（当前设计交付）

完成本设计、ADR-0029、AI 用例/能力登记核对、字段和状态机评审。验收：边界、拒绝矩阵、
版本规则和责任人得到签字；不宣称运行能力。

### SP-P1：主数据 + 确定性编译器（首个代码切片）

扩展 `product_intelligence` 设计实体和仓储投影；实现 `CompileRun`、12 项检查的纯函数
适配器、finding 持久化和重复编译幂等。验收：结构/兼容/流程/安全/人工闸门失败可阻断，
同一输入产生相同 checksum 和 finding；架构测试与 ruff 通过。

### SP-P2：知识治理闭环

建立 Source/DocumentVersion/Claim/Binding/Review 的最小实现，补许可、失效、删除和检索
审计；把现有构建时快照迁为只读导入适配器。验收：未审核 Claim 不可被编译器引用，删除证明可回放。

### SP-P3：合成模拟与人工评审

实现 `SimulationLab` 的正常、缺证据、资源不足、拒绝、超时、敏感主题、供应商不可用、
   返工和取消情境；接入 EvaluationRun、RedTeamFinding、HumanReviewTask。验收：模拟只能
输出 Recommendation，不能触发发布或 ServiceCase。

### SP-P4：发布投影与服务接线

建立 BlueprintRelease 和 `service` 只读目录投影；服务案件绑定冻结蓝图版本，发布/回滚
走人工 Named Action、审计和幂等。验收：旧案件不受新版本影响，回滚保留历史事实。

### SP-P5：反馈归因与复用学习

将履约、质量、投诉、返工、成本和 SLA 事实归因到组件/模式/蓝图，形成变更候选；任何
候选重新走编译、模拟和人工发布。验收：可解释“哪个组件导致何种返工”，但不输出家庭总分、
排名或未经证据支持的成长疗效。

## 12. 评审清单（升格 canonical 前）

- [ ] `product_intelligence` 与 `service` 的主数据归属得到 owner 签字。
- [ ] `ProductComponent` 等实体扩展不产生第二套 canonical contract。
- [ ] 12 项编译规则、finding 严重度和阻断矩阵有测试样例。
- [ ] AI 用例 registry、Principal 路由、模型网关和 Human Gate 端到端可追踪。
- [ ] Consent、Audit 持久化、Idempotency、租户隔离和删除级联均有生产等价测试。
- [ ] 合成模拟、服务质量反馈与真实成长结果明确分离。
- [ ] 首个可发布蓝图经过产品、服务、教研、AI 治理和合规联合评审。

## 13. 依据与关联文件

- `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md` §8（三区方法论与独占区候选）。
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md`、`AI_ARCHITECTURE.md`、`AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md`。
- `docs/05_ai/SERVICE_PRODUCT_DESIGN_AI_PLATFORM.md`（服务产品生命周期设计工作稿）。
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`、`governance/REPOSITORY_CONSTITUTION.md`。
- `governance/AI_USE_CASE_REGISTRY.yaml`、`governance/ADR/ADR-0007-product-zone-scoring-v0.md`、
  `governance/ADR/ADR-0008-product-zone-governance-v0.md`。
- `backend/domains/product_intelligence/`、`backend/domains/service/`、
  `backend/intelligence/design_copilot/`、`backend/intelligence/principal/`。
