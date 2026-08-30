---
id: AI-MARKET-DELIVERY-001
title: 市场洞察到产品交付 AI 能力蓝图
type: ai
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
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
