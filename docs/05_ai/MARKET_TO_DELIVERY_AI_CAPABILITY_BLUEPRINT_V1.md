---
id: AI-MARKET-DELIVERY-001
title: 市场洞察到产品交付 AI 能力蓝图
type: ai
status: draft
version: 0.2
owner: chief-architect
created: 2026-08-30
updated: 2026-08-31
canonical: false
---

# 市场洞察到产品交付 AI 能力蓝图 V1

## 1. 目标

围绕一条完整价值链建设 AI 能力：

```text
需求 → 市场洞察 → 机会 → 产品设计 → 组件组合 → 蓝图编译
    → 小批试点 → 产品发布 → 服务交付 → 质量验收 → 结果回流
```

AI 不只是最后生成一份报告，而是每个阶段的分析、设计、验证和反馈引擎。业务事实仍由
`family_need`、`product_intelligence`、`journey`、`service`、`commerce` 等 canonical 域拥有。

模型采用成熟多模态 LLM 优先策略：所有模型访问经 `ModelGateway`，先支持图片理解/图文
结构化输出，再按 provider capability、合规准入和评估结果逐步启用音频、视频和图像生成。
平台不自研基础模型，也不把某一家供应商写入产品域。

## 2. 端到端能力分层

### A. 需求与市场洞察

AI 能力：需求文本结构化、VOC 聚类、矛盾发现、竞品证据抽取、趋势分析、替代方案识别、
机会排序、研究任务生成。

输入：授权需求、公开市场资料、竞品证据卡、服务质量投影。

输出：`DemandPerspective`、`MarketInsightDraft`、`CompetitorEvidence`、`ResearchTask`、
`OpportunityRecommendation`。

约束：缺少来源时只能生成研究任务；不得把热点直接写成家庭需求；不计算家庭总分或竞品综合排名。

### B. 产品定义与概念

AI 能力：需求假设生成、产品概念发散、21/90 天候选生成、三区定位建议、成本/SLA 假设、
范围外识别、替代概念比较。

输入：DemandFrame、MarketInsight、GrowthProblem、组件 Catalog、Skill Catalog、服务容量。

输出：`ProductConceptDraft`、`ProductCharterDraft`、`RequirementBaselineDraft`、
`ZoneStrategyRecommendation`。

约束：至少保留多个候选；所有结论绑定证据和置信度；AI 不自动立项。

### C. 组件、Skill 与蓝图设计

AI 能力：组件检索、输入输出匹配、Pattern 组合、阶段编排、角色分工、知识/提示词绑定、
服务资源槽位设计、风险和缺口发现。

输入：已审核组件、已发布 Skill、知识/证据包、服务目录、容量、SLA、合规策略。

输出：`ProductPackageDraft`、`PatternDraft`、`BlueprintDraft`、`DesignGapFinding`。

约束：只允许契约兼容的组件连接；AI Runtime 不直接写领域仓储；草案不能直接创建 ServiceCase。

### D. 编译、验证与试点

AI 能力：反例生成、边界场景、红队用例、测试矩阵、容量压力假设、试点分组、指标和 guardrail
建议、异常解释。

确定性能力：需求覆盖、版本一致性、权限/同意、租户边界、SLA、成本、回滚、人工闸门、
AI Eval 和删除路径检查。

输出：`CompileRun`、`VerificationRun`、`PilotPlan`、`PilotRecommendation`。

约束：模拟不能证明真实成长效果；AI 不自动扩大试点、不自动发布、不自动改变家庭事实。

### E. 发布与产品交付

AI 能力：发布前差距解释、资源匹配建议、任务拆解、服务交付辅助、交付物质量检查、异常升级、
客户反馈归因、补救方案草案。

输入：已发布 `BlueprintVersion`、服务能力、授权范围、任务和质量策略。

输出：`DeliveryRecommendation`、`QualityFinding`、`RecoveryDraft`、`HumanTask`。

事实 Owner：`journey` 写成长行动事实，`service` 写案件/任务/交付/质量事实，`commerce` 写
订单/权益事实；AI 只提出建议，人工或业务动作确认后才改变事实。

### F. 结果回流与生命周期

