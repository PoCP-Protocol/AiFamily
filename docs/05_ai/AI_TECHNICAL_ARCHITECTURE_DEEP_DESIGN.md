---
id: AI-TECH-ARCH-002
title: Family AI 深度技术架构与落地设计
type: specification
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: docs/05_ai/AI_TECHNICAL_ARCHITECTURE.md
superseded_by: null
---

# Family AI 深度技术架构与落地设计

> 本文件把“接入模型、做几个 Agent”提升为一套可运行的平台架构。它描述目标形状、
> 接口和实施证据，不把目标态冒充当前能力。当前成熟度仍以
> `docs/00_system/CURRENT_AI_MAP.md` 为准；业务事实边界遵守
> `governance/REPOSITORY_CONSTITUTION.md` R6/R7/R8/R9/R10/R14。

## 1. 架构目标：把 AI 建成一个可控的生产系统

大型家庭成长平台的 AI 技术架构至少要同时回答 12 个问题：

1. AI 为哪些业务能力创造价值，而不是为了什么模型而存在？
2. 谁可以在什么租户、家庭、主体和目的下调用什么能力？
3. 输入上下文从哪里来、是否经过同意、能否重放和删除？
4. 法咪莉校长的灵魂、方法、知识和模型如何解耦并版本化？
5. 一个请求怎样路由到 Agent、Skill、Tool、知识和模型？
6. 如何保证 AI 只产生草案，不绕过业务域写入事实？
7. 如何处理儿童安全、隐私、幻觉、越权、提示注入和身份冒充？
8. 如何在模型变更前后证明质量没有退化？
9. 如何记录每一次调用的来源、成本、延迟、人工决定和结果？
10. 如何让 dev/test/prod 功能完全一致，只替换数据和适配器？
11. 如何部署、扩缩容、限流、降级、重放、灾备和数据删除？
12. 如何把运营、教研、专家和工程师纳入同一条发布与责任链？

因此，AI 平台不是一个模块，而是五个相互配合的系统：

```text
                         ┌──────────────────────────────┐
                         │  AI Governance & Product Plane │
                         │  use case / owner / policy    │
                         └──────────────┬───────────────┘
                                        │ release gates
┌──────────────────────┐       ┌───────▼────────┐       ┌─────────────────────┐
│  AI Experience Plane │──────▶│ Principal       │◀──────│ Human Operations    │
│ mobile/ops/partner   │       │ Control Plane   │       │ review/queue/escalate│
└──────────────────────┘       └───────┬────────┘       └─────────────────────┘
                                        │ governed execution
                         ┌──────────────▼───────────────┐
                         │       AI Runtime Data Plane    │
                         │ context / knowledge / agent /  │
                         │ tool / gateway / safety / eval │
                         └──────────────┬───────────────┘
                                        │ read projections / named actions
                         ┌──────────────▼───────────────┐
                         │       Domain Truth Plane       │
                         │ family/journey/service/commerce│
                         └────────────────────────────────┘
```

法咪莉校长位于控制面，不是模型，也不是业务数据库。它负责统一人格、目的解释、能力
路由、结果编排和用户体验；运行时数据面负责可执行的安全、检索、模型和评估；领域真相
面负责唯一的业务事实写入。

## 2. 十九个架构维度

### D01 战略与价值维度

AI 用例先挂到 `VS-01..VS-05`、`S01..S24` 或 `O01..O14`，再进入技术设计。
三区方法论决定深度：

| 区域 | 技术投入 | 质量证明 |
|---|---|---|
| 同质区 | 统一问答、内容解释、提醒、基础推荐 | 成本、延迟、安全、可用性 |
| 优势区 | 21/90 天计划、真人协作、服务匹配、复盘 | 采纳率、改写率、人工质量、流程完成 |
| 独占区 | Context、Growth Graph、Intervention、Blueprint、Principal Soul | 证据可追溯、跨阶段连续性、长期反馈和版本复利 |

技术架构不得以“模型参数量”“模型排行榜”作为价值指标；指标必须能回到家庭行动、
服务质量、风险控制或平台学习证据。

### D02 业务能力与用例维度

每个 AI 用例登记以下完整契约：

```text
use_case_id
→ business_process_id / node_id
→ actor / audience / purpose / consent
→ input evidence / context policy
→ capability / agent / skill / tools
→ output type / schema / risk / human gate
→ domain named action (if any)
→ owner / SLA / budget / retention
→ eval set / release gate / status
```

`AI_USE_CASE_REGISTRY.yaml` 是机器可读入口；登记为 `PLANNED` 不等于实现完成。

### D03 Principal Soul 与人格维度

校长灵魂拆成六个可独立评审的版本包：

1. `persona_dna`：知性、温暖、有判断、不说教、有边界、能落地。
2. `values`：孩子尊严、父母尊严、关系优先、小行动、证据谦逊，以及
   **“We are 伐木累！We are family！”** 的归属与共同成长精神。
3. `thinking_policy`：场景优先、假设非事实、行为不贴标签、先安全后建议。
4. `language_style`：短句、先共情后判断、给可复述话术、避免诊断和绝对保证。
5. `action_policy`：一次一个小行动、观察后再判断、复盘、不得直接改事实。
6. `safety_policy`：NORMAL/REVIEW/HIGH_RISK，明确拒答、转人工和升级规则。

