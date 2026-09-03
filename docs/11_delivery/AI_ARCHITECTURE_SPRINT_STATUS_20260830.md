# AiFamily AI 架构敏捷冲刺状态（2026-08-30）

## 本轮目标

把多模态体验从“模型调用示例”推进为可治理的 AI 原生纵向链：

```text
Context Broker
  → Multimodal Router
  → Model Gateway
  → DRAFT Model Output
  → Human Gate / Named Action
  → 业务域事实（唯一写入口）
```

测试环境与生产环境使用同一 API、状态机、权限边界和失败语义；仅替换合成数据、Fake Provider 和外部副作用。

## 已完成

1. **供应商无关的多模态路由**：按合规状态、数据分类、用途、延迟/成本策略选择候选；未获准供应商不会被调用。
2. **Context-bound 应用服务**：服务端注入 Tenant/Family/Subject/Consent/Locale/Environment，先生成 Context Snapshot，再进入路由与 Gateway。
3. **API 契约与媒体安全边界**：客户端不能提交 scope、provider、token、API key 或上下文快照；媒体只接受受控引用，拒绝 `data:`、base64、明文凭据和过长内联内容。
4. **Human Gate 之前的 DRAFT 约束**：模型只返回草稿和 provenance，不直写事实，不产生家庭总分或排名。
5. **ExperienceRun 持久化与重放**：新增 append-only run/event/checkpoint 适配器与 Alembic `0008_experience_runs`；支持租户/家庭/主体隔离、幂等重放冲突检测、DRAFT-only 和 worker 重启恢复。
6. **离线多模态评测**：质量、schema、拒答、安全、provenance、p50/p95 延迟与成本聚合；报告不携带原始媒体。
7. **显式 Synthetic Runtime 工厂**：要求调用方显式提供 tenant/family/subject scope，仅允许 `test` 环境，使用与生产相同的 Context Broker、Router、Gateway 和 DRAFT 输出链。
8. **请求级 Runtime Resolver 契约**：API 可按 URL family scope 解析服务端 runtime，body 不能覆盖租户、主体、同意或 provider；静态 runtime 与 resolver 同时存在时 fail-closed。
9. **组合根适配器**：新增 `experience_wiring.py`，提供独立的 router 挂载与 test-only resolver 安装函数；主入口稳定后只需调用该适配器，不改 AI 业务链。
10. **Run 生命周期传播**：ContextBound→Routed→Generation 现在可传递 `DurableExperienceRun`，成功记录 `STARTED/CHECKPOINTED/SUCCEEDED`，供应商失败记录 `STARTED/FAILED`。
11. **移动端 Draft API 联调**：冻结 `MultimodalDraftRequest/Response`，Family API client 调用正式路由并对响应做运行时契约与 family scope 校验；UI-05 展示显式生成中、DRAFT/待人工确认、错误和未连接状态，不使用静默 synthetic fallback。
12. **ExperienceRun→Human Gate 绑定**：新增非领域 bridge 与 ADR-0046，提交前校验 run 成功态、DRAFT checkpoint、草稿内容、scope 与 correlation；Named Action request 保留不可伪造的 `run_id/experience_run_ref`。
13. **Durable Human Gate 事务适配**：`AsyncExperienceRunHumanGateBridge` 接入现有 `SqlAlchemyHumanGate`，submit/decide 只在调用方事务中 flush，显式暴露 `commit/rollback`；重放保持原创建时间与 TTL，ACCEPT/REJECT 复用同一 run binding 校验。
14. **Named Action Relay seam**：新增 provider-neutral `RunBoundNamedActionEnvelope` 与异步 `NamedActionRelay`，ACCEPT 后由调用方显式发布；in-memory relay 按 `request_id` 幂等并拒绝内容冲突，不执行领域命令或隐式提交事务。
15. **Run HTTP 交互闭环**：补齐 decision、feedback、human-review、delete、replay 路由；dev/test 按 family 复用显式 ledger，跨请求可完成 Draft→人工决定→重放，前端 UI-05 同步提供确认/退回操作。
16. **SQL ExperienceRun Ledger**：新增异步 `SqlAlchemyExperienceRunLedger` 与
    `experience_run_interactions` 迁移 0010；创建幂等、交互追加、删除擦除、作用域
    隔离和重放均只 `flush`，由组合根显式持有事务，不伪装成同步 ledger。
17. **最小 Agent Runtime（ADR-0048）**：新增 `AgentDefinition` 静态能力上限、按 tenant/family
    TTL 授权的 `AgentAuthorization`、fail-closed `AgentAuthorizer` 与
    provider-neutral `StructuredGenerationPort` 执行端口；结果强制 DRAFT，运行时
    不导入领域仓储、不执行 Named Action。
18. **SQL Draft preflight/finalize/release**：SQL ledger 补齐 API 当前使用的预留、完成、
    释放协议，持久化 `create_status` 与 `create_response_payload`，进程重启后可安全重放
    已完成响应；未完成预留不会被误当成成功运行。
19. **Async 组合根桥接（ADR-0050）**：新增 awaitable ledger dispatch 与
    `AsyncExperienceRunLedgerBridge`，FastAPI 路由同时兼容同步 test ledger 与异步 SQL
    ledger，不使用 `asyncio.run`，事务仍由组合根持有。
20. **Prompt/Schema Registry（ADR-0049）**：新增不可变、use_case/agent 绑定且带
    effective window 的运行时 Registry；SchemaValidator 强制 required/evidence refs、
    forbidden/allowed fields、enum、JSON 子集和 Human Gate 边界，缺失或非发布版本
    均 fail-closed。
21. **Durable Outbox Worker（ADR-0051）**：新增 provider-neutral consumer/DLQ ports，
    bounded pending pull、成功后标记、瞬时失败重试、永久失败死信与 terminal ack；
    Worker 不提交 session、不调用模型供应商、不写领域事实。
22. **Outbox→Achievement 投影 consumer（ADR-0051）**：新增
    `ExperienceAchievementConsumer`，只接受 `experience.<ExperienceEventType>` envelope，
    fail-closed 重建并校验 scope/provenance/idempotency，调用证据绑定的
    `AchievementEngine`；非法、非事件或暂不支持嵌套引用进入 DLQ，重复投递保持幂等，
    不写 Family/Journey/Commerce 事实。
23. **AgentRun/Trace durable persistence（ADR-0053）**：新增 AI runtime-owned 的
    `ai_agent_runs` 与 `ai_agent_traces` 表、SQLAlchemy store 及 append-only Trace；
    支持 create/start/succeed/fail、请求幂等指纹、tenant/family scope 隔离、DRAFT-only
    输出与重放，store 只 flush，由组合根决定事务。
24. **Tool Runtime human-gated seam（ADR-0054）**：新增具名、版本化工具定义与
    ToolAuthorization；执行前同时校验 AgentDefinition 静态白名单、AgentAuthorization
    动态授权、ToolAuthorization scope/TTL/预算和主体范围，成功结果固定为
    `PENDING_HUMAN_CONFIRMATION`，适配器只准备 Named Action 参数。
25. **AgentAuthorization durable lease（ADR-0055）**：新增 SQL 授权租约与追加审计
    账本，支持 issue/revoke/find_active、tenant/family/use_case/tool/budget/TTL
    fail-closed 查询；仅 flush，由组合根统一提交，撤回记录 `ISSUED/REVOKED` 审计事件。
26. **ToolCall/Named Action durable outbox（ADR-0057）**：将
    `ToolCallResult` 以固定 `PENDING_HUMAN_CONFIRMATION` 状态写入 AI runtime-owned
    outbox，保留主体 scope、provenance、risk/expiry 与幂等 fingerprint；复用通用
    at-least-once Worker 投递到 Human Gate inbox，绝不直接执行领域命令。
27. **Durable Achievement projection（ADR-0058）**：新增 SQL 证据绑定成就读模型，
    `ExperienceAchievementConsumer` 通过 `apply_async` 写入，按 scope fingerprint +
    achievement key 幂等，重启后保留 evidence、provenance、earned_at；投影不包含家庭总分、
    排名或事实写入口。
28. **Tool Action → Human Gate inbox（ADR-0059）**：新增 provider-neutral inbox，严格
    校验 pending envelope、payload 快照、scope 与期限，幂等创建 `DRAFT` proposal/
    `OPEN` HumanTask；不执行领域命令。
29. **AI release/admission gate（ADR-0060）**：将离线 benchmark/multimodal 评测与
    ProviderRegistry 准入、质量/安全/schema/拒答/provenance、p95 延迟和成本阈值绑定，
    输出可审计 `ADMITTED/BLOCKED` 决策；不调用模型、不部署、不写业务事实。
30. **Agent Definition registry（ADR-0061）**：从治理 YAML 加载静态 Agent 白名单，
    校验策略、工具/用例范围、唯一 ID 与 DRAFT-only 不变量，避免运行时手工配置漂移。
31. **Agent Runtime composition factory**：新增显式 `build_agent_runtime`，强制注入
    Agent registry、Prompt Registry、Schema Registry 和 Model Gateway port，禁止隐式
    in-memory/未治理默认值进入生产组合根。