AI 能力：组件效果归因、返工根因、SLA 异常、成本变化、反馈摘要、版本差异分析、改版建议、
SCALE/REVISE/KILL 推荐、下一轮研究任务生成。

输出：`LearningCandidate`、`ChangeRequestDraft`、`LifecycleRecommendation`。

约束：结果证据不能自动升级为疗效或诊断；所有产品变更重新进入 IPD Gate。

## 3. 运行时架构

```text
Web Product Workbench
  → Product Application / Query Projection
  → Principal + Context + Safety
  → Skill Runtime + Tool Runtime
  → Knowledge / Evidence Retrieval
  → Model Gateway
  → Structured Draft + Provenance + Eval
  → Human Gate / Named Action
  → Domain Application (fact write)
  → Outbox / Analytics Projection / PLM feedback
```

AI Runtime 只持有上下文快照、证据引用、草案和建议；领域应用持有事实。长流程由
`workflow_worker` 编排，Web UI 不承载跨时长状态机。

## 4. 关键事件链

```text
DemandCaptured
→ MarketInsightDrafted
→ OpportunityProposed
→ ProductConceptDrafted
→ ProductPackageComposed
→ BlueprintCompiled
→ PilotStarted
→ PilotFeedbackRecorded
→ ReleaseApproved
→ DeliveryRecorded
→ QualityVerified
→ LifecycleCandidateCreated
```

每个事件必须带 tenant、actor、correlation、产品/组件/Skill/知识/模型版本、证据引用和审计引用。

## 5. Web UI 交互原则

- 用户看到“证据、假设、建议、阻断项、下一步动作”，而不是不可解释的 AI 分数；
- 允许批量处理和多候选比较，但不允许批量绕过 Gate；
- 每个草案可回放输入上下文、引用来源、模型版本和评估结果；
- 每个发布动作显示影响范围、版本、回滚点、责任人和过期时间；
- 交付人员只看到被授权的产品蓝图和任务，不看到无关家庭数据。

## 6. 实施顺序

1. 洞察：MarketInsight + CompetitorEvidence + ResearchTask；
2. 设计：ProductPackage + Component/Skill Catalog + 21/90 天组合器；
3. 编译：BlueprintCompiler + VerificationRun；
4. 试点：PilotPlan + Human Gate + Outbox；
5. 交付：Blueprint Projection → Journey/Service → Quality；
6. 学习：Outcome/Quality/Cost 回流 → ChangeRequest → 新版本。

第一条可验收闭环必须贯通“一个有来源的家庭需求 → 一个 21 天产品候选 → 一个受控试点 →
一条交付质量反馈 → 一个可审计的改版或停止建议”。只完成某个 AI 页面，不算链路完成。

## 7. 反主观检查

每次 AI 输出都要标注：

- `evidence_refs`：依据什么；
- `assumptions`：还不知道什么；
- `confidence`：置信度而非事实等级；
- `next_validation`：如何验证；
- `owner`：谁负责决定；
- `expiry`：何时失效或复审。

没有证据、没有 Owner 或没有验证路径的输出只能停留在 Draft，不得进入发布目录。

## 8. 整体平台分层

本蓝图依据 `docs/13_research/market/SERVICE_PRODUCT_PLATFORM_BENCHMARK.md` 的外部证据，
并由 `governance/ADR/ADR-0140-demand-driven-product-factory-loop.md` 固化运行决策。平台不新增
平行业务域，而是在现有唯一 Owner 上形成七层能力：

1. **市场与组合决策层**：Demand/VOC、Market/Competitor Evidence、Opportunity、三区判断和
   IPD Gate，产品设计事实归 `product_intelligence`；
2. **PDM 主数据层**：Component、Skill、Pattern、Knowledge/Prompt/Schema binding、
   ProductPackage、BlueprintVersion；
3. **AI 设计工程层**：Principal、Context、Safety、Skill/Tool Runtime、Model Gateway、
   多候选 Draft、Provenance 和 Eval；
4. **编译与治理层**：十二项确定性编译、CompileRun、Human Gate、Audit 和 Idempotency，
   编译通过只是 Gate 证据，不等于发布；