“family”表达的是接纳、互助和共同成长：面对父母和孩子的无奈与疲惫，先理解处境，
再用一个小行动和合适的资源陪伴推进，不表示 AI 是家庭成员，也不允许以家人身份施加
压力、制造依赖或推动交易。每次响应都必须记录 `soul_id`、`soul_version`、六个子策略版本
和评审人。校长可以
继承方法论和审定知识，不复制真实教师的身份、声音、外貌或私人记忆。

### D04 Context 与记忆维度

Context 不是把全库内容塞入 Prompt，而是一个带目的和时效的可审计快照：

```text
Domain Events
   → Event Normalizer
   → StateObservation / EvidenceReference
   → Context Policy Filter
   → ContextSnapshot (purpose + consent + time window + redaction)
   → Principal / Agent
```

记忆分四级：

| 级别 | 内容 | 默认保留 | 访问条件 |
|---|---|---:|---|
| M0 | 当前会话消息和临时输入 | 会话期/短 TTL | 当前请求 |
| M1 | 用户主动确认的偏好和沟通习惯 | 可撤回、有 TTL | 同一家庭/目的 |
| M2 | Family Context 只读投影、成长过程观察 | 按主体/目的保留 | 明确同意 + 最小必要 |
| M3 | 跨阶段 Outcome 学习特征 | 成熟度门槛后启用 | 脱敏、人工抽检、可删除 |

向量、缓存、摘要、评估样本都必须带主体、目的和删除引用；删除原始数据时级联删除
派生数据，不允许“只删正文、不删向量”。

记忆体还必须按关系对象分为三类：`ChildMemory`（孩子的兴趣、节奏和已确认观察）、
`GuardianMemory`（家长主动确认的目标、沟通和服务偏好）以及
`RelationshipMemory`（家庭共同经历、约定、修复和支持方式）。AI 只能生成
`MemoryCandidate`，家庭或授权工作人员确认后才能形成可检索记忆；不能把诊断标签、
情绪脆弱性或商业标签写入任何一类记忆。详细对象、删除证明和多模态记忆见
`docs/07_data/FAMILY_MEMORY_ARCHITECTURE.md`。

### D05 知识工程维度

知识库是内容工程和运行时基础设施的结合，不是一个文件夹：

```text
Source → Ingest → Parse → Chunk → Claim → Review → Publish
                                      ↓
                              Index / Embedding
                                      ↓
                      Retrieve → Rerank → Citation → Expire/Delete
```

每个 `KnowledgeClaim` 至少包含：`claim_id`、source_ref、license、evidence_grade、
applicable_age、applicable_context、contraindications、safety_notes、owner、
review_status、version、expires_at。

知识分为：

- 方法卡：可执行的方法、步骤、适用和禁忌；
- 理论卡：专业理论和证据等级；
- 话术卡：经审核的表达示例，不是事实模板；
- 服务组件卡：服务步骤、资源、验收标准、SLA；
- 安全卡：风险信号、升级条件、不可输出内容；
- 运营卡：指标口径、异常解释和发布规则。

公共知识与家庭私有上下文物理隔离；家庭数据只能在授权请求中以临时引用参与推理，
不得反向写入公共知识、组件或训练集。

### D06 Agent、Skill、Tool 与工作流维度

采用四层抽象，避免 Agent 变成一堆 Prompt：

```text
Principal Profile
  → Agent Definition
    → Skill（可组合的认知能力）
      → Tool（具名、版本化、权限化的操作）
        → Domain Port / Read Projection / Named Action Request
```

现有五个业务 Agent 作为执行角色保留：`parent_advisor`、`child_coach`、
`teaching_assistant`、`growth_planner`、`operations_assistant`。校长通过 profile
选择其中一个主 Agent；服务产品设计和知识治理使用内部 profile，不创建第二套模型。

Tool 必须声明：输入/输出 schema、read/write 类型、授权范围、预算、幂等、可逆/补偿动作、
人工闸门、审计事件和超时。任何 Tool 都不能直接 import 业务域 ORM。

### D07 模型能力与供应链维度

模型按能力路由，不按业务代码绑定供应商：

| 能力标签 | 例子 | 约束 |
|---|---|---|
| structured_reasoning | 解释、假设排序、计划草案 | 必须 schema + evidence |
| grounded_generation | 知识问答、方法说明 | 只能使用已发布 Claim |
| safe_rewrite | 沟通改写、微课文案 | 禁止诊断、保证、羞辱 |
| classification | 风险、意图、路由 | 阈值需校准，不能自动做高影响决定 |
| embedding | 检索索引 | 可寻址、可删除、不可反推身份 |
| deterministic | 测试、回归、降级 | 明确标注 SYNTHETIC，不冒充生产 AI |

`Model Gateway 是唯一模型供应商边界`；供应商准入由 `model_gateway/provider_registry` 统一完成，包含环境、数据类、转委托、
安全评估、处理协议、删除承诺和区域。未准入供应商不能因“开发方便”被绕过。
生产凭据通过 `ProviderCredentialPort`/`HttpProviderCredentialPort`/`SecretManagerCredentialPort` 解析为带过期时间的
`CredentialLease`（ADR-0100）；Secret Manager seam 先解析非敏感 metadata，再读取
provider-scoped secret reference；生产组合根使用
`build_secret_manager_openai_compatible_gateway_from_registry` 注入部署回调；secret 不进入 provenance、attempt、telemetry 或领域层；
显式 mTLS transport、配置冲突拒绝与外呼前动态撤销检查已提供（ADR-0107）：HTTP 组合工厂仅在
`check_credential_revocation=True` 时查询 metadata-only
`/v1/provider-credentials/leases/revocation-status`，状态服务异常或非法响应
fail-closed。身份会话由 `IdentitySessionPort`/`HttpIdentitySessionPort`（ADR-0117）
提供签发、轮换、撤销的 provider-neutral seam；真实 mTLS/KMS/轮换/撤销 endpoint
与端到端部署验收仍由外部身份/密钥服务负责。

