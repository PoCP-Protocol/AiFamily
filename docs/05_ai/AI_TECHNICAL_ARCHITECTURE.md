---
id: AI-TECH-ARCH-001
title: AiFamily AI 技术架构总设计
type: specification
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md
---

# AiFamily AI 技术架构总设计

> 深度版维度、Principal 控制面、基础设施、评估、删除、可靠性和落地 Wave 见
> `docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md`；本文件保留运行时基础契约。

> 本文件回答“AI 如何作为一个可治理、可替换、可评估的技术系统运行”。
> 它是技术实现规格，不把目标态当成当前能力。AI 语义和红线以
> docs/05_ai/AI_ARCHITECTURE.md、docs/05_ai/AI_NATIVE_PRINCIPLES.md 为准；
> 合规以 docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md 为准；业务、流程、
> 数据、应用分别以 docs/02_business、docs/07_data、docs/06_platform 的对应
> 设计为准。

## 1. 战略翻译：AI 技术必须服务什么

商业战略的核心不是“接入一个更强的模型”，而是让家庭在测评、理解、计划、
行动、服务和复盘中持续得到可信帮助，并形成别人短期无法复制的家庭成长数据
和服务协作能力。因此 AI 技术架构遵循以下优先级：

| 战略目标 | AI 技术含义 | 不能做什么 |
|---|---|---|
| 家是港湾，促进家庭关系和谐 | 以家庭上下文、关系和行为变化为推理对象 | 不把孩子变成分数、等级或排名 |
| 测评→假设→计划→行动→复盘 | AI 贯穿核心流程，生成结构化 Perspective、Draft、Recommendation | 不把 AI 摘要当成最后一步装饰 |
| Family Context / Growth Graph 是长期护城河 | 以可追溯观察、证据、时序和关系图积累上下文 | 不建立无目的、无限期的数据湖 |
| AI+真人协作是优势区 | AI 给出候选和解释，人确认高影响决定 | 不让 Agent 直接分派、验收、退款或改写事实 |
| 家长是商业主体，孩子是成长主体 | 商业推荐只在家长授权场景，孩子端只做安全成长支持 | 不向未成年人做画像驱动商业营销 |
| 三环境功能等价 | dev/test/prod 使用同一 AI 用例、状态机、错误和闸门 | 不因测试环境无真实模型而删除 AI 路径 |

### 1.1 AI 技术架构的中心判断

AiFamily 不是“业务系统 + 一个聊天机器人”，而是 Family Growth Intelligence
OS：Family Context、Family State、Growth Problem Model、Intervention/Service
Blueprint、Evidence/Memory 与 Governed AI Runtime 的组合。

Agent 是上述资产的智能劳动者，模型是可替换的基础设施。最先建设的是 Context、
证据和决策边界，而不是多 Agent 的炫技编排。

## 2. 目标架构总览

### 2.1 五个平面

| 平面 | 主要组件 | 责任边界 | 事实写入 |
|---|---|---|---|
| Domain Truth Plane | Family、Assessment、Journey、Service、Commerce、Community | 管理业务事实、状态机和 Named Action | 只有业务域 |
| Intelligence Data Plane | Context Broker、State Observation、Growth Graph、Memory、Evidence Index | 把业务事件整理为可推理上下文 | 只写 AI 技术对象和投影 |
| AI Runtime Control Plane | Model Gateway、Agent Runtime、Tool Runtime、Safety、Human Gate | 执行生成、工具权限、风险闸门、人工接管 | 不写业务事实 |
| Experience & Operations Plane | Family API、Mobile、Operations、Partner、Workflow Worker | 接收意图、展示投影、执行定时和人工工作 | 通过应用服务写业务事实 |
| Governance & Evidence Plane | Prompt/Schema/Knowledge Registry、Eval、Trace、Cost、Audit、DPIA | 版本、证据、质量、成本和合规 | 写审计/评估/运行记录 |

### 2.2 运行拓扑

Mobile / Operations / Partner → family_api（identity、authorization、consent、
application service）→ Domain Named Action 或 ai_runtime。

ai_runtime 内部链路为：Context Broker → Safety pre-check → Prompt/Schema Registry
→ Agent Runtime → Tool Runtime → Model Gateway → schema validation →
Safety post-check → ModelDraft，并写入 Provenance、Trace、Attempt、Eval。

workflow_worker 负责 schedule、retry、compensation、human-task 和 projection
rebuild。PostgreSQL 按既定业务 schema 加 ai_runtime 技术 schema；Outbox/Inbox
负责跨进程事件。

目标形态保留 family_api、ai_runtime、workflow_worker 三个进程边界。早期可以
同一部署单元运行，但代码依赖方向不能混淆。

## 3. 技术分层与组件职责

