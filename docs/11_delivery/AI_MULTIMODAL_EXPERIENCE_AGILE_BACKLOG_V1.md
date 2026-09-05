---
id: DLV-AI-MULTIMODAL-AGILE-001
title: AiFamily AI 多模态极致体验敏捷 Backlog 与验收矩阵
type: delivery-specification
status: draft
version: 0.2
owner: project-manager
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# AiFamily AI 多模态极致体验敏捷 Backlog 与验收矩阵 V1

> 本文是 AI 多模态体验子项目的交付计划与验收规格，不是能力完成声明。
> `PLANNED`、`PARTIAL`、`EXPERIMENT` 均表示仍需完成纵向接线、验证或治理放行。
> 任何“已完成”结论必须同时有可调用路径、成功/拒绝/重放/删除测试和环境等价证据。

## 1. 产品目标与边界

### 1.1 目标

以 AI 为主路径，把家庭的文字、语音、图片、音频、视频和互动卡片转化为可理解、
可选择、可暂停、可回来的家庭小行动，形成以下闭环：

```text
家庭表达/媒体输入
  → 同意、脱敏、转写/OCR 与上下文快照
  → AI 理解草案（Perspective）
  → 推荐/行动草案（Recommendation / Action Proposal）
  → 家庭选择、暂停或请求人工
  → 过程证据与反馈
  → 非比较的成就记录
  → 下一步个性化建议
```

极致体验的衡量是“更快被理解、选择更容易、失败可恢复、完成后有成就感”，不是
拉长停留时间、提高家庭消费金额、制造比较或给孩子打分排名。成就只能由真实事件
和证据触发，不能用虚构积分、家庭总分或家庭排名替代价值。

### 1.2 强制架构边界

- 所有模型调用只经过 `backend/intelligence/model_gateway`；领域和 UI 不得直连供应商（R7）。
- AI 输出初始只能是 `DRAFT`/`PROPOSED` 的 Perspective 或 Recommendation，不得自动成为事实（R9）。
- 评估、计划变更、教师/服务推荐、购买、对外沟通和未成年人敏感动作必须经过 Human Gate（R8）。
- 未成年人数据不得用于自动化商业营销；媒体、转写、OCR、embedding 和缓存必须可按主体级删除。
- 测试环境与生产环境功能、路由、状态机、权限、Consent、Audit、幂等和人工闸门完全等价；
  仅允许替换数据集和外部适配器（`docs/10_engineering/ENVIRONMENT_PARITY.md`）。
- 供应商选择不先验绑定某一家。Qwen、豆包、Gemini 等候选只能进入隔离评测，法务确认
  委托、转委托、区域、留存和删除责任后，才可申请准入。

## 2. 当前真实状态（基线，不等于目标）

以下结论来自 `docs/00_system/CURRENT_AI_MAP.md`、`CURRENT_SYSTEM_BASELINE.md`、
`docs/05_ai/AI_TECHNICAL_ARCHITECTURE.md` 及本仓库可运行代码（截至 2026-08-30）。
这里的成熟度是能力成熟度，不是 Backlog 卡片完成度；所有 `EXPERIMENT` 均不等于
`PILOT` 或 `PRODUCTION`。

