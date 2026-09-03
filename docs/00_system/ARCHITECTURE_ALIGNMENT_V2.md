---
id: ARCH-ALIGN-002
title: Family 五层架构与法咪莉校长一体化重构蓝图
type: architecture-alignment
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# Family 五层架构与法咪莉校长一体化重构蓝图

> 本文件是业务、流程、数据、应用和 AI 技术五层的对齐设计。它不是“把五份文档
> 拼在一起”，而是规定同一个业务闭环在五层如何使用同一组标识、同一条事实边界和
> 同一套环境闸门。当前成熟度仍以 `docs/00_system/CURRENT_SYSTEM_BASELINE.md`、
> `docs/00_system/CURRENT_AI_MAP.md` 及现有 canonical 文档为准；本文件描述下一步
> 应该建成的形状。

## 1. 这次重构的结论

### 1.1 法咪莉校长不是第六个业务域

法咪莉校长是跨业务的 **Principal Experience + AI Orchestration Layer**：

```text
Principal Soul（人格/价值/语言/关系/行动/安全）
    ↓
Principal Context Broker（目的、同意、家庭上下文、知识引用）
    ↓
Principal Capability Router（把意图路由到既有 AI 用例、Agent、工具和服务产品工厂）
    ↓
Governed AI Runtime（Safety → Model Gateway → Schema → Provenance → Human Gate）
    ↓
Family / Service / Commerce / Operations Named Action
```

校长统一“怎么说、如何判断边界、下一步如何落地”，但不拥有家庭事实、服务事实、
会员权益或运营指标。所有事实仍由对应业务域写入，校长只能返回
`Perspective`、`Draft`、`Recommendation`、`ActionProposal` 或 `HumanTask`。

### 1.2 平台 AI 能力必须分成两类能力包

| 能力包 | 使用者 | 校长的角色 | 事实边界 |
|---|---|---|---|
| 家庭成长能力包 | 家长、孩子、家庭服务人员 | 以校长人格解释、陪伴、规划、复盘 | 家庭确认后才经 Named Action 写入 |
| 服务产品与运营能力包 | 产品、教研、服务运营、AI 治理人员 | 以“产品设计校长/知识管家”内部 profile 工作 | 设计稿、蓝图和运营洞察必须人工发布/采纳 |

这两类能力共用一个 AI Runtime、一个知识版本链、一个 Provenance 图和一个评估体系，
不再建设“家庭端一个模型、运营端另一个模型”的第二条链路。

### 1.3 三个区的投入顺序

| 三区 | 本次架构落点 | 当前判断 | 研发策略 |
|---|---|---|---|
| 同质区 | 通用问答、内容解释、打卡提醒、普通推荐 | 必须有但易复制 | 用校长统一体验；优先确定性降级、成本和安全 |
| 优势区 | 21/90 天 AI+真人计划、专家协作、服务匹配 | 可形成可感知差异 | 通过计划确认、Human Gate、FGCN 交付和反馈做深 |
| 独占区 | Family Context、Growth Graph、Intervention、Service Blueprint、Principal Soul | 当前多数仍是目标态 | 先做数据和版本闭环，再扩大 Agent 自主性 |

校长 IP 不是独占区的替代物；它是把独占区能力变成持续、可信、可复用体验的统一入口。

## 2. 当前系统真实状态与重构缺口

