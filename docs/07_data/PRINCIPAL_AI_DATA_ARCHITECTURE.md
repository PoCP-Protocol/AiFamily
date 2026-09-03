---
id: DATA-PRINCIPAL-001
title: 法咪莉校长集成 AI 数据架构
type: data
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# 法咪莉校长集成 AI 数据架构

本文件将校长运行时落到数据对象、表、关系、事件和删除策略。它不替换业务域事实表，
而是为 Principal 控制面补齐 AI 技术数据；家庭、旅程、服务、商业事实仍由各自域拥有。

## 1. 数据分层

| 层 | 典型对象 | 物理 schema | 写入者 |
|---|---|---|---|
| 主数据 | `PrincipalSoulVersion`、`PromptBinding`、`KnowledgeClaim`、`ComponentDefinition` | `ai_control` / 对应业务 schema | owner + release gate |
| 业务数据 | `Family`、`AssessmentEvidence`、`GrowthIntent`、`JourneyPlan`、`ServiceCase`、`Outcome` | 各业务域 | 业务 Named Action |
| AI 技术数据 | `PrincipalSession`、`ContextSnapshot`、`RouteDecision`、`ModelRun`、`Draft`、`EvalCase` | `ai_runtime` | AI Runtime / Human Gate |
| 运行投影 | 家庭助手、运营队列、质量/成本看板 | `read_model` | Event projection |

## 2. 当前基线与目标增量

仓库已经有 Principal 的一部分 SQL baseline，但这不等于运行时能力已经接通：

| 现有 baseline 表 | 已表达的语义 | 当前缺口 |
|---|---|---|
| `principal_sessions` | 会话和家庭范围 | 没有应用层开会话/关闭/过期状态机 |
| `principal_messages` | 用户/校长消息 | 缺 purpose、data_class、redaction/deletion 元数据 |
| `principal_responses` | 风险、schema、结构化输出 | 缺 Soul/Prompt/Schema/Knowledge provenance |
| `principal_action_proposals` | 非 canonical 行动候选 | 需统一 ActionCard 逻辑对象和确认桥接 |
| `principal_feedback` | 反馈和评分备注 | 缺 Outcome/Evaluation 关联和删除属性 |
| `principal_model_runs` | 逻辑模型运行 | 需与 Python Gateway 的 request/attempt 协议统一 |
| `principal_model_attempts` | provider attempt 账本 | 需由 Gateway 真实写入，而不是只有 SQL |
| `principal_human_handoffs` | REVIEW/HIGH_RISK 人工接管 | 缺队列、SLA、锁定、人工决定投影 |
| `product_events` | Principal 产品事件 | 需接 Outbox/Inbox 和可重放投影 |

以下对象目前没有对应的 Principal 专用表，属于本次增量设计：
`principal_soul_versions`、`principal_profiles`、`principal_prompt_bindings`、
`principal_schema_bindings`、`principal_context_refs`、`principal_knowledge_refs`、
`principal_route_decisions`、`principal_eval_cases`。其中 `ContextSnapshot`、
`AIRequest`、`HumanDecision` 优先复用 AI Runtime 统一表，不再另建 Principal 版本。

## 3. 主数据对象与表

| 对象 | 表 | 主键/唯一键 | 关键字段 | 生命周期 |
|---|---|---|---|---|
| PrincipalSoulVersion | `principal_soul_versions` | `(soul_id, version)` | persona/values/thinking/language/action/safety refs、owner、reviewer | DRAFT→PUBLISHED→RETIRED |
| PrincipalPromptBinding | `principal_prompt_bindings` | `(profile, use_case, version)` | soul_ref、prompt_ref、schema_ref、knowledge_policy、risk | 同上 |
| PrincipalSchemaBinding | `principal_schema_bindings` | `(schema_ref, version)` | required、forbidden、boundary、human_gate | 同上 |
| PrincipalKnowledgeScope | `principal_knowledge_scopes`（目标） | `(profile, knowledge_version)` | purpose、age scope、license、expiry | APPROVED/REVOKED |
| PrincipalProfile | `principal_profiles` | `(profile_id, version)` | audience、allowed agents/tools、context policy、budget | ACTIVE/PAUSED |

