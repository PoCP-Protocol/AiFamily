---
id: RES-TECH-004E
title: 4e — AI 能力的 eval 体系与幻觉检测的实际有效手段
type: research
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: false
supersedes: null
superseded_by: null
---

```text
STATUS: RESEARCH_ONLY
NOT_CANONICAL: TRUE
本文件是证据，不是决定。晋升须走 ADR（docs/12_governance/DOCUMENT_GOVERNANCE.md §8.2）。
```

# 4e — 回归测试怎么做，幻觉检测哪些手段真的有效

**被检验的对象**：宪章 R10 要求 Evaluation 作为唯一 AI Runtime 的一份组件；R4"无测试不得声称能力可用"。`docs/05_ai/AI_ARCHITECTURE.md` 全文**未涉及 eval 体系**——这是本节要填的最大空白。

---

## 1. 幻觉检测：有实测数字的方法与其真实效力

### 声明 4e.1｜采样自一致性（SelfCheckGPT）是有实测数据的黑盒幻觉检测手段，最佳变体句级 AUC-PR 达 93.42
**置信度：high（一手，ACL/EMNLP 论文原文数据表，本轮已本地全文抽取核对）**

来源：Manakul, Liusie, Gales（University of Cambridge），"SELFCHECKGPT: Zero-Resource Black-Box Hallucination Detection for Generative Large Language Models"，arXiv 2303.08896。

方法核心：若 LLM 真的掌握某概念，多次采样的回答会彼此相似且事实一致；对幻觉内容，随机采样的回答会互相分歧和矛盾。**不需要输出概率分布，也不需要外部数据库。**

Table 2 完整实测数据（WikiBio 数据集，GPT-3 生成 238 段人物介绍，人工标注事实性）：

| 方法 | 句级 NonFact | 句级 NonFact* | 句级 Factual | 段级 Pearson | 段级 Spearman |
|---|---:|---:|---:|---:|---:|
| **Random（基线）** | **72.96** | **29.72** | **27.04** | – | – |
| GPT-3 Avg(−log p)（灰盒） | 83.21 | 38.89 | 53.97 | 57.04 | 53.93 |
| GPT-3 Max(−log p)（灰盒） | 87.51 | 35.88 | 50.46 | 57.83 | 55.69 |
| LLaMA-30B Avg(−log p)（代理 LLM） | 75.43 | 30.32 | 41.29 | 21.72 | 20.20 |
| LLaMA-30B Max(−log p)（代理 LLM） | 74.01 | 27.14 | 31.08 | **−22.83** | **−22.71** |
| SelfCheckGPT w/ BERTScore | 81.96 | 45.96 | 44.23 | 58.18 | 55.90 |
| SelfCheckGPT w/ QA | 84.26 | 40.06 | 48.14 | 61.07 | 59.29 |
| SelfCheckGPT w/ Unigram (max) | 85.63 | 41.04 | 58.47 | 64.71 | 64.91 |
| SelfCheckGPT w/ NLI | 92.50 | 45.17 | 66.08 | 74.14 | 73.78 |
| **SelfCheckGPT w/ Prompt** | **93.42** | **53.19** | **67.09** | **78.32** | **78.30** |

### 声明 4e.2｜必须对照基线读这些数字：随机基线的 NonFact AUC-PR 已是 72.96，头条数字 93.42 的实际增量远小于表面
**置信度：high（同一数据表的直接读法）**

**这是本文档最重要的一条方法论警告。** NonFact 列的随机基线是 **72.96**——因为该数据集中非事实句占比本身很高，正类基率高使 AUC-PR 天然虚高。真正体现区分力的是：

- **Factual 列**：随机基线仅 **27.04**，最佳方法 **67.09** —— 这是约 2.5 倍的真实提升
- **NonFact\* 列**（更难的任务：在非"整段幻觉"的段落中识别 major-inaccurate 句）：随机基线 29.72，最佳方法 **53.19** —— 即在真实困难场景下，**准确识别严重错误句的能力仅略高于五成**

**推论（对 AiFamily 有直接约束力）**：把 "93.42 AUC-PR" 当作"幻觉基本能检出"来采信是误读。在最接近生产的困难设定（NonFact*）下，最好的方法也只到 53.19。**因此幻觉检测只能作为分流/加权信号，不能作为"AI 输出可以自动成为 Fact"的依据。** 这正面支持 R9（AI 输出不直写 canonical 事实）与 R8（人工闸门）——它们不是保守，而是当前技术水平下的必需。

### 声明 4e.3｜代理 LLM 方案会失效到"比随机还差"，方法选择本身有失败模式
**置信度：high（一手，同一数据表 + 论文解释）**

