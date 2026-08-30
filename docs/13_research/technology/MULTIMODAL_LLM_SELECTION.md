---
id: RESEARCH-MULTIMODAL-LLM-SELECTION-001
title: AiFamily 多模态 LLM 选型研究
type: research
status: draft
version: 1.1
owner: ai-platform
created: 2026-08-30
updated: 2026-08-30
canonical: false
evidence_class: RESEARCH_ONLY
supersedes: null
superseded_by: null
---

# AiFamily 多模态 LLM 选型研究

## 1. 建议

在不改变 `Model Gateway` 唯一入口的前提下，采用“双层模型策略”：

1. **S1 文本+图片首选：Qwen3-VL-Flash**。它适合家庭场景图片理解和结构化抽取，官方 Model Studio 价格页列出的国际标准价为输入 `$0.05 / 1M tokens`、输出 `$0.4 / 1M tokens`（小于 32K 输入档位）。
2. **后续音频/视频候选：Qwen3.5-Omni-Flash**。官方价格页列出文本/图片/视频输入 `$0.4 / 1M tokens`、音频输入 `$3 / 1M tokens`、输出 `$2.2 / 1M tokens`；能力页明确列出音频、视频理解和 Omni 模型。
3. **质量基准/备选：Gemini 3.7 Flash**。官方价格页列出 2026-12-31 前付费价输入 `$0.75 / 1M tokens`、输出 `$3.75 / 1M tokens`，Batch 价格为标准价的一半；官方定位为 agentic workflows 和 multimodal reasoning。

因此首个 Sprint 不需要同时接入三家。先将 Qwen3-VL-Flash 作为隔离环境候选，通过统一 OpenAI-compatible adapter 做 schema、延迟、成本、安全和中文家庭场景评估；Gemini 3.7 Flash 只进入同一 gold set 的对照组。任何候选的 `TECHNICALLY_VALIDATED` 都不等于可处理真实家庭或未成年人数据。

## 2. 官方证据