| 能力 | 当前状态 | 证据/真实缺口 |
|---|---|---|
| Model Gateway | `EXPERIMENT` | `backend/intelligence/model_gateway` 有 provider-neutral 契约、Fake/OpenAI-compatible adapter、准入、安全、schema、provenance、timeout/retry、Attempt/usage 与显式 registry 组合根（ADR-0081）；已有 Principal/多模态受控调用方；零外部供应商完成合规准入，默认仍不可处理真实家庭数据 |
| Context Engine | `EXPERIMENT/WIP` | 有 InMemory 原语和 `SqlAlchemyContextStore`（作用域过滤、过期、主体删除证明）及测试；尚无完整业务事件接入、跨流程授权检索、生产组合根和删除 worker 证据 |
| Memory / Growth Graph | `EXPERIMENT` | MemoryRef SQL store（0022）与 Growth Graph 只读投影/Experience Outbox consumer（0023）已具备幂等、作用域和主体删除测试；向量检索、全域事件 projector、生产只读权限和长期检索仍缺 |
| ExperienceEvent / Recommendation / Feedback | `PARTIAL/EXPERIMENT` | ExperienceRun HTTP/API（含 decision、feedback、human-review、delete、replay）、SQL ledger、Curator、Outbox worker、Human Gate relay 与 scope-local feedback projections 已实现并测试；生产 scheduler、通知推送、retention 和完整业务域 consumer 仍缺 |
| Achievement Engine / Feedback API | `EXPERIMENT` | Human Gate 后的 evidence-bound achievement、occurrence identity、SQL projection、通知 inbox、scope-local analytics、成就/通知/分析读取 API、共享 scope authority 与幂等已读 API 均已实现（ADR-0082～0088）；生产 scheduler、alerting、retention、dashboard 和完整移动端页面接线仍缺 |
| Agent Runtime | `EXPERIMENT` | AgentDefinition registry、授权 lease、ContextScope、Prompt/Schema 解析、DRAFT-only execution、ModelGatewayExecutionPort、Durable AgentRun/Trace 与显式 composition 已实现；真实 identity/consent、registry 签名发布、业务 Agent 仍缺 |
| Prompt Registry / Schema Registry | `EXPERIMENT` | 版本不可变、use-case/agent 绑定、生效窗口、schema 安全边界和 fail-closed resolve 有运行时代码与测试；durable 发布、签名、回滚工作流仍缺 |
| Safety / Human Gate | `EXPERIMENT` | provider-neutral 输入/输出安全、DRAFT-only、未成年人/高影响 REVIEW、SQL SafetyDecision、SQL HumanTask/Decision、claim lease、ToolAction inbox 与同事务审计 consumer 已实现；供应商 moderation、常驻调度、通知和更多业务 consumer 仍缺 |
| Evaluation / Release Gate | `EXPERIMENT` | offline benchmark/multimodal evaluation、质量/schema/拒答/安全/provenance/延迟/成本门槛、`AiReleaseGate`、SQL release decision ledger、真人签名控制、候选目录、provider-neutral 灰度/回滚、HTTP adapter、production release composition、200-case gold set、metadata-only 报告归档、生产归档组合根、modality/locale/age_band 切片 runner、slice archive 与 operator-only 授权查询 API 已有测试；真实 key service mTLS/轮换/撤销、dashboard、审计落库和平台演练仍缺 |
| Observability / Trace / Cost | `EXPERIMENT` | metadata-only telemetry span 与 SQL 0021、Attempt/SafetyDecision/AgentRun/Trace、OpenTelemetry/Composite sink、token 与显式 rate-card 成本聚合、TTL retention/deletion worker 及 production retention composition 已实现；collector、SLO dashboard、durable deletion proof/audit、scheduler 与告警仍缺 |
| 34 个 UI | `MIGRATED_PENDING_BACKEND_INTEGRATION` | 页面代码与局部测试存在；不能据此宣称 34 个屏幕在 AiFamily 可工作 |

因此，本 Backlog 当前目标是把已经形成的实验接缝收敛为可验证的 sandbox 纵向 Pilot；
不把新增模型数量、页面代码或合成数据误当作能力成熟度提升，也不先做大规模 UI 美化。

## 3. 敏捷运行方式

- **节奏**：1 周一个 Sprint；每个 Sprint 只承诺一个可演示、可回归的纵向切片。
- **工作项**：每张卡绑定用户故事、流程节点、权威数据对象、API/事件、拒绝路径和测试证据。
- **优先级**：P0 = 合规/安全/可运行前置；P1 = 家庭核心体验；P2 = 成本和规模优化。
- **状态**：Backlog 卡片使用 `PLANNED`、`IN_PROGRESS`、`BLOCKED`、`PARTIAL`、
  `DONE_WITH_EVIDENCE`；能力成熟度仍使用 `EXPERIMENT`、`PILOT`、`PRODUCTION`。
  `DONE_WITH_EVIDENCE (EXPERIMENT)` 只表示该卡在隔离环境有可复跑证据，不能把能力
  自动升级为 `PILOT` 或 `PRODUCTION`。