| 能力 | 当前证据 | 成熟度 | 本次重构后的目标 |
|---|---|---|---|
| 34 个 UI 基线 | mobile UI 与跨页测试已存在，部分页面接到 fixture/轻量 API | PARTIAL | UI 不改业务含义，全部改为投影读取 + Named Action |
| 家庭/测评/旅程域 | assessment 有纵向切片；journey、service 等处于部分实现 | PARTIAL | 每个 L2 场景都有 handler、事件、投影和异常分支 |
| 服务交付 | provider/offering/slot/booking/service record 可复用 | PARTIAL | 交付运行时与 Service Blueprint 设计工厂分离，通过冻结版本接线 |
| Product Intelligence | 领域对象、三区引擎和测试存在，HTTP 接线不完整 | PARTIAL | 作为运营侧输入，不写家庭事实；由校长内部 profile 调用 |
| Model Gateway | 结构化请求、provider 准入、Attempt、schema、Provenance、Draft-only 已测试 | EXPERIMENT | 成为所有校长与平台 AI 用例的唯一模型边界 |
| Context Engine | 内存观察/快照原语有代码，无长期持久化与业务调用方 | WIP | M0 会话上下文 → M1 授权偏好 → M2 只读 Family Context |
| Principal Soul | 源项目有 YAML、结构化输出和安全策略；本仓库尚无统一运行时 | PLANNED | Soul 版本化、与模型解耦、可审计、不可身份克隆 |
| Knowledge Base | 9 份 compiled JSON 与测评 grounding；无统一 registry/retrieval/delete | PARTIAL | Source→Version→Chunk→Claim→Review→Publish→Retrieve→Citation |
| Agent / Tool Runtime | 治理登记已创建，业务 Agent 全部 PLANNED | PLANNED | 由 Principal Router 选择一个执行 profile，禁止隐式多 Agent |
| Service Product Design AI | design_copilot 仅有占位编译器/模拟器；平台设计文档已补齐 | PLANNED | 组件→模式→产品→蓝图→模拟→人工发布→交付反馈 |
| 生产模型 | 当前无通过合规准入的外部供应商 | BLOCKED | test 使用 deterministic provider，生产无准入时显式人工/不可用 |

因此，“集成校长”当前首先是架构与契约集成，不应被表述为生产模型已经上线。

## 3. 业务架构重构

### 3.1 业务能力分层

```text
L0 商业目的：经营家庭持续成长需要
 ├─ B1 家庭成长交付：测评、理解、计划、行动、复盘
 ├─ B2 服务协作交付：供给、案件、任务、质量、贡献
 ├─ B3 商业关系增长：商品、会员、权益、邀请、续购
 ├─ B4 家庭关系与信任：社区、数据权利、安全、申诉
 └─ B5 平台经营与能力进化：产品智能、知识、AI、指标、组织、发布

横切能力：法咪莉校长（Principal Experience + AI Orchestration）
支撑能力：身份、授权、同意、幂等、持久化、审计、事件、工作流
```

校长在业务架构中只登记为横切能力，不拥有 `Family`、`ServiceCase`、`Order`、
`Outcome` 等权威对象。这样既能覆盖家庭端与运营端，又不会形成一个难以治理的
“AI 大域”。

### 3.2 Principal 能力契约

| 业务能力 | Principal profile | 输入 | 输出 | 采纳者 |
|---|---|---|---|---|
| 测评解释 | principal/family_understanding | Assessment Evidence、ContextSnapshot | Perspective/Hypothesis Draft | 家长/专业人员 |
| 假设优先级 | principal/growth_reasoning | hypotheses、历史观察、目的 | Priority + uncertainty | 家长/专业人员 |
| 90 天规划 | principal/growth_planning | 已确认意图、可用资源 | JourneyPlan Draft | 家庭确认 |
| 今日小行动 | principal/action_coaching | 当前阶段、最近观察 | ActionProposal | 家庭确认 |
| 沟通改写 | principal/relationship_coaching | 场景、原话、关系边界 | Communication Draft | 家长 |
| 服务匹配 | principal/service_matching | 成长意图、服务目录、资质投影 | Recommendation | 服务管家 |
| 服务产品设计 | principal/service_product_architect | 问题、组件、知识、成本/SLA | Product/Blueprint Draft | 产品/教研/运营 |
| 知识回答 | principal/knowledge_steward | 已发布 KnowledgeClaim | Grounded Explanation | 家长/工作人员 |
| 交付复盘 | principal/delivery_reflection | Task/Quality/Feedback 投影 | ProcessPerspective | 家庭/服务负责人 |
| 运营洞察 | principal/operations_insight | AITrace、质量、成本、队列投影 | OpsInsight/HumanTask | 运营/治理 |

