---
id: SYS-AI-MAP-001
title: AiFamily Current AI Capability Map
type: system
status: current
version: 2.1
owner: chief-architect
created: 2026-08-29
updated: 2026-09-04
canonical: true
supersedes: docs/00_foundation/CURRENT_AI_ARCHITECTURE.md
superseded_by: null
---

# 当前 AI 能力版图 (Current AI Map)

> 本文件回答一个问题：**AiFamily 有哪些 AI 能力，各自真实成熟到什么程度。**
> 它是版图 + 成熟度矩阵。详细设计规格在 `docs/05_ai/AI_ARCHITECTURE.md`，本文件不重复。

---

## 0. 一句话结论（读本文件前先看这里）

```text
backend/intelligence/ 下当前已有 model_gateway、context_engine、agent_runtime、
tool_runtime、human_gate、evaluation、safety、prompt_registry、schema_registry、
observability、memory 和 design_copilot
design_copilot 的每个方法仍是 NotImplementedError；Growth Graph 仍未实现

∴ AiFamily 当前 AI 基础能力的真实成熟度: 12 项 EXPERIMENT；Growth Graph 也已进入 EXPERIMENT 投影阶段
   没有任何一项 AI 能力达到 PILOT 或 PRODUCTION
```

**2026-08-30 增量**：上面“尚无 PILOT/PRODUCTION”结论仍然成立，但 AI Runtime 的
多项基础能力已从 PLANNED/ABSENT 升为 EXPERIMENT，并已具备可验证的组合接缝。

```text
backend/intelligence/
  model_gateway/    真实代码 + 测试通过（EXPERIMENT）
  context_engine/   StateObservation/ContextSnapshot + SQL durable adapter（EXPERIMENT）
  agent_runtime/    Agent/Authorization/Trace + Registry + Composition（EXPERIMENT）
  tool_runtime/     三重授权 + ToolAction outbox（EXPERIMENT）
  human_gate/       SQL HumanTask + inbox consumer（EXPERIMENT）
  evaluation/       offline eval + release gate（EXPERIMENT）
  safety/           provider-neutral safety runtime（EXPERIMENT）
  observability/    metadata-only spans + OTel adapter（EXPERIMENT）
  memory/           MemoryRef durable store + deletion proof（EXPERIMENT）
  design_copilot/  仍全是 NotImplementedError（未变）

但仍需注意：
  零外部供应商通过第16条准入（唯一真实 adapter 被刻意登记为不可调用）
  所有新能力仍处于 EXPERIMENT，尚无真实家庭生产运行记录

∴ 已形成可运行的 AI 基础设施和测试闭环，但 PILOT 与 PRODUCTION 依旧为 0
```

详见 §3 表格第 1 项与 **§3.3（落地后仍然为真的话）**。

**2026-09-04 追记（本条不改写 §2/§4 的既有 Agent 分类）**：`family_need` 域下已落地一个本文件 §2/§4 未登记的能力——**AI Coach**（`backend/intelligence/experience/family_ai_coach.py` + `backend/domains/family_need/application/ai_coach.py`），苏格拉底式引导（不直接给答案，只反馈+提问），本周接入了跨轮次会话记忆（`M1_SESSION`）。它有一份**真实供应商验证测试**（`tests/intelligence/experience/test_family_ai_coach_real_model.py`，设置 `AI_COACH_MODEL_API_KEY`/`AI_COACH_MODEL_BASE_URL` 后跑真实 DeepSeek，未设置则 skip），这与 §3.3 第1点"零个外部供应商可调用"存在需要澄清的细微差别：AI Coach 有一条**可选、已验证**的真实供应商接入路径，不是"完全没有能力接通外部供应商"，但默认仍是 FakeProvider、未在生产默认启用——这仍然是 EXPERIMENT，不是 PILOT/PRODUCTION，本追记不推翻 §3.3 的结论，只是指出它没有覆盖到这个新增能力。是否要把 AI Coach 作为第六个"业务 Agent"正式登记进 §4 表格，属 chief-architect 的分类决策，本条不代做。

**源仓库 TS 侧有真实实现（`packages/ai-gateway/src/index.ts`，894 行）不等于 AiFamily 有。** 按 `governance/REPOSITORY_CONSTITUTION.md` R1（唯一后端真相 = Python），TS 实现只能作为**参考实现**（reference implementation），不是 AiFamily 的能力。

**"研究过 / 设计过"不等于"已实现"。** 本文件下方所有 `PLANNED` 条目都有完整的设计文档，这恰恰是最容易被误读为"已有"的情形 —— `SYSTEM_MANIFEST.md` §6（Current Truth ≠ Specification ≠ Evidence）就是为防这个而存在。

---

## 1. 成熟度词表