| 组件 | 目标位置 | 输入 | 输出 | 是否允许写业务事实 | 当前状态 |
|---|---|---|---|---|---|
| Context Broker | backend/intelligence/context_engine | tenant、family、subject、purpose、时间窗 | ContextSnapshot、DeletionProof | 否 | EXPERIMENT：内存检索与 SQL durable adapter、`SqlContextBrokerFactory` 生产组合、迁移 0036、作用域读取、过期清理和主体删除证明已实现；全域事件接入与生产 worker 待接入 |
| Memory System | backend/intelligence/memory + experience contracts | 已批准观察和记忆策略 | 可过期 MemoryRef | 否 | EXPERIMENT：`SqlAlchemyMemoryStore` + Alembic 0022 支持作用域读取、幂等写入、级联删除证明和 retention purge；不保存原始媒体/embedding |
| Growth Graph Projection | `backend/intelligence/growth_graph`（Experience Outbox worker 投影写入、AI 只读查询） | Evidence、Intent、Action、Outcome 事件引用 | 作用域内时序关系图查询 | 否 | EXPERIMENT：`GrowthGraphOutboxConsumer`、`GrowthGraphEdge`、`SqlAlchemyGrowthGraphProjection`、迁移 0023、幂等投影与主体删除证明已实现；全域 DomainEvent/outbox projector 待接入 |
| Growth Intervention Engine | `backend/intelligence/intervention` | hypotheses、primary contradiction、Growth Graph/Context 证据引用 | 固定 DRAFT 的 InterventionCandidate | 否 | EXPERIMENT：主要矛盾最多 3 个、置信度确定性排序、证据绑定和未成年人/高影响 Human Gate 标记；Blueprint 匹配、pending bridge、accepted-action worker 与 FGCN proposal consumer 已接入，真实模型和生产效果评测仍待接入 |
| Service Blueprint Matching | `backend/intelligence/intervention/blueprint_matching.py` | 业务域 PUBLISHED Blueprint 只读快照、primary contradiction、evidence refs | DRAFT BlueprintRecommendation | 否 | EXPERIMENT：只匹配已发布快照，不创建/发布/执行 Blueprint；Human Gate、durable worker 与 FGCN proposal consumer 已接入，`OPEN_SERVICE_CASE` 仍由独立领域闸门控制 |
| Model Gateway | backend/intelligence/model_gateway | StructuredRequest | ModelDraft + AiProvenance | 否 | EXPERIMENT：有代码/测试，已由 Principal/多模态 Runtime 通过显式组合根调用；`build_openai_compatible_gateway_from_registry`（ADR-0081）按 registry 显式组装可替换 adapter，并支持 ADR-0100 provider-scoped CredentialLease、`SecretManagerCredentialPort` metadata-first KMS/Secret Manager seam；`HttpIdentitySessionPort`（ADR-0117）为真实 auth_identity 提供会话签发/轮换/撤销端口；ADR-0118 在生产启动期校验路由 profile 与 Gateway adapter/model identity/模态能力一致；ADR-0119 提供 Multimodal Draft SQL request-auth wiring；尚无获准外部供应商 |
| Agent Runtime | backend/intelligence/agent_runtime + family_api composition root | AgentDefinitionRegistry、显式/durable composition、AgentAuthorization（SQL lease）、ContextSnapshot、任务 | AgentRun、ModelDraft、HumanTask | 否 | EXPERIMENT：治理 YAML 静态注册表、显式 Prompt/Schema registry 组合、授权租约、ModelGatewayExecutionPort、DurableAgentRuntime、DRAFT-only 执行与 AgentRun/Trace SQL store 已实现；`ProductionAgentRuntimeResolver` 在服务端 ContextScope 下按请求绑定 Attempt/Trace 事务，并支持按 session 创建 SQL Prompt/Schema registry，真实 identity/consent resolver 与 registry 签名发布仍由部署提供 |
| Experience Outbox / Achievement Projection | backend/intelligence/experience | StoredExperienceMessage、scope/provenance/idempotency、EngagementDraft achievement candidate、MultimodalRun feedback | evidence-bound Achievement projection、Engagement Draft HTTP API、dev/test parity runtime、SQL identity/consent scope、request-auth wiring、DLQ、通知 inbox、analytics、feedback API（含已读状态）、UI-05 草稿反馈、反馈偏好上下文 | 否 | EXPERIMENT：Worker、Achievement consumer、occurrence identity、SQL durable projection、metadata-only attempt/status ledger、worker lease/takeover、SQL metadata-only DLQ、通知 inbox、scope-local analytics、严格 scope resolver 与幂等已读状态 API、`POST /families/{family_id}/experience/engagement/drafts`、`POST /families/{family_id}/experience/multimodal/runs/{run_id}/feedback`、`SyntheticEngagementRuntimeResolver`、`DevOperatorIdentityPort`/`DevExperienceOperationsRuntime`（仅 dev/test）、`SqlAlchemyBearerPrincipalResolver`、`SqlAlchemyTrustedTenantScopeStoreFactory`、`SqlAlchemyConsentSnapshotResolver`、`install_sql_engagement_runtime_wiring`、`ProductionExperienceOutboxRuntime.alert_sink`、`AchievementNotificationRetentionWorker`、部署侧 schedule value object/`run_scheduled_tick`、`/internal/ai/experience/delivery-attempts` 分页/summary 运维查询、HMAC cursor 与 operator scope 授权 facade、metadata-only access audit、`last_error` API 脱敏、请求 bearer context/`HttpRequestOperatorIdentityPort`、显式 `build_http_production_experience_operations_query_wiring` 生产组合根、`SqlAlchemyExperienceOperationsAuditSink`/per-access transaction sink/Alembic 0037 已实现；UI-05 通过 `recordMultimodalFeedback` 发送 `helpful|not_helpful|request_human` 有界信号、保留 run/draft/model provenance 与幂等键；`FeedbackPreferenceSnapshot` 仅按精确 scope 聚合三类计数并在生成前以服务端值覆盖同名客户端输入；请求人工仅进入 Human Gate，不自动改写家庭事实；Draft 与 feedback 可共享 scope authority；AI candidate 经过 `PUBLISH_EXPERIENCE_ACHIEVEMENT` Human Gate 后才能投影（ADR-0082~0116、0123~0130），生产主入口调用、数据库权限/并发演练、auth_identity endpoint/mTLS、token 签发/轮换、实际 recurrence、主入口 identity/session-factory wiring 与 dashboard wiring 待接入 |
| Tool Runtime | backend/intelligence/tool_runtime | ToolDefinition、AgentDefinition、AgentAuthorization、ToolAuthorization、ToolCallRequest | ToolCallResult（仅 pending Human Gate Named Action） | 否；只能发起业务命令请求 | EXPERIMENT：三重授权、pending Named Action、SQL durable outbox、SQL Human Gate inbox consumer、`AcceptedNamedActionDispatcher`、post-gate durable attempt/DLQ worker 与 bounded queue poll（ADR-0078）已实现；FGCN 已注册 `CONFIRM_SERVICE_TASK_ASSIGNMENT` 与 `PROPOSE_SERVICE_BLUEPRINT` consumer（ADR-0079），family_api 组合根提供同 session runtime、终态过滤队列、AI achievement consumer 和 metadata-only DLQ 查询（ADR-0080/0082），生产持续调度、lease takeover 压测与其他业务 handler 仍待接入 |
| Prompt Registry | backend/intelligence/prompt_registry | use_case、版本、知识引用 | PromptBundle | 否 | EXPERIMENT：内存与 SQL 不可变 registry 已实现（migration 0030），AgentRuntime 组合工厂已强制 published resolve；运营审批签名、统一 loader 待接入 |
| Schema Registry | backend/intelligence/schema_registry | schema_ref、版本 | 可校验 JSON Schema | 否 | EXPERIMENT：结构/安全边界与 SQL 版本回读已验证（migration 0030），AgentRuntime 组合工厂已强制 published resolve；运营审批签名、统一 loader 待接入 |
| Safety Runtime | backend/intelligence/safety + model_gateway | 输入、输出、主体年龄、风险信号 | SafetyDecision | 否 | EXPERIMENT：Model Gateway 请求前/输出后已执行确定性阻断，高影响与未成年人进入 Human Gate 复核；`SqlAlchemySafetyDecisionSink` 已持久化策略元数据，供应商 moderation、人工反馈与 retention/deletion job 仍待接入 |
| Human Gate | backend/intelligence/human_gate | 高影响 Draft/Proposal、pending Tool Action | HumanTask、HumanDecision | 否；决定交由业务域 | EXPERIMENT：SQL HumanTask、ToolAction inbox、同事务 Audit consumer 已实现，通知/租约/业务 consumer 待接入 |
| Evaluation | backend/intelligence/evaluation + family_api composition root | Golden Case、运行记录、人工反馈、ProviderRegistry | EvalRun、Metric、ReleaseDecision、ReleaseControlEvent、ReleaseCandidate、DeploymentReceipt、Telemetry span、BenchmarkReportArchive、EvaluationSlice、BenchmarkSliceArchive、AuthorizedEvaluationQueryService | 否 | EXPERIMENT：AiReleaseGate + ReleaseAdmissionService + ReleaseControlStore + OperatorIdentity/Token adapter + `ProductionReleaseRuntime` + `ProductionEvaluationArchiveRuntime` + ReleaseCandidateCatalog + ReleaseDeploymentService + HttpDeploymentPort + `MtlsClientConfig` + 共享 `operator_request_context` + `DevEvaluationArchiveRuntime`（仅 dev/test）+ ADR-0101/0102/0103/0104/0105/0106/0107 已实现评测/准入、真人批准、候选状态、provider-neutral 灰度/回滚、HTTP 错误收敛、200-case gold set、metadata-only 报告归档、modality/locale/age_band 切片、slice archive 与 operator-only bounded query 的 fail-closed 边界；真实 key service 的轮换/撤销回调、KMS/Secret Manager、dashboard、审计落库、部署平台权限待接入 |
| Trace/Cost/Audit | platform + ai_runtime ports + family_api retention composition | request、scope、attempt、decision、usage | Trace、Attempt、Cost、Audit、DeletionReceipt | 否 | `backend/intelligence/observability` 提供统一 metadata-only span 与 SQL 0021，scope/request/session opaque、属性 allowlist 与 operation 幂等；`OpenTelemetrySpanSink`/`CompositeTelemetrySink` 已接 SDK exporter；`TelemetryRetentionWorker` 与 `ProductionTelemetryRetentionRuntime` 可按 `started_at` TTL 在独立事务中有界删除并产出 metadata-only receipt；`aggregate_attempts` 按显式 rate card 聚合 token/微 USD，生产 scheduler、collector、durable deletion proof/audit 与告警待部署 |