主数据版本发布必须生成 `principal_release_bundle`，冻结 Soul、Prompt、Schema、Knowledge、
Safety、Model capability、评估结果和回滚版本，禁止原地修改。

## 4. 运行对象与表

| 对象 | 表 | 主键 | 输入/引用 | 输出/状态 |
|---|---|---|---|---|
| PrincipalSession | `principal_sessions` | `session_id` | actor、tenant、family、subject、entry、purpose、consent | OPEN/CLOSED/EXPIRED |
| PrincipalMessage | `principal_messages` | `message_id` | session、actor、content_ref、data_class | RECEIVED/REDACTED/DELETED |
| PrincipalRouteDecision | `principal_route_decisions` | `route_decision_id` | session、capability、profile、policy | RESOLVED/REJECTED |
| PrincipalContextRef | `principal_context_refs` | `context_ref_id` | route、projection refs、snapshot ref、memory refs | INCLUDED/EXCLUDED/EXPIRED |
| PrincipalKnowledgeRef | `principal_knowledge_refs` | `knowledge_ref_id` | claim/version、license、applicability | VALID/EXPIRED/REVOKED |
| PrincipalToolCall | `principal_tool_calls` | `tool_call_id` | route、tool/version、input hash | SUCCEEDED/REJECTED/FAILED |
| PrincipalModelRun | `principal_model_runs` | `model_run_id` | request、attempt、provider capability | STARTED/SUCCEEDED/FAILED |
| PrincipalResponse | `principal_responses` | `response_id` | model run、schema、safety | DRAFT/REVIEW_REQUIRED/EXPIRED |
| PrincipalActionCard（逻辑对象） | `principal_action_proposals`（已有 baseline） | `proposal_id` | response、candidate action、confirmation | PROPOSED/CONFIRMED/REJECTED |
| PrincipalHumanHandoff | `principal_human_handoffs`（已有 baseline） | `handoff_id` | response、risk、queue、deadline | OPEN/DECIDED/ESCALATED/CLOSED |
| PrincipalFeedback | `principal_feedback` | `feedback_id` | response/action/outcome、actor | ACCEPT/EDIT/REJECT/DEFER |
| PrincipalEvalCase | `principal_eval_cases` | `eval_case_id` | input refs、expected policy、versions | OPEN/SCORED/RELEASED |

所有运行表强制包含：`global_id`、`tenant_id`、`region_id`、`family_id`（运营侧可为空但需
`scope_reason`）、`subject_ids`、`actor_id`、`purpose`、`consent_version`、`data_class`、
`locale`、`content_locale`、`created_at`、`expires_at`、`deletion_ref`、`correlation_id`、
`causation_id` 和 `provenance_ref`。涉及模型、策略或人工队列的请求还必须记录
`model_locale`、`policy_locale` 和 `tenant_policy_version`，以便重放时恢复当时的语言和租户策略。

`global_id` 不依赖单区域自增；`tenant_id` 是权限边界，`region_id` 是数据主权边界，
`family_id` 是家庭边界，`subject_ids` 是最小主体范围。任何一个字段缺失都不得进入模型调用、
向量索引或跨区域事件。

## 5. 关系与基数

```text
PrincipalSoulVersion 1 ── N PrincipalProfile
PrincipalProfile 1 ── N PrincipalPromptBinding
PrincipalSession 1 ── N PrincipalMessage
PrincipalSession 1 ── N PrincipalRouteDecision
PrincipalRouteDecision 1 ── N PrincipalContextRef
PrincipalRouteDecision 1 ── N PrincipalKnowledgeRef
PrincipalRouteDecision 1 ── N PrincipalToolCall
PrincipalRouteDecision 1 ── N PrincipalModelRun
PrincipalModelRun 1 ── 1 PrincipalResponse
PrincipalResponse 1 ── N PrincipalActionCard（→ principal_action_proposals）
PrincipalResponse 1 ── N PrincipalHumanHandoff（→ principal_human_handoffs）
PrincipalResponse 1 ── N PrincipalFeedback
PrincipalFeedback 0..N ── 1 PrincipalEvalCase
```

