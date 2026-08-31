---
id: PRD-SLICE-01-PROBLEM-UNDERSTANDING-001
title: AiFamily Slice 01 问题表达—AI理解—家长确认规格 V1
type: product
status: draft
version: 1.0
owner: chief-architect
created: 2026-09-01
updated: 2026-09-01
canonical: false
supersedes: null
superseded_by: null
---

# AiFamily Slice 01｜问题表达—AI 理解—家长确认规格 V1

> 本文件把“家长说出困扰，平台形成可修正理解，家长确认或拒绝，产生 GrowthIntent 交接凭证”定义成可实现的产品纵切。它吸收项目负责人提供的《Problem → GrowthCase → AI Understanding → Confirmation》作为研究输入，但不把其中的目标表、API、状态机或 Patch 清单直接视为施工授权。Current Truth 以 main/ref、Registry、migration 和可运行测试为准。

配套交付编排见 `AIFAMILY_SLICE_01_FULL_STACK_DELIVERY_SPEC_V1.md`。本文件拥有产品语义，配套文件只定义全栈增量和联合验收，不另建一套业务真相。

## 1. 产品结果

作为第一次使用 AiFamily 的家长，我可以用文字、语音或必要图片说出家里最近发生的一件事；法咪莉先理解我的处境，只追问真正影响判断的信息，再把“我说过什么、平台目前怎么理解、仍不知道什么”清楚地交给我确认或修改。

Slice 结束时只产生一个结果：

> 家长确认“这足以代表我们现在想先处理的事情”，形成可回读的 `GrowthIntent`/确认 receipt。

它不表示 AI 的理解成为客观事实，也不表示问题已经改善。

```text
用户表达 ≠ 客观事实
AI 理解 ≠ 家庭权威事实
家长确认方向 ≠ Outcome
成长需要/意图 ≠ ServiceCase
```

## 2. 与全量 MVP 的关系

本 Slice 是 S1“第一次被理解”的入口段，服务 J1→J2；它与 Assessment 入口汇合，但不强迫所有家庭先测评。

```text
Ask Famili 路径
表达 → 澄清 → Understanding Draft → 家长决定 ┐
                                                  ├→ GrowthIntent receipt → S2
Assessment 路径                                   │
Session → Evidence → GrowthHypothesis → 家长决定 ┘
```

Slice 01 不是全量 MVP 的全部。S2–S6 继续由各自 PRD 承担；本 Slice 只冻结与它们的交接，不扩张到介入、行动、服务、直播、社区或交易实现。

## 3. 证据基线

### 3.1 Git 事实

截至 2026-08-31 本文起草时：

| 层级 | Ref | 可声称内容 |
|---|---|---|
| local `main` | `0fa84a1aedaf876eb47890b7b6a55c17ec497fc4` | 本地 main 基线，不等于远端最新 |
| `origin/main` | `4c2b7721bf1dd0354bc0c2a0ef2dc083c37c09ff` | 当前远端跟踪 ref；与 local main 不一致 |
| 本规格父提交 | `86cf9446e3c130cad7c810d5a45b6c3a0f6fa6d8` | `codex/chief-bc-plan` 的领域边界文档提交，不是 main |
| Assessment Action WIP | `codex/family-assessment-action-loop@7e9187bcfc528409f2f6e5f2c02baee1528d3a85` | 分支候选；含 Assessment 支持卡/行动回访与前端变化，不是 main 能力 |
| Assessment UX WIP | `codex/family-assessment-s01@78172c104353fcc68a5b1b56a8f2005f9a6315fc` | 正向体验候选，不在本分支祖先链 |
| Journey WIP | `codex/journey-wave-b@765b843` | Journey 候选 ref，未因存在分支而成为 main 能力 |

任何后续实施必须重新读取 refs；本文中的 commit 是证据快照，不是永久基线。

### 3.2 可复用的现有资产