### 3.1 依赖方向

Domain/Application → AI Port；AI Runtime → Platform Contracts / Event Read Port。
AI Runtime 不得 import Domain Repository/ORM；Model Provider 不得被
Domain/Application 直接调用；Projection 不得写 Fact；AI Draft 不得写
Canonical Fact。

## 4. 一次 AI 请求的完整运行链

### 4.1 同步生成链

1. Application Service 创建 AIRequest（use_case、actor、family、purpose）。
2. Consent/Authorization 检查主体、目的、范围和 AgentAuthorization。
3. Context Broker 读取允许的 Evidence、StateObservation、GraphProjection。
4. 生成 ContextSnapshot，冻结输入版本、时间窗和脱敏结果。
5. Safety pre-check 判断风险级别、是否允许模型处理、是否需要人工。
6. Prompt Registry 取得固定版本 PromptBundle。
7. Schema Registry 取得输出 schema；Schema 不由模型或 UI 自行定义。
8. Agent Runtime 选择 Skill/Tool，生成 StructuredRequest。
9. Model Gateway 做供应商准入、Attempt begin、超时和结构校验。
10. Safety post-check 检查越界、未成年人商业内容、虚构事实和高风险建议。
11. 写入 ModelDraft、Provenance、Trace、Attempt；必要时创建 HumanTask。
12. 返回 Draft/Recommendation 投影，不返回“已完成业务事实”。