| 成熟度 | 定义 | 判据 |
|---|---|---|
| `PRODUCTION` | 已上线，服务真实家庭 | 有生产运行记录 |
| `PILOT` | 有可运行实现 + 测试，在受控环境验证中 | 代码可跑 + 测试通过 + 有验证证据 |
| `EXPERIMENT` | 有可运行代码，未验证、未接线 | 代码能执行但无验收测试或无调用方 |
| `PLANNED` | 有设计与登记，无可运行代码 | governance 有条目 |
| `ABSENT` | 无设计、无登记、无代码 | 什么都没有 |

`NotImplementedError` 占位**不算 `EXPERIMENT`** —— 它不能执行，等价于 `PLANNED` 加一个目录名。这一区分直接来自 R4（代码行数不是成熟度）与 `MIGRATION_MANIFEST.yaml` 中 `design_copilot` 的 override 原文："迁移不得被解读为该能力已存在"。

---

## 2. Family Principal（AI 主体的五类能力）

Family Principal 是平台 AI 主体的统称。其五类能力当前状态：

| 能力 | 说明 | AiFamily 成熟度 | 源仓库参考实现 |
|---|---|---|---|
| **Understanding**（理解） | 从测评证据、对话、家庭历史中理解家庭处境 | `EXPERIMENT` | `AssessmentAiInterpretationAdapter` 已打通 Assessment Evidence → durable Family Context → Principal route → governed Agent Runtime → Perspective Draft，并由 `ProductionAssessmentAiComposition` 统一绑定授权租约、AgentRun 回放和监护人 Named Action 两侧的同一策略。`install_production_assessment_http_wiring` 已提供请求级 SQL 事务与四项 FastAPI 依赖安装；ASGI 纵向测试证明未认证请求零模型调用，认证请求从 UI-03 展示到确认只调用供应商一次并创建 GrowthIntent。真实 SQL Bearer→Guardian 与单证据主体 ASSESSMENT consent resolver 已通过测试；尚未在部署 `main` 启用，也无获准的未成年人数据外部模型。 |
| **Planning**（规划） | 生成 21/90 天成长计划草案 | `EXPERIMENT` | `GrowthPlanAiDraftAdapter` 已打通已由真人确认的 GrowthIntent / onboarding / priority → 三类 durable Context Observation → Principal route → `growth_planner` → governed Agent Runtime → 90 天 Draft Plan，并强制四阶段顺序、可暂停且不惩罚、证据引用闭合以及禁止家庭总分/排名/诊断。`SqlAlchemyGrowthPlanEvidenceReader` 只接受服务端 scope 与 onboarding id，通过权威 binding 解引用 intent / priority / subject，分别保留两次真人确认，并对租户、家庭、主体、guardian、生命周期和重复数据 fail closed。Model Gateway DRAFT 与 `ai_growth_plan_draft_reviews` companion envelope 同事务持久化，绑定 consent / deletion / TTL / input refs / 业务引用 / 稳定摘要；跨请求审核可使用新 correlation，摘要或 scope 漂移 fail closed。共享 accepted-action runtime 已注册两项动作：第一次 Guardian ACCEPT 的 `CREATE_JOURNEY_PLAN_FROM_AI_DRAFT` 只创建 Journey DRAFT 并自动打开第二个独立 HumanTask；第二次 Guardian ACCEPT 的 `CONFIRM_AI_JOURNEY_PLAN` 会重验当前 scope/Consent、原始摘要、provenance 与当前 DRAFT 后才允许激活。认证 HTTP router 与 PostgreSQL bearer→tenant/family→guardian→subject→GROWTH_TRACKING Consent 组合入口已建立。真实 PostgreSQL 已验证 0057 全链升级、回退重建与不可变 trigger。仍缺真实 PostgreSQL Evidence Reader E2E、部署 `main` 挂载、常驻 worker 调度、retention worker、UI-05 展示及获准处理未成年人数据的外部模型。 |
| **Recommendation**（推荐） | 推荐行动、服务、教师 | `ABSENT` | 无（源仓库无真实推荐实现；`detect_scenario_keyword` 已被源仓库自己判定为"keyword-matching masquerading as understanding，verdict DEPRECATE"） |
| **Coordination**（协调） | 协调家庭、教师、机构多方（FGCN 一案一管家） | `ABSENT` | `apps/api/src/modules/orchestration`（5519 行，明确设计为不写 Growth 权威表） |
| **Reflection**（复盘） | 阶段复盘、越用越准的学习闭环 | `ABSENT` | 无。这是 `AI_NATIVE_PRINCIPLES.md` 判据 4（是否越用越准）的载体，源仓库无对应代码落地 |