32. **Provider-neutral Safety Runtime（ADR-0062）**：新增输入/输出安全边界，禁止
    家庭总分/排名和高风险用例绕过人工闸门，统一输出 `ALLOW/REVIEW/BLOCK` 决策。
33. **Safety Runtime→Model Gateway 闭环（ADR-0063）**：Gateway 在 provider admission
    前执行输入阻断，在 JSON/schema 校验后执行输出阻断；`build_gateway` 默认注入安全运行时，
    Synthetic Runtime 显式复用同一策略，高影响/未成年人请求保持 DRAFT 并进入 Human Gate。
34. **Agent→Gateway 执行适配器（ADR-0064）**：新增 `ModelGatewayExecutionPort`，由组合根
    显式绑定已 wiring 的 provider，Agent 不读取供应商或 SDK；复用 Gateway 的准入、安全、超时、
    provenance 和 DRAFT-only 约束，未 wiring provider 在启动时拒绝。
35. **parent_advisor 首个低风险纵向切片**：以已授权的测评证据解释为场景，贯通 Agent 授权、
    Prompt/Schema Registry、Gateway、安全检查和 DRAFT/Human Gate 边界；不写家庭事实。
36. **Durable Model Attempt Sink（0017）**：新增 `SqlAlchemyAttemptSink`，支持异步组合根在
    provider 外呼前持久化 `STARTED`、完成后写入结果；Gateway 同时兼容同步测试 sink 与异步
    持久化 sink，新增跨 session 回读和真实 Gateway 闭环测试。
37. **DurableAgentRuntime 执行编排（ADR-0066）**：将 Agent 授权执行与 AgentRun/Trace
    durable store 绑定，稳定幂等键直接重放已成功 DRAFT，失败/进行中的重复执行 fail-closed；
    wrapper 不提交事务、不执行 Named Action。
38. **Durable Agent composition factory**：新增 `build_durable_agent_runtime`，强制同时绑定
    治理 AgentDefinition、Prompt/Schema Registry、Gateway 执行端口和 durable Run Store，形成
    可移植的生产组合根入口。
39. **ContextBoundAgentRuntime（ADR-0067）**：Agent 执行前校验服务端解析的 ContextScope
    （ACTIVE、consent、tenant/family/data class 一致），避免 HTTP 或 AgentTask 自带的 scope
    绕过身份/同意边界。
40. **Token/Cost 可审计聚合**：Model Attempt 记录 provider-reported prompt/completion/total
    tokens；`model_gateway.usage.aggregate_attempts` 接收显式 rate card 计算微 USD，缺失价卡时
    返回 `estimated_cost_microusd=None` 与未定价数量，避免伪造成本。
41. **SafetyDecision durable ledger（ADR-0069）**：新增 `ai_safety_decisions`（migration 0018）与
    `SqlAlchemySafetyDecisionSink`；Gateway 在输入/输出判定后保存仅含策略元数据的记录，
    持久化失败时 fail-closed，生产多模态/Agent 组合根均在同一请求事务绑定。
42. **Runtime scope traceability**：`StructuredRequest`、Model Attempt 与 SafetyDecision
    贯穿可选 `tenant_id/family_id`，Agent 与多模态 Draft scope 会自动注入；migration 0019
    为历史 ledger 增加索引，支持租户/家庭级 Trace、Token 和成本聚合。
43. **Release decision durable ledger（ADR-0070）**：`AiReleaseGate` 的
    `ADMITTED/BLOCKED` 决策通过 `SqlAlchemyReleaseDecisionSink` 写入
    `ai_release_decisions`（migration 0020），以完整决策指纹幂等，支持按候选/环境
    查询；仅保存治理元数据与 failure codes，不复制评测 payload、媒体或模型输出。
44. **Unified AI telemetry span boundary（ADR-0071）**：新增
    `backend/intelligence/observability` 的 `TelemetryContext`/`TelemetrySink`，
    `SqlAlchemyTelemetrySink` 写入 `ai_telemetry_spans`（migration 0021）；
    Model Gateway 已包住输入安全、准入、provider 外呼、schema/输出安全全链路，
    span 属性 allowlist、scope opaque ref 与 operation 幂等均有测试；生产 Agent/
    Experience 组合根要求注入 durable telemetry sink。新增
    `OpenTelemetrySpanSink`/`CompositeTelemetrySink`，可在不改变 AI Runtime 契约的
    情况下接入 SDK exporter。
45. **Durable Memory reference store（ADR-0072）**：新增
    `SqlAlchemyMemoryStore` 与 `ai_memories`/`ai_memory_deletion_proofs`（migration 0022），
    将 MemoryRef 的作用域、同意版本、来源、保留期和级联删除证明落到可重启存储；
    写入稳定指纹幂等、读取复用 MemoryRef fail-closed 校验，`purge_expired` 复用删除路径。
    不保存原始媒体、prompt、向量或模型输出。
46. **Growth Graph read projection（ADR-0073）**：新增
    `GrowthGraphEdge`/`GrowthGraphQueryPort` 与 `SqlAlchemyGrowthGraphProjection`，
    通过迁移 0023 持久化证据绑定的时序关系边；AI 仅可在作用域内查询，
    projector 写入按稳定指纹幂等，主体删除生成 proof，不创建新的业务域事实。
47. **Experience Outbox → Growth Graph consumer**：新增
    `GrowthGraphOutboxConsumer` 复用现有 at-least-once worker 和 DLQ 语义，
    从 `StoredExperienceMessage` 只解码受治理 `ExperienceEvent`，投影为事件/节点/证据引用边；
    malformed envelope 进入永久失败/DLQ，不会污染图谱。
48. **Service Blueprint matching（ADR-0075）**：新增
    `ServiceBlueprintMatcher`，只读取业务域 `PUBLISHED` Blueprint 快照，按
    `primary_contradiction_ref` 生成 evidence-bound、DRAFT-only 推荐；不创建、发布或执行蓝图，
    未成年人和高影响场景保留 Human Gate 标记。
49. **Blueprint → Human Gate pending action bridge**：`to_pending_named_action` 将
    BlueprintRecommendation 转换为显式 `PROPOSE_SERVICE_BLUEPRINT` pending Named Action，
    固定携带 scope/provenance/expiry；仍须 Human Gate 决策和 service domain consumer，绝不直接执行。
50. **Accepted Named Action dispatcher（ADR-0076）**：新增
    `AcceptedNamedActionDispatcher`，仅向组合根显式注册的业务 handler 分发已接受的
    `NamedActionRequest`；跨作用域、未注册 action、receipt 绑定错误均 fail-closed，
    同一 request_id 重放返回首次 receipt，不重复执行 handler。
51. **FGCN accepted-action adapter（ADR-0077）**：新增
    `build_fgcn_accepted_action_handlers`，把现有
    `execute_task_assignment_named_action` 绑定到 dispatcher，返回带 assignment
    ref 的 `ActionExecutionReceipt`；业务域继续拥有授权、审计、事务与持久化幂等，
    不把 Blueprint 推荐直接当成服务事实。
52. **Accepted Action durable delivery（ADR-0078，本轮）**：新增
    `ai_accepted_action_deliveries`（migration 0024）与
    `AcceptedNamedActionWorker`；先取得 Human Gate claim，再记录 durable attempt，
    通过 dispatcher 执行，成功后才清理 claim；跨进程重启可按 request_id/receipt
    幂等回放，未注册动作进入 `DEAD_LETTERED`，瞬时错误等待 lease takeover。
53. **Accepted Action bounded queue poll**：Human Gate SQL adapter 新增只读
    `pending_accepted_task_ids(limit)`，Worker 新增 `run_once`，逐条隔离 claim 冲突、
    transient error 与 DLQ，避免单条任务阻塞整个批次；持续调度器和 takeover 压测仍由部署接线。
54. **Accepted Action scheduler/takeover verification**：新增 `run_until_idle` 有界
    调度器、DLQ 查询接口，并以两 SQL session 验证 active claim 拒绝、lease 过期接管、
    durable receipt 重放不重复调用 handler。
55. **FGCN Blueprint proposal consumer（ADR-0079）**：新增
    `PROPOSE_SERVICE_BLUEPRINT` accepted-action handler 与 migration 0025，
    将人工接受的 evidence-bound recommendation 落为服务域提案事实；不自动打开
    `ServiceCase`、不预约、不通知、不支付，后续 case opening 仍走独立领域闸门。
56. **FGCN accepted-action runtime composition（ADR-0080）**：新增
    `FGCNAcceptedActionRuntime` 与 `SqlAlchemyAcceptedActionQueue`，按一次 bounded
    scheduler invocation 使用新的 SQL session 组装 Human Gate、delivery ledger、
    FGCN assignment/Blueprint handlers；队列过滤 `SUCCEEDED`/`DEAD_LETTERED` 终态，
    并提供 metadata-only DLQ 查询。staging/production 共用该组合路径，仅替换显式
    worker identity、provider admission 与数据库依赖。
57. **Governed multimodal Gateway composition（ADR-0081）**：新增
    `build_openai_compatible_gateway_from_registry`，部署显式声明 provider ids，
    启动阶段校验 callable status/environment 后才读取凭据并创建 adapter；统一
    Gateway 继续负责 data class、Safety、Attempt、schema、Provenance 与超时。
    未完成合规登记的 provider 在读取凭据前拒绝，测试环境使用同一入口配合
    FakeProvider/MockTransport 验证，不激活真实外部供应商。