任何一步失败都返回明确的 fail-closed 错误或人工待办；不得把原始模型文本、
未校验 JSON、供应商异常或不完整来源传给家庭 UI。

### 4.2 异步学习/行动链

Outbox Event → Event Normalizer → Context Observation → Graph/Memory Projection
→ Worker Schedule → AI Draft → Human Decision → Domain Named Action → Fact Event
→ Outcome/Feedback → Evaluation Dataset。

这条链实现“越用越准”，但学习对象是证据、上下文和策略，不是把家庭转成
单一分数。被驳回、被改写、暂停干预和人工纠正都必须作为负样本保留。

## 5. AI 技术契约

### 5.1 ContextSnapshot

ContextSnapshot 至少包含 snapshot_ref、tenant_id、family_id、subject_ids、
purpose、consent_version、source_event_ids、evidence_refs、observations、
graph_projection_ref、memory_refs、time_window、generated_at、expires_at、
redaction_policy_version 和 data_classes。

快照是一次推理的输入证据，不是家庭事实替代品。快照必须可重放、可过期、
可按主体删除，且不得混入未授权的跨家庭或跨目的内容。

### 5.2 StructuredRequest / ModelDraft

StructuredRequest 必须携带 request_id、session_id、correlation_id、causation_id、
use_case、prompt_version、schema_version、context_snapshot_ref、input_refs、
data_class、purpose、policy_context、payload 和 output_schema。

ModelDraft 必须携带 draft_id、status=DRAFT、通过 schema 校验的 output、
完整 provenance、requires_human_confirmation=true、may_mutate_business_state=false、
limitations 和 evidence_refs。

ModelDraft 没有自动晋升为 VALIDATED 或 APPROVED 的路径。业务域要采纳它，
必须由真实人类 Actor 通过 Named Action 写入自己的事实表。

### 5.3 事件和因果链

统一 envelope 至少包含 event_id、event_type、event_version、tenant_id、
family_id、subject_ids、actor_id、actor_type、correlation_id、causation_id、
occurred_at、data_class、payload_ref 和 provenance_ref。

现有 outbox 路径只有 correlation_id 的地方，目标架构必须补 causation_id，
使跨阶段、跨月的决策来源图可以重建。

## 6. Family Context 与 Family Growth Graph

| 对象 | 用途 | 典型来源 | 留存/删除 |
|---|---|---|---|
| StateObservation | 一次有来源、有限期的状态观察 | 家庭回答、行动记录、服务反馈 | 按主体、目的、expires_at 删除 |
| EvidenceReference | 观察或 Draft 的原始证据引用 | assessment evidence、human note | 随原始证据和权利请求级联 |
| ContextSnapshot | 某次推理的冻结输入 | Context Broker | 到期后删除或脱敏 |
| MemoryItem | 经策略批准的长期偏好/经验 | 多次观察和人工确认 | 必须有记忆类型、TTL、撤回路径 |
| GrowthGraphEdge | 主体、关系、目标、行动、结果的时序边 | Domain Event 投影 | 从事件重建；主体删除级联 |
| EmbeddingRef | 仅用于检索的向量引用 | 允许向量化的文本 | 原文删除时同步删除向量和缓存 |

建议 AI 技术表：ai_context_snapshots、ai_state_observations、ai_memory_items、
ai_growth_graph_edges、ai_embedding_refs、ai_requests、ai_model_attempts、
ai_drafts、ai_tool_calls、ai_human_tasks、ai_human_decisions、
ai_prompt_versions、ai_schema_versions、ai_knowledge_versions、
ai_evaluation_runs、ai_trace_spans、ai_cost_records。

关系固定为：Domain Event → Observation/GraphEdge → ContextSnapshot → AIRequest
→ ModelAttempt → ModelDraft → HumanTask → HumanDecision → Domain Named Action
→ Domain Fact Event。

AI 表的 family_id、subject_id、tenant_id 和 data_class 必须可索引。向量、缓存、
快照、trace、训练/评估样本都必须支持主体级删除。

## 7. Model Layer 与供应商治理

### 7.1 能力路由，不绑定供应商