**五个业务 Agent 仍未进入 PILOT/PRODUCTION。** `parent_advisor` 已有 UI-03 Perspective Draft 实验切片，`growth_planner` 已有 UI-05 Draft Plan 实验切片；二者均可消费持久化 Context、动态授权与 AgentRun 回放，但都尚未挂载部署主应用，也没有获准处理未成年人数据的外部模型。其余 Agent 仍只有统一 `AgentDefinition`、授权和 DRAFT-only Runtime 基础；`principal_core` 仍按后续批次推进。

R9 硬约束（对全部五项适用）：Principal 的任何输出都只能是 `Perspective` / `Recommendation`，永不得直接写入家庭权威事实。源仓库 `principal` 模块自身已遵守此约束（明确不写 Growth 权威状态），这一正确决定必须在 Python 侧保留。

---

## 3. AI Runtime 组件（R10：各一份）

R10 要求所有 AI 能力收敛于 `backend/intelligence/`，且 Model Gateway / Context Engine / Agent Runtime / Tool Runtime / Prompt Registry / Safety / Human Gate / Evaluation / Trace / Cost / Audit **各一份**。

| # | 组件 | 目标位置 | AiFamily 成熟度 | 说明 |
|---|---|---|---|---|
| 1 | **Model Gateway** | `backend/intelligence/model_gateway` | `EXPERIMENT` | Provider 准入、Timeout、Attempt、JSON/Schema、Provenance、DRAFT-only、Safety、预算、首选/备用、ReleaseSet invocation fence 与 OpenAI-compatible adapter 已落地。0052 将服务端审核的 System Policy/SHARED Knowledge 绑定到调用；0053 用 bounded lease/backoff 自动恢复 PREPARED/UNKNOWN/ACKNOWLEDGED，且不生成新授权或自动解除失败锁。ReleaseSet scope lock/CAS 和 reconciliation single-owner 均通过真实 PostgreSQL 并发验证。仍是 `EXPERIMENT`：零个外部供应商完成第16条准入，真实发布平台尚未接入。 |
| 2 | **Context Engine** | `backend/intelligence/context_engine` | `EXPERIMENT` | 已有 StateObservation、ContextSnapshot、InMemoryContextStore 与 `AsyncSqlContextBroker`；`SqlContextBrokerFactory`、迁移 0036、作用域/consent/TTL 校验和主体删除证明已接入 Multimodal Draft 生产组合。SQL observation 的完全相同重放已幂等，内容漂移仍失败关闭，支持 Assessment Evidence 的至少一次投递；仍缺部署级 SQL 权限与全域事件 worker。Family Context 的载体，见 §5.1 |
| 3 | **Agent Runtime** | `backend/intelligence/agent_runtime` + `backend/apps/family_api/production_agent_wiring.py` | `EXPERIMENT` | 已有 AgentDefinition/Authorization、Prompt/Schema 解析、ContextScope 绑定、DRAFT-only 执行、AgentRun/Trace SQL store、DurableAgentRuntime/显式 composition factory 与 ModelGatewayExecutionPort；生产 resolver 在任何模型调用前强制回读真实 durable ContextSnapshot，并可把家庭范围裁剪到本次证据主体。`AgentTask.input_refs` 已贯通 Model Gateway 且纳入 SHA-256 幂等指纹，不复制保存原始未成年人 payload。UI-03 组合按证据内容、consent、Prompt/Schema 形成稳定 request identity，重复请求回放同一成功 AgentRun，避免监护人确认时二次生成漂移；SQL 授权解析只接受当前认证 actor 预先签发且仍有效的 durable lease。真实 HTTP identity/consent 安装、授权签发流程、批准供应商和部署接线仍待完成。 |
| 4 | **Tool Runtime** | `backend/intelligence/tool_runtime` | `EXPERIMENT` | 已有三重授权、具名 Named Action、pending 状态、SQL outbox、Human Gate inbox consumer、`AcceptedNamedActionDispatcher`、post-gate durable attempt/DLQ worker、bounded queue poll 与 `run_until_idle` scheduler（ADR-0078）；FGCN 已提供 assignment 与 Blueprint proposal handler（ADR-0077/0079），family_api 组合根已提供同 session runtime、终态过滤队列与 AI achievement consumer（ADR-0080/0082），部署级持续调度、lease 压测与更多业务动作仍待接入 |
| 5 | **Memory** | `backend/intelligence/memory` + `experience/memory_adapter` | `EXPERIMENT` | `SqlAlchemyMemoryStore` 与迁移 0022 已提供 durable MemoryRef 引用存储、严格 tenant/family/subject/consent/purpose/expiry 读取、幂等写入、级联删除证明与 retention purge；不保存原始媒体、prompt、embedding 或模型输出。向量检索与生产 worker 仍待评审 |
| 6 | **Prompt Registry** | `backend/intelligence/prompt_registry` + `experience/execution_materials.py` | `EXPERIMENT` | Prompt 版本不可变、绑定、生效窗口和 fail-closed resolve 已有内存 + SQL（0030）；System Policy 与仅限 SHARED 的 Knowledge 已由内容寻址材料注册表和 0052 持久化，家庭多模态 ReleaseSet 调用强制解析已发布正文。运营审批签名、统一 loader 与回滚工作流待接入。 |
| 7 | **Schema Registry** | `backend/intelligence/schema_registry` | `EXPERIMENT` | 结构/安全边界、绑定、JSON 校验与 SQL 版本回读（0030）已实现；AgentRuntime 组合工厂已强制 published resolve，运营审批签名、统一 loader 与回滚工作流待接入 |
| 8 | **Safety** | `backend/intelligence/safety` | `EXPERIMENT` | 已有 provider-neutral 输入/输出安全运行时，并已接入 Model Gateway 与 Synthetic Runtime：禁止用例/字段 BLOCK，高影响或未成年人 REVIEW + Human Gate，DRAFT-only 校验；Agent 级二次授权与持久化决策待完成 |
| 9 | **Human Gate** | `backend/intelligence/human_gate` | `EXPERIMENT` | 已有 SQL HumanTask/Decision、审计、过期/claim lease、ToolAction inbox 与同事务 consumer；Achievement notification inbox 与 retention/调度 seam 已由 Experience runtime 提供，常驻调度和完整业务域 consumer 仍待部署接入 |
| 10 | **Evaluation** | `backend/intelligence/evaluation` + family-experience release/canary runtime | `EXPERIMENT` | 已有 offline benchmark、版本化 gold/report/slice、Release Gate、Decision/Control/Candidate/Deployment receipt SQL ledger、完整 `FamilyExperienceReleaseBundle` 与四环境同构 HTTP deployment。ADR-0137/0138/0139 新增 metadata-only canary observation、版本化 SLO、0041 assessment、0042 alert/ack 与 0043 durable job/lease ledger；四环境复用同一有界 scheduler，未成年人安全违规立即 breach，AI/监控不能生成授权或确认告警。当前仍无真实 key/部署/观测/paging 平台、外部定时触发器和 PostgreSQL 多 worker 演练证据，故保持 EXPERIMENT。 |
| 11 | **Observability**（Trace / Cost） | `backend/intelligence/observability` + ModelGateway/AgentTrace + `backend/apps/family_api/production_telemetry_retention_wiring.py` | `EXPERIMENT` | 统一 `TelemetryContext`/`TelemetrySink` span 接缝与 `ai_telemetry_spans`（0021），scope/request/session 使用 opaque ref、属性 allowlist 拒绝原始内容并支持 operation 幂等；`TelemetryRetentionWorker` 与 `ProductionTelemetryRetentionRuntime` 已提供按 `started_at` TTL 有界删除、同事务 metadata-only deletion receipt，`OpenTelemetrySpanSink`/`CompositeTelemetrySink` 可接入 SDK exporter，Attempt/SafetyDecision/AgentRun 仍提供业务审计，部署级 scheduler、collector、durable deletion proof/audit 与告警待配置 |
| 12 | **AI Provenance** | 跨组件（`backend/packages/contracts` + model_gateway） | `EXPERIMENT` | 2026-08-29 由"仅类型层"升级：记录机制已存在。`model_gateway/contracts.py` 的 `AiProvenance` 强制 model / model_version / prompt_version / schema_version / context_snapshot_ref / confidence / latency_ms / provider_id / data_class，身份字段缺一即构造失败（依据 PIPL 第24条，见 `COMPLIANCE_HARD_CONSTRAINTS.md` §2）。`backend/packages/contracts` 的 `Provenance` / `evidence` 类型仍是被 4 个域引用的证据等级原语，两者**不重复**：前者记录"这条 AI 输出是怎么产生的"，后者标注"这条数据的证据等级"。仍缺的是**人工审批记录链条**（Human Gate 未落地）与持久化（attempt 账本仅进程内） |