- **每日同步**：Lead/PM、AI Runtime、平台合规、移动端和 QA 各提交一条证据或一个阻塞项。
- **评审**：Sprint Review 必须演示成功、拒绝、超时、重放、暂停、删除和人工升级路径；
  Retro 只记录可执行改进，不以文档数量作为产出。

## 4. 角色与战场

| 角色 | 主要责任 | 默认战场 |
|---|---|---|
| PM/Lead | 目标、切片、优先级、跨层验收、发布决策 | `docs/11_delivery/`、集成评审 |
| AI Runtime | Gateway、Context、Agent、Prompt/Schema、评测 runner | `backend/intelligence/` |
| Platform/Compliance | Identity、Consent、Audit、Deletion、Human Gate、供应商准入 | `backend/platform/`、`governance/` |
| Domain | Family/Growth/Service/Commerce 的事实和 Named Action | `backend/domains/` |
| Mobile | UI-03→UI-05→UI-09 纵向体验、多模态状态和无障碍 | `frontend/mobile/` |
| QA/Eval | gold set、回归、性能、故障注入、生产 parity 证据 | `tests/`、`reports/` |
| 法务/安全 | 供应商委托与转委托、跨境、留存、DPIA 结论 | `governance/`（决策记录） |

## 5. Sprint Backlog

### Sprint 0：对齐与可测性基座（1 周，P0）

目标：把供应商选择从“口头偏好”变成可复现评测，并冻结媒体、同意、删除、人工闸门和
功能等价边界。

| ID | 用户故事/任务 | 验收标准 | 依赖 | 当前状态 |
|---|---|---|---|---|
| S0-M01 | 作为 PM，我要有统一多模态输入/输出契约，才能并行开发 | text/image/audio/voice/video/interactive_card 六种模态均有 schema、operation、locale、provenance、deletion_ref；非法模态和缺同意拒绝 | Experience contracts | `DONE_WITH_EVIDENCE (EXPERIMENT)`（契约、Family API、运行时校验和测试已接线；媒体真实存储仍待接入） |
| S0-M02 | 作为合规负责人，我要知道候选模型能否处理家庭数据 | 为每个候选供应商登记区域、数据训练、留存、分包/转委托、删除 SLA、DPIA 状态；未完成法务项不得 `ADMITTED` | Vendor due diligence | `PLANNED/BLOCKED_BY_LEGAL` |
| S0-M03 | 作为 QA，我要一套不含真实儿童数据的 gold set | 至少 200 个匿名/合成用例：文本 50、图片 40、语音/音频 40、视频 30、混合模态 40；≥20% 为拒绝/对抗样本；每例含期望结构和安全标签 | Consent/data governance | `PARTIAL`（ADR-0101 `gold.v1` 生成器已稳定提供 200 例与 fingerprint，ADR-0102 报告归档已建立；切片 runner 未建立） |
| S0-M04 | 作为运营，我要看见每次 AI 的延迟、令牌和成本 | Trace 关联 `tenant/family/correlation_id`；记录 model/version/prompt/schema、输入输出 token、重试、估算成本、latency；不得记录原始儿童媒体 | Observability design | `PARTIAL`（Attempt、SafetyDecision、Telemetry span、usage/rate-card 聚合与 TTL retention/deletion composition 已实现；collector、SLO 看板、durable deletion proof/audit、scheduler 和告警未部署） |
| S0-M05 | 作为 Lead，我要确认测试环境不删功能 | 建立同一 API/状态机/错误码/闸门的 parity 清单；sandbox provider 只替换外部依赖；至少一条失败注入用例 | ENVIRONMENT_PARITY | `PARTIAL`（环境等价架构测试和 Synthetic Runtime 已有；尚无 staging/production 运行差异报告与 QA 签署） |
| S0-M06 | 作为家长，我要知道 AI 何时在理解、等待或需要我确认 | UI 状态字典覆盖 loading、partial、success、refused、timeout、retry、human_review、deleted；文案不把草案伪装事实 | Mobile baseline | `DONE_WITH_EVIDENCE (EXPERIMENT)`（UI-03/05/09 状态与契约测试已覆盖；其余 UI 尚未逐屏接线） |