| 用例 | 能力需求 | 输入 | 输出 |
|---|---|---|---|
| ASSESSMENT_INTERPRETATION | 结构化解释、证据引用、限制说明 | Assessment Evidence | GrowthPerspective/Hypothesis Draft |
| GROWTH_PLANNING | 多阶段计划候选、家庭可编辑 | Context + GrowthIntent | JourneyPlan Draft |
| DAILY_ACTION | 小行动生成、可执行性、儿童安全 | Active Phase + recent observations | Action Proposal |
| SERVICE_MATCHING | 能力匹配、理由、替代方案 | Blueprint + family need | Recommendation |
| REFLECTION | 过程观察、暂停/调整建议 | Action/Outcome/Feedback | ProcessPerspective |
| OPERATIONS_INSIGHT | 只读运营聚合、异常解释 | Operational events | Ops Recommendation |

Model Gateway 根据 capability、data_class、environment、预算和合规登记选择
provider。凭据只能在 Model Gateway 边界读取：生产组合根通过
`ProviderCredentialPort`（`HttpProviderCredentialPort` 或 `SecretManagerCredentialPort`）注入短期 `CredentialLease`；生产组合根可使用
`build_secret_manager_openai_compatible_gateway_from_registry` 接入 KMS/Secret Manager 回调；Secret Manager 适配器先校验 metadata，再读取 secret reference，
兼容的环境变量读取也只保留在 Gateway 工厂内；Provider Registry 的安全评估、
分包关系、数据区域和删除承诺是准入条件。
HTTP 凭据组合根可显式开启
`POST /v1/provider-credentials/leases/revocation-status` 的 metadata-only 查询，
在每次 provider 外呼前检查动态撤销；默认不开启，避免把外部密钥服务契约隐藏在
领域代码中；若配置检查器却未提供 CredentialLease port，工厂会在启动期拒绝。
租约有效期还必须覆盖本次 provider 请求 deadline；撤销服务超时、网络异常或非法
响应均 fail-closed。

### 7.2 当前可用性

当前 Model Gateway 已具备结构化请求、schema 校验、超时、Attempt、Provenance、
Draft-only 输出和受控路由的代码与测试，但没有业务调用方，且没有外部供应商
通过当前合规准入。因此 dev/test 使用 FakeProvider 或 deterministic adapter
时，也必须经过同一 StructuredRequest、schema、Provenance、Safety 和 Human Gate
契约；production 无获准供应商时必须显式返回 MODEL_UNAVAILABLE 或人工待办。

离线评测结果现在还必须经过 `backend/intelligence/evaluation/release_gate.py`：
`AiReleaseGate` 先调用 `ProviderRegistry.admit`，再校验质量、安全、schema、拒答、
provenance、延迟与成本阈值，缺证据即 BLOCKED。该门禁只返回可审计决策，不代表
已部署或已获得业务域执行权限。

### 7.3 可靠性策略

模型调用默认 automatic_retry=0。只有已批准且可证明是基础设施失败的多个供应商，
才允许由 Routing Gateway 按独立准入结果切换。JSON/schema 失败、策略拒绝、
数据不合规、供应商 4xx 不得换供应商“采样到一个能回答的结果”。

## 8. Agent Runtime 与 Tool Runtime

| Agent | 首要用例 | skills | tools | 默认人工闸门 |
|---|---|---|---|---|
| ParentAdvisor | 理解和沟通建议 | explain、reflect、conversation | read_context、draft_message | 对外发送必须人工 |
| ChildCoach | 安全的小行动陪练 | encourage、check_in、reflect | read_today_task、propose_action | 未成年人敏感动作必须人工 |
| TeachingAssistant | 服务交付建议 | review、summarize、flag | read_case、draft_feedback | 批改/预警写入需人工 |
| GrowthPlanner | 90 天计划和阶段建议 | plan、sequence、explain | read_growth_graph、draft_plan | 计划变更必须家庭确认 |
| OperationsAssistant | 运营解释和资源建议 | analyze、monitor、explain | read_ops_projection、draft_insight | 个体或商业决策必须人工 |

每个 AgentDefinition 还必须声明 context_policy、safety_policy、
human_handoff_policy、budget_policy 和 may_mutate_business_state=false。

AgentAuthorization 是动态授权，至少包含 authorization_id、agent_id、tenant/
family scope、allowed_use_cases、allowed_tools、issued_by、issued_at、expires_at、
revoked_at、budget、policy_version、reason 和 audit_ref。没有有效授权、超过 TTL、
超出主体/目的范围或预算时，Agent 不得运行。

工具必须是具名、版本化、输入输出可校验的 Port。request_domain_named_action
只能创建待确认业务命令，不直接调用 ORM；结果必须带 source_refs、data_class、
latency、error_code 和是否需要人工。

先让一个 Agent（优先 GrowthPlanner 或 ParentAdvisor）在真实 Context 上跑通
记忆、解释、人工确认和反馈闭环，再扩展其余 Agent。多 Agent 协同不是第一批任务。

## 9. Safety、合规与 Human Gate

