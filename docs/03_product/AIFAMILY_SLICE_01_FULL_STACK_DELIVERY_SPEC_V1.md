---
id: PRD-SLICE-01-FULL-STACK-DELIVERY-001
title: AiFamily Slice 01 全栈纵切交付规格 V1
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

# AiFamily Slice 01｜全栈纵切交付规格 V1

> 本文件是 `AIFAMILY_SLICE_01_PROBLEM_UNDERSTANDING_SPEC_V1.md` 的交付配套规格。前者定义产品语义与领域边界；本文件定义如何把“家长表达—AI 共同理解—家长修正/确认—GrowthIntent”做成可运行的 App/Web/API/Domain/AI/Data 闭环。附件《FGK-01 前后端一体化设计 V2.0》是重要设计输入，不自动成为 canonical 架构或施工授权。

## 1. 交付目标

家长能在同一条连续体验中：

```text
自然表达一件真实困扰
→ 确认语音/图片转写
→ 回答 1–3 个高价值澄清
→ 看见平台当前理解、依据与未知
→ 逐项补充或修正
→ 确认现在真正希望改变的方向
→ 获得可恢复的 GrowthIntent 交接凭证
```

一个能力只有在用户体验、前端、API、Domain、AI、数据和场景测试共同闭环后才算完成。不得再以“后端完成百分比”“UI 完成百分比”替代产品结果。

## 2. 开发方法

每个增量都从用户可观察结果开始，并同时回答：

1. 家长看到什么、做什么、得到什么；
2. App/Web 进入什么状态，刷新或重启后如何恢复；
3. 调用哪个共享契约和 API；
4. 哪个 Application Use Case 与 Domain owner 处理变化；
5. 写入哪些数据、版本、Audit 与 Outbox；
6. AI 生成何种 Draft，失败后保留什么；
7. 正向、反向、恢复和真实环境证据是什么。

禁止重新回到“Domain 全做完→数据库→API→最后接前端”的瀑布式交付。

## 3. Current Truth 与目标差距

### 3.1 可以复用

- 当前 UI-01 已有真实困扰文本入口、失败重试与后续调用经验，但仍强制选择孩子并过早进入推荐/服务；
- 当前 UI-02 是结构化 Assessment 页面；自由表达、语音、本地草稿和 `inferInternalFocus()` 只存在于可审 WIP，不是 main/当前分支已接通能力；
- 当前 UI-03 已接 Assessment/Hypothesis，并有结果解释雏形；“家庭关注、未知、补充上下文”等更完整体验同样主要来自 WIP 设计证据；
- Assessment 已有版本化量表、解释边界、AI run ledger、repository 与 HTTP 候选；
- Model Gateway、Consent、Idempotency、Audit/Outbox 与 Journey 已有不同成熟度的候选资产；
- baseline 中存在 `growth_need_inputs`、`growth_need_signals`、`growth_intents` 等历史 schema。

### 3.2 必须修正

- WIP 中 UI-02 的 `inferInternalFocus()` 只能辅助 Assessment 题目路由，不得代表“平台理解了家庭”；
- UI-03 的默认 50、`overall_score`、`peer_reference`、总分与同伴比较不得进入目标体验；
- Assessment repository 不应长期直接拥有 Growth 表；
- 家长确认时必须锁定其看到的 signal/version，不能重新执行 AI interpretation；
- `family-state-core.ts` 不再承载新的远程业务真相；
- `family-api-client.ts` 可复用底层 request，但新增能力应有聚合后的 feature client；
- baseline 表存在不等于 canonical Domain、ORM、owner 或运行能力存在。
- 当前仓库没有可运行的 `frontend/web`，Web 端属于目标能力；已有 Web build 候选只能选择性复用构建壳，不能被视为本 Slice 已实现。

### 3.3 证据等级

WIP、commit、测试源码和 fixture 只能证明候选资产。只有同一可复核 ref 上的 App/Web→HTTP→真实 PostgreSQL→AI adapter→恢复流程，才能证明场景闭环。main、构建 artifact、真实环境和 production 必须分别报告。