**汇总**：按上表 12 项计，`PLANNED` 0 项、`ABSENT` 1 项、`EXPERIMENT` 11 项。大多数 EXPERIMENT 只表示契约、测试和组合接缝可运行，不表示已有生产业务能力。**`PILOT` 与 `PRODUCTION` 仍为 0。**

### 3.3 Model Gateway 落地后仍然为真的话（不得被"已落地"掩盖）

1. **零个外部供应商可调用。** 真实 adapter 的登记条目 `openai-compatible-unassessed` 刻意设为 `status=TECHNICALLY_VALIDATED` + `sub_delegates=未确立`，因此 `admit()` 对它的任何数据类别都返回 `POLICY_REJECTED`——并有测试断言这一点。放行的前提是法务确立厂商分包结构（《儿童个人信息网络保护规定》第16条**不得转委托**，见 `COMPLIANCE_HARD_CONSTRAINTS.md` §7 与 §11.1 待办第1项）。**这不是工程可以自行判断的事**，也不是配置项。
2. **已有受控调用方，但尚无获准生产供应商。** Principal/多模态 Runtime 和 Family API 已通过显式 composition seam 使用 Model Gateway；当前仍只能以 synthetic/test provider 验证，不能据此声称真实家庭 AI 业务已上线。
3. **Attempt 持久化已具备但尚未成为默认生产接线。** `SqlAlchemyAttemptSink` 可在异步组合根中记录 STARTED/结果、token usage 并跨 session 回读；`aggregate_attempts` 通过显式 rate card 计算微 USD，缺价不生成成本数字。默认低层构造仍使用 `InMemoryAttemptSink`，生产必须显式注入持久化 sink，且网关只依赖 `AttemptSink` 协议，不得反向 import 业务域仓储。
4. **Prompt/Schema Registry 与 Evaluation 已有实验实现；Context Engine 已具备 durable SQL adapter。** Agent Runtime 与组合工厂已可在显式组合根中解析 SQL/内存的已发布 Prompt/Schema，`AiReleaseGate` 可消费离线评测并 fail-closed；ReleaseControlStore 已补齐真人批准/回滚控制，但运营签名、统一 loader 和真实生产部署仍未完成。
5. **§3.2 列出的机械检查已补。** `AI_NATIVE_PRINCIPLES.md` §5 的隔离、DRAFT-only、凭据边界由架构测试执行，且新增 Human Gate inbox、Agent registry 和 release gate 的针对性测试；真实供应商批准、持久化 eval/trace 与生产运行证据仍未补齐。