| 资产 | 当前价值 | 边界 |
|---|---|---|
| Assessment 四层模块 | Session、Response、GrowthHypothesis、决策、API 和 repository 形状 | 当前是测评路径，不是通用问题理解 Context |
| GrowthHypothesis 决策 | `CONFIRM/DISMISS`，确认后返回 `HUMAN_CONFIRMED_INTENT_NOT_OUTCOME` | 尚无 `CORRECT/ADD_CONTEXT` 通用协议 |
| Model Gateway | structured Draft、provider gate、timeout、provenance、fail-closed | 尚无正式 Problem Understanding 业务调用方 |
| Platform Core | actor/tenant、authorization、Consent Gate、Audit、idempotency、UoW | 完整 Family/Guardian/Consent record 与所有域原子接线未闭合 |
| Journey 候选 | `JourneyPlan`、FamilyPractice、PracticeRecord、PhaseReview | 属后续 S2，不纳入本 Slice 实现 |
| `family-assessment-action-loop` | conversation-led UI、支持卡、行动/回访实验资产 | 逐文件复核后作为 S1体验/S2候选，不整体合入 |

现有 Assessment 边界还有两项必须修复的技术债：Assessment repository 声明并实现 `load_or_create_growth_intent`，越界拥有 Growth 写入；GrowthHypothesis 的确认 handler 会再次执行 interpretation，可能导致家长确认的不是此前看到的同一 Draft 版本。目标实现必须固定用户实际查看的 Draft，确认事务中不得重新调用 AI/interpretation。

### 3.3 只能作为研究/迁移证据的资产

`database/baseline/0020_growth_orchestration_v1.sql` 定义了 `growth_need_inputs`、`growth_need_signals`、`growth_intents` 和 service orchestration 对象，语义与本 Slice 高度相关。该 baseline 由 `0001_legacy_schema_baseline.py` 纳入 Alembic 链，因此 fresh baseline upgrade 后可能存在这些表；但这仍是历史 schema 快照，不代表 Growth Python Domain、ORM、owner 或产品能力已经成立。Assessment SQLAlchemy repository 已访问 `growth_intents`，说明运行依赖真实存在，同时也暴露了跨域 owner 缺口。

因此：

- 可以复用 `raw input → non-canonical signal → human-confirmed intent` 语义；
- 不得仅凭 baseline 文件宣称当前环境、ORM 或产品链已经可用；
- 不得直接复制 baseline SQL 到新 migration；
- migration owner 必须核对完整链、现有列、FK、回滚和真实 PostgreSQL；
- `families/persons/relationships/consents` 的历史 SQL 同样不等于 Python Family/Consent 业务能力已完成。

还存在明确 migration 冲突：本分支 Journey 候选使用 `0004_journey_mvp_persistence.py`，Action Loop 分支使用另一个 `0004_assessment_support_loop.py`。两者从旧链分叉，禁止直接 cherry-pick 或并列进入同一 Alembic 链，必须由 migration owner 重新编号、校验 down_revision 并提供 fresh PG upgrade/downgrade/restart 证据。

## 4. Slice 内的业务语言

| 用户语言 | 内部语义 | 是否为事实源 |
|---|---|---|
| “我想说说最近发生的一件事” | Need/Problem Intake | 原始表达是用户报告事实 |
| “我目前这样理解” | `ProblemUnderstandingDraftV1` | Perspective/Draft |
| “我还想确认” | Clarification Question | AI Draft |
| “对，就是这样” | Guardian `CONFIRM` decision | 决策事实 |
| “有一点不对” | `CORRECT` + 新输入 | 决策和新用户报告 |
| “我还想补充” | `ADD_CONTEXT` + 新输入 | 新用户报告 |
| “这不是我要解决的” | `DISMISS` | 决策事实，不产生 Intent |
| “我们先从这个方向开始” | `GrowthIntent` / confirmation receipt | 家长确认的意图，不是 Outcome |

前端不显示 `GrowthCase`、`GrowthNeedSignal`、`canonical_family_fact`、`provenance` 或 `idempotency` 等内部语言。

## 5. 是否建立 GrowthCase

附件建议用 `GrowthCase` 容纳多轮输入、理解版本和长期处理过程，这个业务问题真实存在，但当前不能直接建表：

1. `FamilyNeed/GrowthNeed/GrowthIntent/Problem/Case` 的关系尚未有 Accepted ADR；
2. baseline 的 `growth_need_*` 只是历史结构；
3. Journey/Service 已各有自己的长期过程语义；
4. 通用 Case 容易成为所有对象的强制外键和超级聚合。

### 5.1 本 Slice 推荐的最小边界

P0 不创建 `GrowthCase` 或新的 `NeedUnderstandingSession` Aggregate。确认前使用现有语义的输入/信号版本组织协作，确认后使用 GrowthIntent 与 receipt 交接：