| 风险级别 | 示例 | AI 可做 | 必须做 |
|---|---|---|---|
| LOW | 一般解释、家庭自愿的小行动建议 | 生成 Draft | 证据、限制、来源 |
| MEDIUM | 计划调整、服务候选、对外沟通草稿 | 生成 Proposal | 家庭/工作人员确认 |
| HIGH | 类诊断、高风险信号、教师分派、退款、会员升级 | 只能生成提醒和人工待办 | Human Gate、理由、审计、可拒绝 |
| PROHIBITED | 家庭总分/排名、儿童画像商业营销、自动临床诊断 | 不得生成或展示 | 直接拒绝并记录 |

Human Gate 流程为 Draft/Proposal → risk classifier + policy check → HumanTask
（对象、原因、证据、截止时间）→ reviewer 身份/权限验证 → APPROVE、EDIT、
REJECT 或 ESCALATE → 业务域 Named Action → Audit + Domain Event。

HumanDecision 必须由非 AI Actor 创建，记录 reviewer、decision、reason、before/after、
evidence_refs、policy_version 和时间。撤回同意、删除权、终止服务或目的变化时，
必须级联处理原始事实引用、ContextSnapshot、MemoryItem、EmbeddingRef、模型缓存、
Trace 和评估副本。

## 10. Prompt、Schema、Knowledge 和版本治理

AI 用例、Agent、Tool、输出类型和 Human Gate 的边界由
`governance/AI_USE_CASE_REGISTRY.yaml` 登记。该文件是治理契约，不是上线证明：
登记为 `PLANNED` 只说明接口和责任已经冻结，仍需代码、测试和发布证据才能进入
`PILOT` 或 `PRODUCTION`。运行时的 Prompt/Schema/Knowledge Registry 必须读取
同一组 `use_case`、`agent` 和 `tool` 标识，禁止在代码中另建一套隐式清单。

PromptBundle 至少包含 prompt_ref/version、use_case、system_policy_ref、
knowledge_refs、input_contract_ref、output_schema_ref、safety_policy_version、
locale、author、reviewer、status、effective_at、retired_at 和 change_reason。
已发布版本不可原地修改，只能创建新版本。

Schema 至少声明 schema_ref/version、object_type、required_fields、
evidence_refs_non_empty、forbidden_fields、enum_constraints、boundary_labels
和 human_gate_rule。GrowthHypothesis 不得包含家庭总分、同伴排名等字段；
Recommendation 必须包含 why_this、limitations 和候选来源；DailyAction 必须
区分 Proposal 与 ActionRecord。

Knowledge 按主题、版本、适用年龄、证据等级、许可范围和过期时间登记。检索返回
knowledge_refs，不把无法验证的模型自报引用当作依据。知识、Prompt、Schema、
Model 版本共同进入 Provenance。

## 11. Evaluation 与“越用越准”

| 层次 | 评估内容 | 发布门槛 |
|---|---|---|
| Contract Eval | JSON/schema、边界标签、Evidence refs、Draft-only | 100% 通过 |
| Safety Eval | 未成年人商业、诊断、排名、隐私越权、高风险升级 | 关键禁止项 100% 拦截 |
| Grounding Eval | 证据引用正确、无虚构事实、限制完整 | 按用例设阈值并人工抽检 |
| Usefulness Eval | 采纳、改写、驳回、暂停干预 | 不使用家庭间排名 |
| Workflow Eval | Human Gate、Named Action、审计、补偿、重放 | 关键路径无旁路 |
| Drift Eval | 输入/反馈分布、模型和 Prompt 变更 | 超阈值降级或暂停 |

反馈闭环为 Draft → ACCEPT/EDIT/REJECT/DEFER → Human reason + outcome observation
→ eval case / policy update / prompt candidate → review → publish new version。
驳回和暂停是策略边界的学习数据；评估副本必须继承主体、目的、留存和删除属性。

## 12. Trace、成本、审计与可观测性

每次运行至少形成 ai.request、context.snapshot、safety.precheck、prompt.resolve、
agent.plan、tool.call、model.attempt、schema.validate、safety.postcheck、
human_gate、domain.named_action 和 ai.response 等 span/record。

记录 request_id、trace_id、correlation_id、causation_id、family/subject scope、
data_class、provider/model、版本、token usage、latency、错误、重试、人工决定
和删除标记。Attempt 必须在外呼前登记；持久化失败要有运维告警。

成本按 use_case、tenant、family、agent、provider 和版本聚合，但不能把家庭消费、
成长结果或完成率转成家庭排名。预算超限返回可解释的人工或确定性降级路径。

Model Attempt 持久化 provider 报告的 prompt/completion/total tokens；
`backend/intelligence/model_gateway/usage.py` 只接受部署显式提供的 rate card，
缺少价卡时返回未定价计数而不生成成本数字。

## 13. 三环境功能等价

dev/test/prod 必须使用相同的 AgentDefinition、ToolDefinition、Prompt/Schema
contract、Context scope、Safety policy、Human Gate、ModelDraft status、
Error codes、Retry semantics、Workflow triggers、Named Actions、Audit、Outbox
和 Evaluation/Release gates。

仅允许替换 synthetic data factory、FakeProvider/deterministic adapter/approved
sandbox provider、数据库/队列/密钥/容量、故障注入和时钟。模拟适配器必须通过
同一个 Port，标记 data_class=SYNTHETIC，不能跳过 schema、Safety、Provenance、
Human Gate、审计或状态机。

## 14. 安全与部署基线