5. **Pilot/PLM 控制层**：容量受限的 PilotRun、guardrail、ReleaseBaseline、回滚，以及
   SCALE/REVISE/PAUSE/STOP；
6. **执行与学习层**：Journey/Service/Commerce 只消费冻结的 BlueprintVersion，各自拥有业务
   事实，再通过 Outbox 将质量、成本和结果投影为 LearningCandidate；
7. **Web 工作台层**：Demand Studio、Market Evidence、Component/Skill Library、Compile/Gate
   Board、Pilot Ops、PLM Console 和后续 Asset Studio；Gate 判定必须由服务端拥有。

多模态产品采用“结构化内容包 + 可替换渲染适配器”：平台先保存大纲、卡片、引用、视觉指令、
品牌与权利信息，再通过 Model Gateway 和 Creative Provider Adapter 调用成熟模型或外部编辑器。
PPT、图片、视频和短剧都必须反链到产品版本与需求证据。

## 9. PDCA 迭代路线

每轮只交付一条可运行纵向链，证据不足时不扩大范围：

### Iteration 1：市场证据闭环（当前）

- Plan：竞品证据与市场洞察分开建模，默认 UNKNOWN；
- Do：Web 创建竞品证据，持久化回读，再自动引用到 MarketInsight DRAFT；
- Check：输入、租户、provenance、状态、刷新回读和 Gate 阻断测试；
- Act：形成可进入产品概念生成的证据包，或生成新的 ResearchTask。

### Iteration 2：产品概念与三区闭环

- 从 Demand + Market Evidence 生成多个 ProductConcept 候选；
- 同屏展示依据、反证、未知项和三区建议；
- 人工选择或退回研究，不由 AI 自动立项；
- 只有 durable Human Gate 已接受并生成 `NamedActionRequest` 后，
  `ADOPT_PRODUCT_CONCEPT_AS_DEFINITION` 才能进入 PDM；
- accepted-action handler 从 `approved_zone` 派生产品定义三区，不接受 Web 提交 zone；
  结果仅为 `ProductDefinition(DRAFT)`，并保留 task/proposal/decision、评估版本、
  provenance，并生成同事务审计记录。具体边界由
  `governance/ADR/ADR-0141-product-definition-human-adoption.md` 固化；
- 当前 Web 选择仍是未持久化 Decision DRAFT。应用/SQL 测试面已按 ADR-0145 增加不可变
  `ProductPackageDraftVersion`，冻结 approved-zone、证据、组件/Skill、AI provenance 和 content
  hash，并与 OPEN HumanTask 在同一事务提交。严格 HTTP create/read 测试面只接受业务意图和
  opaque locator，拒绝浏览器提供 zone、claim/applicability 要求、证据状态、AI provenance、
  身份和 Gate 字段；可信服务端 source resolver 必须为每个 locator 给出精确证据要求，随后由
  receipt-backed resolver 编译准入快照。真实 PostgreSQL metadata-schema 测试已覆盖同意图
  并发和 Evidence 行锁漂移；Alembic-schema parity、registry、生产挂载和前端 Web 工作台仍未
  落地，因此不能把 HTTP 测试面称为 Web 或生产能力。
- 证据治理测试面已按 ADR-0146 增加不可变 `EvidenceVerificationReceipt`：只有已接受的
  `VERIFY_PRODUCT_EVIDENCE` NamedAction 才能物化，冻结证据版本/哈希、claim scope、适用范围、
  方法、策略、验证人和 Human Gate lineage；旧竞品来源卡 HTTP 只允许 `UNKNOWN`，不能由客户端
  自报 `VERIFIED`。验证提案/评审 Web、撤销/替代、迁移、registry、PostgreSQL 和 resolver 接入
  尚未完成，因此 receipt 仍是独立可测治理接缝。
- Operator Review Queue 已实现为独立可测 Web/API surface：只读取服务端 OPEN HumanTask，
  浏览器仅提交 outcome + reason，ACCEPT 只生成待执行 NamedActionRequest。当前主应用尚未挂载
  Product Factory router，生产权限解析器也未安装，故不能宣称生产可用；边界见
  `governance/ADR/ADR-0143-product-definition-operator-review-surface.md`。