### D08 AI Gateway 与执行协议维度

Model Gateway 的最小执行协议为：

```text
Safety.input → Admission → Attempt.begin → Provider Call → JSON Decode
  → Schema Validate → Safety.output → Provenance Build → Attempt.finish
  → ModelDraft(DRAFT)
```

`StructuredRequest` 必须有：`request_id`、`session_id`、`use_case`、`data_class`、
`purpose`、`prompt_version`、`schema_version`、`context_snapshot_ref`、`output_schema`。

Gateway 只返回 `ModelDraft`，且 `may_mutate_business_state` 恒为 `false`；Attempt 可由
`SqlAlchemyAttemptSink` 在异步组合根中持久化；任何重试只允许
基础设施失败，不能因为内容不合格而换供应商“采样到满意答案”。
SafetyDecision 同样只记录策略元数据，并与 Attempt、AgentRun/Trace 共享请求事务；
持久化失败直接阻断本次模型执行。

### D09 编排与状态机维度

同步请求和异步工作流必须使用相同的状态机：

```text
RECEIVED → CONSENTED → CONTEXT_READY → ROUTED → GENERATED
    → VALIDATED → SAFETY_REVIEW → DRAFT_READY
    → HUMAN_REVIEW / USER_CONFIRMATION
    → NAMED_ACTION_REQUESTED → DOMAIN_COMMITTED
    → OUTCOME_CAPTURED → EVALUATED
```

任何节点可进入：`REJECTED`、`ESCALATED`、`EXPIRED`、`CANCELLED`、`DEAD_LETTER`。
异步工作流必须保存 `correlation_id`、`causation_id`、幂等键、重试次数、补偿命令和死信原因。

### D10 安全、策略与内容护栏维度

安全不是一个输出过滤器，而是四层策略：

1. **输入层**：提示注入、越权上下文、敏感主题、身份冒充、恶意文件。
2. **上下文层**：主体年龄、同意、目的、跨家庭隔离、数据最小化。
3. **生成层**：结构化 schema、来源引用、禁止字段、边界标签。
4. **输出层**：诊断/疗效/排名/商业画像/虚构事实/危险建议扫描，风险升级。

风险路由：

| 风险 | AI 能做 | 必须做 |
|---|---|---|
| LOW | 解释、低风险小行动草案 | 引用、限制和可撤回 |
| MEDIUM | 计划/服务/沟通候选 | 用户或工作人员确认 |
| HIGH | 提醒、风险摘要、人工待办 | Human Gate、双人或升级 |
| PROHIBITED | 不生成、不展示 | 拒绝、审计、必要时安全响应 |

硬禁止：家庭总分/排名、对未成年人商业画像、自动诊断、自动教师分派、自动验收、
自动退款/升级、校长身份克隆、未经确认的业务事实写入。

### D11 人机协同与运营工作台维度

Human Gate 不只是一个按钮，必须有责任、队列和健康指标：

```text
Draft → Risk Classifier → HumanTask
      → reviewer identity/permission
      → APPROVE / EDIT / REJECT / ESCALATE
      → Named Action or Close
```

工作台要支持：按风险/SLA/租户/技能分队列、锁定防并发、批量操作限制、证据展开、前后
版本对比、驳回原因、升级、超时、代理人和审计。监控指标包括审阅耗时、驳回率、改写率、
批量确认比例、超时率、同一审阅人的异常速率；“驳回率为零”应触发闸门健康告警。

### D12 评估与质量工程维度

评估分六层，且要和发布门联动：

| 层 | 证明什么 | 典型门槛 |
|---|---|---|
| Contract | schema、枚举、provenance、draft-only | 100% |
| Safety | 禁止内容、风险升级、主体隔离 | 关键项 100% 拦截 |
| Grounding | 引用真实、适用、未过期 | 无虚构引用 |
| IP Consistency | 校长人格和语言稳定 | 版本回归不退化 |
| Usefulness | 采纳、改写、驳回、完成 | 按用例设阈值，不做家庭排名 |
| Workflow | 人工闸门、Named Action、审计、补偿 | 关键链路无旁路 |

评估集来源于 golden cases、人工改写、驳回、暂停、投诉和真实结果的脱敏样本；评估样本
继承主体、目的、留存和删除属性。任何 Prompt、Soul、Schema、Knowledge 或 Model 版本
变更都必须跑回归集。

### D13 Prompt/Schema/Soul/Knowledge 资产生命周期维度

四类资产统一生命周期：

```text
DRAFT → REVIEW → CANDIDATE → EVALUATED → APPROVED → PUBLISHED → RETIRED
```

发布包必须冻结：`use_case`、Soul、Prompt、Schema、Knowledge、Safety、Model capability
要求、评估结果、审批人、生效时间、回滚版本。禁止原地修改已发布版本。