- 只有 Model Gateway Provider Adapter 可以读取模型凭据。
- ai_runtime 默认无业务数据库写权限，使用只读事件/投影连接。
- 外部出域按 data_class、目的、供应商准入和数据区域白名单控制。
- 生产密钥、测试密钥、合成数据和真实家庭数据物理隔离。
- 日志和 Trace 默认脱敏，禁止记录原始儿童文本和完整 Prompt payload。
- ai_runtime 使用独立技术表和最小权限 role；Outbox/Inbox 支持至少一次投递、
  去重、死信和重放。
- Context/Memory/Graph/Vector 删除作业具有可观测的完成证明。

## 15. 当前实现成熟度

| 能力 | 当前证据 | 当前成熟度 |
|---|---|---|
| Model Gateway | 有代码与测试；多模态与 Agent 生产组合根已有受控调用方；ADR-0081 提供显式 registry/env 组装入口；供应商准入受限 | EXPERIMENT |
| Context Engine | 有内存观察/快照原语、SQL durable adapter、过期清理与主体删除证明 | EXPERIMENT |
| Agent Runtime | `backend/intelligence/agent_runtime`：Definition、Authorization lease、Prompt/Schema 解析、DRAFT-only execution port、SQL AgentRun/Trace store | EXPERIMENT：运行时、授权租约、ContextScope 与生产组合根已实现，尚待 ToolCall 业务 consumer |
| Tool Runtime | `backend/intelligence/tool_runtime`：具名 ToolDefinition、三重授权、subject scope、pending Named Action、SQL outbox、accepted-action worker | EXPERIMENT：基础、durable outbox、SQL Human Gate inbox、post-gate attempt/DLQ worker 与 FGCN assignment adapter 已实现，尚待生产队列调度和更多业务 consumer |
| Prompt/Schema Registry | `backend/intelligence/prompt_registry` + `schema_registry`：版本、绑定、生效窗口、校验 | EXPERIMENT：内存 + SQL registry 与 0030 migration 已实现，版本变更保留旧记录并 fail-closed；AgentRuntime 组合工厂已强制 published resolve，运营审批签名、统一 loader 与回滚工作流仍待接入 |
| Safety/Human Gate | SafetyRuntime、SafetyDecision SQL ledger、SQL HumanTask、ToolAction inbox 与同事务审计 consumer 已形成统一 seam；业务通知/二次授权待接入 | EXPERIMENT |
| Evaluation | offline benchmark/multimodal eval、AiReleaseGate、`SqlAlchemyReleaseDecisionSink`、`SqlAlchemyReleaseControlStore`、`OperatorIdentity/Token adapter`、`ProductionReleaseRuntime`、`SqlAlchemyReleaseCandidateCatalog`（0032）、`SqlAlchemyDeploymentReceiptStore`（0033）、`HttpDeploymentPort`、`MtlsClientConfig`（ADR-0107）、`ReleaseDeploymentService` 的 metadata-only TelemetrySink、`gold.v1` 生成器、`BenchmarkReportArchive`（0034）、`BenchmarkSliceArchive`（0035）与 `AuthorizedEvaluationQueryService`（ADR-0106）已形成评测→外部签名人审→候选状态→provider-neutral 灰度/回滚→观测→归档→授权查询链；真实 key service 轮换/撤销回调、KMS/Secret Manager、dashboard、审计落库、部署平台权限、scheduler 待接入 | EXPERIMENT |
| Durable Trace/Cost/Attempt | AgentRun/Trace、Attempt、SafetyDecision、Telemetry 与 0044 Budget Reservation 已形成可审计 SQL seam；生产运行账本用独立短事务保证失败证据不随草稿回滚，Gateway 外呼前原子预留租户日预算并按 usage/不确定失败核销；0045–0048 以原子 ReleaseSet 绑定 provider Bundle、route/rate/budget/safety 内容摘要及 ACTIVE/ROLLBACK receipt，并将 release_set/bundle/deployment refs 传播到 Budget、Attempt、Provenance；已发布 Prompt template 通过 server-owned PromptExecutionPlan 进入真实 adapter；0049 的签名 control 绑定 exact transition 与期望有效序列；0050 增加 scope 唯一的 active projection、部署 CAS 与 adapter I/O 前的幂等 invocation fence claim；0051 在发布外部调用前独立提交 scope 排他 transition，并在 ACK 后同事务提交 receipt、projection 与 COMMITTED。围栏语义是“claim 为线性化点”，不承诺撤销已获准的 in-flight 调用；system-policy/Knowledge material resolver、真实发布平台 adapter、UNKNOWN reconciler、真实 PostgreSQL 并发演练、collector、scheduler、durable deletion proof/audit 与告警仍待完成 | EXPERIMENT |
| Durable Memory | `SqlAlchemyMemoryStore`（0022）持久化 MemoryRef 与删除证明；严格作用域/同意/期限校验，过期清理复用删除路径 | EXPERIMENT |
| Family Context/Growth Graph | Context SQL durable adapter 与 Growth Graph 0023 + Experience Outbox consumer 已具备实验接缝；全域事件接入、生产只读权限和跨流程检索尚未完成 | EXPERIMENT |
| 五类业务 Agent | 只有设计定义，没有 Runtime 承载 | NOT_IMPLEMENTED |