58. **AI achievement Human Gate landing（ADR-0082）**：新增
    EngagementDraft scope 绑定、achievement candidate 证据校验和
    `PUBLISH_EXPERIENCE_ACHIEVEMENT` Named Action；仅在 Guardian/Professional
    接受后写入 `ai_achievement_projections` 的 `AI_EVIDENCE_MOMENT`，并通过 SQL
    projection 保留 provenance、scope、evidence 与幂等回放。AI 不直接写业务事实。
59. **Durable Experience Outbox runtime（ADR-0083）**：新增
    `ProductionExperienceOutboxRuntime`，每次 bounded poll 使用全新 SQL session，
    以 metadata-only `experience_outbox_delivery_attempts` ledger 持久化 attempts、
    status、error 与时间戳；worker 重启后继续递增并支持 PUBLISHED/DEAD_LETTERED
    终态查询，原始家庭 payload 不复制到运营 DLQ 元数据。
60. **Experience Outbox lease/takeover（ADR-0084）**：delivery ledger 新增
    `worker_id` 与 `lease_until`，worker 领取消息后才允许消费；健康租约由其他
    worker 跳过，过期租约可接管并递增 durable attempt，成功/死信清理租约。
61. **SQL metadata-only DLQ（ADR-0085）**：新增
    `SqlAlchemyExperienceDeadLetterSink` 与 migration `0027`，按 `message_id`
    幂等保存事件类型、租户/家庭范围、attempt、错误和终态时间；不复制原始
    家庭 payload，受控 replay 仍从 source outbox 读取。
62. **Repeatable achievement occurrence（ADR-0086）**：`Achievement` 新增稳定
    `occurrence_id`，AI evidence moment 按 validated evidence 派生 identity；SQL
    projection 唯一键扩展为 `scope + key + occurrence`，distinct evidence 可产生多个
    家庭私有成就，重复 evidence 仍 fail-closed/idempotent。
63. **Achievement feedback projections（ADR-0086）**：Experience consumer 在同一
    outbox 事务内更新 SQL notification inbox 与 scope-local analytics；analytics
    通过 metadata-only record ledger 去重，不存原始 event/model payload，不计算家庭总分或排名。
64. **Feedback read API vertical slice**：新增只读
    `GET /families/{family_id}/experience/achievements`、`notifications`、`analytics`；
    family scope 由 resolver 服务端解析，未安装 identity/consent resolver 时统一 503，
    移动端新增 response normalizer 与 API client 方法，禁止客户端覆盖 tenant/subject/provider。
65. **Shared scope authority（ADR-0087）**：新增
    `SharedExperienceFeedbackRuntimeResolver`，反馈读取可直接复用 Draft runtime
    的认证、家庭绑定、同意和删除状态检查；没有 resolver 时保持 503 fail-closed，
    避免 Draft 与反馈入口出现授权漂移。
66. **Notification read-state（ADR-0088）**：新增
    `POST /families/{family_id}/experience/notifications/{notification_id}/read`，
    服务端按共享 `ExperienceScope` 校验 tenant/family，只更新通知 read model；
    移动端要求 `Idempotency-Key`，重试收敛到同一 `READ` receipt，不改写成就、事件或 AI provenance。
67. **Durable Prompt/Schema registry（ADR-0089）**：新增 migration `0030` 与
    SQL adapters；版本身份不可覆盖，生命周期变更生成新版本，AgentRuntime 组合工厂
    支持异步 SQL registry 并强制解析 `PUBLISHED` 且生效中的 Prompt/Schema，缺失或歧义 fail-closed。
68. **AI release human control（ADR-0090）**：新增 migration `0031` 与
    `ReleaseControlStore`；只有真人 operator 及外部签名 verifier 能对 `ADMITTED`
    决策记录 APPROVAL，回滚以 append-only 指针记录并支持幂等重放，AI actor、BLOCKED
    决策、无效签名和同候选目标均 fail-closed；只保存不可逆 signature_ref，控制边界
    不触发部署副作用。
69. **Agent Runtime request-scoped SQL registries（ADR-0091）**：生产 Agent 组合根支持
    `Prompt/SchemaRegistryFactory(AsyncSession)`，在请求级 UoW 中读取 migration `0030`
    的已发布版本，并与 Attempt、Safety、Telemetry、AgentRun/Trace 共用事务；新增
    集成测试证明重启后版本资产不依赖进程内 registry。
70. **AI release candidate catalog（ADR-0092）**：新增 migration `0032` 与
    `ReleaseCandidateCatalog`，分离保存候选版本元数据并投影
    `BLOCKED/ADMITTED/APPROVED/ROLLED_BACK`；状态推进必须引用签名控制事件，批准前
    回滚、未批准目标和元数据冲突均 fail-closed，不产生部署副作用。
71. **Provider-neutral deployment/rollout port（ADR-0093）**：新增 migration `0033`、
    `ReleaseDeploymentService` 与 `DeploymentPort`；仅已批准候选和签名控制事件可驱动
    CANARY/ACTIVE/ROLLBACK，端口调用前以幂等 receipt ledger 防重复外部副作用；测试
    使用显式 deployment adapter 替身，生产仍需真实平台权限、补偿与演练证据。
72. **HTTP deployment adapter（ADR-0094）**：新增 `HttpDeploymentPort`，base URL、
    token provider、请求 timeout 与 HTTP client 全部显式注入；统一发送
    control/environment/idempotency headers，编码 candidate path，屏蔽家庭 payload，并将
    token source 异常、非 2xx、timeout/network/malformed response 收敛为稳定错误码。
    `MockTransport` 测试与生产使用同一请求契约。
73. **Release deployment telemetry（ADR-0096）**：`ReleaseDeploymentService` 支持显式
    注入统一 `TelemetrySink`，在真实端口调用前后记录 canary/active/rollback 的
    provider/model/version、环境、阶段和稳定错误码；trace id 由候选与环境摘要派生，
    不保存签名、幂等键、报告或家庭 payload。成功/平台错误均有 InMemory sink 测试。
74. **Telemetry retention/deletion worker（ADR-0097）**：新增 `TelemetryRetentionWorker`
    与 SQL/InMemory `TelemetryRetentionStore`，以 `started_at` 为 TTL 基准执行稳定排序、
    有界批量删除并生成 metadata-only deletion receipt；审计 sink 幂等，SQL 只 flush
    并由调用方事务负责提交/回滚。测试覆盖 TTL、批次边界、幂等和事务回滚。
75. **Production release composition root（ADR-0098）**：新增 `ProductionReleaseRuntime`
    与 HTTP 组合工厂，显式绑定 OperatorIdentity、短期 token、DeploymentPort、receipt
    和 TelemetrySink；每次发布从外部身份解析真人并强制 `ai.release.deploy` scope，调用者
    不能注入 `human_actor`，staging/production 共享同一路径。
76. **Production telemetry retention composition（ADR-0099）**：新增
    `ProductionTelemetryRetentionRuntime`，每次 bounded TTL run 使用独立 SQL session/
    transaction，并强制注入 deletion-audit sink；删除与 metadata-only receipt 原子提交，
    失败可回滚，scheduler 仍由部署层触发。
77. **Model Gateway credential lease（ADR-0100）**：新增
    `ProviderCredentialPort`、`HttpProviderCredentialPort` 与带过期时间的
    `CredentialLease`；组合工厂在 registry admission 后解析外部租约，适配器不持久化
    或记录 secret，provider mismatch/过期均 fail-closed。保留环境变量兼容路径，
    HTTP 组合工厂支持注入 mTLS/CA 配置 client，revoked lease 在 adapter 构造前
    fail-closed；真实生产仍需密钥服务、轮换/撤销与
    演练证据。
78. **Versioned synthetic gold set（ADR-0101）**：新增 `gold.v1` 可复现生成器，
    固定提供 text 50、image 40、audio 40、video 30、mixed 40，共 200 个无媒体字节
    case，其中 40 个拒答/对抗样本；fingerprint 可用于 CI、staging 与发布演练对齐。
    报告归档和按模态/语言切片 runner 仍待完成。
79. **Benchmark report archive（ADR-0102）**：新增 InMemory/SQL
    `BenchmarkReportArchivePort` 与 migration `0034`；按 `report_ref` + dataset
    fingerprint 幂等归档聚合报告，递归拒绝 prompt/output/media/credential 等敏感字段，
    SQL adapter 只 flush、由组合根负责事务，并提供有界 metadata 回读查询。生产调度、
    按模态/语言切片 API 和长期保留策略仍待接入。
80. **Production evaluation archive composition（ADR-0103）**：新增
    `ProductionEvaluationArchiveRuntime`，staging/production 每次使用独立 SQL
    session/transaction 归档报告，提交/回滚边界与测试一致；scheduler、按模态/语言切片和
    长期保留策略继续由部署层负责。
81. **Multimodal evaluation slice runner（ADR-0104）**：新增
    `MultimodalSliceRunner`，按 modality/locale/age_band 复用统一评测契约生成独立
    aggregate reports；混合模态按包含关系进入多个 modality slice，年龄段只来自合成
    Gold Set。生产 slice 查询 API 与 dashboard 仍待接入。
