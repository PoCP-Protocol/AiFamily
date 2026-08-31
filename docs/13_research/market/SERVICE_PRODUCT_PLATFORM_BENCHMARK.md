---
id: RESEARCH-SERVICE-PRODUCT-PLATFORM-001
title: Service Product AI Platform Market Benchmark
type: research
status: draft
version: 1.0
owner: service-product
created: 2026-08-31
updated: 2026-08-31
canonical: false
supersedes: null
superseded_by: null
---

# 服务产品 AI 平台市场对标研究

> **RESEARCH_ONLY / NOT_CANONICAL**
>
> 本文是外部证据，不是 AiFamily 当前系统真相。架构与产品决策须经 ADR，
> 当前能力须以 `docs/00_system/CURRENT_SYSTEM_BASELINE.md` 和可运行测试为准。

## 1. 研究问题

AiFamily 需要的不是通用聊天机器人，而是一套把家庭需求、市场证据、服务产品定义、
小规模试点、多模态交付和生命周期反馈连接起来的 Web 产品研发操作系统。本研究聚焦：

1. 成熟产品研发平台怎样把客户反馈转成可追溯的产品决策；
2. 家庭教育 AI 怎样保持启发式帮助、家长可见性和安全边界；
3. SHEIN 的按需小批模式中，哪些机制可迁移到服务产品研发；
4. 成熟多模态模型应当怎样被平台调用，而不是被领域代码绑定。

## 2. 一手资料发现

### 2.1 Productboard：AI 应先压缩证据处理成本