### 3.3 不允许的业务越界

- 不把校长输出写入 `Family`、`GrowthProfile`、`GrowthAction`、`ServiceTask`、
  `Entitlement` 或 `Outcome`；必须由业务域 Named Action 写入。
- 不以校长人格包装诊断、疗效保证、家庭总分、家庭排名、未成年人商业画像或
  对外自动发送。
- 不把源教师/真实人物身份复制成模型身份；只能继承已审定的方法与表达原则。
- 不把“今天可以做的小行动”直接创建为权威行动；先成为 `ActionProposal`，经用户确认后再调用业务命令。

## 4. 分级流程架构重构

### 4.1 层级与标识

```text
L0 价值流 VS-01..VS-05
  L1 端到端流程组 P01..P06
    L2 业务/运营场景 S01..S24、O01..O14
      L3 子流程（如 P02.4 AI 助手与人工升级）
        L4 Principal 横切节点 PR-N01..PR-N10
          L5 API / Command / Event / Job / Human Task
```

现有 S/O 场景仍是完整业务边界；Principal 节点被复用，不创建一套平行的“AI 业务场景”。
每个 S/O 场景只引用一个 Principal capability route，业务事实仍回到原主场景。

### 4.2 Principal 通用闭环（可嵌入任意 L2 场景）

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| PR-N01 接收意图 | actor、tenant、family、entry_point、purpose | 创建 PrincipalSession，校验作用域 | SessionOpened | 未知入口、越权租户直接拒绝 |
| PR-N02 同意与身份 | ConsentGrant、ActorContext、主体年龄 | 校验 AI 个性化/家庭数据用途与成员可见性 | ConsentDecision | 未授权不得读取家庭/未成年人上下文 |
| PR-N03 上下文组装 | 允许的事实投影、观察、时间窗 | Context Broker 生成冻结快照 | ContextSnapshot | 只读投影；M0/M1/M2 分层；不得跨家庭混入 |
| PR-N04 安全预检 | 输入文本、风险信号、主体类型 | 风险分类、敏感主题识别、人工升级判断 | SafetyPrecheck | HIGH 风险只能生成提醒/人工任务 |
| PR-N05 能力路由 | intent、entry_point、context、内部角色 | Principal Router 选择一个 profile、Agent、Tool 集 | RouteDecision | 只能命中登记的 capability；不按模型名路由 |
| PR-N06 知识检索 | route、适用年龄、用途、版本 | 检索已发布 Claim，校验来源/许可/反禁忌 | KnowledgeRefs | 未核验引用清空；公共知识与家庭数据隔离 |
| PR-N07 结构化生成 | soul、prompt、schema、context、knowledge | 经 Model Gateway 生成 Draft | ModelDraft | `may_mutate_business_state=false`；Attempt 先登记 |
| PR-N08 输出复核 | Draft、provenance、policy | schema、安全、边界、引用和风险复核 | PrincipalResponse | 失败 fail-closed；不返回原始模型散文 |
| PR-N09 人工/用户闸门 | Response、风险、动作候选 | 展示、编辑、确认、拒绝或升级 | HumanDecision / UserConfirmation | 高影响动作必须真人；校长不能代签 |
| PR-N10 行动与学习 | Named Action、Outcome、Feedback | 业务域写事实；AI 侧记录反馈/评估样本 | DomainEvent + EvalCase | 事实由业务域写；驳回/暂停也进入评估闭环 |

### 4.3 关键业务场景的 Principal 嵌入