**Sprint 0 退出门**：gold set 可版本化复现；候选供应商均有准入结论或明确阻塞；媒体删除
和拒绝契约通过；trace/cost 字段可查询；parity 清单通过 QA 签字。否则不得进入真实供应商
对比或把模型接入家庭 UI。

### Sprint 1A：安全媒体入口与上下文快照（1 周，P0）

目标：先把“输入可控、可解释、可删除”做成真实端到端切片，不追求模型效果。

| ID | 用户故事/任务 | 验收标准 | 依赖 | 当前状态 |
|---|---|---|---|---|
| S1A-M01 | 作为家庭成员，我可以上传图片/语音并明确用途 | Purpose/subject/locale/consent 不完整即拒绝；上传、转写/OCR 均生成新 media ref 和 provenance | S0-M01 | `PARTIAL`（media contract/runtime 与 Synthetic adapter 已测试；Family API 只接受受控引用，真实上传/转写/OCR worker 未接入） |
| S1A-M02 | 作为家长，我可以撤回并删除媒体 | 删除源媒体会级联删除转写、OCR、缓存、embedding、播放副本；返回 deletion proof；重试幂等 | S1A-M01 | `PARTIAL`（媒体运行时和 Context/Memory 删除证明有隔离测试；跨存储删除 worker、API 和生产回读未完成） |
| S1A-M03 | 作为 AI Runtime，我只读取授权上下文 | Context Broker 按 tenant/region/family/subjects/purpose/有效期过滤；跨家庭读取有可测拒绝 | S0-M01 | `PARTIAL/EXPERIMENT`（内存原语、SQL durable adapter、作用域/过期/主体删除测试已有；全域事件接入和生产 resolver 未完成） |
| S1A-M04 | 作为用户，我能在低带宽或解析失败时继续 | 支持替代文本/重试/跳过/人工入口；不把 OCR/转写当作用户原话 | S1A-M01 | `PARTIAL`（移动端与 media contract 覆盖失败/替代状态；真实低带宽上传与异步处理尚未验收） |

### Sprint 1B：模型 Gateway 对比 Pilot（1 周，P0/P1）

目标：在隔离 sandbox 上对候选模型做同一输入、同一 schema、同一安全规则的可重复对比。

| ID | 用户故事/任务 | 验收标准 | 依赖 | 当前状态 |
|---|---|---|---|---|
| S1B-M01 | 作为 AI 工程师，我可以通过一个 Gateway 调用候选模型 | 业务代码零供应商 SDK；超时、重试、降级、schema 校验、provenance 和 may_mutate=false 均可测试 | S0-M02 | `PARTIAL`（受控 Synthetic/Fake 调用方、OpenAI-compatible adapter、显式组合根与 125+ 测试已具备；零外部供应商准入） |
| S1B-M02 | 作为评测员，我可以复跑同一 gold set | 每次评测固定 dataset/prompt/schema/model 版本；生成 JSON 报告和失败样例；结果可按模态/年龄段/语言切片 | S0-M03 | `PARTIAL`（offline benchmark/multimodal eval、release gate、决策账本、`gold.v1` 200 例生成器、metadata-only report archive、production archive composition、slice runner、slice archive 与 operator-only bounded query API 已实现；operations 访问审计已有 Alembic 0037 durable sink，生产主入口 identity/session-factory 接线、scheduler、dashboard 仍未完成） |
| S1B-M03 | 作为财务负责人，我知道每个成功任务的成本 | 成本含输入/输出 token、媒体处理和重试；超过预算自动标记，不自动换成未审供应商 | S0-M04 | `PARTIAL`（provider token usage、显式 rate card 聚合与缺价 fail-closed 已有；媒体处理账单和预算处置流程未接入） |
| S1B-M04 | 作为合规负责人，我能阻断未准入供应商 | 未完成法务或未成年数据策略时 Gateway fail-closed；拒绝原因可审计且不泄露媒体 | S0-M02 | `PARTIAL/BLOCKED_BY_LEGAL`（registry/admission 与拒绝审计有测试；无供应商完成委托/转委托、区域、留存和 DPIA 准入） |