### 3.1 R10 的伤疤（Python 侧必须避免重演）

源仓库只有一份网关**实现**，但有三套互不相同的**接入模式**：

| 接入点 | 模式 | 严格程度 |
|---|---|---|
| `principal.module.ts:19-34` | DI 工厂 + fail-closed + AttemptRecording | 最严 |
| `family/family-model-gateway.provider.ts:17-22` | DI + 双 env 门控 | 中 |
| `orchestration/llm-gateway/family-llm-gateway.service.ts:58-63` | **裸 `new OpenAICompatibleAiGateway`** | 违规 |

**重复的不是实现，是纪律。** Python 侧落地 Model Gateway 时必须只允许一种接入模式。第三种是 R7 的直接伤疤：源仓库自己在 `packages/ai-gateway/src/index.ts:544-560` 声明了 `AI_GATEWAY_POLICY = { business_module_direct_provider_call: 'forbidden' }`，然后在业务服务方法内部违反了它 —— **策略写成了常量，但没有任何东西执行它**，这是 R14 存在的原因。

该违规文件在 manifest 中登记为 `orchestration_llm_gateway_violation`，status = BLOCKED，blocking_action：**REIMPLEMENT 时必须走 R7 的 Model Gateway，不得重复此违规**。

### 3.2 已有的机械护栏

`tests/architecture/test_no_direct_provider_calls.py` 与 `test_compliance_constraints.py::test_no_direct_provider_sdk_outside_model_gateway`（R7）已存在并通过。2026-08-29 之前它们**没有真实拦截对象**（无任何 AI 调用代码），属"预置护栏"；Model Gateway 落地后，`backend/intelligence/model_gateway` 成为它们唯一放行的路径，护栏开始有实际约束对象。

`AI_NATIVE_PRINCIPLES.md` §5 列出的两项待补检查**已于 2026-08-29 补齐**，落在 `tests/architecture/test_ai_runtime_isolation.py`：

| 检查 | 实现 | 验证会咬人 |
|---|---|---|
| `backend/intelligence/` 不得 import 业务域 repository | `test_ai_runtime_does_not_import_business_domains`（禁 `backend.domains.*` 与 `backend.platform.persistence`；后者刻意纳入——拿到 UnitOfWork 就等于拿到写 canonical 的能力） | 已植入违规验证失败 |
| 不得把 AI 产出置为 VALIDATED/APPROVED | `test_ai_runtime_does_not_promote_its_own_output`（查**赋值**而非提及：把这些状态写进拒绝清单是护栏，不是提升） | 已植入违规验证失败 |
| `may_mutate_business_state = false` 是运行时事实 | `test_model_gateway_output_type_cannot_mutate_business_state`（真实 import 并断言，且断言它**不是** dataclass 字段——带 False 默认值的字段今天能过检查、明天能在构造时被传 True） | 已把 property 改回字段验证失败 |
| 凭据只由 Model Gateway 读取（R7 原文） | `test_credentials_are_read_only_inside_the_model_gateway` | 已植入违规验证失败 |