| L2 场景 | Principal 入口 | 主业务域 | 终态 |
|---|---|---|---|
| S04 测评执行 | Ask Principal / 结果解释 | assessment | Evidence 冻结；解释仍是 Perspective |
| S05 假设与意图 | Ask Principal | growth | 家庭确认 GrowthIntent |
| S06 90 天计划 | 90-Day Journey | journey | 家庭确认 JourneyPlan |
| S07 21 天行动 | Today Action / Say It Tonight | journey | 用户确认后生成 GrowthAction |
| S09 对话与升级 | Ask Principal | assistant/operations | Response 或 HumanTask |
| S10-S14 服务协作 | Service Recommendation / Delivery Reflection | service | 管家分派、验收、质量事实 |
| S15-S18 商业关系 | 会员权益解释 | commerce | 只读解释；支付/权益由商业域处理 |
| S19-S20 社区与权利 | Safety Review / Rights Helper | trust | 审核、导出、删除由治理域处理 |
| O02/O12 AI 发布 | Product Design / Knowledge Steward | operations/governance | 人工发布/回滚/删除证明 |
| O13/O14 运营发布 | Operations Insight | operations/release | 运营决策、变更、事故闭环 |

## 5. 数据架构重构原则

### 5.1 三类数据分层

| 层 | 例子 | 归属 | 可否由 AI Runtime 写 |
|---|---|---|---|
| 主数据 | Soul/Prompt/Schema/Knowledge/Component/Pattern/Service Blueprint policy | 相应治理或业务 owner | 只能通过版本发布流程 |
| 业务数据 | Family、Assessment、GrowthIntent、JourneyPlan、ServiceCase、Order、Outcome | 业务域 | 不可直接写 |
| AI 技术数据 | Session、ContextSnapshot、RouteDecision、ToolCall、ModelAttempt、Draft、Trace、Eval | AI Runtime/Governance | 可以写技术对象；不得写业务事实 |

### 5.2 Principal 关系骨架

```text
principal_soul_versions ─┐
principal_prompt_bindings ├─ principal_route_decisions
principal_schema_bindings ┘          │
                                     ├─ principal_sessions
                                     │      ├─ principal_messages
                                     │      ├─ principal_context_refs ── context_snapshots
                                     │      ├─ principal_knowledge_refs ─ knowledge_claims
                                     │      ├─ principal_tool_calls
                                     │      ├─ principal_model_runs ── ai_model_attempts
                                     │      ├─ principal_responses ── human_review_decisions
                                     │      ├─ principal_action_proposals ── user confirmation
                                     │      ├─ principal_human_handoffs ── ops_queue_items
                                     │      └─ principal_feedback ── evaluation_cases
```

`principal_action_proposals` 只保存候选和确认状态；确认后仍通过现有 Action Bridge 调用
`GrowthAction` 或其它业务 Named Action。任何表都必须带 `tenant_id`、主体范围、
`purpose`、`data_class`、版本引用和留存/删除状态。

### 5.3 与已有业务表的关系

| AI 对象 | 业务数据来源 | 关系方向 | 约束 |
|---|---|---|---|
| ContextSnapshot | Assessment、Family、Journey、Service 只读投影 | Domain Event → Snapshot | 不读业务 ORM；可重放、可过期 |
| KnowledgeRef | KnowledgeVersion/Claim | AI → 主数据版本 | 引用必须存在、可审计、可撤回 |
| RouteDecision | EntryPoint、UseCase、内部角色 | Session → Decision | 一个请求一个主路由；拒绝也留痕 |
| ModelDraft | ModelAttempt、Prompt/Schema/Soul | Decision → Draft | 仅 DRAFT；不可自动晋升 |
| HumanDecision | Draft、ActionProposal | Draft → Human Gate | 真人 reviewer；必须 reason/before/after |
| Named Action | Family/Journey/Service/Commerce | Human/User → Domain | AI 只能提交待确认命令，不持有 repository |
| Outcome/Feedback | Action、ServiceDelivery、Quality | Domain Event → Eval | 不得转成家庭总分或排名 |

### 5.4 物理表建议

目标表名统一使用 `principal_` 前缀，避免把校长运行时误当业务域：

`principal_soul_versions`、`principal_prompt_bindings`、`principal_sessions`、
`principal_messages`、`principal_route_decisions`、`principal_context_refs`、
`principal_knowledge_refs`、`principal_tool_calls`、`principal_model_runs`、
`principal_responses`、`principal_action_proposals`、`principal_human_handoffs`、
`principal_feedback`、`principal_eval_cases`。

