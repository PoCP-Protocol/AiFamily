---
id: MULTIMODAL-PRODUCT-FACTORY-001
title: 家庭成长多模态产品工厂分期实现方案
type: product
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# 家庭成长多模态产品工厂分期实现方案 V1

## 1. 总原则

PPT、图片、视频、短剧和周边商品不是五套独立功能，而是同一个 `ProductPackage` 的不同
交付载体。平台先设计产品，再生成资产，再验证，再发布和经营：

```text
Demand / Market Insight
  → ProductPackage
  → Component / Skill / ContentSpec
  → AssetBundle（PPT / Image / Video / Drama / Merchandise）
  → Quality / Rights / Safety Review
  → Micro Pilot
  → Release / Delivery
  → Feedback / Lifecycle
```

产品只做 Web UI；生成和渲染由 AI Runtime/worker 执行，家庭、服务和商业事实仍由各自域拥有。

## 2. 为什么不能一开始做短剧和商品

多模态越往后，成本、版权、质量、合规和履约复杂度越高：

```text
PPT/图片  <  视频  <  短剧  <  实体商品
低成本       中成本    高编排      高履约/库存/售后
```

如果没有统一的资产版本、素材权利、提示词/模型 provenance、审核和回滚，先做视频或短剧
只会产生大量不可复用的孤立文件；如果没有需求验证和小批机制，先做商品会把库存风险带入
家庭教育产品。

## 3. 分期路线

### M0：多模态产品底座（必须先做）

目标：让所有载体共享同一套 PDM/PLM 数据和治理。

建立：

- `AssetDefinition`、`AssetVersion`、`AssetBundle`、`ContentSpec`；
- `MediaType`：TEXT、PPT、IMAGE、VIDEO、DRAMA、MERCHANDISE；
- 素材、字体、音乐、声音、人物形象和模型输出的权利/许可引用；
- Model/Prompt/Knowledge/Context/Tool provenance；
- 生成任务、渲染任务、质量检查、人工评审、发布、暂停、回滚和删除；
- 成本、耗时、失败率、复用率和质量指标；
- Web UI 的 Asset Library、Template Library、Rights Review、Quality Review。

验收：同一个 21 天产品可以绑定多种资产版本；重新生成不会覆盖已发布版本；删除和回滚可追溯。

### M1：文档与静态视觉产品

范围：PPT、PDF、长图、海报、社群卡片、课程封面、活动物料。

AI 能力：大纲、页面结构、视觉变体、图文排版、品牌适配、引用校验、无障碍检查、多语言
草案和版本比较。

产品方式：给一个产品包生成 3–5 个低成本变体，先在 Web 端内部评审或小范围试用，再选择
版本发布。PPT/PDF 必须保留来源、版权、数据时间和人工审核记录。

退出条件：模板复用率、人工返工时间、事实错误率、版权阻断率达到产品设定阈值。

### M2：短视频与可复用视频片段

范围：30 秒至 5 分钟的讲解、行动示范、家长引导、服务说明和课程片段。

增加：Storyboard、Shot、VoiceTrack、Subtitle、AudioMix、RenderJob、Transcode、
Thumbnail 和播放质量检查。

AI 能力：脚本、分镜、配音草案、字幕、剪辑建议、镜头替换、版本裁剪和多语言适配。

治理：真人肖像、声音、音乐和素材必须有授权；涉及儿童时默认不生成可识别的真实儿童
肖像/声音；发布前必须通过安全、版权、事实和人工评审。

### M3：短剧/系列化叙事产品

范围：多集短剧、家庭情境演示、角色对话和成长主题故事。

先做“生产设计”，后做生成：

- StoryBible：主题、角色边界、关系、世界观和禁用内容；
- EpisodePlan：集数、目标、冲突、节奏和退出点；
- ScriptVersion：剧本和事实引用；
- ShotPlan：镜头、角色、声音、场景和资产引用；
- ReviewPack：版权、未成年人、价值导向、事实和敏感主题评审。

AI 可以生成多版本剧本、分镜和镜头草案，但不能让模型自行决定儿童价值判断、心理诊断、
商业诱导或对外发布。先用 1–3 集、单一主题、明确人工导演的微型试点验证。