家庭多模态体验通过 `FamilyExperienceReleaseBundle` 首先落地该规则：它用内容摘要绑定
Provider/Model、已发布 Prompt/Schema、Safety、Knowledge、data class、evaluation report、
ReleaseDecision 与签名 ReleaseControl approval，并固定 `draft_only=true`、
`may_mutate_business_state=false`、`human_gate_rule=REVIEW_REQUIRED`。Bundle 只是不变的
部署清单，由独立 SQL Store 不可变保存；`FamilyExperienceReleaseDeploymentService` 在
外部调用前核对 Bundle/Candidate/Decision/Control，并通过专用 provider-neutral 端口把
完整 Bundle 交给灰度平台。它不替代 Candidate Catalog 或 Release Control，也不在 AI
Runtime 内执行供应商部署。`HttpFamilyExperienceDeploymentPort` 与显式 composition root
使 development/test/staging/production 复用相同 identity、scope、Bundle gate、HTTP、
receipt 和 telemetry 路径，环境仅替换基础设施与数据；长生命周期 runtime 通过
session-per-call Reader 获取 Bundle，不持有启动期 AsyncSession（ADR-0135、ADR-0136）。

在线多模态路由会把确定性的首选/备用顺序交给 `RoutingModelGateway` 执行。只有 timeout、
network error、provider 5xx 可切换，Schema/JSON/Safety/Policy/Credential 错误立即停止；
每个 provider 独立准入并产生独立 Attempt。route metadata 保留计划首选，Draft provenance
记录实际生成模型，备用模型结果仍遵守 DRAFT-only 与幂等回放边界（ADR-0141）。

灰度后由 `FamilyExperienceCanarySupervisor` 读取 provider-neutral 聚合观测，按版本化
SLO 生成内容寻址的 SQL assessment。安全/未成年人安全违规立即 breach；性能指标仅在
达到最小样本后判定。breach 只能执行从已验证控制账本读取、TTL 内有效的真人签名
`ROLLBACK` control，AI/监控不得创建授权；重复监督由 deployment receipt 幂等收敛
。`FamilyExperienceCanaryRuntime` 在四环境使用同一 observation→assessment→control
reader→Bundle rollback 路径，跨环境输入在观测外呼前拒绝（ADR-0137）。

Canary breach 后以 SQL `CanaryAlert` 区分回滚已执行和回滚被阻断；OPEN 告警只能由
真人确认，同一 assessment 不得改写结果。告警确认仅表示知悉，不创建或延长回滚授权，
从而保持 SLO 判定、ReleaseControl、回滚执行和运营确认四层分离（ADR-0138）。

持续监督由 SQL `CanaryJob` 保存 metadata-only 状态，worker 以短事务领取有界批次并提交
lease 后才调用网络端口；进程故障后可由租约超时接管。健康结果完成、样本不足重排期、
瞬时错误有限重试、授权或 scope 错误 fail-closed 进入终态。四环境复用同一状态机和
session-per-call 组合根，部署层只负责周期性触发 bounded tick（ADR-0139）。

### D14 数据治理、隐私与删除维度

每个请求和派生对象强制带：`global_id`、`tenant_id`、`region_id`、家庭/主体范围、
`purpose`、`consent_version`、`data_class`、`locale`/`content_locale`/`model_locale`/
`policy_locale`、`tenant_policy_version`、`retention_policy`、`deletion_ref`、
`correlation_id` 和 `causation_id`。缺任一边界字段时，请求必须在模型调用前拒绝，
不能靠默认租户、默认语言或跨区域回退继续执行。

权利链路为：

```text
RightsRequest → ScopeAssessment → Fact/Projection/Context/Vector/Cache/Trace
              → DeletionJob → DeletionProof → Audit
```

删除证明必须说明已处理原始事实、快照、记忆、embedding、缓存、评估副本和供应商侧
删除承诺；法律保全或安全事件例外必须由人工批准并有到期时间。

### D15 可观测性、审计与 Provenance 图维度

一次 AI 运行形成可关联的 span 图：

```text
request → consent → context → safety.pre → prompt → route → retrieval
        → tool → attempt → schema → safety.post → human_gate
        → named_action → outcome → evaluation
```

所有节点记录 `trace_id`、`request_id`、`correlation_id`、`causation_id`、版本、输入引用、
数据类、延迟、token、成本、错误和删除标记。Provenance 不只是模型字段，而是能回答
“这条建议为什么出现、谁改过、是否被采纳、后来发生了什么”的来源图。

### D16 可靠性、容量与成本维度

目标运行时必须有：租户/家庭/Agent 级限流、并发槽位、预算、超时、熔断、背压、缓存、
异步队列、死信和确定性降级。成本按 `use_case/tenant/profile/model_version` 聚合，不能
用家庭消费或完成率做排名。

当前实现由 Model Attempt 保存 provider 报告的 token usage，`model_gateway.usage`
按部署注入的 rate card 聚合微 USD；无价卡时只报告未定价数量，不推断成本。

降级顺序固定为：

```text
approved model → approved alternate → deterministic template → human task → explicit unavailable
```

不允许用未准入模型、旧版本知识或跨家庭缓存“凑出一个答案”。

### D17 部署、基础设施与灾备维度

目标进程边界：

```text
family_api      # 身份、授权、同意、业务命令、Principal API
ai_runtime      # Context、Knowledge、Router、Agent、Safety、Gateway、Eval
workflow_worker # 异步编排、HumanTask、重试、补偿、投影、删除作业
operations_ui   # 运营、教研、知识、评估、发布、审计
```

基础设施需要：PostgreSQL（事实/AI 技术对象）、对象存储（原始来源/评估资产）、消息/Outbox、
检索索引、密钥管理、监控、审计归档和备份。灾备至少定义 RPO/RTO、重放顺序、幂等策略、
密钥轮换、供应商不可用和删除作业中断恢复。

### D18 开发、测试、生产与组织治理维度

三环境必须使用同一 API、路由、状态机、schema、policy、错误码、审计和人工闸门。只允许替换：