## 4. P0 不以 GrowthCase 建模为前置

附件提出 `GrowthCase`、`family_growth_cases` 与 `/growth-cases`。它能表达长期会话，但当前 owner、生命周期和与 GrowthIntent/Journey 的关系尚未获得 ADR 证明，直接施工会形成第二套 Case/Need 真相。

P0 使用：

```text
确认前：tenant_id + family_id + conversation_id/correlation_id
       + input_ref + signal_ref/version

确认后：growth_intent_id + receipt_ref + correlation_id
```

因此本文用中性产品名 `ProblemUnderstandingWorkspaceV1` 表示前端工作区 Read Model，而不是宣告新的 Aggregate。只有出现跨多个 Intent、独立 owner/SLA、关闭/重开/转交、跨 Journey/Service 长期协调且现有对象无法表达时，才另行 ADR 论证 `GrowthCase`。

禁止在 P0 新建：

- `ProblemV2`、`ConfirmedProblemV2` 或第二套 GrowthIntent；
- 未获批准的 `GrowthCase` 表、API 与事件；
- 第二套 Assessment、Consent、Audit、Outbox 或 AI 运行账本。

## 5. 用户体验与组件

### 5.1 Concern Composer

支持文字、语音、必要图片、草稿恢复和场景快捷填充。快捷项只填充家长表达，不决定 need type、风险、服务或干预。

首屏应以真实语言邀请表达，例如“最近家里哪件事最让你费心？”；不得出现 `provenance`、`canonical fact`、`idempotency`、`GrowthCase` 等工程语言。

目标上由 UI-01 承担表达与未完成理解的恢复入口；它不再强制先选择孩子，也不在确认后自动触发服务推荐。UI-02 回归按需 Assessment 工具，UI-03 演进为理解地图与测评解释，两者都不再独占 Family Understanding。

### 5.2 Transcript Review

语音与图片先产生可编辑转写。家长确认后才进入理解；低质量或不完整转写必须允许重录、重拍、删除与手动编辑。

### 5.3 Clarification Conversation

默认只问 1–3 个真正改变理解的问题，不伪装成 15 题问卷。若确需标准化量表，显式桥接到 Assessment，并说明目的、时长和结果用途。

### 5.4 Understanding Map

核心不是聊天气泡，而是结构化、可修正的共同理解：

- 你刚才告诉我的；
- 我目前的理解；
- 也可能是另一种情况；
- 这个家庭已经在努力的地方；
- 你希望先发生的变化；
- 我还不知道什么。

允许查看依据，但不向家长显示伪精确的“AI 置信度 86%”。雷达图只能呈现版本化 Assessment 维度、量表锚点、Evidence 与 Unknown，不得展示家庭总分、排名、默认 50 或虚构同伴均值。

### 5.5 Correction Sheet

家长可以针对 summary、context、strength、desired change 或 unknown 分项修正。Correction 必须作为新输入持久化，旧 Draft 进入 superseded 历史；前端不得就地改写旧理解。

### 5.6 Confirmation Card

确认只表示“这足以代表我们现在想先处理的方向”。成功后显示“我们已经把这件事说清楚，可以继续选择下一步”，不得显示“问题已解决”，也不得立即跳进商城。

### 5.7 连续服务

Slice 01 到 GrowthIntent receipt 为止。Assessment、知识解释、行动方案、专家服务或 Journey 是后续可选择工具，不是确认后的硬编码去向。

## 6. 前端状态模型

本地 UI state 与 server state 必须分开。

本地状态包括 draft、录音/上传进度、正在编辑的 correction、展开依据；server state 包括 input、signal/version、guardian decision、GrowthIntent 与 receipt。

推荐 UI 状态：

```text
DRAFTING
SUBMITTING
REVIEWING_TRANSCRIPT
UNDERSTANDING
CLARIFICATION_REQUIRED
AWAITING_CONFIRMATION
CORRECTING
CONFIRMING
CONFIRMED
AI_UNAVAILABLE
ACCESS_BLOCKED
VERSION_CONFLICT
ERROR
```