**Sprint 1B 退出门**：至少一候选模型通过技术评测，但仍只能标 `PILOT_CANDIDATE`；只有
 供应商合规准入、DPIA 和人工闸门证据齐全后，才可进入 Sprint 1C 的家庭数据路径。

### Sprint 1C：理解→选择→小行动→成就纵向切片（1 周，P1）

目标：把 AI 价值落实到 UI-03（理解）→UI-05（方案草案）→UI-09（小行动）的一条可暂停、
可恢复、非比较的体验链。成就只由真实 ExperienceEvent 触发。

| ID | 用户故事/任务 | 验收标准 | 依赖 | 当前状态 |
|---|---|---|---|---|
| S1C-M01 | 作为家长，我能看到 AI 对我表达的可解释理解 | 输出含 evidence/provenance/confidence、限制和“这不是事实”的状态；可改写、拒绝、请求人工 | S1B-M01, Human Gate | `PARTIAL`（多模态 Draft API、ExperienceRun、UI-03/05 状态、Human Gate 绑定和 DRAFT 文案已有；完整改写/人工服务路径未闭合） |
| S1C-M02 | 作为家庭，我能从建议中选择一个小行动 | RecommendationDecision → ActionProposal；确认前不写权威事实；成功/拒绝/超时/重放均有测试 | S1C-M01 | `PARTIAL`（Curator、Named Action、Tool/FGCN accepted-action dispatcher 与 durable worker 已有；完整 Journey/业务域 consumer 仍缺） |
| S1C-M03 | 作为家庭成员，我可以暂停并安全回来 | pause/resume 产生事件；恢复时重新校验 scope、Consent 和有效期；不靠停留时长奖励 | ExperienceGateway | `PARTIAL`（Journey/Experience 状态机、UI 暂停/恢复和 scope 校验已有测试；ExperienceRun 尚未形成统一的 pause/resume 持久化事件与生产 scheduler/retention） |
| S1C-M04 | 作为家庭成员，我在完成真实行动后获得成就记录 | `AchievementEngine` 只消费完成/暂停后返回/主动表达服务意向事件；证据引用可追溯；不产生积分、等级、排名或家庭总分 | S1C-M02 | `DONE_WITH_EVIDENCE (EXPERIMENT)`（Human Gate 后 evidence-bound SQL projection、occurrence identity、通知/analytics、feedback API 与重放测试已完成；生产 scheduler/push/retention/UI 全链路仍缺） |
| S1C-M05 | 作为移动端用户，我能在成就轨道中继续下一步 | Achievement Rail 展示最多 3 个真实成就；空、不可用、加载和错误态；无障碍标签；不显示假数据 | S1C-M04 | `PARTIAL`（Achievement Rail、DTO/view-model 和 API client 有测试；完整屏幕挂载、通知消费和无障碍逐屏验收未完成） |

**Sprint 1C 退出门**：UI-03→05→09 在 sandbox 完成一次成功和一次拒绝/人工升级；每条
ExperienceEvent、Recommendation、Feedback、Achievement 可重放且幂等；删除后 UI 不再展示
派生记录；同一测试脚本可切换 sandbox 与待准入真实 adapter。

### Sprint 2：反馈学习、人工协同与体验优化（1 周，P1/P2）