```text
确认前：tenant_id + family_id + conversation_id/correlation_id
       + input_ref + signal_ref/version

确认后：growth_intent_id + receipt_ref + correlation_id
```

这足以支持多轮输入、澄清、修正、Draft 版本、Guardian 决定和 Journey 消费。只有同时出现“一个问题跨多个 Intent、独立责任人/SLA、必须关闭/重开/转交、跨 Journey/Service 长期协调，且 Intent+receipt+projection 无法表达”时，才重新通过 ADR 论证 `GrowthCase`。

### 5.2 标识语义

```text
family_id / subject_ref       家庭与服务对象作用域
conversation_id               本次对话/协作分组，不是业务事实根
input_id / draft_id           本 Context 的事实身份
growth_intent_ref             确认后的业务交接
receipt_ref                   跨场景稳定凭证
correlation_id / causation_id 技术追踪
```

`subject_ref` 初始允许为空，因为家长可能表达的是家庭氛围、夫妻协作或尚未明确涉及谁的问题。

## 6. 产品流程

### 6.1 Screen 1｜低门槛表达

入口文案：`说说家里最近发生的一件事`。

支持：

- 文字直接输入；
- 语音录入并在提交前显示可编辑转写；
- 图片作为补充上下文，必须由家长添加说明；
- 不要求首次填写完整家庭画像或固定测评。

提交后立即保存不可变的用户表达版本，并显示温和、具体的接纳反馈；不能让家长面对长时间“AI分析中”。

### 6.2 Screen 2｜先确认系统听到了什么

语音与图片处理结果先以可编辑转写/描述呈现。家长可以删除误识别片段、补充时间和人物，也可以暂不指定家庭成员。机器派生文字没有经过家长确认前不能冒充用户原话。

### 6.3 Screen 3｜必要澄清

每轮最多 1–3 个真正改变理解或下一选择的问题。每个问题包含 `why_needed`，但家长端用自然语言表达。允许：

- 回答；
- “我不确定”；
- 跳过该问题；
- 改正上一条表达；
- 暂停并稍后继续。

AI 不得为了填满 schema 追问年龄、成绩、收入、夫妻关系等全部信息。

### 6.4 Screen 4｜家庭理解地图

理解地图分五层：

```text
你刚才告诉我的       用户明确表达，带来源
我目前的理解         AI Perspective
可能还有别的解释     Alternative explanations
你们已经拥有的力量   Family strengths
你希望先改变的       候选 desired change，允许编辑
我还不确定的         Unknowns
```

只有来自版本化 Assessment 的维度结果才能进入可交互雷达图。雷达图显示量表锚点、Evidence 和 Unknown，不显示家庭总分、默认 50 分或虚构同龄均值。

### 6.5 Screen 5｜逐项校正

每条理解都支持“准确、部分准确、不准确、换一种说法、还缺一件事”，而不只是整卡二选一。操作：

- `对，就是这样`；
- `有一点不对`；
- `我还想补充`；
- `这不是我要解决的`。

### 6.6 Screen 6｜确认成长重点

- `CONFIRM`：生成/请求 Growth owner 创建 `GrowthIntent`，返回 confirmation receipt；
- `CORRECT`：旧 Draft 保留并标 superseded，新建用户输入后重新理解；
- `ADD_CONTEXT`：追加输入，不隐式确认旧 Draft；
- `DISMISS`：关闭本次理解协作，不产生 GrowthIntent；
- Assessment 建议仅在 Evidence 缺口明确时作为可选下一步；
- 下一页只说明“接下来可以怎么继续”，不在本 Slice 自动生成课程、专家、直播、购买或介入。

确认后的支持选择可以包括：深化专项测评、查看知识与解释、设计最小充分家庭介入、邀请另一位家庭成员补充、寻求真人支持或先保存继续观察；不应自动降格成“做一件小事”。

### 6.7 Screen 7｜形成连续服务入口

结果页展示当前理解版本、家长修正、Evidence、相关 Assessment 和继续入口，告诉家长“以后补充的观察、测评、方案和复盘会回到这个成长重点”，而不是只显示“完成”。

## 7. 多模态输入边界

Growth/Understanding 只保存业务需要的 `SourceRef` 与转写/描述，不拥有媒体执行对象：

```text
InputSourceV1
source_type: TEXT | VOICE_TRANSCRIPT | IMAGE_DESCRIPTION | ASSESSMENT_REF
source_ref
user_reported_text
media_asset_ref?
transcript_ref?
language
captured_at
```