网络错误不得改变业务状态；App 被杀、浏览器刷新、请求超时或双设备冲突后，均从 Workspace Projection 恢复服务器真相。

## 7. 共享 Read Model

候选 `ProblemUnderstandingWorkspaceV1`：

```yaml
projection_version: PROBLEM_UNDERSTANDING_WORKSPACE_V1
workspace:
  correlation_id: string
  version: integer
  status: string
subject:
  person_id: string | null
inputs:
  - input_ref: string
    input_type: CONCERN | CLARIFICATION | CORRECTION | FOLLOW_UP
    modality: TEXT | VOICE | IMAGE
    transcript_status: NOT_REQUIRED | NEEDS_REVIEW | CONFIRMED
understanding:
  signal_ref: string
  signal_version: integer
  draft: ProblemUnderstandingDraftV1
  lifecycle: PROPOSED | SUPERSEDED | CONFIRMED | DISMISSED
decision:
  type: CONFIRM | DISMISS | null
  receipt_ref: string | null
intent:
  growth_intent_id: string | null
next_step: REVIEW_TRANSCRIPT | ANSWER_CLARIFICATION | GENERATE_UNDERSTANDING |
  CONFIRM_UNDERSTANDING | CONTINUE_JOURNEY | HUMAN_REVIEW
capabilities:
  can_add_context: boolean
  can_correct: boolean
  can_confirm: boolean
  can_dismiss: boolean
```

App 与 Web 共用同一语义契约；表现布局可以不同。后端不得建立 `/mobile/...` 和 `/web/...` 两套业务 API。

`next_step` 与 `capabilities` 由 Application Policy 根据权限、Consent、版本和状态计算；AI 只能建议 `proposed_next_step`，不能控制按钮、导航或流程迁移。

## 8. HTTP 与命令候选

最终 URI 由 canonical owner 与 ADR 决定。本文件与产品语义规格使用同一组 Input→Signal→Intent 候选契约，不另造 `/growth-cases` 或 `/problem-understandings` 事实资源：

```text
POST /families/{family_id}/growth/need-inputs
POST /families/{family_id}/growth/need-inputs/{input_id}/understandings
GET  /families/{family_id}/growth/understandings/{signal_id}
POST /families/{family_id}/growth/understandings/{signal_id}/decisions
GET  /families/{family_id}/growth/intents/{intent_id}
```

`ProblemUnderstandingWorkspaceV1` 由 root input、conversation/correlation、signal/version 和 intent receipt 聚合形成可重建 Projection，不拥有新的业务生命周期。Command 成功后可返回最新 Projection，减少额外往返；它不意味着 AI Draft 已成为 canonical Fact。

所有写请求携带 actor、tenant/family scope、idempotency key、expected version、correlation id 和 source。统一错误至少包括：

```text
CONSENT_REQUIRED
FAMILY_ACCESS_DENIED
UNDERSTANDING_NOT_FOUND
VERSION_CONFLICT
AI_PROVIDER_UNAVAILABLE
AI_OUTPUT_INVALID
HUMAN_REVIEW_REQUIRED
IDEMPOTENCY_KEY_PAYLOAD_MISMATCH
```

错误响应包含稳定 code、retryable 与 correlation_id；前端不得靠散落的 HTTP 500 判断业务含义。

## 9. AI Use Case

`family_problem_understanding_v1` 经 Model Gateway 生成 `ProblemUnderstandingDraftV1`，至少包含：

```text
summary
explicit_claims[]
inferred_context[]
alternative_explanations[]
family_strengths[]
desired_change
clarifying_questions[]
unknowns[]
limitations[]
proposed_next_step
model/prompt/context/provenance refs
```

Context Snapshot 只读取本次目的所需、版本明确且可追踪的数据。Unknown 不得由模型补齐，claim 与 inference 分开。AI 输出非法、超时或 provider 不可用时，原始输入必须已可靠保存并可稍后继续；不得要求家长重新讲一遍。

确认时锁定 `signal_ref + signal_version + expected workspace version`，不得重新调用模型。只有具名 Guardian Command 能创建 GrowthIntent receipt。