目标：让“越用越准”有真实评测证据，而不是把点击/停留时间当作唯一优化目标。

| ID | 用户故事/任务 | 验收标准 | 依赖 | 当前状态 |
|---|---|---|---|---|
| S2-M01 | 作为家庭，我可以接受、跳过、改写或投诉建议 | FeedbackSignal 绑定 recommendation_id/target；投诉和人工请求进入补救队列；不改变权威事实 | S1C-M02 | `PARTIAL`（ExperienceRun feedback、通知 inbox/已读、analytics projection 已有；投诉补救队列和完整 Recommendation feedback UI 未接线） |
| S2-M02 | 作为 AI 工程师，我能用授权反馈改进下一轮 | 只使用 consented、purpose-bound、已删除敏感字段的聚合特征；建立离线回归集；禁止直接用儿童商业行为调参 | S0-M04 | `PLANNED` |
| S2-M03 | 作为人工顾问，我能审阅高影响输出 | Human Gate 有 approve/reject/request-more-evidence、理由、操作者、超时和重试；全链路审计 | Human Gate | `PARTIAL`（SQL HumanTask/Decision、claim lease、ToolAction inbox、同事务审计和 accepted-action worker 已有；常驻调度、通知和更多业务 consumer 未完成） |
| S2-M04 | 作为 SRE，我能在供应商故障时保持体验可恢复 | 超时/限流/错误码/降级演练；降级不伪装成 AI 成功；用户可稍后重试或转人工 | S1B-M01 | `PARTIAL`（Gateway timeout/retry/fail-closed、Outbox 重试/DLQ/lease takeover 和 Agent/Experience 重放已有；部署级持续调度、告警和容量演练未完成） |

### Sprint 3：生产 parity 与扩展（1 周，P1/P2）

目标：将通过 Pilot 的切片扩展到更多 UI 和多租户区域，但不以扩展掩盖基础缺口。

| ID | 用户故事/任务 | 验收标准 | 依赖 | 当前状态 |
|---|---|---|---|---|
| S3-M01 | 作为产品团队，我能复用同一体验契约接入 UI-11/UI-28 等屏幕 | 页面只消费权威投影；每屏有成功/拒绝/暂停/删除/无障碍测试；不复制供应商逻辑 | S1C | `IN_PROGRESS`（UI-03/05/09 已形成纵向切片；UI-11/UI-28 及其逐屏验收尚未接线） |
| S3-M02 | 作为平台管理员，我能按租户/区域控制模型和成本 | 配置变更有审批、版本和回滚；区域不允许的模型 fail-closed；成本预算超限触发人工处置 | S1B/S2 | `PLANNED` |
| S3-M03 | 作为发布负责人，我能证明测试与生产功能一致 | 同一验收套件跑 sandbox/staging；差异报告只允许数据/外部 adapter；PostgreSQL 重启回读通过 | ENVIRONMENT_PARITY | `PARTIAL`（环境 parity 约束和架构测试已通过；staging/production 运行报告、PostgreSQL 完整 round-trip 和部署证据仍缺） |

## 6. Definition of Done（DoD）

任何 Backlog 卡只有同时满足以下条件，才能标记 `DONE_WITH_EVIDENCE`：

### 6.1 产品与流程

1. 有用户故事、业务场景、流程节点（N0-N8 或对应节点）和可演示的成功路径。
2. 明确拒绝、超时、重试、暂停、人工升级、撤回和删除路径；异常不是“后续再补”。
3. 体验文案区分事实、Perspective、Recommendation、Action 和 Outcome；无总分、排名、焦虑式比较。

### 6.2 架构与数据

1. 绑定唯一权威数据对象、API/Command/Event/Projection；AI Runtime 不导入领域仓储。
2. 所有 AI 输出带 model/model_version/prompt_version/schema_version/context_snapshot_ref、
   confidence、latency、provider、data_class 和 correlation_id。
3. 媒体、转写、OCR、embedding、缓存均有 purpose、locale、consent_version、deletion_ref、
   retention；源删除可证明派生删除完成。