82. **Multimodal slice archive（ADR-0105）**：新增 migration `0035` 与
    `BenchmarkSliceArchivePort`；父报告与 modality/locale/age_band slices 在同一
    production transaction 提交，按 `report_ref + dimension + value` 幂等回读，查询
    只返回 bounded aggregate metadata。dashboard、审计落库、scheduler 和长期保留
    策略仍待接入。
83. **Authorized evaluation query API（ADR-0106）**：新增
    `AuthorizedEvaluationQueryService` 与 Family API 内部只读端点
    `/internal/ai/evaluations/reports`、`/internal/ai/evaluations/slices`；
    外部 `OperatorIdentityPort` 必须授予 `ai.evaluation.read`，默认未组合时 503，
    无 scope 时 403，响应只返回 bounded aggregate metadata。真实 operator
    identity/mTLS、审计落库、dashboard、游标分页与长期保留策略仍待部署接入。
84. **Explicit mTLS transport and lease revocation（ADR-0107）**：新增
    `MtlsClientConfig`，要求显式 CA/client cert/key 绝对路径并同时支持 sync/async
    httpx client；`CredentialLease.revoked` 在模型 adapter 构造前 fail-closed 为
    `CREDENTIAL_REVOKED`；provider 外呼前可执行组合根注入的 revocation checker，
    HTTP 凭据端口提供 metadata-only revocation-status 查询，工厂通过
    `check_credential_revocation=True` 显式开启。证书轮换、KMS/Secret Manager、
    真实 endpoint 与端到端演练仍待部署。
85. **动态租约撤销状态查询**：`HttpProviderCredentialPort` 新增
    `POST /v1/provider-credentials/leases/revocation-status` metadata-only 查询，
    严格校验 `revoked: bool`；HTTP Gateway 通过
    `check_credential_revocation=True` 显式绑定到 provider 外呼前检查。新增
    组合工厂、非法响应和状态查询测试；目标密钥服务仍需实现该 endpoint 并纳入
    mTLS/轮换/告警演练。
86. **租约 deadline 安全边界**：Provider adapter 在网络调用前要求
    `expires_at` 覆盖本次请求 timeout；临近到期的租约直接返回
    `CREDENTIAL_EXPIRED`，并以测试证明没有发生 provider 外呼。
87. **mTLS 配置冲突防护**：凭据、身份和部署 HTTP adapter 禁止同时传入已构造
    client 与 `MtlsClientConfig`，避免 mTLS 配置被静默忽略；新增构造期冲突测试。
88. **Engagement 授权实时复核（ADR-0108）**：`EngagementDraftService` 在调用
    Model Gateway 前重新校验 consent/授权有效期，并支持可信时钟注入；过期时不
    发生 provider invocation，保持 AI Draft-only 与 Human Gate 边界。
89. **异步撤销检查隔离**：同步实现的 credential revocation checker 通过线程池
    执行，异步 checker 继续 await；新增线程归属测试，防止同步密钥服务阻塞模型
    请求事件循环。
90. **Engagement 服务端事件读取端口（ADR-0109）**：新增
    `EngagementEventReader` 与 `EngagementDraftApplication`，调用方只提交
    `event_ids`，由受信任 reader 按 `ExperienceScope` 返回真实事件；缺失或非法
    事件在 Model Gateway 前拒绝，客户端不能伪造 achievement 证据。
91. **SQL Event Reader 实现**：新增 `SqlAlchemyEngagementEventReader`，复用
    `experience_outbox_messages`，按租户/区域/家庭/consent 与 event id 查询，
    重建并校验 `ExperienceEvent`，删除中的 scope、非法 envelope 和跨范围事件
    均 fail-closed；生产主入口 wiring 与 PostgreSQL 并发演练仍待接入。
92. **Production Engagement Runtime 组合根（ADR-0110）**：新增
    `ProductionEngagementRuntimeResolver`，将真实 `ExperienceScope`、SQL Event
    Reader、Model Gateway 与 Attempt/Safety/Telemetry durable sink 绑定到同一
    请求级 UnitOfWork；测试环境通过同一 resolver 形状验证生产功能 parity，真实
    真实 identity/consent store、主入口挂载和 PostgreSQL 并发演练仍待部署平台接入。
93. **Authenticated Engagement Scope 适配（ADR-0111）**：新增
    `AuthenticatedEngagementScopeResolver`，复用 principal、trusted tenant/family
    binding 和 `ConsentGate`，将已授权 `ContextScope` 转为 Engagement 所需的
    `ExperienceScope`；缺失/撤回 consent 在模型调用前 fail-closed。
94. **Engagement Draft HTTP 边界（ADR-0112）**：新增
    `POST /families/{family_id}/experience/engagement/drafts`，请求只允许
    `request_id`、`event_ids` 和生成意图 payload；路由始终挂载，无 runtime 时
    稳定返回 503，注入 runtime 后返回 DRAFT、证据事件和 provenance，成就仍需
    经过 Human Gate。
95. **family_api 主入口挂载**：`create_app()` 现在统一挂载 Engagement Draft
    router，并支持通过 `engagement_runtime_resolver` 显式注入生产组合根；未注入
    时保持 OpenAPI 可发现但 503 fail-closed。
96. **dev/test 功能 parity runtime（ADR-0113）**：`dev_wiring.py` 通过已认证的
    bearer session 注入 `SyntheticEngagementRuntimeResolver`，复用同一
    EngagementDraftApplication/Model Gateway/HTTP 契约生成 `SYNTHETIC` DRAFT，
    不因模拟数据而裁剪功能，且明确禁止进入生产组合根。
97. **SQL consent snapshot resolver（ADR-0114）**：新增
    `SqlAlchemyConsentSnapshotResolver` 与 `SqlAlchemyFamilySubjectIdsResolver`，
    从 canonical `persons/consents` 表读取主体和当前授权，生成稳定 consent
    version；缺失主体年龄、非法枚举或空授权均 fail-closed。
98. **SQL request-auth composition（ADR-0115）**：新增
    `SqlAlchemyBearerPrincipalResolver`（token 只以 SHA-256 摘要查询）和
    `SqlAlchemyTrustedTenantScopeStoreFactory`，并由
    `SqlAlchemyAuthenticatedEngagementScopeResolver` 组合身份、租户、家庭主体与
    consent，生产可以通过显式 resolver 注入真实数据库链路。
99. **HTTP request-auth Engagement wiring（ADR-0116）**：新增
    `install_sql_engagement_runtime_wiring`，按请求读取 Authorization 与追踪头，
    构造 SQL identity/consent resolver 和生产 Engagement runtime；身份不缓存，
    未配置生产安装器时路由继续 503 fail-closed。
100. **Identity session 签发/轮换端口（ADR-0117）**：新增
    `IdentitySessionPort` 与 `HttpIdentitySessionPort`，将真实 auth_identity 的
    会话签发、轮换、撤销从 AI 组合根显式注入；bootstrap credential、mTLS client、
    access token 传输均有独立边界，响应过期/畸形和非 2xx 统一 fail-closed。dev/test
    继续使用合成会话但保持同一 scope/consent/Model Gateway 路径。
101. **多模态路由/Gateway 一致性闸门（ADR-0118）**：生产组合根启动时校验路由
    profile 与 Model Gateway adapter 集合、`model/model_version` 及
    `supported_modalities` 一致；缺 adapter、模型身份漂移或 AUDIO/VIDEO 能力夸张在
    启动期 fail-closed。新增三项组合测试，防止可替换模型配置在路由目录与实际调用层
    之间静默分叉。
102. **多模态 HTTP request-auth wiring（ADR-0119）**：新增
    `install_sql_experience_runtime_wiring` 与 `SqlAlchemyAuthenticatedContextScopeResolver`，
    使 Multimodal Draft 路由按请求复用 Bearer→tenant/family→subject→consent 链，
    并通过 `create_app(experience_runtime_wiring=...)` 显式安装；缺失安装器继续 503，
    缺失/失效 token 在 scope 边界返回 401/403，生产与测试保持同一运行时形状。
103. **Durable ContextBroker 生产组合（ADR-0120）**：新增 `SqlContextBrokerFactory` 与
    `build_sql_context_broker`，并允许 Multimodal Draft SQL wiring 通过 factory 显式构造
    session-per-operation 的 `AsyncSqlContextBroker`；新增 migration `0036` 建立
    observations、snapshots、snapshot-observations 三张技术投影表，进程重启后继续执行
    tenant/family/subject/purpose/consent/TTL 校验。
104. **Engagement Context 快照复核（ADR-0121）**：Production Engagement Runtime 可显式
    注入 ContextBroker，将 ExperienceScope 投影为 ContextScope 后复核 `context_snapshot_ref`；
    任何跨租户、跨家庭、主体不匹配、同意撤回或过期快照均在 Model Gateway 外呼前拒绝，
    并新增组合测试证明 provider invocation 不受影响。
105. **auth_identity 实时 introspection（ADR-0122）**：`HttpIdentitySessionPort` 新增
    `introspect`，`HttpIdentityPrincipalResolver` 将经过 auth_identity 验证的会话转换为
    `AuthenticatedPrincipal`；不复制 token 表，family 绑定与过期在 tenant/consent 组合前
    fail-closed，dev/test 仍保持原有合成与 SQL fixture 路径。