### M4：周边商品与实体交付

范围：家庭行动卡、绘本、教具、手册、贴纸、文具、活动包等。

新增 PDM 对象：`MerchandiseSpec`、BOM、包装、供应商能力、样品版本、质检标准、成本、
起订量、库存策略和售后策略。实体商品必须与教育效果解耦：购买不代表成长结果，成长数据
不能用于孩子端自动化商业营销。

采用“需求证据 → 设计样品 → 小批/预售验证 → 质量验收 → 扩大/停止”的方式，先做非易
腐、低库存、可复用的产品。库存、订单、支付、退款和履约由 Commerce/Service 域负责，
PLM 只管理产品设计版本和供应质量证据。

## 4. 统一 PDM 模型

```text
ProductPackage
  ├─ Component / Skill / Pattern
  ├─ ContentSpec
  ├─ AssetBundle
  │    ├─ AssetVersion（PPT / Image / Video / Drama）
  │    └─ MerchandiseSpec
  ├─ RightsGrant / SafetyPolicy / QualityPlan
  ├─ PilotPolicy / ReleaseBaseline
  └─ LifecycleDecision
```

每个 AssetVersion 必须绑定：产品版本、组件版本、模型/Prompt/知识版本、素材权利、目标
受众、数据目的、生成时间、质量结果、人工评审和发布状态。

## 5. AI 能力分层

- **Discover**：发现需求、竞品和内容缺口；
- **Design**：生成多模态概念、脚本、版式、视觉和商品方案；
- **Compose**：把多个资产组合成 21 天/90 天产品包；
- **Render**：异步生成、转码、排版和多语言版本；
- **Evaluate**：事实、版权、安全、无障碍、品牌、质量和成本评估；
- **Operate**：试点分组、异常解释、质量归因和版本建议；
- **Learn**：根据使用、反馈、交付和售后生成下一版候选。

所有能力经 Model Gateway 和统一 Skill Runtime，AI 输出默认是 Draft/Recommendation；高影响
发布、商品价格、对外承诺、儿童相关敏感内容和订单动作必须经过人工/业务闸门。

## 6. Web UI 分期工作台

- **Product Studio**：产品包、需求、三区、概念和生命周期；
- **Asset Studio**：PPT/图片/视频/短剧/商品资产生成与变体；
- **Component Library**：组件、Skill、模板、Pattern 和兼容关系；
- **Rights & Safety**：素材权利、敏感内容、未成年人和人工评审；
- **Pilot Lab**：小批试点、实验、质量和成本；
- **Release & PLM**：发布、回滚、版本差异、反馈、售后和退役。

## 7. 关键 Gate

- **G0 需求**：有需求来源和市场/竞品证据；
- **G1 产品**：有 ProductPackage、三区定位、范围外和停止条件；
- **G2 资产**：组件、Skill、模板、权利和成本可追溯；
- **G3 质量**：事实、版权、安全、无障碍、人工评审和渲染结果通过；
- **G4 试点**：小批范围、授权、指标、guardrail、容量和回滚明确；
- **G5 发布**：版本冻结、运营/履约准备、监控和回滚演练完成；
- **G6 生命周期**：按价值、质量、成本、库存和售后决定扩展、改版或停止。

## 8. 建议首个多模态纵向切片

选择“21 天家庭行动产品 + Web 设计工作台 + PPT/图片资产包”：

1. 输入一个有来源的家庭需求与市场洞察；
2. AI 生成 3 个 21 天产品候选；
3. 选择一个候选并组合 21 天组件；
4. 自动生成 PPT、行动卡和复盘图片的多个版本；
5. 通过权利、事实、安全和人工评审；
6. 创建受控试点；
7. 根据反馈生成新版资产包或停止建议。

这个切片能验证 IPD、PDM、PLM、组件库和 AI 的共同底座，成本远低于直接做视频、短剧或库存商品。

## 9. 采用与放弃标准

每一期都必须回答：资产是否复用、质量是否可测、成本是否可控、权利是否清楚、家庭是否
真正受益、是否能回滚。若不能回答，就停留在研究/试验态，不进入正式产品目录。