4. 领域状态变更经过 Named Action、Policy、Consent、Audit、Idempotency 和 Human Gate（适用时）。

### 6.3 质量、运行和安全

1. 单元、契约、集成、架构和至少一条 PostgreSQL/重启回读测试通过；gold set 回归结果已归档。
2. Trace 可关联输入模态、模型版本、延迟、重试、token 和成本，但日志不包含原始儿童媒体。
3. 通过安全拒绝矩阵：跨租户、无同意、过期媒体、未成年人商业营销、越权读取和未审供应商均 fail-closed。
4. 供应商调用只能经 Model Gateway；凭据不进入领域、前端、fixture 或日志。

### 6.4 环境与发布

1. sandbox/staging/production 使用相同路由、schema、状态机、权限、错误语义和闸门；差异只登记为数据或外部适配器。
2. 有回滚开关、重试上限、预算上限和人工处置人；降级响应不能伪装为模型成功。
3. 变更文件、测试命令、实际结果、已知缺口和后续债务写入 Sprint Review；全量失败不得隐藏。

## 7. 多模态评测验收矩阵（目标值，非当前结果）

以下阈值是 Sprint 0 需由 PM、QA、合规和财务共同确认的初始门槛。它们是发布目标，
不是当前系统已经达到的指标；任何调整必须记录 ADR 或评测决策。

| 维度 | 指标与计算 | 初始验收目标 | 失败处置 |
|---|---|---:|---|
| 任务质量 | gold set 结构化任务成功率（按模态、语言、年龄段切片） | ≥90%，任一关键切片不得低于 85% | 降级为人工/不发布该切片 |
| 结构化可靠性 | schema 校验一次通过率 | ≥99% | Gateway 重试一次仍失败则返回可解释错误 |
| 证据可追溯 | 输出含完整 provenance/evidence 的比例 | 100% | fail-closed，不展示输出 |
| 有害/越权 | 安全拒绝集命中率（儿童营销、诊断承诺、跨租户等） | 100% 阻断 | 立即阻断供应商/版本并人工复核 |
| 可解释性 | 用户/评审能定位证据与限制的比例 | ≥95% | 退回 Prompt/Schema 设计 |
| 首字节延迟 | 文本/互动卡片 p95 | ≤1.5 秒（目标） | 走缓存/降级/稍后通知，不伪装成功 |
| 完成响应延迟 | 图片 p95；30 秒语音 p95；30 秒视频 p95 | ≤5 秒；≤6 秒；≤12 秒（目标） | 异步任务+进度态或人工入口 |
| 可用性 | sandbox 请求成功率（排除用户拒绝） | ≥99% | 重试、熔断、供应商切换需有审计 |
| 成本 | 单次成功任务估算成本（含媒体处理与重试） | 文本≤¥0.05；图片≤¥0.30；30秒语音≤¥0.40；30秒视频≤¥1.20（暂定预算） | 超预算停止扩量，提交财务/PM 决策 |
| 成本透明 | 有 token、媒体处理、重试和供应商账单关联的请求比例 | 100% | 不得进入生产 Pilot |
| 人工闸门 | 适用高影响动作经过人工决策且可审计的比例 | 100% | 阻断状态变更/推荐交付 |
| 用户控制 | 提供跳过、暂停、改写、拒绝、人工请求的适用会话比例 | 100% | UI 不得发布 |
| 删除 | 源媒体删除后派生物删除证明完成率 | 100%；目标 ≤24 小时 | 立即隔离索引/缓存并告警 |
| 幂等与重放 | 相同 idempotency key 重试不产生重复事件/成就的比例 | 100% | 阻断队列消费者并修复 |
| 环境 parity | sandbox/staging 与生产契约差异（功能/规则/错误码） | 0 项；仅允许 adapter/数据差异 | 发布闸门拒绝 |
| 学习闭环 | 经过授权反馈后离线回归集质量提升 | ≥5% 相对提升且安全指标不下降 | 不自动上线，进入人工评审 |