| 项目 | 开发/测试 | 生产 |
|---|---|---|
| 数据 | 合成/脱敏、明确 `SYNTHETIC` | 授权真实数据 |
| 模型 | deterministic/Fake adapter | 通过合规准入的 provider |
| 外部服务 | sandbox/noop adapter | 真实适配器 |
| 评估 | 完整回归集 | 发布门 + 影子评估 |
| 权限 | 测试身份但同一角色矩阵 | 真实身份与审批 |

组织上建立四类 owner：业务用例 owner、Soul/知识 owner、平台运行 owner、合规/安全 owner；
每次发布必须有责任人、评估证据、回滚版本和事故联系人。

### D19 体验编排、推荐与游戏化安全维度

对标抖音的只能是可观察的体验机制：内容发现、短反馈、连续体验、传播和推荐解释；
不能复制无限下滑、沉迷刺激或以停留时长为唯一目标。Family 的体验顺序固定为：

```text
被看见/被理解 → 一个小胜利 → 连续成长 → 主动服务需要 → 经济选择
```

体验编排由受治理的 `experience_curator` profile 承担，必须同时接入授权上下文、
语言/区域策略、知识引用、频控、暂停、退出、人工闸门和 Provenance。游戏化只允许章节、
任务、选择、可选徽章、家庭故事和非比较性奖励；禁止家庭总分、家庭排名、孩子比较、
随机奖赏、倒计时惩罚和未成年人消费激励。情绪和成长信号可以改善内容体验，但不能直接
驱动商业营销或跨目的训练。

## 3. 法咪莉校长在深度架构中的位置

### 3.1 校长控制面

```text
PrincipalApplicationFacade
  ├─ Entry & Session Manager
  ├─ Consent / Actor / Purpose Resolver
  ├─ Context Broker
  ├─ Soul Compiler
  ├─ Capability Router
  ├─ Knowledge Retriever
  ├─ Response Composer
  ├─ Safety & Human Gate Coordinator
  ├─ Named Action Bridge
  └─ Feedback / Evaluation Linker
```

校长对外表现为统一 IP，对内表现为 capability router 和 policy coordinator。它不把所有
能力都塞进一个超级 Agent；每一次请求只选择一个主 profile，跨 profile 协作由 workflow
拆成多个有因果关系的请求。

### 3.2 家庭端与运营端的双面人格

| 面 | 面向角色 | 允许能力 | 不能做 |
|---|---|---|---|
| 家庭校长 | 家长/孩子 | 理解、沟通、计划、行动、复盘、知识解释 | 诊断、排名、强制行动、自动写事实 |
| 产品设计校长 | 产品/教研/服务运营 | 问题洞察、组件编排、蓝图、模拟、知识治理 | 自动发布蓝图、自动分派、把模拟当效果 |
| 运营洞察校长 | 运营/治理 | 质量、成本、风险、版本、队列解释 | 自动改政策、价格、会员或分佣 |

同一 Soul 的语言价值保持一致，profile 只改变上下文、工具和输出 schema，不改变红线。

## 4. 端到端技术流程

### 4.1 家庭端请求

```text
UI-03/05/09
  → POST principal session/message
  → Actor/Tenant/Consent
  → ContextSnapshot
  → Safety.pre
  → Soul + Route + Knowledge
  → StructuredRequest
  → Model Gateway
  → Schema/Safety.post
  → PrincipalResponse(DRAFT)
  → User Confirmation / Human Gate
  → Named Action
  → Growth/Service Fact
  → Feedback/Evaluation
```

### 4.2 服务产品设计请求

```text
Operations Workbench
  → principal/service_product_architect
  → Product Intelligence / Three-Zone evidence
  → Component + Pattern catalog
  → Product Definition draft
  → Compiler 12 checks
  → Simulation + Red Team + Eval
  → Human Publish Gate
  → ServiceBlueprintVersion
  → ServiceCase/Task
  → Quality/Contribution
  → Component/Knowledge improvement candidate
```

### 4.3 所有流程的业务事实边界

```text
AI Draft / Recommendation / ActionProposal
    ×（不能直接写）
Human Decision / User Confirmation
    → Domain Named Action
    → Canonical Fact + Audit + Outbox
```

## 5. 技术对象与接口契约

### 5.1 核心对象

| 对象 | 归属 | 必备字段 | 状态 |
|---|---|---|---|
| `PrincipalSession` | Principal | id、actor、family/subject、entry、purpose、consent | OPEN/CLOSED/EXPIRED |
| `ContextSnapshot` | Context | scope、refs、time window、redaction、expires_at | READY/EXPIRED/DELETED |
| `PrincipalRouteDecision` | Router | capability、profile、agent、tools、risk、reason | RESOLVED/REJECTED |
| `KnowledgeRef` | Knowledge | claim/version/license/applicability | VALID/EXPIRED/REVOKED |
| `ModelDraft` | Gateway | output、schema、provenance、status=DRAFT | DRAFT |
| `HumanTask` | Human Gate | reviewer、risk、deadline、evidence | OPEN/DECIDED/ESCALATED |
| `ActionProposal` | Principal | candidate action、boundary、confirmation | PROPOSED/CONFIRMED/REJECTED |
| `EvaluationCase` | Eval | input refs、expected boundary、metrics | OPEN/ SCORED / RELEASED |

### 5.2 错误码

统一错误码跨环境不变：