### Iteration 3：组件与 Skill 闭环

- 建立版本化 Catalog、兼容矩阵、许可证、成本和容量字段；
- AI 编排 21 天最小试点包及 90 天扩展候选；
- 十二项编译结果持久化并可回读。

### Iteration 4：小 cohort 试点闭环

- 每个试点有容量、责任人、同意、暂停和停止条件；
- 交付可行性、安全、家庭体验、成本和成长证据共同进入 Gate；
- 21 天是验证机制，90 天是经验证后的扩展候选，不是固定售卖模板。

### Iteration 5：多模态资产闭环

- 先接成熟 PPT/图片模型与编辑通道，再扩音频、视频、短剧；
- 保存结构化内容包、AssetVariant、RightsRecord、RenderJob 和评测结果；
- 生成失败可换供应商，人工编辑后仍能回写版本与 provenance。

### Iteration 6：PLM 学习闭环

- 从交付、质量、安全、成本和主观体验产生 LearningCandidate；
- AI 解释组件级差异并建议 SCALE/REVISE/PAUSE/STOP；
- 所有改版重新进入需求、证据、编译和 Gate 链。

## 10. 当前真实缺口

截至 2026-09-01，代码已有 Product Factory 草案 API、竞品证据持久化、教育产品字段、十二项
编译器、人工生命周期契约和 Web Demand Composer，但仍有以下阻断：

- Product Factory 尚未在 canonical `family_api` 完成无争议的生产挂载与真实身份组合；
- HTTP 幂等键尚未真正接入平台幂等执行；
- DemandFrame 与 MarketInsight 的完整 envelope 缺少独立持久化回读；
- EvidenceVerificationReceipt 已有 accepted-action/SQL 测试接缝，但尚无提案 Web、撤销影响账本、
  Alembic、独立收据创建并发证明和 ProductPackage resolver 生产接入；
- ProductPackage HTTP 已按 ADR-0147 在可信来源解析前执行 durable intent replay：浏览器意图、
  source locator 和 requested TTL 进入 canonical hash，相同 key/相同 intent 返回冻结结果，
  相同 key/不同 intent 在 resolver 前冲突；resolver 暂不可用时历史 exact replay 仍可回读。
  metadata-schema PostgreSQL 同键竞态已通过确定性 barrier 验证；新列尚无 Alembic 及
  Alembic-schema parity 证明，因此仍不是生产挂载能力；
- ProductPackage v1.2 已按 ADR-0148 用 `EvidenceAdmissionSnapshot` 替代来源解析器自报的
  `VERIFIED` 字符串：冻结 receipt/evidence 版本与哈希、claim/applicability scope、策略、
  Human Gate lineage 和有效期；浏览器只提交 locator，claim/applicability 要求由可信服务端
  source resolver 提供并与 locator 序列精确匹配；写 draft/HumanTask/audit 前以最新提交时钟在
  同一 SQL session 重读收据、锁定 Evidence 后精确复核，失败即回滚。缺少撤销/替代影响账本、
  typed EvidenceDescriptor 与 Alembic。真实 PostgreSQL 的 metadata-schema 测试已证明同意图
  并发收敛及行锁等待后的证据漂移会 fail closed，但尚未证明 Alembic 产出的结构具备同等行为，
  故仍只是一条非生产但可验证的可信证据准入接缝；
- ProductPackage 已有独立可测的 SQL DRAFT→OPEN ActionProposal、receipt-backed resolver 与严格
  HTTP create/read 接缝，但尚无生产 source/provenance resolver、Alembic、生产挂载、前端 Web 工作台、
  十二项编译报告绑定和 Alembic-schema PostgreSQL 并发证明；
- Component/Skill Catalog、PilotRun、GateRecord、ReleaseBaseline 和多模态资产主数据尚未形成
  可运行闭环；
- Web 的历史 `ProductStudio` 状态机仍是 Sandbox，不得作为真实 Gate 或能力完成证明。

这些缺口决定实施顺序：先让市场证据链可调用、可回读、可授权，再进入 21/90 天生成和多模态
资产生产。