Context 引用可以关联 `ChildMemory`、`GuardianMemory` 和 `RelationshipMemory` 的最小只读
投影，但不能把记忆正文复制进响应或公共知识库；每次记忆读取都要记录 purpose、可见范围、
确认版本和 `MemoryRetrieval` 审计。

与业务域的关系均为只读引用或待确认命令：

```text
Assessment/Family/Journey/Service Projection
   → ContextSnapshot → PrincipalResponse
   → UserConfirmation/HumanDecision
   → Domain Named Action → Domain Fact Event
   → PrincipalFeedback/EvalCase
```

不允许 `PrincipalResponse` 直接外键写入 `growth_actions`、`service_tasks`、
`entitlements` 或 `outcomes`；如需关联，只保存 `requested_action_ref` 和最终事件引用。

## 6. 事件模型

事件统一使用 `principal.<aggregate>.<verb>.v1`，并采用平台事件 envelope：

| 事件 | 触发 | 消费者 |
|---|---|---|
| `principal.session.opened.v1` | 会话建立 | trace、consent、projection |
| `principal.context.snapshot_ready.v1` | 上下文冻结 | route、audit |
| `principal.route.resolved.v1` | 能力路由完成 | retrieval、agent runtime |
| `principal.response.drafted.v1` | Draft 生成并校验 | UI、Human Gate |
| `principal.handoff.created.v1` | 高风险/不确定 | operations queue |
| `principal.action.proposed.v1` | 小行动候选 | user confirmation |
| `principal.action.confirmed.v1` | 用户确认 | application action bridge |
| `principal.feedback.recorded.v1` | 采纳/改写/拒绝/暂停 | eval、quality |
| `principal.data.deletion_completed.v1` | 派生数据删除完成 | audit、compliance |

事件只描述事实或技术状态；AI 建议本身不能伪装成业务完成事件。

## 7. 数据分类、留存和删除

| 数据 | 分类 | 默认留存 | 删除动作 |
|---|---|---:|---|
| 会话正文 | FAMILY_PRIVATE_TEXT / MINOR_PERSONAL_DATA | 目的期限 | 脱敏或主体删除 |
| ContextSnapshot | 派生敏感 | 短 TTL | 级联 observations、缓存 |
| KnowledgeRef | INTERNAL/PUBLIC | 版本生命周期 | 失效后不可检索 |
| ModelAttempt/Trace | 技术审计 | 审计期限 | 主体删除时去标识化/级联 |
| Embedding/Cache | 派生敏感 | 与源一致或更短 | 主体级删除并生成证明 |
| EvalCase | 继承原始数据 | 经脱敏后有限期 | 追溯 deletion_ref |
| Soul/Prompt/Schema | 主数据 | 版本归档 | 不物理删除已发布审计版本，按法律保全 |

删除作业必须记录 `scope_assessment`、处理对象数量、失败项、重试、供应商删除回执、
完成时间和 `deletion_proof_ref`。法律保全只能延迟删除，不能默默跳过。

## 8. 索引、隔离与一致性

- 所有家庭/主体表按 `(tenant_id, family_id, subject_id, created_at)` 建组合索引。
- `purpose`、`consent_version`、`data_class` 是策略索引，不是展示字段。
- Route、ModelRun、Response 以 `idempotency_key` 保证一次请求不重复生成事实。
- 版本引用使用不可变 revision；历史响应永不被新 Soul 或新知识重写。
- 投影可重建，事实表和 AI 技术表通过 Outbox/Inbox 连接；跨服务不使用隐式双写。

## 9. 当前缺口与实施顺序

1. 先复用现有 `principal_sessions`、`principal_messages`、`principal_responses`、
   `principal_action_proposals`、`principal_human_handoffs`，补 `route_decisions` 和审计事件。
2. 接入现有 `principal_model_runs/attempts` 与 Python Gateway；不新增第二套 Attempt/Trace 真相。
3. 再补知识引用、Soul/Profile 版本、统一 HumanTask 和 Eval 表。
4. 最后实现 embedding、M3 记忆和跨阶段归因；没有删除证明前禁止进入生产。