| 候选 | 官方能力证据 | 官方价格证据 | 本项目用途 |
|---|---|---|---|
| Qwen3-VL-Flash | [Alibaba Model Studio supported models](https://www.alibabacloud.com/help/en/model-studio/models) | [Alibaba Model Studio model pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing) | S1 图片理解、OCR/结构化抽取、低成本体验草稿 |
| Qwen3.5-Omni-Flash | [Alibaba Model Studio supported models](https://www.alibabacloud.com/help/en/model-studio/models) | [Alibaba Model Studio model pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing) | 后续音频/视频理解与语音体验预研 |
| Gemini 3.7 Flash | [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) | 同一官方价格页 | 质量基准、复杂多模态推理对照 |

价格是官方页面在 2026-08-30 可见的标准价，实际账单还受区域、免费额度、缓存、Batch/Flex、汇率和活动影响；不应把单次价格写死在产品代码中。

## 3. 选型评价矩阵

| 维度 | Qwen3-VL-Flash | Qwen3.5-Omni-Flash | Gemini 3.7 Flash |
|---|---|---|---|
| 首个图片切片成本 | 最低 | 中等 | 较高 |
| 图片/文档理解 | 适合 | 适合 | 适合 |
| 音频/视频统一理解 | 非首选 | 首选候选 | 可作为对照 |
| 中文家庭场景 | 必须用 gold set 验证 | 必须用 gold set 验证 | 必须用 gold set 验证 |
| 结构化输出 | 通过 Gateway schema 验证 | 通过 Gateway schema 验证 | 通过 Gateway schema 验证 |
| 合规可用性 | 未自动获得批准 | 未自动获得批准 | 未自动获得批准 |
| 生产状态 | 候选，默认不可调用 | 候选，默认不可调用 | 候选，默认不可调用 |

“好”不能只由模型榜单或价格决定。本项目必须以真实但匿名/合成的家庭场景 gold set 评估：结构化通过率、观察与推断边界、风险提示召回、中文表达、人工修改率、延迟、单位成本和失败可恢复性。

### 3.1 离线评分与合规闸门

`backend/intelligence/experience/model_benchmark.py` 提供不调用供应商的离线
harness。它只接收匿名 gold case 与已采集的逐 case 结果，因此评分本身不能绕过
`Model Gateway` 的 provider admission。

| 评分 | 定义 | 备注 |
|---|---|---|
| `quality_score` | schema 通过率 | 这里的“质量”只表示结构化契约质量，不代表教育效果 |
| `safety_score` | (`safety_pass_rate` + `refusal_accuracy_rate`) / 2 | 拒答正确性与安全标签同时纳入 |
| `cost_score` | 合规候选中的最低单位成本 / 本候选单位成本 | 只比较已观测的匿名评估成本 |
| `latency_score` | 合规候选中的最低 P95 / 本候选 P95 | 缺少 P95 时不补造数值 |
| `composite_score` | 0.35 × quality + 0.35 × safety + 0.15 × cost + 0.15 × latency | 固定权重写入 report，便于复核 |

未通过合规闸门的候选仍可展示离线测量值，但其四项运营评分与综合评分为 0，
不能据此进入运行时。闸门必须同时检查候选状态、环境、匿名数据许可、安全评估、
处理协议和转委托状态；任何一项不明均为 `BLOCKED`。评分不包含点击率、转化率、
家庭分数或家庭排名；教育结果统一标记为 `NOT_MEASURED`，需另建经批准的纵向评估。

### 3.2 本轮决策记录（研究结论，不是生产批准）

| 决策角色 | 候选 | 当前结论 | 进入条件 |
|---|---|---|---|
| `PRIMARY_IMAGE` | Qwen3-VL-Flash | 首个文本+图片 Web 纵向切片首选 | 先完成匿名 gold set、结构化/安全/延迟/成本评估；仍须通过 provider 合规闸门 |
| `FOLLOW_UP_OMNI` | Qwen3.5-Omni-Flash | 音频/视频阶段候选，不进入首个切片 | 完成音视频能力、成本、数据处理区域与转委托核验 |
| `QUALITY_BACKUP` | Gemini 3.7 Flash | 复杂多模态质量对照与备选 | 使用同一 gold set；不因质量对照自动获得生产调用权 |

以上是 `RESEARCH_ONLY` 阶段的实现顺序，不是对任何供应商的安全评估或生产授权。

## 4. 直接使用的工程方式

```text
Web Studio
  → MultimodalExperienceService
  → MultimodalRouteRequest
  → Provider Registry admission
  → Model Gateway / OpenAI-compatible adapter
  → Schema validation + provenance
  → DRAFT only
```

- 开发/测试：FakeProvider + Qwen/Gemini 隔离 livecheck，数据类仅 `SYNTHETIC` 或 `OPERATIONAL_TEXT`。
- 真实家庭数据：只有在供应商安全评估、处理协议、区域、转委托、删除 SLA、DPIA 和 Human Gate 完成后，才可将 registry 状态提升为 `INTERNAL_APPROVED`/`PRODUCTION_APPROVED`。
- 凭据：只由 Model Gateway 读取，前端、领域代码、Experience API 都不能读取。
- 降级：只在已经分别批准的 provider 之间按基础设施失败切换；不得为了“有答案”自动切到未审 provider。
- 结果：模型输出只产生 `ModelDraft(DRAFT)`；成就、行动、计划和产品交付必须基于真实事件与人工/领域 Named Action。

## 5. “极致体验、游戏感、成就感”的 AI 用法

AI 的职责不是发放虚构积分，而是：

1. 根据家庭当前上下文生成低摩擦的下一步候选，控制任务粒度和节奏；
2. 根据真实行动事件生成即时、具体、非比较性的反馈；
3. 将一次完成解释成可理解的成长叙事，并明确证据来源；
4. 根据家长反馈调整内容频率、表达方式和难度；
5. 在不确定、敏感或高影响情形下主动暂停并请求人工。

产品成就只能来自 `ExperienceEvent`、行动完成记录或人工确认的结果；模型不得凭空生成完成状态、家庭总分、家庭排名或儿童商业画像。

## 6. S1 试用验收

- 用同一份匿名/合成 gold set 对 Qwen3-VL-Flash 与 Gemini 3.7 Flash 做 A/B 离线评估；不把在线点击率当教育效果。
- 每个请求都记录 provider/model/version、prompt/schema、context ref、媒体 hash、延迟和 token/cost（供应商返回时）。
- 记录 schema 错误、超时、拒绝、人工升级和用户改写；失败不能返回原始模型散文。
- 没有合规批准时，任何真实家庭/儿童媒体请求必须稳定返回 `POLICY_REJECTED`，且 provider invocation 计数为零。

**RESEARCH_ONLY / NOT_CANONICAL**