语音转写和图片理解产生的文本必须标明 `machine_derived`，允许家长在进入 AI Understanding 前修改。原媒体、转写、Draft 和索引共享 deletion lineage，但不在 Growth 表内复制二进制或供应商状态。

## 8. AI Use Case

候选唯一用例：`family_problem_understanding_v1`。当前 `governance/AI_USE_CASE_REGISTRY.yaml` 不存在，因此这里只定义待登记 contract，不声称已经注册。

```text
input:  FamilyUnderstandingContextV1
output: ProblemUnderstandingDraftV1
tools:  family_context_read, need_taxonomy_read
may_mutate_business_state: false
requires_confirmation: true
```

### 8.1 `ProblemUnderstandingDraftV1`

```text
summary
explicit_claims[]:
  statement / source_input_refs
inferred_context[]:
  statement / basis / alternative_explanations / source_input_refs / boundary=PERSPECTIVE
subjects[]
situations[]
patterns[]
family_strengths[]
desired_change_candidate
dimension_profile?:
  assessment_version / dimension_ref / observed_position
  scale_anchors / evidence_refs / unknowns
unknowns[]:
  key / question / why_needed / can_skip
limitations[]
risk_signals[]
proposed_next_step: ASK_CLARIFICATION | ASK_CONFIRMATION | HUMAN_REVIEW
confidence: calibrated number | null
```

没有经过校准的 confidence 必须为 `null`。Unknown 不得由模型补齐；explicit claim 与 inference 必须分开展示和存储。`proposed_next_step` 是 AI 建议，最终流程迁移由 Application Policy/具名 Command 决定。

### 8.2 Context Snapshot

最小 Context 只包含当前 purpose 所需信息：actor/family/subject refs、ordered inputs、明确相关的关系/Assessment refs、Consent snapshot、taxonomy version。Context Engine 通过公开 Port 获取裁剪后的 snapshot，不 import Family/Growth repository，也不把全部家庭历史发送给模型。

无 admitted provider 时返回可恢复的“智能理解暂时不可用”；test/sandbox 可使用显式 synthetic provider，不能伪装真实 AI 成功。

## 9. Domain 与 Application Contract

### 9.1 候选 Commands

```text
RecordGrowthNeedInput
AppendGrowthNeedInput
RequestUnderstandingDraft
RecordUnderstandingDecision
ConfirmGrowthIntentFromUnderstanding
```

`ConfirmGrowthIntentFromUnderstanding` 最终必须由 Growth owner 实现。Assessment 的现有 confirm bridge 未来也调用同一 Growth Application Port，Assessment 不再直接拥有/写入 `growth_intents`。

### 9.2 候选 Queries

```text
GetGrowthNeedInputThread
GetCurrentUnderstandingCard
GetUnderstandingTimeline
GetGrowthIntentReceipt
```

### 9.3 候选 Events / Receipts

```text
NeedInputRecorded
UnderstandingDraftProposed
ClarificationRequested
UnderstandingDraftSuperseded
UnderstandingDecisionRecorded
GrowthIntentConfirmed
NeedUnderstandingDismissed
```

若 `GrowthCase` 尚未被 ADR 接受，不使用 `GrowthCaseOpened` 等事件名。AI 风险信号只产生 review request，不自动改变 Need/Growth 状态。

## 10. HTTP Contract 候选

最终路径需由 Growth/API owner 会签；本规格建议避免 `/problems` 与通用 `/cases`：

```text
POST /families/{family_id}/growth/need-inputs
POST /families/{family_id}/growth/need-inputs/{input_id}/understandings
GET  /families/{family_id}/growth/understandings/{signal_id}
POST /families/{family_id}/growth/understandings/{signal_id}/decisions
GET  /families/{family_id}/growth/intents/{intent_id}
```

所有 Mutation 使用 `Idempotency-Key`；correlation ID 可由客户端提供或服务端生成并回传。相同 key + 相同规范化 payload 返回原 receipt；相同 key + 不同 payload 返回 409。Authentication 缺失为 401，已认证但无 family scope 为 403；跨 family 不泄露对象详情。

现有 Assessment decision API 保留为兼容 facade，内部最终委托同一 Growth confirmation command。明确不新增 `/growth-cases`、`/problems-v2`、`/confirmed-problems` 或 `/understanding-decisions-v2`。

## 11. 持久化原则

本规格不预先命名表。经 ADR/owner 接受后，migration 必须证明：