当前 AI 业务能力不得宣称 PILOT 或 PRODUCTION。Model Gateway/Context Engine
的存在只能说明基础原语已开始建设。

## 16. 与业务、流程、数据、应用架构的对齐

| 业务/流程 | AI 技术调用 | 输入数据 | 输出边界 | 应用落点 |
|---|---|---|---|---|
| S04 测评执行 | 证据结构化与解释准备 | AssessmentSession、EvidenceSet | Perspective/Draft，不产生诊断 | AssessmentApplication |
| S05 假设与入营 | Interpretation + Human Gate | Evidence、ContextSnapshot | Hypothesis、GrowthIntent 建议 | GrowthApplication Named Action |
| S06 90 天计划 | GrowthPlanner + Blueprint | GrowthIntent、Graph、Template | JourneyPlan Draft | JourneyApplication |
| S07 21 天行动 | ChildCoach/ParentAdvisor + Worker | ActivePhase、近期行动、偏好 | DailyAction Proposal | Journey/ActionApplication |
| S08 结果复盘 | Reflection + Evaluation | ActionRecord、Outcome、Feedback | ProcessPerspective/Story Draft | GrowthApplication |
| S09 对话助手 | Context Broker + Safety + Agent | 家庭授权上下文 | Explanation/Recommendation/人工待办 | AssistantApplication |
| S10-S14 服务协作 | Matching/TeachingAssistant | Service Blueprint、资格、质量证据 | 推荐/质检建议 | Service/FGCN Application |
| O12 AI 运行治理 | Evaluation/Release/Trace | 运行记录、反馈、版本 | ReleaseGate、Rollback、运营洞察 | OperationsGovernanceApplication |

AI Runtime 不直接操作 family_journey_plans、growth_actions、orders、bookings
等业务事实表。

## 17. 分阶段实施路线

### Phase 0：合同和治理冻结

建立并维护 `governance/AI_USE_CASE_REGISTRY.yaml`，再补齐 Prompt、Schema、Knowledge
运行时 Registry 的最小格式；
冻结 data_class、purpose、输入证据、输出对象和 Human Gate；统一 causation_id、
Provenance、Attempt、删除标记和三环境 contract/safety/parity 测试。

### P0：Family Context 最小闭环

将 assessment、journey、service 的已授权事件转换为 StateObservation；建立
PostgreSQL durable ContextSnapshot、主体删除和保留策略；建立只读 Growth Graph
projection；让 S04→S05 的解释请求可回放、可解释、可删除。

### P1：领域增量智能

在现有 hypotheses/action_candidates 上增加 primary_contradiction_ref 和
置信排序；将其作为 Service Blueprint、JourneyPlan Draft 输入；先实现一个
Agent 的 Context→Draft→Human Decision→Feedback 闭环。

### P2：Growth Intervention Engine

用结构化证据、家庭状态、历史反馈和 Blueprint 生成下一步候选；允许暂停干预、
需要人工、暂无足够证据等结果；将 Action Proposal 与 ActionRecord 分开并接入 S07。

### P3：Human Gate、Eval 和 Workflow Worker

统一高影响行为闸门、人工队列、超时、升级、补偿和审计；建立 Contract、Safety、
Grounding、Workflow、Drift Eval；持久化 Attempt、Trace、Cost 和模型版本，支持回滚。

### P4：横向扩展五类 Agent

单 Agent 证据充分后，逐一启用 ParentAdvisor、ChildCoach、TeachingAssistant、
GrowthPlanner、OperationsAssistant。多 Agent 只通过事件、ContextSnapshot 和
具名工具协作；新增 Agent 必须新增授权、工具白名单、评估集和接管策略。

## 18. AI 技术能力完成定义

一项 AI 能力只有同时满足以下条件，才能从设计态进入 PILOT：

1. 有 AI 用例、Agent、Tool、Prompt、Schema、Knowledge 的唯一版本登记；治理契约与
   运行时 Registry 的标识一致。
2. 有目的、主体、同意、data_class、留存和删除策略。
3. ContextSnapshot 能从事件/证据重建，且没有跨租户越权。
4. Model Gateway 通过 provider admission、schema、timeout 和 Attempt。
5. 输出始终是带 Evidence refs 和 Provenance 的 Draft/Recommendation。
6. 高影响动作有 Human Gate，只有人类 Named Action 能写业务事实。
7. 有成功、拒绝、超时、供应商不可用、人工超时和删除测试。
8. dev/test/prod 使用同一应用路径和状态机，只替换数据/外部适配器。
9. 有 Contract、Safety、Grounding、Workflow 和 Drift 评估证据。
10. 有 trace、成本、审计、回放、回滚和事故处置记录。

## 19. 本轮架构结论

第一阶段不是同时建设五个 Agent，而是先建成一条可验证的智能主链：

S04 Evidence → Family Context Snapshot → S05 Hypothesis Draft
→ Human-confirmed GrowthIntent → S06 Plan Draft → S07 Action Proposal
→ Human/Family ActionRecord → Reflection + Eval。

这条主链既服务当前 B2C 核心价值，又沉淀 Family Context、Growth Graph、
Intervention 和 Service Blueprint 四项长期护城河。任何不能增加证据质量、
家庭理解、行动可执行性或可信人工协作的 AI 组件，都不进入第一批核心研发。