Productboard 将 AI 用于反馈分类、语义搜索、趋势监测、长反馈摘要，以及将客户需要汇总到
feature specification。值得移植的是“反馈—洞察—产品项”的证据连接，不是让模型直接决定
优先级。来源：[Productboard AI](https://www.productboard.com/product/ai/)（访问于 2026-08-31）。

对 AiFamily 的含义：AI 可以主动聚类、找矛盾、提出待验证假设，但每条市场洞察必须保留
来源、适用分群、有效期、未知项和下一验证。

### 2.2 Jira Product Discovery：发现与交付必须双向可追溯

Jira Product Discovery 把机会、候选方案和客户研究放在一起，在进入开发 backlog 前完成评估
和验证，并把 discovery idea 与交付 ticket 连接。值得移植的是“发现对象与交付对象分离，
但状态可追溯”。来源：[Jira Product Discovery features](https://www.atlassian.com/software/jira/product-discovery/features)
（访问于 2026-08-31）。

对 AiFamily 的含义：`DemandFrame`、`MarketInsight`、`CompetitorEvidence`、`ProductPackage`
不能被一个自由文本页面替代；每个对象都要有独立状态、证据和 Gate 结果。

### 2.3 Aha!：AI 覆盖产品全链路，而不是只做文案

Aha! 公开的 AI 能力覆盖外部与内部研究汇总、访谈学习提取、反馈主题聚类与去重，并可继续
形成 initiative、epic、feature、原型、规格和发布内容；同时强调上下文、安全和成本控制。
值得移植的是“同一上下文贯穿研究—定义—交付”，不是照搬一套重型软件套件。来源：
[Aha! AI overview](https://www.aha.io/suite/ai-overview)（访问于 2026-08-31）。

对 AiFamily 的含义：上下文包、模型路由、成本预算、用途版本和证据引用都是平台一级能力；
模型推荐仍必须保持 DRAFT 并接受确定性检查和人工责任人决策。

### 2.4 Khanmigo：教育 AI 的价值是引导，不是代答

Khanmigo 面向家庭强调不直接给答案、通过引导建立思考与信心，同时向家长提供聊天历史、
安全提示和管理工具。值得移植的是“帮助方式 + 监护人可见 + 护栏”的组合，而不是把家庭
成员变成被自动评分的对象。来源：[Khanmigo for parents](https://www.khanmigo.ai/parents)
（访问于 2026-08-31）。

对 AiFamily 的含义：AI 输出应是可讨论、可驳回、可追溯的 Perspective、Recommendation
或 Draft；高风险输出和发布动作必须经过人工闸门。

### 2.5 成熟多模态平台：结构化内容与渲染通道分离

Canva Connect 支持外部平台创建、同步、编辑和导出设计；Brand Template Autofill 可将结构化
字段填入模板。Gamma 将生成路径区分为 Generate、Paste、Import，并支持导出 PDF、PNG 和
PPTX。Adobe Firefly API 把生成、编辑、合成和可版本化的自定义资产接入创意工作流。来源：
[Canva Connect APIs](https://www.canva.dev/docs/connect/)、
[Canva Autofill guide](https://www.canva.dev/docs/connect/autofill-guide/)、
[Gamma create workflow](https://help.gamma.app/en/articles/7838093-how-do-i-create-a-new-presentation-document-or-webpage-in-gamma)、
[Gamma export](https://help.gamma.app/en/articles/8022861-what-s-the-easiest-way-to-export-my-gamma)、
[Adobe Firefly API](https://developer.adobe.com/firefly-services/docs/firefly-api/)
（访问于 2026-08-31）。

对 AiFamily 的含义：平台保存中立的 `ProductContentPackage`、品牌包、引用和资产配方，
Canva/Gamma/Firefly 只是可替换的编辑或渲染通道。第一阶段调用成熟模型和模板；只有当调用量、
品牌一致性或角色一致性形成可测瓶颈后，才评估专属模型。

### 2.6 SHEIN：从预测驱动转成需求证据驱动

SHEIN 官方描述其按需模式以客户偏好和购买表现，而不是单纯趋势预测做决策；每个款式先生产
100–200 件小批量，只对有需求的款式补货，并用数字化后端连接端到端生产周期。值得迁移的
不是服装行业的高频上新，而是“小批试验—真实反馈—选择性扩展”的经营机制。来源：
[SHEIN Group on-demand model](https://www.sheingroup.com/our-group)（访问于 2026-08-31）。

对 AiFamily 的含义：服务产品先进入有明确边界的小规模 Pilot Cohort；只有交付可行性、
家庭主观感受、安全、退订/暂停和成本证据满足 Gate，才允许扩展。家庭教育不能照搬“销量
即验证”：效果声明仍需适当的证据等级，未成年人安全永远不能由增长指标覆盖。

## 3. 可移植模式与禁止照搬

### 3.1 可移植

- 统一接入多来源反馈，AI 完成去重、聚类、摘要、反证搜索和假设生成；
- 证据对象与洞察对象分开，洞察必须引用证据且带有效期；
- 产品发现、产品定义、交付试点和生命周期数据形成双向追溯；
- 先用小规模服务批次验证，再决定扩大、修改、暂停或停止；
- 成熟多模态模型通过 Model Gateway 调用，保留模型、提示、上下文、成本与评测 provenance；
- 家长或指定专业人员能看见并控制高风险 AI 输出。

### 3.2 禁止照搬

- 不把 RICE、销量、参与率或模型置信度变成家庭总分或家庭排名；
- 不把未核验的社交媒体热度直接当作家庭真实需求；
- 不用 AI 自动发布产品、自动宣称疗效或自动向未成年人营销；
- 不因追求“快反”绕过 consent、purpose limitation、Human Gate 和退出机制；
- 不在业务域直接集成任一模型供应商 SDK。

## 4. 对整体蓝图的证据结论

平台应采用一条需求驱动的闭环：

```text
家庭场景信号
  -> DemandFrame
  -> MarketInsight + CompetitorEvidence
  -> ProductConcept / 三区判断
  -> Component + Skill + ProductPackage
  -> Deterministic Compiler + Human Gate
  -> Pilot Cohort
  -> Multimodal Delivery
  -> Outcome / Safety / Cost / Experience Evidence
  -> Modify | Scale | Pause | Stop
```

AI 在闭环中应拥有较强的研究、生成、编排、模拟和异常发现能力；限制对象不是 AI 的思考与
建议空间，而是未经证据和授权就把输出写成事实、发布产品或改变家庭权益的动作。

## 5. 建议的迭代顺序

1. **证据闭环**：Web 创建竞品证据，持久化回读，再生成引用该证据的市场洞察草案；
2. **概念闭环**：从需求与洞察生成三区判断和产品概念，显式展示反证与未知项；
3. **组件闭环**：组件/Skill 目录、兼容矩阵、版本与许可证进入确定性编译器；
4. **试点闭环**：从产品包建立有容量、暂停/停止条件和人工责任人的 Pilot Cohort；
5. **多模态闭环**：通过 Model Gateway 生成 PPT、图片、视频草案并进入评测与人工发布；
6. **PLM 闭环**：依据结果、安全、体验、成本证据给出扩大、修改、暂停或停止建议。

## 6. 研究局限

- 资料来自厂商官方页面，适合确认其公开产品模式，不等于独立效果评估；
- 不同厂商使用的“AI”“洞察”“验证”定义不完全一致；
- 本轮没有把价格作为架构依据，模型和多模态供应商仍应通过可替换 Pilot 评测选择；
- 任何市场模式进入家庭教育场景前，都要经过未成年人保护和家庭数据合规复核。