这些表与 `ai_requests`、`context_snapshots`、`ai_model_attempts`、`human_review_decisions`
共享 provenance、审计、幂等和删除机制，不另建第二套 AI 追踪表。

## 6. 应用架构重构

### 6.1 应用模块

```text
PrincipalApplicationFacade
 ├─ PrincipalSessionService       # 会话、消息、入口、目的
 ├─ PrincipalConsentResolver      # 同意与主体/租户范围
 ├─ PrincipalContextBroker        # 只读家庭/服务/运营投影
 ├─ PrincipalCapabilityRouter     # capability → profile/agent/tools
 ├─ PrincipalKnowledgeRetriever   # reviewed claim/citation
 ├─ PrincipalResponseComposer     # soul + schema + boundary
 ├─ PrincipalHumanGate            # review/edit/reject/escalate
 ├─ PrincipalActionBridge         # 仅创建待确认 Named Action 命令
 └─ PrincipalFeedbackService      # outcome/feedback/eval projection
```

内部 profile 不是新的 Agent 类型，而是同一校长人格下的执行配置：

`family_understanding`、`growth_planner`、`relationship_coach`、
`service_product_architect`、`knowledge_steward`、`operations_insight`。
每次请求只允许一个主 profile；需要跨角色协作时由 workflow 创建新的、可审计的请求，
而不是在一次请求中隐式串联多个模型。

### 6.2 接口与 34 UI 对齐

| 接口 | 用途 | UI |
|---|---|---|
| `POST /families/{id}/principal/sessions` | 创建校长会话并声明入口/目的 | UI-01、03、05、09 |
| `POST /principal/sessions/{id}/messages` | 发送结构化请求，返回 Response/Draft | UI-03、05、09、10 |
| `GET /principal/sessions/{id}/context` | 查看允许的上下文来源 | UI-03、08、31 |
| `POST /principal/action-cards/{id}/confirm` | 用户确认一个小行动/话术 | UI-09、10、11 |
| `POST /principal/responses/{id}/review` | 工作人员人工审阅/改写/升级 | UI-24、31、34、运营端 |
| `POST /ops/principal/product-design/runs` | 运行服务产品设计草案/编译/模拟 | 运营工作台 |
| `POST /ops/principal/knowledge/refs` | 知识引用、审核、失效与删除 | 教研/治理工作台 |

API 返回必须是带 `response_id`、`status`、`provenance`、`risk_route`、`action_boundary` 的
结构化 DTO；禁止 UI 自行拼装模型文本或把按钮点击当成事实完成。

### 6.3 依赖方向

```text
Mobile / Operations
      ↓
Family API Router → PrincipalApplicationFacade
      ↓                         ↓
Named Action ports       backend/intelligence/*
      ↓                         ↓
Business Domain Facts    Context / Knowledge / Safety / Gateway
```

Principal 只依赖 AI ports、platform contracts 和只读 projection ports；不导入业务域
ORM/repository，不直接调用模型 SDK，不直接写 outbox 之外的业务表。

## 7. AI 技术架构重构

### 7.1 统一运行时拓扑

```text
EntryPoint
  → Principal Session
  → Actor / Tenant / Consent
  → Context Broker (M0/M1/M2)
  → Safety Precheck
  → Principal Soul Compiler
  → Capability Router
  → Knowledge Retriever
  → Agent/Tool Runtime
  → Model Gateway (唯一模型边界)
  → Schema + Safety Postcheck
  → Principal Response / Draft
  → Human Gate / User Confirmation
  → Named Action Bridge
  → Outcome / Feedback / Evaluation
```

家庭端输入/输出不是纯文本链路：`Text / Voice / Image / Audio / Video / InteractiveCard`
先经过 MediaSession、同意、转写/OCR、内容安全和 provenance，再进入 ContextSnapshot；
输出按家庭设备、语言和无障碍偏好选择文字、语音、音频、视频或互动卡片。原始媒体、
转写/OCR、Embedding、缓存和 AI 输出分层存储，删除和租户隔离规则不变。