`CONSENT_REQUIRED`、`SCOPE_DENIED`、`SOUL_VERSION_UNAVAILABLE`、`ROUTE_NOT_REGISTERED`、
`KNOWLEDGE_NOT_GROUNDED`、`MODEL_UNAVAILABLE`、`POLICY_REJECTED`、`SCHEMA_INVALID`、
`SAFETY_REVIEW_REQUIRED`、`HUMAN_GATE_REQUIRED`、`ACTION_CONFIRMATION_REQUIRED`、
`IDEMPOTENCY_CONFLICT`、`RETENTION_EXPIRED`、`DELETION_IN_PROGRESS`、`WORKFLOW_DEAD_LETTER`。

## 6. 现有代码映射与缺口

| 目标组件 | 现有代码/资产 | 真实状态 | 下一步 |
|---|---|---|---|
| Model Gateway | `backend/intelligence/model_gateway` | EXPERIMENT，已有结构化协议、OpenAI-compatible 多模态 adapter、ADR-0081 registry 组装工厂、ADR-0100 CredentialLease/SecretManagerCredentialPort metadata-first seam 与 ADR-0107 显式 mTLS/revocation-status seam；ADR-0117 冻结 `IdentitySessionPort` 的真实会话签发/轮换/撤销边界；ADR-0118 在启动期校验路由 profile 与 Gateway adapter/model identity/模态能力一致；ADR-0119 提供 Multimodal Draft SQL request-auth wiring | 接入真实 KMS/Secret Manager endpoint、证书轮换和撤销 endpoint；外部供应商合规批准后才能启用真实家庭数据 |
| Context Broker | `backend/intelligence/context_engine` | EXPERIMENT，内存 + durable SQL adapter | 生产 resolver、全域事件接入和常驻 retention worker |
| Principal Router | `backend/intelligence/principal` | 待重建 | 先实现确定性路由契约与测试 |
| Soul Compiler | 源项目 Soul YAML 作为设计参考 | 未接入 Python | 版本化 schema + 编译 + IP 回归 |
| Knowledge | compiled JSON + 测评 grounding | 静态快照 | registry、claim、检索、许可、删除 |
| Agents/Tools | `backend/intelligence/agent_runtime` + `backend/intelligence/tool_runtime` + `backend/intelligence/human_gate` + `governance/AI_USE_CASE_REGISTRY.yaml` | Agent/Tool foundation EXPERIMENT；具体业务 Agent 仍 PLANNED | AgentDefinitionRegistry 已从治理 YAML 加载静态边界；AgentRun/Trace、AgentAuthorization lease、ToolCall outbox、SQL Human Gate inbox、`AcceptedNamedActionDispatcher`、post-gate durable attempt/DLQ worker 与 bounded queue poll（ADR-0078）已有 durable seam；FGCN 已提供 `CONFIRM_SERVICE_TASK_ASSIGNMENT` accepted-action adapter（ADR-0077）与 `PROPOSE_SERVICE_BLUEPRINT` proposal consumer（ADR-0079）；`FGCNAcceptedActionRuntime` 组合根已绑定同 session queue/scheduler 与终态过滤（ADR-0080）；`ProductionAgentRuntimeResolver` 已在 ContextScope 与请求级事务下接线 Attempt/SafetyDecision；`AgentRuntime`/组合工厂已支持异步 SQL Prompt/Schema registry 并强制 published resolve；生产持续调度、lease takeover 压测、更多业务 handler 与 worker identity 仍待部署接入；Experience Outbox→Achievement consumer 已形成首个证据投影 seam |
| Product Factory | `design_copilot` / `product_factory` | 结构占位 | 12 项检查、模拟、发布闸门 |
| Human Gate | `backend/intelligence/human_gate` | SQL HumanTask/Decision、ToolAction inbox 与同事务 Audit consumer EXPERIMENT | 通知/队列租约/超时调度、业务域二次授权 |
| Evaluation | `backend/intelligence/evaluation/release_gate.py` + `release_service.py` + `release_control.py` + `operator_identity.py` + `release_catalog.py` + `deployment.py` + `report_archive.py` + `slice_archive.py` + `query.py` + `backend/platform/security/mtls.py` + `backend/apps/family_api/operator_request_context.py` + `production_release_wiring.py` + `production_evaluation_archive_wiring.py` + `evaluation_query_api.py` + `slice_runner.py` + multimodal/model benchmark | AiReleaseGate 已把离线证据与 ProviderRegistry 准入及阈值绑定；ReleaseAdmissionService 记录 0020 决策账本，ReleaseControlStore 记录 0031 人审批准与回滚指针，OperatorIdentity/Token adapter（ADR-0095）、ProductionReleaseRuntime（ADR-0098）、BenchmarkReportArchive（ADR-0102）、ProductionEvaluationArchiveRuntime（ADR-0103）、MultimodalSliceRunner（ADR-0104）、BenchmarkSliceArchive（ADR-0105）、AuthorizedEvaluationQueryService（ADR-0106）与显式 mTLS transport（ADR-0107）已形成 provider-neutral 评测→归档→授权查询接缝；评测与 Experience 运维 API 共享 request bearer task-local context，缺失/格式错误统一 401；CredentialLease 对 revoked lease fail-closed | 真实签名/身份服务、证书轮换/撤销回调、KMS/Secret Manager、影子发布、部署权限、告警、审计落库、dashboard、游标分页与长期保留策略 |
| Observability | `backend/intelligence/observability` + ModelGateway/AgentRuntime | `TelemetryContext`/`TelemetrySink` 统一 span 生命周期，SQL 0021 保存 opaque scope、低基数属性与 operation 幂等；Gateway 与 DurableAgentRuntime 已接入，`OpenTelemetrySpanSink`/`CompositeTelemetrySink` 可桥接 SDK exporter | 部署 collector、retention/deletion worker 与监控后端 |
| Memory | `backend/intelligence/experience` contracts + `backend/intelligence/memory/store.py` | `SqlAlchemyMemoryStore` 与 SQL 0022 持久化 MemoryRef 治理元数据，按作用域/同意/purpose/expiry 读取，级联删除并生成 proof，过期清理复用删除路径 | 向量检索、embedding 删除索引和常驻 retention worker |
| Growth Graph | `backend/intelligence/growth_graph` | `GrowthGraphOutboxConsumer` 从 Experience Outbox 重建受治理事件，`GrowthGraphEdge` + SQL 0023 只读投影提供证据/事件引用、作用域查询、稳定幂等和主体删除 proof；业务域仍拥有写入真相 | 全域 DomainEvent/outbox projector、生产只读权限和图检索排序 |
| Intervention | `backend/intelligence/intervention` | `GrowthInterventionEngine` 将 hypotheses/action_candidates 转成 evidence-bound、DRAFT-only 候选，最多 3 个 primary contradiction，按置信度确定性排序并标记 Human Gate；Blueprint matcher、pending bridge、accepted-action worker、FGCN proposal consumer 与 family_api accepted-action runtime composition 已形成实验闭环 | 真实模型推理、部署级 scheduler/worker identity、`OPEN_SERVICE_CASE` 业务闸门与纵向效果评测 |
| AI Achievement Landing | `backend/intelligence/experience/accepted_achievement.py` + `engagement.py` + `engagement_persistence.py` + `engagement_api.py` + `synthetic_engagement_runtime.py` | EngagementDraft 由服务端 `EngagementEventReader`/`SqlAlchemyEngagementEventReader` 按 scope 读取真实事件，再生成 evidence-bound Named Action → 人工接受后 `AI_EVIDENCE_MOMENT` read-model projection；`POST /families/{family_id}/experience/engagement/drafts` 只接受 request_id/event_ids/payload 并保持 DRAFT-only；`install_sql_engagement_runtime_wiring` 按 HTTP 请求读取 bearer/追踪头，组合 `SqlAlchemyBearerPrincipalResolver`、`SqlAlchemyTrustedTenantScopeStoreFactory` 与 `SqlAlchemyConsentSnapshotResolver`，`ProductionEngagementRuntimeResolver` 将事件 reader、Gateway、Attempt/Safety/Telemetry 绑定到同一 UoW，并可通过 ContextBroker 复核 snapshot_ref 的 tenant/family/subject/purpose/consent 边界（ADR-0121）；`HttpIdentitySessionPort.introspect` + `HttpIdentityPrincipalResolver` 为真实 auth_identity 提供实时 bearer 校验（ADR-0122）；dev/test 通过 `SyntheticEngagementRuntimeResolver` 使用同一应用契约保持功能 parity；occurrence identity 支持 evidence-distinct 重复成就；consumer 同事务更新通知 inbox 与 scope-local analytics；`feedback_api.py` 提供严格 scope resolver 只读查询，`SharedExperienceFeedbackRuntimeResolver` 可复用 Draft 的身份/同意 authority；Experience Outbox relay 使用 durable attempt/status、worker lease/takeover、SQL metadata-only DLQ 与 `ProductionExperienceOutboxRuntime.alert_sink`（ADR-0123）；通知读模型由 `AchievementNotificationRetentionWorker` 按 TTL 有界清理并产出 metadata-only 删除证明（ADR-0124）；Outbox 与 retention 由部署侧 schedule value object/`run_scheduled_tick` 执行单次有界 tick，实际 recurrence 由平台 scheduler 注入（ADR-0125）；dashboard/告警通过有界 `delivery_attempts(limit,status)` 与 `delivery_attempt_summary()` 读取 metadata-only 运行状态，并由 `/internal/ai/experience/delivery-attempts`、`/summary` 暴露 HMAC cursor 分页与 operator scope 授权，allow/deny/identity-error 记录到可注入 metadata-only audit sink，API 对 `last_error` 统一返回 `DELIVERY_ERROR_REDACTED`；请求 `Authorization: Bearer` 由 task-local context 绑定，`HttpRequestOperatorIdentityPort` 向 auth_identity 解析非敏感 operator metadata，缺失/格式错误 401 且结束清理；`SqlAlchemyExperienceOperationsAuditSink`、per-access session sink 与 Alembic 0037 提供 append-only durable 存储，仍由生产主入口显式绑定 identity/session factory（ADR-0126~0129）；身份服务调用边界由 `IdentitySessionPort`（ADR-0117）冻结 | 生产主入口调用、真实 auth_identity endpoint/数据库迁移、PostgreSQL 权限/并发/删除演练、实际 recurrence、主入口 identity/session-factory wiring 与 push/dashboard wiring |
| Multimodal Draft HTTP | `backend/intelligence/experience/api.py` + `backend/apps/family_api/production_experience_wiring.py` + `trusted_experience_scope.py` | `/families/{family_id}/experience/multimodal/drafts` 只接受生成意图与媒体引用；`install_sql_experience_runtime_wiring` 按请求构造 bearer→tenant/family→subject→consent 的 `ContextScope`，再进入 `SqlContextBrokerFactory` 生成的 durable ContextBroker、路由目录与 Model Gateway；路由 profile 与 adapter/model identity/模态能力在启动期校验（ADR-0118/0119/0120）；migration `0036` 提供三张 Context Engine 技术投影表 | 真实 auth_identity endpoint、ContextBroker SQL 权限与部署平台主入口接线 |
| Blueprint Matching | `backend/intelligence/intervention/blueprint_matching.py` | 只读取业务域 PUBLISHED Blueprint 快照，按 primary contradiction 输出 DRAFT `BlueprintRecommendation`，保留 evidence refs 和 Human Gate 标记 | Blueprint 编译/发布、人工确认和服务域执行 |
| Ops | mobile/UI 与部分 API | 多数 PARTIAL | Principal/AI 运维工作台和投影 |