## 10. 数据、事务与可追踪性

一次业务命令的 Domain change、canonical Audit、Outbox 与 idempotency receipt 必须同一事务提交或全部回滚。

需要保留的链路：

```text
UI action/source
→ API request/correlation
→ input/version
→ context snapshot
→ AI run/provenance
→ signal/version
→ correction/supersede
→ guardian decision
→ GrowthIntent receipt
```

Analytics event 与 Domain event 分开。分析指标不得反向成为业务事实，也不得以埋点成功替代业务事务成功。

正式 migration 前必须由 owner 解决 chief 分支 `0004_journey_mvp_persistence.py` 与 assessment action-loop `0004_assessment_support_loop.py` 的 revision 冲突；禁止复制 baseline SQL 或让业务 Agent 私自线性化。

## 11. Feature 组织建议

不以 UI-35、UI-36 的方式继续堆页面。优先抽成可被 Ask Famili、Assessment 和后续入口复用的 feature：

```text
frontend/mobile/features/problem-understanding/
frontend/web/features/problem-understanding/
contracts/problem-understanding/
```

候选组件包括 `ConcernComposer`、`TranscriptReview`、`ClarificationConversation`、`UnderstandingMap`、`CorrectionSheet`、`ConfirmationCard` 与 `useProblemUnderstandingController()`。

Controller 只编排 UI、缓存、请求和恢复；不得包含“文本含手机→设备问题”等 Domain 规则。共享 API client 复用现有 HTTP transport，不复制认证、重试与错误解析。

## 12. Full-Stack 增量计划

FS-01A 是横向准备，不计为业务能力完成。FS-01B 起，每一片都必须同步包含可操作 UI、真实 API、Domain/Application 行为、数据、当片端到端测试和展示 artifact；不得等到 FS-01H 才第一次联调。

### FS-01A｜Contract + UX Skeleton

交付可操作的 Mobile/Web fixture 体验、共享 schema、OpenAPI 候选、前后端 contract fixture 与视觉 artifact。fixture 必须显式标识，不能被宣称为运行能力。

### FS-01B｜Concern Intake

家长真实提交文字 concern，HTTP 写入真实 PostgreSQL，重复/超时重试不产生第二份输入，返回 Projection；尚无 AI 也能退出重进继续。当片 E2E 必须覆盖 UI→HTTP→PG→Projection→重启恢复。

### FS-01C｜Multimodal Intake

接入语音/图片 adapter、上传状态、转写确认、删除与恢复，并以当片 E2E 证明确认后的文本/片段进入同一 Input 主链。测试使用 synthetic media；真实 provider 证据单独报告。

语音流程是“录音→上传→转写→家长编辑/确认→进入理解”；图片流程是“预览→提取候选片段→家长采用/删除/改写→形成 Evidence”。转写或识别失败时保留原始输入并允许手动补充，不要求家长重讲。

### FS-01D｜AI Understanding

完成 Context Snapshot、Model Gateway、结构化校验、signal/version、clarification、Understanding Map 与 AI unavailable 恢复。当片 E2E 从已保存 Input 开始，以理解卡或可恢复失败结束。

### FS-01E｜Correction

完成分项修正、旧 signal supersede、新理解生成和完整历史；当片 E2E 必须证明旧 Draft 未被前端或数据库原地覆盖。记录 correction rate 但不以其判断家庭优劣。

### FS-01F｜Confirmation

完成 confirm/dismiss、GrowthIntent receipt、幂等与并发版本控制。证明 AI 不能直接产生 Intent。开工前先裁决 Assessment→Growth handoff 与 Intent owner，避免把现有越界写入固化进新确认链。

### FS-01G｜Assessment Bridge

将 Assessment 输出作为版本化 GrowthHypothesis/证据输入，同样委托 FS-01F 的 Growth confirmation command；移除 UI-03 总分和虚构比较，保留维度深挖与依据展示。Assessment 的 owner handoff 在 FS-01F 前裁决，兼容 facade 的实现可在本片完成。

### FS-01H｜Golden E2E