### 7.2 Soul 的六个版本化维度

| 维度 | 内容 | 版本化规则 |
|---|---|---|
| Persona DNA | 知性、温暖、有判断、不说教、有边界、能落地 | 不得包含真实身份克隆指令 |
| Values | 孩子尊严、父母尊严、关系优先、小行动、证据谦逊 | 变更必须回归 IP 与安全集 |
| Thinking Policy | 场景优先、假设非事实、行为不贴标签、先安全后建议 | 禁止输出思维链 |
| Language Style | 短句、先共情后判断、可执行、可复述 | 与输出 schema 解耦 |
| Action Policy | 一次一个小行动、观察后再判断、复盘、不可直接改事实 | 高影响动作强制闸门 |
| Safety Policy | NORMAL/REVIEW/HIGH_RISK、诊断/保证/排名/商业画像禁用 | 任何版本都必须 fail-closed |

### 7.3 运行时不变量

1. `Model Gateway` 是唯一模型供应商边界。
2. Principal 与所有 Agent 的 `may_mutate_business_state` 恒为 `false`。
3. 每次请求都有 `soul_version`、`prompt_version`、`schema_version`、
   `context_snapshot_ref`、`knowledge_refs`、`model_attempt_id`。
4. 未授权、未核验引用、schema 失败、风险不明时 fail-closed。
5. 高影响决定必须进入 Human Gate；普通小行动也必须经过用户确认后才生成事实。
6. dev/test/prod 走完全相同的 route、schema、状态机、错误码、审计和人闸；test 只替换合成数据与适配器。

## 8. 服务产品设计 AI 与校长的结合

服务产品设计 AI 不进入家庭端自由对话，而是作为校长的内部能力 profile：

```text
产品/教研问题
 → Principal/service_product_architect
 → Product Intelligence（问题、假设、价值、三区）
 → Component/Pattern Catalog
 → Service Product Definition
 → 12 项 Compiler Checks
 → Simulation / Red Team / Eval
 → Human Publish Gate
 → ServiceBlueprintVersion
 → ServiceCase / ServiceTask
 → Quality / Contribution / Feedback
```

知识管家 profile 负责来源、许可、claim、反禁忌和失效，不允许把家庭私有上下文复制到公共知识库。
运营洞察 profile 只读聚合投影，不能改价格、分派、会员或政策。

## 9. 分阶段实现路线

| 阶段 | 交付 | 真实完成判据 |
|---|---|---|
| A0 契约冻结 | Soul、Principal Route、表/事件/错误码、IP 红线 | contract tests + ADR + registry 对齐 |
| A1 单一家庭切片 | UI-03 测评解释 → UI-05 计划预览 → UI-09 小行动 | Context→Gateway→Draft→确认→Named Action→反馈闭环 |
| A2 关系与安全 | Say It Tonight、人工升级、删除/撤回 | 高风险 100% 进闸，主体删除级联 AI 派生数据 |
| A3 服务协作 | 服务匹配、交付复盘、FGCN 接线 | 推荐不分派，验收/贡献全由真人事实完成 |
| A4 设计工厂 | 组件、知识、编译、模拟、蓝图发布 | 12 项检查可重复，模拟不可自证，发布可回滚 |
| A5 运营与学习 | 质量/成本/漂移/评估 | 驳回/改写/暂停进入 eval，版本发布有证据 |

### 9.1 验收门槛

- 任何“校长已建议”都能追溯到 `response_id → route → context → knowledge → attempt`。
- 任何“家庭已行动/服务已完成”都能追溯到业务域 Named Action，而不是 AI 响应。
- 任何环境都具备相同接口、错误码、状态机、人工闸门、回滚和删除路径。
- 当前代码仍是 `PLANNED/EXPERIMENT` 的能力不得在 UI、运营报表或对外材料中标为“已上线”。

## 10. 反向架构审查：成立条件、失败模式与裁决

这次设计不只列“为什么可行”，也列出“为什么可能失败”。只有正反两面都能被测试或
明确裁决，才允许进入实现。