LLaMA-30B Max(−log p) 的段级相关性是 **−22.83 / −22.71（负相关）**。论文解释：不同 LLM 有不同生成模式，当被评估的响应与代理 LLM 的生成风格不同时，即使常见 token 也可能得到低概率；换用 GPT-NeoX 或 OPT-30B 时性能"near that of the random baseline"。

**含义**：用"另一个模型去打分"这条看似便宜的路径**有明确的失败模式**——不是效果差一点，而是可能给出反向信号。AiFamily 若要做 LLM-as-judge，评判模型与被评判模型的关系是设计变量，不能随便挑一个便宜模型。

### 声明 4e.4｜作者自陈的三条限制，其中两条直接命中 AiFamily 场景
**置信度：high（一手，论文 Limitations 章节原文）**

1. **领域窄**：238 段文本"predominantly passages about individuals in the WikiBio dataset"，作者建议扩展到地点、物体等更多概念
2. **粒度粗**：本工作在**句级**判定事实性，但作者指出"a single sentence may consist of both factual and non-factual information"，并引 Min et al. (2023) 的原子事实分解作为更细粒度方向
3. **成本高**：表现最好的 SelfCheckGPT-with-Prompt "is quite computationally heavy. This might lead to impractical computational costs"

**对 AiFamily 的判定（推论）**：
- 限制 1 是**致命的适用性缺口**：WikiBio 是**可查证的百科事实**。AiFamily 的 AI 输出是 Hypothesis / Recommendation / Perspective——**根本不存在"客观正确答案"可供对照**。"孩子可能因为缺乏成就感而拖延"这句话不是事实陈述，无法判定 factual/non-factual。**因此 SelfCheckGPT 这类事实性幻觉检测对 AiFamily 的核心输出基本不适用。**
- 限制 3 意味着最优变体需要多次采样 + LLM 打分，成本是单次生成的数倍——对每一次家长交互都跑是不现实的，只能抽检。

**这条推论是本文档对 `AI_ARCHITECTURE.md` 最实质的补充**：AiFamily 需要的不是"幻觉检测"，而是**"违规检测"**——检测输出是否越过了 R9 红线（是否出现了打分/排名/类诊断断言/把假设写成结论）。后者是**规则可判定**的，前者不是。这是一个方向性的重新定位。

---

## 2. 回归测试：可用的确定性抓手

### 声明 4e.5｜受约束解码把"输出结构回归"从概率测试变成确定性测试
**置信度：high（一手；详见 4c.1/4c.2）**

因为受约束解码提供 schema 合规的硬保证（"No retries needed for schema violations"），**输出形状的回归测试是确定性的**：给定 schema，输出必然合规，测试只需断言 schema 本身未被意外放宽（例如某字段从 required 变 optional、`additionalProperties` 被改成非 false）。

**推论**：AiFamily 的 AI eval 体系应把测试分成两层，且只有第一层能做成确定性 CI 测试：

| 层 | 内容 | 可否确定性测试 |
|---|---|---|
| L1 结构与红线 | schema 合规、必填字段存在、**输出中不得出现总分/排名字段**、`may_mutate_business_state` 未被违反、provenance 齐全、confidence 在 0..1 | **可以**，属常规单测/架构测试 |
| L2 语义质量 | 建议是否恰当、假设是否站得住、话术是否符合"家是港湾"定位 | **不可以**，需人工评审或 LLM-as-judge（且受 4e.3 失败模式约束） |

L1 直接满足 R4/R14；L2 只能作为抽样质量流程，不能作为 CI 门禁。

### 声明 4e.6｜平台侧提供"rubric 打分 + 迭代修订"的评估回路，其参数与失败态是明确的
**置信度：high（一手，Anthropic Managed Agents Outcomes 文档）**

机制：发送 `user.define_outcome` 事件（含 `description` 与**必填** `rubric`，`{type:"text"|"file"}`），由**独立上下文窗口的 grader** 对每次迭代按 rubric 逐条打分，并把每条未达标项反馈给 agent 修订。

参数与终态：
- `max_iterations` 默认 **3**，最大 **20**
- 评估结果 `result` 取值：`satisfied`（终态）、`needs_revision`（再迭代）、`max_iterations_reached`、`failed`（rubric 与任务根本不匹配，如描述与 rubric 矛盾）、`interrupted`
- 事件：`span.outcome_evaluation_start` / `_ongoing` / `_end`，`_end` 携带 `explanation` 与 `usage`
- **grader 推理过程不透明**："Grader reasoning is opaque — you see *that* it's working, not *what* it's thinking."

官方对 rubric 写法的硬要求："Use explicit, gradeable criteria ('CSV has a numeric `price` column'), **not vibes** ('data looks good') — the grader scores each criterion independently, so vague criteria produce noisy loops."