§5 的第三项（判据 4“越用越准”需真实 eval 框架与回归测试）**仍未补齐** —— 当前 Evaluation 已能执行离线评测和发布控制，但尚无真实家庭反馈驱动的回归闭环。

---

## 4. 五个业务 Agent

`AI_NATIVE_PRINCIPLES.md` §3.5 定性：这 5 个不是五个功能，而是**五类被声明的 `AgentDefinition`**，各有 `allowed_skills` / `allowed_tools` / `context_policy` / `safety_policy` / `human_handoff_policy`，且统一 **`may_mutate_business_state = false`**。

| Agent | 服务对象 | 输出物定性（R9） | AiFamily 成熟度 |
|---|---|---|---|
| **家长顾问** | 家长 | Perspective / Recommendation | `EXPERIMENT`（UI-03 请求级纵向切片已装配，尚未挂载部署主应用） |
| **孩子陪练** | 孩子 | Perspective（**儿童直接作答继续 HOLD**，见 UI-10 `GATE_BOUNDARY`） | `ABSENT` |
| **助教助手** | 教师/助教 | Recommendation | `ABSENT` |
| **成长规划师** | 家长 | Draft Plan（草案，非计划本身） | `EXPERIMENT`（UI-05 权威证据读取、不可变审核信封、认证 HTTP、共享 worker、DRAFT 创建与独立激活双 Guardian Gate 已装配；尚无 Evidence Reader PG E2E、部署挂载、常驻调度与 UI 展示） |
| **经营助手** | 机构/运营 | Recommendation | `ABSENT` |

五个 Agent 均未进入 PILOT/PRODUCTION。`parent_advisor` 已有受治理的 UI-03 Perspective Draft 实验适配器，`growth_planner` 已有受治理的 UI-05 Draft Plan 实验适配器；另外三个仍未形成业务纵向切片。生产形态 Registry 只装载状态为 `EXPERIMENT` / `PILOT` / `PRODUCTION` 的 Agent、Use Case 与 Tool，`PLANNED` 定义不会获得模型调用资格；注册定义仍不能被误读成业务 Agent 已上线。

孩子陪练的额外约束：涉未成年人的动作须过 Human Gate（R8），且**禁止向未成年人做自动化决策商业营销**（《未成年人网络保护条例》第 24 条第 3 款，法定绝对禁止，见 `SYSTEM_MANIFEST.md` §3.2）。

---

## 5. 四个独占区候选

商业战略 V2 §8.2 提出的四个独占区候选。`AI_NATIVE_PRINCIPLES.md` §1 规定：**独占区候选必须 AI 原生**（五条判据全部答"是"）。

| 独占区候选 | 归属 | AiFamily 成熟度 | 空白证据 |
|---|---|---|---|
| **Family Context** | `backend/intelligence/`（AI Runtime 消费侧输入层，不产生业务权威状态） | `EXPERIMENT` | AiFamily 已有内存 Context 原语、`AsyncSqlContextBroker`、`SqlContextBrokerFactory` 与迁移 0036，支持 durable snapshot、scope/consent/TTL 校验和主体级删除证明；跨流程事件接入、部署 SQL 权限与生产 worker 仍待完成。源仓库 `FamilyMemoryDialogueRuntime` 仍未接入调用方，embedding / pgvector 仍不存在 |
| **Family Growth Graph** | 业务域事件写入真相；`backend/intelligence/growth_graph` 只读投影查询 | `EXPERIMENT` | `GrowthGraphEdge` + `GrowthGraphOutboxConsumer` + `SqlAlchemyGrowthGraphProjection` + 迁移 0023 已提供 Experience Outbox→证据边、作用域查询、幂等投影和主体级删除证明；全域 DomainEvent/outbox projector 与生产只读权限仍待接入 |
| **Growth Intervention Engine** | `backend/intelligence/intervention` | `EXPERIMENT` | `GrowthInterventionEngine` 已实现 primary contradiction（最多 3 个）筛选、置信度确定性排序、evidence refs 和 DRAFT/Human Gate 标记；Blueprint 匹配、pending action bridge、FGCN accepted-action adapter、durable dispatcher worker 与 Blueprint proposal consumer（ADR-0079）已接入实验链，真实模型推理和生产队列调度仍待接入 |
| **AI Achievement Landing** | `backend/intelligence/experience/accepted_achievement.py` + `engagement_review.py` + `achievement_persistence.py` | `EXPERIMENT` | EngagementDraft achievement candidate 已绑定真实事件 evidence；0054 持久化完整多主体 scope、output/provenance、TTL/deletion binding 与稳定摘要。候选提交 HTTP 只接受服务端 draft/candidate identity，生产 runtime 重新读取 Experience Outbox 并写未成年人读取审计后创建 HumanTask；人工决策由 bearer→account→active guardian membership 解析可信 reviewer。ACCEPT 只产生 `NamedActionRequest`；accepted-action worker 在落库前重新加载不可变 draft、回读 evidence 并重建 action，拒绝正文、候选、scope 或 provenance 篡改，再于同一 SQL 事务幂等写入 `AI_EVIDENCE_MOMENT`、通知 inbox 与 scope-local analytics。fresh Alembic head 的真实 PostgreSQL HTTP 测试已验证完整链路。仍缺 worker 执行时的当前 consent/deletion 实时复核、真实 bearer identity 的 PostgreSQL 并发 E2E、draft retention deletion、生产 push/dashboard 与实际 scheduler，故保持 EXPERIMENT。 |
| **Service Blueprint Library** | 蓝图对象 → `backend/domains/product_intelligence`/`service`；匹配能力 → `backend/intelligence/intervention` | `EXPERIMENT` | `ServiceBlueprintMatcher` 仅消费业务域 PUBLISHED 快照并输出 DRAFT 推荐；蓝图编译、发布、Human Gate 决策与业务执行仍待接入 |