- input append-only，保留 source/provenance；
- Draft versioned，CORRECT 不覆盖旧版本；
- decision append-only，CONFIRM 幂等只产生一个 Intent receipt；
- subject nullable；
- confidence nullable；
- domain row + canonical Audit + Outbox + idempotency receipt 同事务；
- PostgreSQL 重启后完整回读；
- 撤回/删除传播到原媒体、转写、Draft、索引和供应商副本；
- upgrade→downgrade→restart→upgrade 和 ORM/schema parity 通过。

不得从 baseline 直接复制表，也不得由 Assessment repository 长期跨边界直写 Growth 表。

AI 调用不能占用业务数据库写事务：先读取并关闭授权 ContextSnapshot 事务，再调用 Model Gateway；结构校验通过后开启新事务写 signal/version、AI run ref、Audit、Outbox 与 idempotency receipt。Guardian 决定事务锁定 signal/version，且不得重新运行 AI。

## 12. 前端体验状态

| 状态 | 用户体验 |
|---|---|
| Empty | 给一个具体但不诱导的开场例子 |
| Capturing | 可见录音/转写状态，可取消 |
| Clarifying | 一次少量问题，可跳过/不确定 |
| Draft ready | 四层理解卡与明确修改入口 |
| Correcting | 原理解不消失，显示正在根据补充重新整理 |
| Confirmed | 显示已确认的关注方向和可选下一步 |
| Dismissed | 明确未保存为成长方向，可重新开始 |
| AI unavailable | 保留已输入内容，可稍后重试或仅保存 |
| Consent withdrawn/expired | 停止继续处理，说明可执行的恢复/删除状态 |
| Conflict | 不重复创建，重新加载最新版本 |

视觉交付必须使用真实字体层级、插画/图片策略、语音波形、留白和微动效；不得把 `fixture`、`provider`、`PERSPECTIVE_NOT_FACT` 等开发语言放进 UI。

### 12.1 已知现有体验冲突

- `frontend/mobile/app/ui/UI-03.tsx` 仍包含默认 50 分、`overall_score` 与 `peer_reference` 展示；
- `backend/domains/assessment/api/responses.py` 仍暴露相应总分/同伴参照契约；
- `backend/domains/assessment/api/requests.py` 当前 decision 只有 `CONFIRM/DISMISS`；
- `frontend/mobile/app/ui/UI-02.tsx` 仍以预设关注分类为主要开始方式；
- `codex/family-assessment-s01@78172c1` 的“依据/未知/修正”方向可以复核，但不能直接视为已集成。

多维雷达图本身不是问题；问题是默认分数、总分、虚构同伴参照和不可追溯解释。目标 UI 保留有意义的维度位置、量表锚点、Evidence、Unknown 与版本变化，并允许家长逐项修正。

## 13. 验收矩阵

### 13.1 正向

1. 家长输入一句真实困扰；
2. 系统保留原始表达；
3. AI 只问 1–3 个必要问题；
4. 确认卡区分 explicit claim、inference 和 unknown；
5. 家长先修正，再看到新 Draft；
6. 家长确认后只产生一个 GrowthIntent receipt；
7. 新会话与进程重启后完整回读。

### 13.2 拒绝与恢复

- 不回答某个问题仍可继续或暂停；
- `DISMISS` 不产生 Intent；
- `CORRECT` 不覆盖旧 Draft；
- provider timeout/schema invalid 不渲染成功；
- 无 provider 时保留输入并允许稍后重试；
- 同幂等键同 payload 重放，同键异 payload 409；
- 版本冲突重新加载最新 Draft；
- 跨 family、撤回、过期和删除路径可复核；
- Voice/Image 处理失败不破坏文字输入路径。

### 13.3 AI 输出

- 每条 explicit claim 有 source refs；
- inference 不伪装用户原话；
- unknown 不被补全；
- schema 无效整体拒绝；
- provider/model/prompt/schema/context/latency/data class/use case provenance 完整；
- AI 无创建 GrowthIntent、ServiceOrder、Action 或购买的工具；
- confidence 未校准时为 null。

### 13.4 真实环境与 artifact

完成证据至少包括：

- clean checkout 的 API/domain/AI/前端测试；
- 真实 PostgreSQL migration、restart readback；
- 真实 HTTP 正反路径；
- 浏览器/移动端录屏：表达→澄清→修正→确认；
- 四张关键截图：输入、澄清、理解卡、确认结果；
- 一份脱敏/synthetic trace 展示 input→draft→decision→receipt；
- branch、commit、main、artifact、real environment、production 分层状态。