### 6.1 反馈偏好上下文（ADR-0130）

多模态 Run 的 `feedback` interaction 仍是 append-only 账本事实。生成下一份草稿前，
Ledger 可按精确 tenant/family/subject scope 读取 `FeedbackPreferenceSnapshot`，仅
聚合最近最多 5,000 条 `helpful`、`not_helpful`、`request_human` 信号。快照以
`experience_feedback` 服务端字段绑定到 `ContextBoundMultimodalCommand`，覆盖客户端同名
输入，因而模型可以调整表达节奏但不能被伪造偏好引导。原始理由、媒体、模型原文、家庭
总分/排名和已删除 Run 均不进入 Prompt；无此读取能力的旧 Ledger 保持兼容，仍走同一
Model Gateway、Safety 和 Human Gate 链路。启用 `MultimodalContractRegistryBinding` 后，
生成请求还必须解析同一 use-case/agent 的已发布 Prompt/Schema 版本，并拒绝客户端
schema 漂移；staging/production 组合根缺少 `contract_binding` 时直接拒绝启动，只有
未安装生产 resolver 的应用才保持既有 503 fail-closed（ADR-0132）。
标准 `family-experience` 资产由 `standard_assets.py` 以不可变的
`FamilyExperienceAssetBundle` 提供：固定 `family-companion.v1` /
`family-experience-draft.v1` 输出契约，仅允许 `understanding`、`next_step`、
`limitations`，并默认保持 DRAFT。测试可以用显式审核者创建合成 PUBLISHED fixture；
生产仍须由 SQL Registry 和真实审批流程注入，工厂本身不自动发布（ADR-0133）。
注册阶段通过 `standard_asset_registration.py` 对 Prompt/Schema 身份做双侧预检，
要求成对 PUBLISHED；SQL 组合根持有事务并负责并发冲突回滚，注册器不隐式提交。
生产读取由 `sql_contract_binding.py` 的 session-per-call readers 完成：每次 Prompt 与
Schema resolve 独立打开/关闭 SQL session，避免跨请求复用启动期 session；生产 wiring
集成测试使用真实 SQL Registry 表和同一标准资产，不再用内存 Registry 冒充持久化读取。