| 设计判断 | 正向价值 | 反向风险 | 防止失控的裁决 |
|---|---|---|---|
| Principal 统一人格和路由 | 家庭端、设计端、运营端体验一致，Soul/Trace 可复用 | 变成超级 Agent，所有业务被一个中心阻塞 | 每次请求一个主 profile；能力通过 registry/port 插拔；跨 profile 只能走显式 workflow |
| AI Runtime 单一网关 | 凭据、准入、Attempt、成本和安全集中 | 网关成为单点瓶颈；某个供应商不可用时全平台停摆 | capability-based routing、基础设施失败才允许已准入 failover、确定性/人工降级 |
| Context/Memory 形成独占壁垒 | 长期连续性和家庭成长证据可积累 | 过度采集、目的漂移、删除困难、监控式产品 | M0-M3 分层、purpose/TTL/subject 删除、默认最小上下文；未通过 DPIA 不启用 M3 |
| Human Gate 保证高影响安全 | 让责任回到真人，可拒绝可解释 | 形式审批、批量橡皮章、延迟拖垮体验 | 风险分级、SLA、批量限制、前后版本、驳回率/耗时/异常速率监控 |
| AI 参与产品设计 | 组件复用、编译、模拟和知识治理提效 | 模拟结果被包装成真实效果，AI 自动发布错误蓝图 | 模拟永远是 synthetic evidence；12 项检查失败阻断；发布/回滚真人负责 |
| dev/test/prod 功能等价 | 测试结果能说明生产路径 | 真实供应商未准入，团队用测试假成功冒充生产 | 同一 route/state/error/gate；测试只替换 adapter；生产不可用必须显式返回 |
| 统一知识库 | 引用、版本、许可、失效可治理 | 公共知识混入家庭私有内容；旧知识继续被召回 | Source→Claim→Review→Publish；家庭数据不进入公共 registry；过期即不可检索 |

### 10.1 已发现的跨架构矛盾和处理结果

1. **AI 现状文档不一致**：`AI_ARCHITECTURE.md` 仍保留“Model Gateway 零实现”的历史断言，
   而 `CURRENT_AI_MAP.md` 与代码测试已经证明 Model Gateway 为 `EXPERIMENT`。处理结果：
   当前状态以 `CURRENT_AI_MAP.md` 和可执行测试为准；本次深度设计仍保持 `draft`，未经 ADR
   接受前不改变 canonical 文档。
2. **Principal 数据表不是从零开始**：SQL baseline 已有
   `principal_sessions`、`principal_messages`、`principal_responses`、
   `principal_action_proposals`、`principal_human_handoffs`、`principal_model_runs`、
   `principal_model_attempts`。处理结果：新增设计只补 route、Soul、Profile、Knowledge、
   Eval 等缺口，不再创建 `principal_action_cards` 或第二套 attempt 表。
3. **FGCN 数据脚本不等于 FGCN 能力**：`service_cases/service_tasks` 等表存在，但应用 handler、
   投影、权限、验收和贡献闭环仍需证据。处理结果：数据层标为 `BASELINE`，业务/应用能力仍为 `PARTIAL`。
4. **“主要矛盾”来源不足**：一手材料更稳定的表达是“优先级和不确定性”，不强行新建
   `PrimaryContradiction` 实体。处理结果：沿用 `GrowthHypothesis`，增加排序/不确定性字段，
   待业务确认后再改变对象边界。
5. **服务产品设计与服务交付边界**：设计工厂属于 Product Intelligence/AI 控制面，
   `ServiceBlueprintVersion` 和交付事实属于 Service 域。处理结果：编译生成 Draft，真人发布后
   才形成蓝图版本，案件按 snapshot 引用，历史交付不反写设计稿。

### 10.2 最小可行架构（MVA）与不可删减项

为了避免“大平台一次性建设”反噬项目，第一阶段只实现：

```text
PrincipalSession
 → Consent + ContextSnapshot
 → Deterministic Route
 → ModelGateway/FakeProvider
 → Schema + Safety + Provenance
 → PrincipalResponse(DRAFT)
 → User Confirmation
 → 一个业务 Named Action
 → Feedback
```