### 7.1 按模态的最低覆盖

| 模态 | 最低用例 | 必测失败/安全情形 |
|---|---:|---|
| Text | 50 | 模糊表达、敏感内容、长上下文、空输入 |
| Image | 40 | OCR 错误、低清、儿童面部/隐私、无同意 |
| Voice/Audio | 40 | 转写错、噪声、多人说话、方言、播放失败 |
| Video | 30 | 超时、关键帧缺失、容量限制、派生删除 |
| Mixed | 40 | 文图冲突、语音+图片跨主体、部分失败、重试重放 |

## 8. 发布闸门与证据包

### 8.1 闸门顺序

```text
G0  需求/合规范围冻结
 → G1  契约、同意、删除、审计和 parity 测试
 → G2  sandbox gold-set 技术评测
 → G3  供应商/DPIA/人工闸门准入
 → G4  UI-03→05→09 纵向 Pilot
 → G5  生产容量、成本和灾备演练
```

任一闸门失败，状态回到 `BLOCKED` 或 `PARTIAL`，不得用确定性 fallback 冒充 AI 成功。

### 8.2 每个 Sprint 必须归档

- Backlog 卡与负责人、分支、变更文件 pathspec；
- API/schema/event/projection 版本和迁移记录；
- 成功、拒绝、超时、重试、暂停、人工、删除和重放测试结果；
- gold set 版本、供应商/模型/prompt/schema 版本、质量/延迟/成本报告；
- 安全、DPIA、供应商委托/转委托和数据留存决策；
- sandbox/staging parity 差异报告、回滚演练和未解决债务。

## 9. 当前明确阻塞项（不得隐藏）

1. 没有任何外部多模态供应商完成合规准入；技术 adapter 可运行不代表可处理真实家庭数据，
   `openai-compatible-unassessed` 仍必须在 Gateway 中 fail-closed。
2. Evaluation、Observability、Agent Runtime、Prompt/Schema Registry、Safety、Human Gate
   已有实验级实现和测试，但均未达到 `PILOT`：仍缺真实身份/同意与 key service mTLS/轮换/撤销、
   生产 scheduler、dashboard/游标分页、collector、durable deletion proof/audit 或完整业务 consumer 等证据。
3. Experience/achievement 已具备 ExperienceRun API、SQL ledger、Outbox/lease/DLQ、
   Human Gate 后 evidence-bound achievement、通知/analytics、feedback API（含幂等已读）和
   共享 scope authority；生产 scheduler、推送/告警、retention、dashboard、完整业务域和移动端
   页面接线仍缺，不能称生产闭环。
4. Context Engine 已有 SQL durable adapter 的实验接缝，但缺全域事件接入、跨流程授权检索、
   生产组合根与删除 worker/回读证据；`EXPERIMENT/WIP` 不得写成已上线 Context。
5. Memory 与 Growth Graph 已有 SQL/投影实验实现和主体删除测试，但向量检索、全域 projector、
   生产只读权限和长期评测仍缺。
6. 34 个 UI 的迁入和局部测试不等于在 AiFamily 后端可工作；UI-03/05/09 之外必须按纵向切片
   逐屏接线，并验证通知、错误、暂停、删除和无障碍状态。
7. 任何 Qwen、豆包、Gemini 的具体型号、价格和路由权重，均须以 Sprint 0/1B 的实测报告和
   法务结论为准，不能凭印象写死。

## 10. 完成定义的责任声明

本子项目的 PM 负责把上述目标拆为 Sprint、协调 Agent、维护阻塞和组织评审；但 PM 不得
替代法务批准供应商，不得把“模型能回答”“页面能打开”“fixture 有数据”当作能力完成，
也不得为了速度删除 Consent、Audit、Human Gate、删除或生产 parity。只有证据包完整，
并通过架构测试、目标测试和真实失败演练，才允许把一个纵向切片从 `PARTIAL/EXPERIMENT`
升级为 `PILOT`。
