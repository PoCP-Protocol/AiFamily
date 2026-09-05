---
id: RESEARCH-FIVE-COMPANY-BENCHMARK-001
title: Five-Company Benchmark — What Is Already Built vs. What Remains
type: research
status: draft
version: 1.0
owner: product-intelligence
created: 2026-09-03
updated: 2026-09-03
canonical: false
supersedes: null
superseded_by: null
---

# 五家标杆公司对标 — 现状盘点与真实增量差口

> **RESEARCH_ONLY / NOT_CANONICAL**
>
> 本文是外部证据 + 现状代码盘点，不是新的架构决策。任何要落地的差口仍须走 ADR。
> 目的：防止把已经写进代码的对标结论再"重新设计"一遍。

## 0. 为什么写这份文档

此前的对标工作分散在多处：Triple P / Khanmigo 的结论已经写进架构和
`SERVICE_PRODUCT_PLATFORM_BENCHMARK.md`；Maven Clinic / 小红书 / TikTok
是这次补充研究的对象。核对代码后发现：**这次原本要"新增"的建议，
半数以上已经在代码里实现了**。本文逐条标注"已落地"或"真实差口"，
避免下一轮开发把已完成的能力当成待办重做。

## 1. Triple P — 已落地，无差口

- **机制**：stepped-care 五级分级。
- **代码**：`InterventionTierLabel`（`UNIVERSAL`/`LIGHT_GUIDANCE`/
  `BRIEF_CONSULTATION`/`INTENSIVE_SUPPORT`/`ENHANCED_SUPPORT`），出现在
  `family_need` 的需求画像（N2）以及 `product_intelligence` 的
  `family_experience_signal.py` / `improvement_candidate.py`（跨域镜像值，
  不直接 import，见这两个文件的模块注释）。
- **结论**：不需要新工作。

## 2. Khanmigo — 已落地，无差口

- **机制**：引导而非代答 + 家长可见 + 安全护栏。
- **代码**：`ai_coach` 域的生成式苏格拉底式引导实现（见 ADR-0152）；结论已写入
  `SERVICE_PRODUCT_PLATFORM_BENCHMARK.md` §2.4。
- **结论**：不需要新工作。

## 3. Maven Clinic — 一手资料（2026-09 抓取 mavenclinic.com）

### 3.1 分诊/匹配分层

Maven 用 24/7 Care Advocate 做首触分诊，再匹配具体专科。

**代码现状**：`backend/domains/service/fgcn/` 已经有 `admission.py`（准入）、
`entry.py`、`engine.py`、`application.py` 构成的多阶段派单管线，是比 Maven
更严格的"人工授权"派单（FGCN = 人工授权的教师/专家派单网络）。
**结论**：Maven 的分诊分层思路已经被 FGCN 的多阶段结构覆盖，无需新增角色。

### 3.2 结果证据可复现、公开发表

Maven 的 Clinical Research Institute 公开发表可复现研究（如"doula 支持
降低20%剖腹产率"），方法论开放供外部复用。

**代码现状**：`quality_contribution_application.py` 已经把"质量审核"和
"交付"做成两个独立的人工动作——只有审核通过才能产生 `ServiceContribution`
事实，且该模块显式声明"不调用 AI、不计算家庭价值、不产生资金/结算行"
（见该文件模块 docstring）。这已经是比 Maven 更保守的证据链设计。
**真实差口（很小）**：目前没有看到"把汇总后的贡献/结果证据公开发表或
提供给外部复现"的机制——Maven 的做法是把研究方法论开放给行业。这是否
值得做，取决于产品战略是否需要对外证明疗效，**不是当前技术债，是产品
决策，先不建议动代码**。

## 4. 小红书 — 机制已落地，且比原版更安全

`FamilyExperienceSignal`（`backend/domains/product_intelligence/domain/
family_experience_signal.py`）已经实现"去标识化跨家庭体验信号"：

- 无 `family_id`/`tenant_id`/儿童身份/家庭自由文本——结构上不可能出现
  "虚假种草"，因为它根本不是自由文本 UGC，而是系统记录的结构化结果verdict
  （`HELPED`/`PARTIALLY_HELPED`/`DID_NOT_HELP`），来自 `FamilyConfirmedOutcome`。
- 正负结果都记录（不是只记差评的投诉台账）——docstring 里显式讨论了这个
  设计取舍。
- 已有 `ComponentExperienceSummary`（`application/family_experience_signal.py`）
  做"家庭问题相似度搜索"的聚合，对应小红书"种草搜索"的产品形态。

**真实差口（具体、可执行）**：`summarize_by_component` 目前没有看到最小样本量
门槛——如果某个 component 只有 1-2 条信号就显示"100% helped"，这正是小红书式
社交证明最容易翻车的地方（小样本伪共识）。**建议**：给 `ComponentExperienceSummary`
加一个 `total_count` 阈值提示位（比如 `total_count < N` 时前端展示"数据尚不足以
形成结论"而非具体百分比），这是一个小增量，不涉及重新设计。

## 5. TikTok — 机制已落地一半，明确反例已规避

- **反例已规避**：FGCN 的曝光机制（`quality_contribution_application.py`）
  是"通过审核才产生贡献事实"，不是按流量/热度决定教师曝光，天然规避了
  TikTok 式"纯流量决定分发"的反例，不需要额外防护。
- **无限滚动/变量奖励/秒级反馈**：本项目未见任何面向家庭/儿童的信息流式
  交互组件，这类风险目前不存在于代码里，无需修复，只需要在未来做任何
  列表型 UI 时记住这条红线（可以写进前端设计准则，不必现在动代码）。
- **真实差口**：细粒度兴趣建模用于课程/教师资源匹配——目前
  `course_content` 域看不到基于家庭历史互动做匹配排序的机制（如果这属于
  product_intelligence 或 course_content 的既定范围之外，则不算差口，
  只是尚未排期的产品能力，不建议现在补，等有真实课程供给规模了再谈）。

## 6. 结论：这次唯一值得排的增量

对照代码现状，五家里只有**一个**是"小、具体、不涉及重新设计"的增量：

> 给 `ComponentExperienceSummary` 的消费端（API 响应或前端渲染规则）加最小
> 样本量提示，防止小样本伪共识误导家长决策。

其余的都已经落地或者是需要产品战略拍板的更大决策（Maven 式对外发表证据、
TikTok 式兴趣建模排课），不建议现在动代码。

## 7. 研究局限

- Maven Clinic 部分为本次实时抓取的一手官网资料（2026-09-03）。
- 小红书、TikTok 官方页面在本环境网络层被拦截（连接超时），未能实时核验，
  结论基于既有公开共识，置信度中等；后续网络环境恢复后应补一次核验。