### 5.1 Family Context 与 Family Growth Graph 是地基，不是增强

`AI_NATIVE_PRINCIPLES.md` §3.3 明确定性：

> Family Context 与 Family Growth Graph 是 AI 原生的**地基**，不是可选增强 —— 它们正是判据 2（数据结构为 AI 理解而设计）和判据 4（越用越准）的载体。当前 Context 已有 SQL durable adapter、生产组合 factory 与授权 scope 校验，Growth Graph 已有只读投影 seam，但跨流程事件接入与生产检索仍未完成，因此**不能把 EXPERIMENT 误读成生产能力**。

**含义**：不能把"已有 Context Engine 代码"读成"我们有一个可优化的生产 Context 层"。当前 durable、授权检索和删除闭环已有实验实现，但仍缺部署级权限、跨流程事件和生产运行证据。

---

## 6. 明确不算 AI 能力的东西（反面清单）

`AI_NATIVE_PRINCIPLES.md` §4 的反面清单，均在源仓库真实存在，**不得作为 AI 能力交付**：

| # | 反面模式 | 源仓库实例 |
|---|---|---|
| 1 | **硬编码文案冒充智能** | `dev-core-growth.service.ts` 的 `GROWTH_FOCUS_CONTENT` 文案字典 + `dev-platform-surfaces.service.ts` 的 24 张硬编码卡片，返回体自述 `model_gateway: 'NOOP_NOT_INVOKED'` |
| 2 | **关键词匹配冒充理解** | `detect_scenario_keyword` —— 源仓库 `CAPABILITY_TRUTH_REGISTRY.yaml` 自己判定为 "keyword-matching masquerading as understanding，verdict DEPRECATE"。**这个自我诊断是对的，继续有效** |
| 3 | **确定性 fallback 冒充 AI 输出** | `principal_soul_deterministic`，标为 `DETERMINISTIC_TEST_BASELINE + SAFE_FALLBACK / verdict DEPRECATE`。fallback 本身是必要的（fail-closed 要求），但**不得对外呈现为 AI 能力** |
| 4 | **硬编码兜底数值** | UI-17 的 `pointsBalance = membership?.dev_points?.balance ?? 1280` |
| 5 | **AI 只在最后一步做摘要** | 前面全是传统表单流程，最后加一个"AI 生成报告"按钮 —— 判据 1 的典型失败 |

`design_copilot` 属于第六类：**目录名冒充能力**。它已迁入 `backend/intelligence/design_copilot`，`ProductCompiler` / `DesignSimulator` 的每个方法都是 `NotImplementedError`，零调用方、零测试。manifest override 原文：

> 代码已迁入 …… 但其能力状态不变 …… **迁移不得被解读为该能力已存在。**

---

## 7. 成熟度汇总

```text
PRODUCTION    0
PILOT         0
EXPERIMENT   12   Model/Agent/Tool Runtime、Prompt/Schema Registry、Human Gate、
                  Evaluation、Safety、Context Engine、Memory、Observability、Growth Graph、AI Provenance（均有代码/测试，尚缺生产证据）
PLANNED       0
ABSENT        0
                  Family Principal ×5, 业务 Agent ×5,
                  独占区候选 ×4, design_copilot 的实际能力, ...
```