106. **身份组合回归验收**：身份端口、HTTP principal resolver、Engagement/Multimodal
    production wiring 与治理登记专项测试共 **30 passed**；真实 auth_identity endpoint、
    KMS/Secret Manager 和默认生产 middleware 仍由部署平台接入。
107. **身份 resolver 注入 seam**：`SqlAlchemyAuthenticatedContextScopeResolver` 与
    `SqlAlchemyAuthenticatedEngagementScopeResolver` 新增 request principal factory，
    production wiring 可将 `HttpIdentityPrincipalResolver` 接入同一 tenant/consent 组合，
    同时保留 SQL bearer fallback 与 dev/test parity。
108. **身份 resolver 工厂固化**：新增 `build_http_identity_principal_resolver_factory`，
    统一把请求 Authorization/追踪头绑定到 auth_identity introspection resolver，减少部署
    代码重复实现 token 解析，并通过 fail-closed 测试验证非法端口不会被接受。
109. **Secret Manager 凭据适配器**：新增 `SecretManagerCredentialPort` 与
    `CredentialLeaseMetadata`，以 metadata-first 顺序解析 provider/environment scoped
    secret reference，再构造短期 `CredentialLease`；provider mismatch、空 secret、
    metadata/reader 异常均 fail-closed；revoked/expired metadata 在读取 secret 前拒绝，
    secret 不进入 repr 或异常文本。凭据专项测试当前 15 项
    回归测试全部通过；真实 KMS/Secret Manager endpoint、轮换/撤销运维证据与生产演练
    仍由部署平台接入。
110. **Secret Manager 组合根**：新增
    `build_secret_manager_openai_compatible_gateway_from_registry`，将 KMS/Secret
    Manager 回调显式注入 Model Gateway；测试/生产都沿用同一 registry admission、
    Safety、Attempt、Telemetry 和 deadline/revocation 边界，不因测试环境缩减功能。
111. **UI-02 AI 入口一致性**：将补充题答案选择收敛到
    `answerAssessment(itemRef, optionId)`，并统一升级 CTA 文案为“升级到 AI 成长诊断，
    看更完整的分析”；UI-02 专项测试 **11 passed**，TypeScript 编译通过。
112. **移动端服务契约测试迁移**：`family-mobile-core` 测试已对齐当前
    `service_offering_id`/`availability_slot_id` canonical aggregate ID 契约，并将 UI
    registry tab 覆盖断言校正为 UI-01～UI-34 的 34 个页面；移动端全量回归 **261 passed,
    1 skipped**。
113. **移动端数据加载状态可见性**：UI-31/UI-32/UI-34 将服务、资产和记录同步失败状态
    显式呈现在页面中，清理了未使用的 load state/error 变量；Expo lint 从 6 个 warning
    收敛为 **0 个 lint error/warning**（仅保留 Node 模块类型提示）。
114. **UI-01 Achievement Rail 真实挂载**：首页通过 Family API 同时读取成就投影与未读
    成就提醒，使用客户端契约归一化并校验 family scope 后展示 `AchievementRail`；加载、
    失败重试、空/不可用投影、无成就提醒和通知已读跳转均保留生产同构语义，不生成本地
    演示成就。移动端全量回归保持 **262 passed, 1 skipped**。
115. **UI-29 成长成果同源投影**：成长成果页复用 `/experience/achievements` 的真实
    Achievement Projection，并保留 scope 校验、加载失败重试和继续行动出口；首页提醒
    跳转后不再落入独立的静态成就数据源。
116. **UI-34 成就提醒中心**：服务记录页接入未读成就提醒查询，逐条通过幂等
    `markFamilyAchievementNotificationRead` 消费提醒；网络或授权失败时保留未读状态并
    提供重试，不触发自动联系、消息发送或工单创建。移动端全量回归 **262 passed,
    1 skipped**。
117. **生产 Outbox 告警 seam（ADR-0123）**：`ProductionExperienceOutboxRuntime` 增加
    provider-neutral `alert_sink`，仅在 retry/dead-letter 后、数据库事务提交完成时
    投递脱敏 `OutboxWorkerReport`；告警传输故障不会回滚已确认的投影或 outbox 状态，
    staging/production 继续共用相同调度与失败语义。
118. **成就提醒投影留存（ADR-0124）**：新增有界
    `AchievementNotificationRetentionWorker` 与生产组合根，按 TTL/批量上限清理
    `ai_achievement_notifications`，通过注入的 metadata-only audit sink 记录删除证明；
    不删除 Achievement/ExperienceEvent 事实，不发送通知，不依赖用户是否已读来延长保留。
119. **部署侧 AI runtime 调度契约（ADR-0125）**：Outbox 与通知 retention 组合根新增
    显式 schedule value object 和 `run_scheduled_tick`，校验 interval/批量/最大轮询上限；
    每次 tick 有界、可重试且不启动 API 常驻线程，实际 recurrence 由部署 scheduler 注入。
120. **调度契约回归验收**：Outbox 与通知 retention 的 schedule tick、上限校验、事务边界
    与告警/删除证明专项测试通过；部署平台仍需将 interval 配置映射到实际 CronJob、队列
    调度器或内部 scheduler。
121. **Outbox 运维只读查询（ADR-0126）**：新增有界
    `delivery_attempts(limit, status)`、cursor 分页和 `delivery_attempt_summary()` 查询，
    仅返回 delivery attempt metadata，支持 dashboard/告警按状态观察积压、重试和死信；
    不暴露 family scope、原始 payload 或模型输出，也不参与投递事务。
122. **运维查询 operator 授权（ADR-0127）**：新增
    `AuthorizedExperienceOperationsQueryService`，每次查询要求外部 operator identity
    环境匹配并具备 `ai.experience.operations.read` scope；家庭 API 不暴露运维数据，
    未授权或身份服务异常均 fail-closed。
123. **运维查询 HTTP 边界与访问审计**：在 `/internal/ai/experience` 挂载分页与 summary
    endpoint；cursor 由注入的 HMAC signer 绑定状态并短期过期，查询仅返回 metadata；
    operator allow/deny/identity-error 事件可注入 metadata-only audit sink，审计故障
    fail-closed，未配置 service/signer 时接口保持 503；`create_app()` 提供显式
    `experience_operations_query_wiring` composition hook，禁止与半套依赖混用。
124. **运维访问审计 durable sink（ADR-0128）**：新增
    `SqlAlchemyExperienceOperationsAuditSink` 与 Alembic `0037_ai_experience_operations_audit`，
    只写 operator 授权结果和时间等 metadata，沿用 caller-owned session 的 add/flush 语义；
    同时提供基于 `async_sessionmaker` 的 per-access transaction sink，在查询返回前提交
    审计；组合 helper 要求显式 session/session factory，不读取隐藏配置。
125. **FastAPI durable dependency 回归修复**：依赖覆盖改用无默认参数闭包，避免
    `async_sessionmaker` 携带的驱动模块被 FastAPI 深拷贝；完整 production wiring
    通过 HTTP summary 请求验证，审计记录仍在返回前提交。
126. **运维错误信息脱敏**：delivery attempt API 不再透传 worker/provider 的
    `last_error` 文本，统一只返回 `DELIVERY_ERROR_REDACTED`；dashboard 仍可按
    status、attempts、时间和 lease 定位问题，避免原始 payload、凭据或模型错误文本
    越过 metadata-only 边界。
127. **请求绑定的 operator identity（ADR-0129）**：运维 API 强制解析
    `Authorization: Bearer ...`，以 task-local 短生命周期上下文绑定当前请求；新增
    `HttpRequestOperatorIdentityPort` 向 auth_identity 转发 bearer 并仅解析 operator
    metadata。缺失/格式错误返回 401，身份服务拒绝/网络错误保持 503；请求结束清理
    context，token 不进入异常、审计或持久化。
128. **HTTP 生产组合根**：新增
    `build_http_production_experience_operations_query_wiring`，将 request-bound
    identity port、durable audit session factory、HMAC cursor signer 和 operations
    runtime 组装为 `create_app()` hook；HTTP MockTransport 端到端测试确认 bearer 与
    environment header 正确转发，且不改变 dev/test 路由契约。
129. **内部评测 API 身份边界统一**：抽取共享
    `operator_request_context`，让 `/internal/ai/evaluations/*` 与
    `/internal/ai/experience/*` 均要求 request bearer；缺失/非法凭据统一 401，
    真实 `OperatorIdentityPort` 仍负责环境和 scope 授权，避免内部 API 出现认证策略分叉。
130. **评测查询 HTTP 生产组合根**：新增
    `build_http_production_evaluation_query_wiring`，与 Experience 运维查询复用同一
    request-bound identity port 和显式 mTLS/client 注入方式；端到端测试确认评测归档
    查询只在 bearer identity 通过 scope 校验后返回。
131. **dev/test 内部 AI 查询 parity**：新增仅限显式 dev/test 环境的
    `DevOperatorIdentityPort`、synthetic operations metadata runtime 与 synthetic
    evaluation archive，并在 `create_app()` 中安装；两类内部 API 可使用模拟会话走完
    bearer→identity→scope→query→metadata response 链路，production 仍保持未配置时 503。
