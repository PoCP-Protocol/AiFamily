---
id: EXPERIENCE-CONTRACTS-001
title: Family Experience Closed-loop Contracts V1
type: specification
status: draft
version: 0.1
owner: chief-architect
canonical: false
---

# Family 体验闭环契约（S0-01）

> 本文件只冻结体验闭环的数据边界和拒绝规则，不代表运行时能力已经上线。
> 当前交付状态为 `PLANNED/CONTRACT_ONLY`。

## 1. 为什么需要三个契约

核心蓝图中的“先情绪价值、再成长价值、最后经济价值”必须可观察、可解释、可修正，
但不能让推荐或 AI 输出越过 Family/Journey/Service/Commerce 的事实边界：

```text
ExperienceEvent（发生了什么）
  → RecommendationDecision（为什么给出这个候选）
  → FeedbackSignal（家庭接受、跳过、暂停、投诉或请求人工）
```

三个对象均为不可变记录，只能追加，不能直接创建家庭事实、成长结果、订单、服务验收
或贡献结算。事实写入必须通过相应领域的 Named Action、授权和审计。

## 2. 与家庭需求 N0-N8 的对应关系

| 契约 | 主要节点 | 作用 |
|---|---|---|
| `ExperienceEvent` | N0、N1、N5、N7、N8 | 记录测评/表达、内容与行动互动、服务意向和回流信号 |
| `RecommendationDecision` | N1、N2、N3、N4 | 记录教育内容、行动、产品/服务/方案候选及过滤/拒绝原因 |
| `FeedbackSignal` | N5、N6、N7、N8 | 记录完成、改写、跳过、暂停、投诉、人工请求和下一步偏好 |

体验记录不能替代 `NeedSignal`、`FamilyNeed`、`SolutionBlueprintVersion`、
`ServiceCase`、`QualityDecision` 或 `OutcomeEvidence`；它们只为这些对象提供可审计的
交互证据和候选建议。

## 3. 五层架构和六引擎对齐

- **业务**：服务家庭教育第一入口，向家庭需求编排、FGCN 高质量服务和商业闸门提供证据。
- **流程**：P0 体验闭环共享 E0–E4 闸门；家庭先被理解，再选择行动，主动表达服务需要后才进入经济选择。
- **数据**：每条记录含 `tenant_id`、`region_id`、`family_id`、`subject_ids`、`purpose`、
  `consent_version`、`data_class`、四类 locale、`provenance`、`deletion_ref`、
  `correlation_id` 和 `causation_id`。
- **应用**：34 个 UI 继续作为家庭渠道；事件、建议和反馈由 ExperienceApplication
  投影，业务域仍是事实唯一写入方。
- **AI**：`experience_curator` 只能经 Context、Registry、Safety、Model Gateway、
  Provenance 和人工/家庭闸门输出候选草案。

六引擎映射：教育定义 21/90 天节奏；游戏提供章节、小行动、暂停和非比较进度；字节式
分发使用授权反馈而非脆弱情绪/停留时长；海底捞式服务把投诉和人工请求放入补救队列；
贝壳式 FGCN 只在家庭主动表达服务需要后组织任务和贡献；拼多多式传播只能使用公开、
授权的案例和挑战，不以未成年人数据驱动营销。

平台精神 **We are 伐木累！We are family！** 体现为：先接住疲惫和无奈，给一个可以
跳过或暂停的小行动，允许家庭共同成长；“大家庭”不取消隐私、价格、责任和退出边界。

## 4. 规模、多语言、多租户和幂等

契约中的 scope 是每次推荐、事件、反馈进入缓存、流、评估集或删除索引前的最小隔离单元：

- 租户、家庭和主体必须精确匹配；跨租户/家庭/主体 join 直接拒绝。
- `IdempotencyKey` 按租户隔离；重试只能返回已存在的同一结果，不能重复产生体验副作用。
- `locale`、`content_locale`、`model_locale`、`policy_locale` 分开记录；不支持的语言或区域
  在入口拒绝，不能静默使用错误的政策。
- 未成年主体数据禁止用于 `marketing`、`upsell`、`sales` 等自动商业目的。
- `deletion_ref` 和 `provenance` 不可省略，以支持区域 Cell、数据删除、解释和重放。

## 5. 多模态边界

体验契约支持 `text`、`voice`、`image`、`audio`、`video` 和 `interactive_card` 六种
模态。`ExperienceMediaRef.operation` 必须标识它是 `input`、`output`、`transcription`、
`ocr` 还是 `playback`，不能把转写/OCR 结果伪装成用户原话：

```text
家庭输入（voice/image）
  → 受同意约束的转写或 OCR（新 media_id + 新 provenance）
  → Principal/experience_curator 草案
  → 文本/卡片/音频/视频输出
  → 家庭播放、跳过、暂停或反馈
```

媒体引用只保存区域 Cell 内的 `media_ref`，不把原始文件交给推荐事件。每个媒体及其派生
结果都必须带租户、家庭、主体、用途、同意版本、数据分类、语言、`provenance` 和
`deletion_ref`；删除源媒体时可沿 provenance/deletion 索引找到转写、OCR、缓存和播放
副本。私有/未成年人媒体没有有效同意时入口拒绝，过期媒体播放 fail-closed，跨租户/家庭/
主体的媒体挂载拒绝。模型供应商调用仍只能通过 `backend/intelligence/model_gateway`。

## 6. 孩子、家长与家庭关系记忆

体验上下文允许三类显式 `memory_scope`：`child`、`guardian`、`family_relationship`，
并用 `M0`（单轮）、`M1`（会话）、`M2`（旅程）和 `M3`（经复核的长期记忆）标记保留
范围。M0–M3 都必须有过期时间和删除策略；不存在“无限记忆”。

记忆读取前必须同时满足租户、区域、家庭、主体集合、用途、同意和有效期；家庭关系记忆
至少绑定两个明确主体，不能从孩子记忆推导家长画像，也不能跨家庭/租户共享。源记忆、
转写/OCR 等派生记忆通过 `derived_memory_ids` 组成删除级联，保留各自 provenance，供
区域删除 Worker 扇出。任何 `marketing`、`upsell` 或 `sales` 用途都拒绝进入记忆层，
尤其不能把未成年人记忆变成商业画像。

## 7. 当前状态和后续接线

实现文件为 `backend/intelligence/experience/contracts.py`，纯内存确认适配器为
`backend/intelligence/experience/memory_adapter.py`，测试文件为
`tests/intelligence/experience/test_contracts.py` 和 `test_memory_adapter.py`。适配器仅实现
`MemoryCandidate → confirm/retract/retrieve/delete-proof`，不接模型、不写领域事实；它是
契约验证用的 PLANNED 端口，不是生产记忆存储。当前尚未挂载 Family API，也未宣称
`experience_curator` 生产可用。下一步由 Lead/前后端 Agent 将契约接入 UI-03 → UI-05 →
UI-09 纵向切片，并由业务领域 Named Action 承接确认后的事实写入。