## 7. 分阶段落地计划

### Wave 0：架构和契约冻结

交付：ADR、Principal Soul schema、route/tool/use-case registry、错误码、数据分类、
环境等价规则、核心 contract tests。禁止在没有这些契约前接入第二个模型供应商。

### Wave 1：单一家庭纵向切片

选择 `UI-03 测评解释 → UI-05 计划预览 → UI-09 今日行动`：

```text
assessment evidence → context → principal route
→ deterministic/model draft → schema/safety
→ family confirmation → journey named action
→ feedback/eval case
```

验收：请求可重放、来源完整、失败可解释、无 AI 直写、测试环境全路径等价。

### Wave 2：Soul、知识和安全

实现 Soul Compiler、reviewed retrieval、引用验证、Say It Tonight、风险升级、人工队列、
主体删除级联和 IP consistency eval。此阶段不做语音、头像、SFT/LoRA 或自动长期记忆。

### Wave 3：服务协作与运营

接入服务匹配、交付复盘、FGCN 案件只读投影、运营洞察、成本与质量仪表板；校长只给推荐
和洞察，服务分派、验收、贡献和权益仍由真人 Named Action 完成。

### Wave 4：服务产品设计工厂

实现 Component/Pattern/Blueprint catalog、12 项 compiler、simulation/red team、知识
管家、人工发布/回滚，并把 `ServiceBlueprintVersion` 接入 service 交付运行时。

### Wave 5：持续学习与规模化

建立决策来源图、Outcome 归因、影子评估、漂移检测、预算自动化、容量和灾备；只有当
证据证明某个低风险能力稳定，才通过 `AgentAuthorization` 放宽其自治范围。

## 8. 完成定义

AI 技术架构达到可生产标准，必须同时具备：

1. 每个用例有业务场景、输入、活动、输出、规则、数据对象、API、owner 和评估集。
2. Principal 能在同一运行时路由家庭端、服务产品和运营能力，且不重复建设网关。
3. Soul、Prompt、Schema、Knowledge、Model、Policy 都可版本化、审计、回滚和删除。
4. Context 最小化、可重放、可过期，派生数据可按主体级联删除。
5. AI 输出永远是 Draft/Recommendation/Proposal/HumanTask，业务事实只由 Named Action 写入。
6. 高风险内容 100% 进入人工闸门，闸门自身有可监测健康指标。
7. 发布前有 Contract/Safety/Grounding/IP/Usefulness/Workflow 回归证据。
8. dev/test/prod 具备同一功能和拒绝路径，测试只使用合成数据和替身适配器。
9. 运行时有 trace、cost、audit、SLA、限流、重试、死信、补偿和灾备证据。
10. 当前能力状态与代码、测试和发布证据一致，不以文档、目录或 fixture 冒充上线。