132. **UI-05 AI 草稿反馈闭环**：在陪伴草稿的 DRAFT 展示层提供“有帮助 / 没帮助 /
    请求人工”三个有界反馈动作，调用既有
    `POST /families/{family_id}/experience/multimodal/runs/{run_id}/feedback` 追加式
    ledger；请求携带 `run_id`、`draft_version`、`model_version` 与幂等键，提交状态、
    重试错误和人工升级文案均在 UI 内可见。反馈只用于体验调优/人工复核，不自动写入
    Family、Growth、Service 或 Commerce canonical fact。
133. **反馈偏好上下文接入生成链路（ADR-0130）**：Run Ledger 新增
    `FeedbackPreferenceSnapshot` 读取契约，内存、SQL、async bridge、session-per-call
    和 committed wrapper 保持一致；生成前按精确 tenant/family/subject scope 聚合
    最近最多 5,000 条反馈，仅把三类信号计数作为服务端拥有的
    `experience_feedback` Prompt 上下文，覆盖客户端同名字段并隐藏已删除 Run。该上下文
    不包含原始理由、媒体、模型原文、家庭总分或排名，缺少旧 Ledger 能力时保持兼容。
134. **Prompt/Schema 版本绑定（ADR-0132）**：新增显式
    `MultimodalContractRegistryBinding`，在组合根注入时同时解析已发布 PromptBundle 和
    SchemaDefinition，校验 use-case/agent/ref/version 及客户端 schema 完整一致；未登记、
    非生效或 schema 漂移均在 Provider 外呼前拒绝，返回稳定
    `PROMPT_SCHEMA_BINDING_REJECTED`。staging/production wiring 现在缺少
    `contract_binding` 即启动拒绝；未安装生产 resolver 的应用仍以既有 503 fail-closed，
    真实 SQL Registry 资产部署仍需审批证据。
135. **反馈上下文离线评测**：`GoldCase` 支持媒体无关的有界
    `feedback_context`，Multimodal Eval Runner 在同一 `gold.v1` 中对照不同反馈信号，
    验证 adapter 能按反馈调整表达策略；报告仍只保留 aggregate metrics，技术评测继续
    固定 `education_outcome_status=NOT_MEASURED`，不形成家庭分数或供应商排名。
136. **家庭体验标准 Contract Selector**：新增
    `standard_contracts.py`，冻结 `family_assistant_conversation` → `parent_advisor` →
    `family_assistant_v1` / `assistant_response_v1` 的唯一 ref 映射；它只提供选择器，不
    内置未审核 Prompt 文本或 schema，必须由显式注入的 reviewed Registry 解析。
137. **家庭体验标准 Prompt/Schema 资产基线（ADR-0133）**：新增
    `standard_assets.py`，以不可变 `FamilyExperienceAssetBundle` 固定
    `family-companion.v1` / `family-experience-draft.v1` 的结构化草稿契约，包含
    understanding、next_step、limitations 和禁止字段边界；工厂默认 DRAFT，只有显式
    reviewer/effective_at 才可构造 PUBLISHED。测试覆盖合成发布 fixture 与 Registry
    成对解析，生产仍需 SQL Registry/审批流程显式注入，不能把 fixture 当生产资产。
138. **标准资产成对注册（ADR-0133）**：新增
    `standard_asset_registration.py`，注册前同时预检 Prompt/Schema 的不可变身份，
    默认要求成对 PUBLISHED，兼容内存与异步 SQL Registry；SQL 事务仍由组合根持有。
    集成测试验证跨事务提交后的绑定解析与重复注册拒绝。
139. **Request-safe SQL Contract Binding**：新增 `sql_contract_binding.py`，分别以
    session-per-call reader 解析 Prompt/Schema，不保留启动期 AsyncSession；production
    wiring 测试现从真实 SQL Registry 表注册标准已发布资产，并跨独立 session 完成
    HTTP 草稿、重放和缺失 binding 启动拒绝验证。
140. **AI 回归时钟确定性**：修正 Context observation TTL、Human Gate deadline 与
    Product Package provenance/expiry 测试中的隐式系统时钟依赖；测试显式注入固定 aware
    datetime，生产过期和人工闸门规则保持不变，跨日期运行不再产生伪失败。
141. **家庭体验不可拆分 AI 发布包（ADR-0135）**：新增
    `FamilyExperienceReleaseBundle`，以稳定摘要同时绑定 Provider/Model、已发布
    Prompt/Schema、Safety/Knowledge、data class、评测 report/decision 与签名人工审批；
    Provider 准入、模型版本、审批指纹、Human Gate 或 DRAFT-only 边界任一不一致均拒绝。
    Bundle 本身不调用模型、不部署、不保存原始签名或家庭数据。
142. **发布包持久化与 Bundle-aware 灰度闸门（ADR-0135）**：新增独立 SQL Store 与
    `0040_ai_experience_bundles` 迁移，按 bundle id 和 candidate/environment 不可变保存
    metadata；新增 `FamilyExperienceDeploymentPort`，在外部调用前校验完整 Bundle、
    Candidate、Decision、模型、report 与审批 control。缺包或任一漂移均 fail-closed，
    幂等重放不会二次调用部署端口。
143. **Bundle-aware HTTP 与四环境同构组合（ADR-0136）**：新增
    `HttpFamilyExperienceDeploymentPort` 和 `FamilyExperienceReleaseRuntime`，完整 Bundle
    随 canary/rollback 请求进入部署平台；development/test/staging/production 使用同一
    identity、`ai.release.deploy` scope、短期 token、Bundle gate、HTTP、receipt 与 telemetry
    链路。测试 payload 明确排除 Prompt 原文、原始签名、token 与家庭标识。
144. **发布包 request-safe SQL Reader**：将部署依赖从可写 Store 收窄为只读 Reader，
    新增 `SessionPerCallFamilyExperienceReleaseBundleReader`；长生命周期 runtime 每次查询
    创建并关闭独立 AsyncSession，测试以提交后的新 session 回读真实 Bundle。
145. **灰度 SLO 与预授权人工回滚（ADR-0137）**：新增 provider-neutral canary
    observation、版本化 SLO、metadata-only SQL assessment ledger 与 HTTP observation
    adapter。未成年人安全违规不等待样本立即 breach；协调器只能读取 verifier 已写入、
    TTL 内有效的真人 ROLLBACK control，缺失/AI/过期/错 scope 均拒绝，重复监督只回滚一次。
146. **四环境 Canary Runtime**：新增 `FamilyExperienceCanaryRuntime` 与 HTTP composition；
    development/test/staging/production 复用相同 observation、版本化 policy、assessment、
    control reader 和 Bundle rollback。四环境均验证未成年人安全即时回滚，跨环境在任何
    observation 网络调用前 fail-closed。
147. **Canary 告警与真人确认（ADR-0138）**：新增 0042 metadata-only alert ledger，
    区分回滚已执行/被阻断；同 assessment 结果不可漂移，OPEN 告警仅真人可确认，同 actor
    重放幂等、换人覆盖拒绝。确认只表示知悉，不创建或延长 ReleaseControl。
148. **Canary 持久化调度与租约（ADR-0139）**：新增 0043 metadata-only job ledger、
    `PENDING/LEASED/COMPLETED/FAILED` 状态机与租约超时接管；claim 提交后才执行网络调用，
    bounded tick 支持样本不足重排期、瞬时错误有限重试和 fail-closed 终态。四环境使用同一
    SQL scheduler 组合根与 session-per-call assessment/alert/control 边界。
149. **多模态受控模型故障切换（ADR-0141）**：将 route 的首选/备用顺序接入家庭体验
    生成链路，仅 timeout/network/5xx 可推进；每个 provider 独立准入、Attempt 分序记录，
    Schema/JSON/Safety/Policy/Credential 错误不切换。备用模型 Draft 可幂等回放，HTTP
    modality 与真实 media input 对齐，媒体上限按实际条目计数。

## 验收证据