**对 AiFamily 的含义**：这提供了一个可借鉴的 eval 形态——**可逐条打分的 rubric + 独立评判上下文 + 有界迭代**。但两条限制必须记录：
1. **grader 不透明** → 无法审计"为什么判定不合格"，因此不能用它承担 R8 闸门职责（闸门决策必须落库可审计）
2. **rubric 必须可逐条判定** → 这恰好把 AiFamily 的评估逼回 L1（红线/结构可判定），而"建议是否恰当"这类 vibes 标准官方明确说会产生噪声循环

---

## 3. 未获证据支持

1. **"回归测试怎么做"的行业标准做法**：本轮**未找到**任何关于 LLM 应用回归测试的一手工程实践文档（如某团队公开的 eval 套件设计、golden set 规模、通过阈值设定）。检索受限（WebSearch 在当前模型组不可用；DuckDuckGo 反爬；Brave 429 限流）。**"业界如何做 LLM 回归测试"未获证据支持**，本文档只基于平台机制文档给出可推导的结论（4e.5/4e.6），不假称这是业界做法。
2. **幻觉检测在生产环境的实际有效性**：SelfCheckGPT 的数字来自 WikiBio 学术数据集。**未找到任何生产环境的幻觉检测有效性数据。** 从学术数字外推到生产是不可靠的。
3. **非事实性输出（建议/假设）的质量评估方法**：这是 AiFamily 真正需要的东西。本轮**未找到任何针对"建议类输出"（无客观正确答案）的可复现评估方法与实测数据**。这是一个真实的方法论空白，不是检索失败——现有的幻觉检测文献几乎全部假定存在可查证的事实基准。
4. **多次采样一致性对中文的有效性**：SelfCheckGPT 的实验全为英文。**中文场景的有效性未获证据支持。**

---

## 4. 建议走 ADR 的结论

| 结论 | 依据 | 影响文档 |
|---|---|---|
| AI eval 体系分 L1/L2 两层：**只有 L1（结构 + 红线）可作 CI 门禁**；L2（语义质量）只能作抽样人工评审，不得作为门禁 | 4e.5、4e.6 | `docs/05_ai/AI_ARCHITECTURE.md`（新增 eval 节）、`docs/10_engineering/` 测试策略 |
| AiFamily 需要的是"**违规检测**"（是否越过 R9 红线：打分/排名/类诊断/假设写成结论）而非"幻觉检测"——前者规则可判定，后者对无客观答案的建议类输出基本不适用 | 4e.4 | 同上 |
| 幻觉/事实性检测只能作为分流与加权信号，**不得作为 AI 输出自动升格为 Fact 的依据**（最难设定下最佳方法仅 53.19 AUC-PR） | 4e.1、4e.2 | 同上 + `AI_ARCHITECTURE.md` §4.3 |
| 若采用 LLM-as-judge，评判模型与被评判模型的关系是设计变量并须实测；代理模型方案有产生**反向信号**的实证失败模式 | 4e.3 | 同上 |
| 若借鉴 rubric 评估回路：rubric 必须逐条可判定；且因 grader 推理不透明，**不得由其承担 R8 闸门职责** | 4e.6 | 同上 + Human Gate 规格 |
| L1 必须包含一条专门断言：AI 输出中不得出现家庭总分/排名字段（R9 红线的机械化，符合 R14） | 4e.5 | `tests/architecture/` 或领域测试 |

---

## 5. 声明汇总

| # | 声明 | 置信度 | 来源类型 |
|---|---|---|---|
| 4e.1 | SelfCheckGPT 最佳变体句级 NonFact AUC-PR 93.42、段级 Spearman 78.30 | high | 一手（论文数据表） |
| 4e.2 | 必须对照基线读：NonFact 随机基线已 72.96；最难设定 NonFact* 最佳仅 53.19 | high | 一手（同表直接读法） |
| 4e.3 | 代理 LLM 方案可产生负相关（−22.83），有明确失败模式 | high | 一手 |
| 4e.4 | 作者自陈三限制：领域窄（百科人物）、句级粒度粗、最优变体成本高；前者致 AiFamily 建议类输出不适用 | high | 一手（Limitations）+ 推论 |
| 4e.5 | 受约束解码使结构回归成为确定性测试；eval 应分 L1/L2 | high | 一手 + 推论 |
| 4e.6 | rubric + 独立 grader + 有界迭代（默认 3 / 上限 20）；grader 推理不透明；rubric 须逐条可判定 | high | 一手 |
| — | 业界 LLM 回归测试实践、生产幻觉检测有效性、建议类输出评估方法、中文有效性 | **未获证据支持** | 检索受限 / 文献空白 |