Mobile 与 Web 使用同一 Projection，完成输入→澄清→理解→修正→重新理解→确认→杀进程/刷新→恢复。必须包含真实 HTTP/PG、网络中断、AI 失败、重复提交、双设备冲突与可展示 artifact。

每个增量都有独立 DRI 与窄 pathspec，但验收按单一用户场景，不允许前后端分别宣布 Done。

## 13. 联合验收矩阵

### 13.1 正向

- 首次进入只显示低门槛 Concern Composer；
- 语音/图片先确认机器转写；
- 澄清阶段不出现确认按钮；
- Unknown 非空时必须展示“我还不确定”；
- Correction 不在本地覆盖旧 Card；
- Confirm 绑定家长实际看到的 signal/version；
- 成功只显示已确认方向和连续服务入口，不宣称问题解决；
- App/Web 重启后恢复相同 server state。

### 13.2 反向与恢复

- 401、403、跨 tenant/family、Consent 缺失/撤回/过期均不能读取或写入；
- 请求超时后重试不创建第二输入、decision 或 Intent；
- 相同 key 不同 payload 被拒绝；
- AI 不可用或输出非法时保留 concern，允许稍后继续；
- 并发版本冲突提示重载，不覆盖最新记录；
- dismiss 后旧理解不能再次被确认；
- correction 后 superseded signal 不能形成 Intent；
- Audit/Outbox 任一失败时业务事实回滚；
- fixture/fake/provider stub 在非测试环境 fail closed。

### 13.3 体验与视觉

- 用真实中文内容、长短文本、键盘、弱网、空态、错误态做视觉走查；
- 字体、字号、行宽、图片、留白、动效和无障碍达到设计系统要求；
- UI 不出现开发过程、状态码、内部对象或治理术语；
- 交付 Mobile/Web 截图或录屏 artifact，而不只提交组件源码。
- 用自动扫描阻止 `fixture`、`provider`、`idempotency`、`DTO`、HTTP 状态码和内部对象名进入面向家长的字符串。

## 14. 产品指标

核心是“家长是否感到被准确理解并愿意继续”，而非页面点击量：

- 首次理解确认率；
- 修正率与修正后确认率；
- 高价值澄清轮数；
- 从表达至可理解 Draft 的时间；
- 从表达至 confirmed intent 的时间；
- 中途退出后恢复率；
- AI 失败恢复率；
- “被理解/不被理解”的直接反馈及原因。

指标必须按 source、model/prompt/version 与体验版本切分，但不得形成家庭总分、家庭排名或孩子营销画像。

## 15. Definition of Done

本 Slice 只有同时满足以下条件才可称 `CAPABILITY_DONE`：

1. UX：家长能说出、看懂、修正、确认并继续；
2. Frontend：Mobile/Web 状态可恢复、可重试、不伪造服务器状态；
3. API/Domain：owner、命令、版本、边界与失败语义明确；
4. Data：真实 PG 持久化、迁移链、并发和回滚成立；
5. AI：Gateway、结构化输出、Context、Provenance 与家长确认闭环成立；
6. Platform：identity、tenant/family、Consent、Audit/Outbox、Idempotency 复用；
7. Quality：contract、component、HTTP、PG、Golden E2E、恢复和视觉 artifact 可复核；
8. Evidence：branch、commit、main、artifact、real environment、production 分层如实报告。

## 16. 进入施工前的最小裁决

- 由唯一 PMO 指定 Slice DRI、Experience、Growth、Assessment、AI、Platform、Migration 与 QA owner；
- 接受 Problem Understanding 与 GrowthIntent 的边界 ADR，并明确 P0 不建 GrowthCase；
- 在 Capability/AI Use Case/Domain/Migration 登记中补齐真实 owner 与 traceability；
- 为 FS-01A 至 FS-01H 锁定不重叠 pathspec 和依赖 DAG；
- 解决两个 `0004` migration 候选冲突；
- 确认同一 ref 的场景验收与 artifact 归档方式。

本文件保持 `draft/canonical=false`。它可以指导评审与拆解，但不能单凭文档存在宣称能力、main、真实环境或生产已经完成。