## 14. 产品指标

| 指标 | 正确解释 |
|---|---|
| Time to First Useful Reflection | 从首次表达至看见有价值理解的时间 |
| Understanding Confirmation Rate | 用户有意识确认的比例，不追求强制提升 |
| Initial Misunderstanding Rate | 第一次 Draft 被指出关键错误的比例 |
| Correction-to-Alignment Rate | 修正后能否快速达到共同理解 |
| Clarification Burden | 确认前轮次、问题数和退出率 |
| Unknown Disclosure Quality | 关键未知是否被诚实表达且不阻塞所有人 |
| Intent Readback Success | 确认结果跨会话/重启可回读比例 |
| Recovery Success | AI/网络/冲突失败后保留输入并恢复的比例 |
| Provenance Completeness | AI Draft 的来源链完整率 |

Correction Rate 不能单独追求越低越好；过度模糊的 Draft 也可能获得低修正率。必须与具体性、首次误解率和修正后对齐率联读。

## 15. 实施增量与责任门

| 增量 | 用户可见结果 | 技术边界 | 前置裁决 |
|---|---|---|---|
| D0 语义/owner | 无代码 | Need/Intent、明确不建GrowthCase、Growth owner、receipt | ADR/Registry owner |
| D1 Intake foundation | 可以保存并继续一次表达 | input/signal thread、family scope、Audit/Outbox | Family/Consent read contract |
| D2 Understanding card without external AI | 可演示完整确认/修正状态 | typed Draft fixture only in test | API/DTO/decision contract |
| D3 AI Understanding | 看到真实 structured Draft/clarification | Context Port、Model Gateway、provenance | AIUC owner/provider gate |
| D4 Confirmation | 确认/修正/拒绝并回读 receipt | Growth Application Port、idempotency | GrowthIntent ownership |
| D5 Assessment convergence | Ask 与 Assessment 进入同一 Intent contract | Assessment 不再直写 Growth table | 跨域 migration plan |
| D6 E2E | 完整多模态场景可展示 | UI/API/PG/AI clean ref | QA/Experience/Release signoff |

这些是依赖增量，不是七个可以同时修改共享文件的团队。每个增量必须有单一 DRI、窄 pathspec、接口 owner 和失败停止条件；可并行的是互不重叠的 UX prototype、contract test、AI eval fixture、migration research 和 accessibility review。

WIP 使用规则：Assessment 的 Session/Response/Hypothesis、人工确认→GrowthIntent 模式和 ModelDraft 边界可 `REUSE`；Assessment 直写 GrowthIntent、旧 score/peer DTO、Action Loop 的“小步骤”语义和 Journey 挂载需 `REFACTOR`；禁止整体复制 `family-assessment-action-loop@7e9187b`、复制其冲突 `0004`、把分支 ADR 冒充主线裁决，或新建 `ProblemV2/ConfirmedProblemV2`。

## 16. 明确不做

Slice 01 不实现课程/专家/直播/社区/支付/会员推荐、完整 Intervention、Outcome、长期 Memory 或复杂 Multi-Agent。它也不新建第二 Assessment、第二 Model Gateway、第二 Consent、第二 Audit/Outbox 或第二 GrowthIntent。

不做这些并非缩小全量 MVP，而是保持本 Slice 的输入输出稳定；其他 S2–S6 通过独立场景团队并行建设，并只消费本 Slice 的 accepted receipt contract。

## 17. 进入施工前必须完成

1. Accepted ADR：FamilyNeed/GrowthIntent 的关系、Growth canonical owner，以及 P0 明确不建 GrowthCase；
2. Growth、Family、Consent、AIUC、API、migration、Experience、QA owner；
3. baseline SQL 与 canonical Alembic/ORM 的逐表差距报告；
4. Assessment confirm bridge 的过渡与迁移方案；
5. API/DTO/event/receipt version 冻结；
6. Current WIP 的逐文件 `REUSE / REFACTOR / RETIRE / DO_NOT_COPY` 清单；
7. 首个 synthetic scenario pack 和可展示 UX prototype。

本文件完成只代表产品与开发规格候选已形成，不代表 Slice 01 已实现、main 已具备、AI provider 已准入或 production 可用。