- `uv run pytest tests/intelligence/experience tests/intelligence/human_gate tests/intelligence/evaluation -q` → **当前组合命令为历史证据；最新分域证据见下方 evaluation/observability 与 AI 全量命令**
- `uv run pytest tests/intelligence/experience/test_sql_run_ledger.py tests/intelligence/experience/test_async_ledger_bridge.py -q` → **历史证据，未作为本轮最新计数**（SQL 生命周期、进程重启响应重放与 bridge）
- `uv run pytest tests/intelligence/experience/test_outbox_worker.py -q` → **5 passed**（成功、重试、死信、DLQ 故障保留 pending、pull limit）
- `uv run pytest tests/intelligence/agent_runtime -q` → **28 passed**（含 AgentRun/Trace SQL durable store、DurableAgentRuntime 幂等重放/并发重复执行阻断、Durable composition factory、ContextScope 绑定、授权租约、治理 YAML AgentDefinition registry、Gateway 执行适配器、parent_advisor 纵向切片、scope 隔离、失败重放与事实字段拦截）
- `uv run pytest tests/intelligence/safety -q` → **5 passed**（低风险放行、高影响复核、未成年人复核、禁止字段与 DRAFT-only）
- `uv run pytest tests/intelligence/tool_runtime -q` → **12 passed**（pending Named Action、三重授权、TTL/静态白名单、主体 scope、Tool Action durable outbox 与状态闸门）
- `uv run pytest tests/intelligence/agent_runtime/test_authorization_persistence.py -q` → **3 passed**（租约 issue/revoke、scope/TTL/use_case/tool/budget fail-closed 与审计）
- `uv run pytest tests/intelligence/prompt_registry tests/intelligence/schema_registry -q` → **7 passed**（版本不可变、绑定/生效窗口、结构与安全边界）
- `uv run pytest tests/intelligence/model_gateway -q` → **158 passed**（含 durable token usage、显式 rate card 聚合、TokenUsage fail-closed 校验、HTTP credential service、CredentialLease、SecretManager metadata-first adapter、mTLS client injection、revocation-status 查询、请求 deadline 覆盖校验、配置冲突拒绝、adapter 模态能力声明与外呼前撤销检查）
- `uv run pytest tests/intelligence/evaluation -q` → **44 passed**（含 ReleaseDecision durable ledger、ReleaseAdmissionService、ReleaseControlStore、ReleaseCandidateCatalog、ReleaseDeploymentService、HttpDeploymentPort、Operator Identity/Token adapter、request bearer context/HttpRequestOperatorIdentityPort、mTLS 配置冲突拒绝、BenchmarkReport/Slice archive 与授权评测查询）
- `uv run pytest tests/apps/family_api/test_production_release_wiring.py -q` → **4 passed**（显式 identity-derived actor、scope 闸门、环境边界与 HTTP identity/token/deployment 组合路径）
- `uv run pytest tests/apps/family_api/test_family_experience_release_wiring.py -q` → **6 passed**（development/test/staging/production 同一 Bundle-aware HTTP canary 路径、完整 metadata payload、无敏感正文/token、rollback Bundle/target/control 契约）。
- `uv run pytest tests/apps/family_api/test_family_experience_canary_wiring.py -q` → **5 passed**（四环境同一未成年人安全 breach→预授权真人 rollback 路径及跨环境外呼前拒绝）。
- `uv run pytest tests/intelligence/experience/test_canary_scheduler.py tests/apps/family_api/test_family_experience_canary_scheduler_wiring.py -q` → **15 passed**（SQL/内存 lease 抢占与超时接管、有界 tick、重试/重排期/终态和 development/test/staging/production 同构组合）。
- `uv run pytest tests/intelligence/experience/test_multimodal_application.py tests/intelligence/experience/test_multimodal_generation.py tests/intelligence/experience/test_multimodal_routing.py tests/intelligence/experience/test_api_contract.py tests/intelligence/model_gateway/test_routing_and_attempts.py tests/apps/family_api/test_production_experience_wiring.py -q` → **58 passed, 1 warning**（覆盖生产 HTTP fallback、非基础设施错误停机、Attempt sequence、幂等回放与媒体信任边界）。
- `uv run pytest tests/apps/family_api/test_production_telemetry_retention_wiring.py -q` → **2 passed**（独立 SQL transaction、TTL deletion/audit receipt 与环境/批次边界）
- `uv run pytest tests/intelligence/observability tests/intelligence/model_gateway/test_telemetry_integration.py -q` → **16 passed**（scope 脱敏、allowlist、operation 幂等、Gateway 成功/策略失败 span、SDK exporter 与组合 sink、TTL retention/deletion）
- `uv run pytest tests/intelligence/experience/test_notification_retention.py tests/apps/family_api/test_production_achievement_notification_retention_wiring.py tests/apps/family_api/test_production_experience_outbox_wiring.py -q` → **15 passed**（通知投影 TTL 有界删除、metadata-only audit receipt、生产单事务组合根、schedule tick、retry/DLQ alert seam 与告警故障不回滚）
- `uv run pytest tests/intelligence -q` → **754 passed, 1 skipped, 1 warning**（本轮从工作区重跑；含受控多模型 failover、备用 Draft 回放与媒体信任边界。）
- `uv run pytest tests/intelligence/experience -q` → **319 passed, 1 warning**；覆盖反馈上下文、Registry/SQL 绑定、发布包、灰度调度和受控多模型切换。
- `uv run pytest tests/apps/family_api -q` → **187 passed, 2 skipped, 1 failed**；失败仍是既有 unset `AIFAMILY_ENV` 默认 development 的安全 acceptance（ENV-01）；生产 HTTP fallback 与测试环境真实 media reference 路径均通过。
- `uv run pytest tests/intelligence/experience/test_operations_query.py tests/apps/family_api/test_experience_operations_query_api.py tests/intelligence/experience/test_operations_audit_persistence.py tests/intelligence/evaluation/test_request_operator_identity.py -q` → **27 passed**（HMAC cursor 状态绑定/过期、operator allow/deny/identity-error metadata-only audit、审计故障 fail-closed、SQL sink 回读/过滤/时区与边界、迁移链与 revision 长度、per-access transaction commit、HTTP bearer 401/分页/summary、HTTP identity 生产组合根、last_error 脱敏、composition hook 互斥、持久化 sink 与 FastAPI 依赖深拷贝回归、request identity metadata parsing、签名校验、挂载与 503 fail-closed）。
- `uv run pytest tests/intelligence/context_engine -q` → **27 passed, 1 skipped**（SQL durable broker 跨 session 回读、scope/consent/TTL 隔离、主体删除、重复写入幂等与 `SqlContextBrokerFactory` 组合工厂）。
- `uv run pytest tests/apps/family_api/test_production_engagement_wiring.py tests/intelligence/experience/test_engagement_persistence.py tests/intelligence/experience/test_engagement.py -q` → **14 passed**（生产 Engagement 组合根、SQL Event Reader、授权复核与事件范围边界）。
- `uv run pytest tests/apps/family_api/test_trusted_experience_scope.py -q` → **5 passed**（认证 principal、trusted tenant/family binding、ConsentGate 与 Engagement scope 适配）。
- `uv run pytest tests/intelligence/experience/test_engagement_api.py -q` → **3 passed**（HTTP fail-closed、服务端事件读取、DRAFT/provenance 响应与客户端 scope/provider 字段拒绝）。
- `uv run pytest tests/intelligence/experience -q`（含反馈偏好上下文）→ **261 passed, 1 warning**；覆盖内存/SQL scope 聚合、删除隔离、幂等反馈与服务端 Prompt 绑定。
- `uv run pytest tests/intelligence/experience/test_contract_binding.py -q` → **3 passed**；覆盖已发布 Prompt/Schema 成对解析、客户端 schema 漂移和 use-case 缺失拒绝。
- `uv run pytest tests/intelligence/experience/test_multimodal_eval.py -q` → **10 passed**；覆盖 feedback context 的 shape/上限校验与同一 gold set 的策略对照评测。
- `uv run pytest tests/intelligence/experience/test_standard_contracts.py -q` → **1 passed**；验证家庭体验用例、Agent 与 Prompt/Schema ref 的唯一映射。
- `uv run pytest tests/apps/family_api/test_engagement_router_mount.py -q` → **2 passed**（family_api OpenAPI 挂载与生产未配置 runtime 的 503 边界）。
- `uv run pytest tests/apps/family_api/test_engagement_router_mount.py tests/intelligence/experience/test_synthetic_engagement_runtime.py -q` → **5 passed**（dev/test synthetic Engagement parity、认证家庭绑定、完整 DRAFT 响应和生产环境拒绝）。
- `uv run pytest tests/apps/family_api/test_sqlalchemy_consent_snapshot_resolver.py -q` → **3 passed**（SQL consent grant、主体读取、年龄/版本摘要和空授权边界）。
- `uv run pytest tests/apps/family_api/test_sqlalchemy_bearer_principal_resolver.py tests/platform/identity/test_trusted_context.py -q` → **18 passed**（bearer 摘要绑定、跨家庭/会话 fail-closed、SQL trusted scope factory 与完整 identity→consent 组合）。
- `uv run pytest tests/apps/family_api/test_production_engagement_wiring.py -q` → **3 passed**（生产组合根与 HTTP request-auth wiring 的缺失 token 403 边界）。
- `uv run pytest tests/platform/identity/test_session_port.py -q` → **4 passed**（identity session 签发、轮换、撤销、过期响应与 mTLS/credential fail-closed）。
- `uv run pytest tests/apps/family_api/test_production_experience_wiring.py tests/intelligence/experience/test_multimodal_routing.py -q` → **14 passed**（生产路由目录/Gateway adapter、模型版本与模态能力一致性闸门）。
- `uv run pytest tests/apps/family_api/test_production_experience_wiring.py tests/apps/family_api/test_experience_router_mount.py -q` → **15 passed**（多模态 SQL request-auth wiring、create_app hook 互斥与缺失 token 401 边界）。
- `uv run pytest tests/intelligence/memory/test_sql_store.py -q` → **3 passed**（跨会话读取、跨租户隔离、幂等写入、级联删除证明与过期清理）。
- `uv run pytest tests/intelligence/growth_graph/test_store.py -q` → **3 passed**（只读作用域查询、投影幂等、过期隐藏、主体级删除 proof）。
- `uv run pytest tests/intelligence/growth_graph -q` → **5 passed**（Experience Outbox worker 投影、重放幂等与 malformed envelope DLQ）。
- `uv run pytest tests/intelligence/intervention -q` → **11 passed**（primary contradiction、DRAFT-only 干预候选、Blueprint PUBLISHED 匹配与 Human Gate 标记）。
- `uv run pytest tests/intelligence/intervention -q` → **13 passed**（含 Blueprint → Tool Action Outbox pending Named Action bridge）。
- `uv run pytest tests/intelligence/tool_runtime/test_accepted_dispatch.py -q` → **3 passed**（注册 handler、scope/receipt 校验与 request_id 幂等重放）。
- `uv run pytest tests/architecture/test_ai_technical_architecture.py tests/architecture/test_principal_integration_architecture.py tests/architecture/test_docs_truth_boundary.py tests/architecture/test_no_direct_provider_calls.py tests/architecture/test_environment_parity.py -q` → **24 passed**
- `uv run pytest tests/architecture -q` → **109 passed, 1 skipped, 1 failed**；唯一失败仍为全仓 Ruff lint-debt ratchet 的并发 WIP `backend/domains/family/domain/entities.py:331` E501，AI 相关架构断言均通过。
- `pnpm vitest run tests/multimodal-draft-api.test.ts tests/ui03-ui05-ui09-vertical-slice.test.ts tests/achievement-contracts.test.ts tests/achievement-view-model.test.ts tests/achievement-telemetry.test.ts` → **20 passed**；`pnpm tsc --noEmit` 通过
- `pnpm vitest run`（移动端全量）→ **262 passed, 1 skipped**；57 个测试文件通过，UI-02、multimodal draft、成就契约、SERVICE canonical ID 与 34 屏 UI 契约均已通过；`pnpm tsc --noEmit` 与 `pnpm build` 通过。
- `pnpm vitest run`（移动端全量，含 UI-05 反馈闭环）→ **263 passed, 1 skipped**；57 个测试文件通过；`pnpm tsc --noEmit` 与 `pnpm build` 通过。
- `uv run alembic heads` → `0043_ai_canary_jobs (head)`；AI runtime 链路新增
  `0024` accepted-action delivery、`0025` service blueprint proposal、`0026` Experience
  Outbox attempt/status ledger、`0027` metadata-only dead-letter index、`0028` achievement
  occurrence identity、`0029` notification/analytics projections、`0030` prompt/schema registry、
  `0031` release controls、`0032` release candidates、`0033` deployment receipts、
  `0037` operations access audit、`0040` family-experience immutable release bundle、`0041`
  canary assessment ledger、`0042` canary alert/ack ledger、`0043` durable canary job/lease；`0038` product definition 与
  `0039` competitor evidence 位于同一线性链。