**AiFamily 已形成可运行的 AI Runtime 基础和受控实验闭环，但仍没有进入 PILOT/PRODUCTION 的 AI 业务能力。** `backend/intelligence/` 下的 Model Gateway、Context、Agent、Tool、Human Gate、Evaluation 均有代码与测试；`design_copilot` 仍是占位实现。

必须同时记住：Model Gateway 是**前置基础设施**，不是能力本身。它已有 Synthetic/Family API
受控调用方，但**零个外部供应商通过第16条准入**（见 §3.3）。也就是说，网关能否发出一次真实外呼，眼下取决于一个法务问题而不是工程问题。

这与 `SYSTEM_MANIFEST.md` §2 的定位形成的张力仍然成立：平台被定调为 **AI 原生**，而 AI 层依然是全系统最空的一层 —— 平台内核（6 项有代码有测试）和前端（34 屏幕完整）仍比它实在。**AI 原生目前是架构承诺，不是既成事实。** 落地 Model Gateway 改变的是"这条承诺现在有了合规的落地路径"，不是"承诺已实现"。

---

## 8. 约束来源（AI 能力落地时的硬约束，不可协商）

| 约束 | 内容 |
|---|---|
| **R7** | 领域不得直连模型供应商。一律经 `backend/intelligence/model_gateway`，凭据只由 Model Gateway 读取。`test_no_direct_provider_calls.py` 强制 |
| **R8** | 高影响行为必须过 Human Gate，闸门决策必须落库可审计 |
| **R9** | AI 输出永不自动成为事实。`Fact` ≠ `Perspective` ≠ `Recommendation` ≠ `Action`。**AiFamily 不计算、不存储、不暴露家庭总分与家庭排行** —— 即便某个模型偏好输出一个分数，落地层也不得将其持久化为权威状态 |
| **R10** | 唯一 AI Runtime：所有 AI 能力收敛于 `backend/intelligence/`，禁止 `family_ai_service` / `growth_llm_service` / `assessment_gpt_service` / `teacher_ai_service` 各自调模型。每个组件只允许一份，且只允许一种接入模式 |
| **R6 + Provenance** | AI 参与的每次状态变更必须可追溯到 model / model_version / prompt_version / context_snapshot / confidence / 人工审批记录 |
| **AI 原生五判据** | `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1，**上位约束**，与任何分项架构文档冲突时以它为准 |
| **AI Runtime 隔离** | `may_mutate_business_state = false`；AI Runtime 不得直接 import 业务域 repository；canonical 写入只能经业务域自己的 Named Action |
| **合规** | `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`；不做临床诊断；不向未成年人做自动化决策商业营销 |

**R9 的 FELS 继承否定语义**（AI 相关部分）：

| 旧世界对象 | 规则 | 红线 |
|---|---|---|
| `legacy_ai_report.ai_conclusion` | HISTORICAL_AI_HYPOTHESIS | 非 Fact / 非诊断 / 非疗效承诺 |
| `legacy_assessment_score.score` | HISTORICAL_EVIDENCE | 非 GrowthState |
| `legacy_advisor_note.note_text` | PERSPECTIVE | 非 Fact |
| `legacy_alert.risk_score` | SAFETY_SIGNAL_SOURCE | 非阈值 / 非自动动作；高风险须 Human Gate |
| `legacy_profile.family_score` / `.ranking` | **RETIRE** | 永不入 Family |

---

## 9. 与其它文档的分工（避免两处重复维护）

| 文档 | 职责 | 与本文件的关系 |
|---|---|---|
| **本文件** | AI 能力**版图 + 成熟度** | 只答"有什么、多成熟" |
| `docs/05_ai/AI_ARCHITECTURE.md` | AI Runtime **详细设计规格**：5 个 Agent 的输出物定性、数据资产三层画像、Growth Intervention Engine 设计、`primary_contradiction` 判断层的最小可执行落地方式、排期依据 | 详细设计**只在那里维护**，本文件不复制 |
| `docs/05_ai/AI_NATIVE_PRINCIPLES.md` | AI 原生 5 条判据 + 反面清单（**上位约束**） | 本文件引用其判据与反面清单，不改写 |
| `governance/REPOSITORY_CONSTITUTION.md` | R7 / R8 / R9 / R10 原文 | 本文件引用，冲突以宪章为准 |
| `governance/MIGRATION_MANIFEST.yaml` | 各 AI 能力的 disposition 与证据 | 本文件的成熟度断言以它为依据 |
| `TARGET_ARCHITECTURE.md` | AI Runtime 在目标拓扑中的位置、独占区归属判断 | 本文件只记成熟度，不记归属推理 |
| `CURRENT_SYSTEM_BASELINE.md` §4.3/§4.4 | AI 层的 Not Implemented 声明 | 与本文件一致，本文件是其展开 |