可以延后：M3 长期记忆、Embedding、复杂多 Agent 协同、语音/头像、自动预算调优。
不可删减：同意、主体隔离、Draft-only、唯一网关、Human Gate、审计、幂等、删除和环境等价。

### 10.3 六引擎体验与商业修正

本版进一步纳入“拼多多 + 字节 + 海底捞 + 贝壳 + 教育 + 游戏”六种能力来源：

```text
拼多多：低门槛/社交传播/挑战营
字节：内容发现/兴趣反馈/推荐实验
海底捞：被重视/即时响应/服务补救
贝壳：ACN/FGCN 案件协作/贡献凭证
教育：方法论/21-90-年度成长节奏
游戏：章节/任务/反馈/非比较性解锁
```

六引擎不是六个业务域，而是通过 X0 Experience & Trust、B1-B5 业务域和 Principal
控制面落地。体验顺序固定为“情绪承接 → 小胜利 → 连续成长 → 主动服务需要 → 经济选择”。
抖音式推荐只能优化发现和反馈速度，不能把停留时长、未成年人情绪或消费行为直接变成
商业画像；游戏化不能引入家庭总分、家庭排名、随机奖赏或连续打卡惩罚。
详细正反评审见 `docs/00_system/ARCHITECTURE_BENCHMARK_REVIEW_V3.md`。

## 11. 目标—五层架构对齐矩阵

| 目标/设想 | 业务架构 | 流程架构 | 数据架构 | 应用架构 | AI 技术架构 | 验证证据 |
|---|---|---|---|---|---|---|
| 家是港湾、孩子是希望 | 家庭成长交付 VS-01 | S04-S09 理解→行动→复盘 | Evidence/Observation/Outcome | Assessment/Journey/Growth Application | Principal 家庭 profile + 安全策略 | 无总分/排名、用户可拒绝 |
| 经营家庭持续成长需要 | VS-01→VS-05 长周期价值流 | P01-P06 跨场景闭环 | Family Context + Growth Graph | Journey/Service/Feedback 投影 | Context、Memory、Provenance 图 | 可重放、可删除、Outcome 归因 |
| AI+真人协作 | AI 是横切能力，不拥有事实 | PR-N09 Human Gate、PR-N10 Named Action | Draft/Decision/Fact 分层 | Review/Action Bridge | `may_mutate=false` + Human Gate | R8/R9 测试 |
| 三区独占区 | Context、Intervention、Blueprint | P02/P03/P06 关键节点 | 观察、组件、蓝图、反馈版本 | Product Design/Service Application | Soul、Knowledge、Eval、编译器 | 版本复利、模拟不自证 |
| FGCN 协作网络 | 服务协作交付 VS-02 | S13 案件→任务→验收→贡献 | ServiceCase/Task/Contribution | ServiceCollaborationApplication | 服务匹配/复盘只读推荐 | 真人分派/验收/贡献 |
| 可持续商业关系 | 商业关系增长 VS-03 | S15-S18 目录→意向→会员→权益 | Product/Order/Entitlement/Ledger | Commerce Application | 校长只解释，不自动营销或支付 | 未成年人商业禁投 |
| 平台可运营、可发布 | 平台经营 VS-05 | O12-O14 AI/指标/发布/事故 | Trace/Cost/Eval/Change/Audit | Operations/Release Application | LLMOps、预算、漂移、回滚 | release gate、parity report |
| 测试可直接走生产路径 | 环境不是业务分层 | 所有 L0-L5 节点相同 | 同 schema/事件/状态 | 同 API/错误码/闸门 | 同 route/model contract | synthetic adapter only |

矩阵的使用规则：任何新 UI、接口、表、Agent 或知识卡片都必须补齐一行对齐证据；如果
只能填“页面存在”或“模型能回答”，而填不出业务场景、节点、权威数据、应用 handler、
安全策略和测试证据，就只能标为 `DESIGN_ONLY`，不能进入实现完成统计。