- migration 回归当前为 **14 passed, 1 failed, 9 skipped**（未配置 PostgreSQL 的测试
  均按门控跳过）；唯一失败是 `test_all_alembic_revisions_form_one_complete_chain_including_0016`
  的旧 allow-list 尚未纳入 `0024..0043`，不是
  SQL DDL 执行错误。完整 Alembic chain 仍保持 WIP，待 revision/Manifest/ADR 集成后
  重跑 fresh PostgreSQL upgrade→downgrade→upgrade 门禁。
- `uv run alembic upgrade head --sql` 受既有 `0001_legacy_schema_baseline` 直接访问
  asyncpg driver connection 的实现限制而失败，离线 `MockConnection` 无该属性；未执行到
  `0040`。本轮以单 head、ORM 建表/约束、SQLite 跨 session 和迁移清单校验作为本地证据，
  真实 PostgreSQL round-trip 仍待 `AIFAMILY_TEST_DATABASE_URL`。
- 本轮新增/修改文件通过针对性 Ruff 检查。
- `uv run ruff check backend/intelligence/experience` → 通过；全仓 Ruff 当前仅剩并发 WIP 的 `backend/domains/family/domain/entities.py:331` E501。

## 下一冲刺入口

### P0：UI-03 → UI-05 → UI-09 多模态 Draft API 联调（已完成）

Family API 已由 `main.py` 挂载 experience router；dev/test 由 `dev_wiring.py` 按认证家庭路径注入 `SyntheticRuntimeResolver`，生产保持无 resolver 时的 503 fail-closed。移动端 API client 与 UI-05 已接入冻结的 `POST /families/{family_id}/experience/multimodal/drafts` 契约，并显式呈现 loading、DRAFT、人工确认与错误状态。

### P1：人工闸门后的 Named Action（inbox seam 已完成）

ExperienceRun→Human Gate 的 scope/correlation/run_ref seam、SQL Human Gate 事务适配、Tool Action inbox consumer 与 provider-neutral relay seam 已完成；Experience Outbox Worker、Achievement consumer 和 durable Achievement projection 已把事件投递、重试、死信和证据投影闭环。下一步仍需接入业务域审计投影与二次授权执行。

### P2：Agent Runtime 的可重启与可审计执行（核心 seam 已完成）

当前 Agent Runtime 与 Tool Runtime 已具备授权租约、Prompt/Schema 治理、DRAFT-only 执行、AgentRun/Trace durable store、ModelGatewayExecutionPort、pending Named Action、ToolCall outbox 和 Human Gate inbox seam；AiReleaseGate 已提供评测/供应商准入门，parent_advisor 已完成合成数据纵向切片。Token usage、显式 rate card 成本聚合、统一 AI telemetry span、OpenTelemetry exporter 与 metadata-only retention/deletion 已落地；下一步进入真实身份/同意、生产 scheduler/collector/告警和 durable deletion proof。

## 当前明确缺口

- 尚无获准生产多模态供应商和真实密钥调用；当前路由候选仅完成内部 livecheck/离线评测。
- ExperienceRun 目前是可替换 SQLAlchemy seam，尚未由 worker 在真实部署中消费。
- SQL ledger 已通过 async 组合根 bridge 接入 API 的 awaitable dispatch；真实部署仍需在
  目标 composition root 注入 AsyncSession/UnitOfWork，并把 outbox/audit 纳入同一事务。
- 迁移 0010/0012/0013 已有对应 ADR 与 migration manifest；0012/0013 依赖并发 WIP 的
  0011 human-task claim lease。本地 PostgreSQL DDL 已验证的旧链路，完整 round-trip 门禁仍受
  “migration 必须 tracked”治理条件阻塞，生产部署仍需在目标环境执行同一套 migration
  与并发压测。
- Agent Runtime 已接入治理 YAML AgentDefinition registry、Prompt/Schema Registry、AgentRun/Trace durable store 与授权租约；仍需完成受控 registry 发布/签名、真实身份/同意和生产组合根 wiring。
- 多模态与 Agent 生产组合根已将 Attempt、SafetyDecision、Telemetry span、AgentRun/Trace 绑定到请求级 UnitOfWork；OpenTelemetry SDK adapter 与 metadata-only retention/deletion worker 已接入，生产 scheduler、collector、durable deletion proof/audit 与告警仍待完成。
- Tool Runtime 的 ToolCall outbox 与 Human Gate inbox consumer seam 已完成；post-gate durable attempt/DLQ worker 与 bounded queue poll 已落地，仍需接入工具目录持久化、持续调度、lease takeover 压测与更多业务域二次授权 consumer。
- Synthetic Runtime 已接入 `dev_wiring.py` 的请求级身份解析，仅允许 dev/test；生产 Engagement 与 Multimodal Draft 均已具备 SQL identity/consent composition、`Authenticated*ScopeResolver` 适配和 HTTP request-auth wiring，仍需真实 auth_identity endpoint、数据库权限、ContextBroker 数据权限与部署平台 context wiring。
- Human Gate bridge 已接入 durable SQL Human Gate 的显式事务 seam；Tool Action consumer 已能在同一 AsyncSession 中原子写入 HumanTask+Audit 并确认 outbox；FGCN 已有首个 accepted-action adapter，post-gate durable dispatcher worker 已完成，生产 outbox relay 与队列调度仍待接入。
- AiReleaseGate 已完成离线评测与供应商准入门禁，0020 决策账本、0031 人审批准/回滚控制与 `ProductionReleaseRuntime` 组合根已建立；真实 operator key service 的 mTLS/轮换/撤销、部署平台权限、灰度部署演练与报告归档仍待接入。
- dev/test 的内部 Experience 运维与 Evaluation 查询已通过 `DevOperatorIdentityPort` 和 synthetic metadata runtime 走通完整 API 契约；生产仍需真实 auth_identity/session-factory 主入口接线。未设置 `AIFAMILY_ENV` 时默认 development 的既有安全门禁仍未收口，相关 acceptance 测试保持失败。
- Safety Runtime 已接入 Model Gateway 请求前/输出后边界，合成运行时复用同一策略；生产 composition root 已强制工厂化接线与持久化安全决策，供应商 moderation、人工复核反馈、scheduler/告警与 durable deletion proof 仍待完成。
- Outbox Worker 与 Achievement consumer 已完成 provider-neutral 投递、重试、DLQ 与证据绑定投影；
  `ProductionExperienceOutboxRuntime` 已接入 durable attempt/status ledger 与 worker lease/takeover，
  生产仍需 scheduler、DLQ alerting/retention、operations audit sink 的主入口 identity/session-factory 接线，以及 PostgreSQL 多 worker 并发抢占验证。

这些缺口保持显式记录，不将“代码已迁入”描述为“生产能力已具备”。
