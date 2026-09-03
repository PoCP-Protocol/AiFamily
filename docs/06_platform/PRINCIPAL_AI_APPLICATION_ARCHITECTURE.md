---
id: APP-PRINCIPAL-001
title: 法咪莉校长集成应用架构
type: application
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# 法咪莉校长集成应用架构

## 1. 应用边界

校长应用层负责“接收意图、编排 AI、返回结构化结果、等待人确认”，不负责拥有家庭、
服务、会员或运营事实。业务域继续通过自己的 Application Service 和 Named Action 写入权威状态。

```text
Mobile / Operations / Partner
          ↓
Family API Router
          ↓
PrincipalApplicationFacade
          ├─ Session / Consent / Context
          ├─ Capability / Profile Router
          ├─ Knowledge / Soul / Schema
          ├─ AI Runtime Ports
          ├─ Human Gate / Action Bridge
          └─ Feedback / Evaluation
```

## 2. 模块分解

| 模块 | 职责 | 依赖 | 禁止 |
|---|---|---|---|
| `PrincipalSessionApplication` | 会话、消息、入口、目的 | identity、consent、idempotency | 直接调用模型 |
| `PrincipalContextApplication` | 组装只读 ContextSnapshot | context port、projection port | 读业务 ORM |
| `PrincipalSoulApplication` | 加载/编译 Soul 版本 | soul registry、policy | 写家庭事实 |
| `PrincipalRoutingApplication` | capability→profile/agent/tool | AI use case registry | 按供应商名写路由 |
| `PrincipalKnowledgeApplication` | claim 检索、许可、失效、引用 | knowledge port、index port | 接受模型自报引用 |
| `PrincipalGenerationApplication` | 组装 StructuredRequest、调用 Gateway | model gateway、schema、safety | 直连 SDK |
| `PrincipalReviewApplication` | HumanTask、review、edit、escalate | human gate、ops queue | AI 自行批准 |
| `PrincipalActionBridge` | 创建待确认业务命令 | domain command port | 直接调用 ORM |
| `PrincipalFeedbackApplication` | 记录反馈、Outcome 引用、EvalCase | event/query ports | 改写历史 response |
| `PrincipalProductDesignApplication` | 组件、蓝图、模拟、发布草案 | product intelligence、design copilot | 自动发布 ServiceBlueprint |

## 3. API 与应用用例

| API | Command/Query | 主要输入 | 返回 |
|---|---|---|---|
| `POST /families/{family_id}/principal/sessions` | OpenPrincipalSession | entry、purpose、subject、consent | SessionReceipt |
| `POST /principal/sessions/{session_id}/messages` | GeneratePrincipalResponse | message、capability hint、idempotency | PrincipalResponse DTO |
| `GET /principal/sessions/{session_id}/context` | ReadContextSources | scope、purpose | ContextSourceProjection |
| `POST /principal/action-cards/{id}/confirm` | ConfirmPrincipalAction | confirmation、actor、idempotency | NamedActionReceipt |
| `POST /principal/responses/{id}/feedback` | RecordPrincipalFeedback | decision、reason、outcome ref | FeedbackReceipt |
| `POST /ops/principal/responses/{id}/review` | ReviewPrincipalResponse | approve/edit/reject/escalate | HumanDecisionReceipt |
| `POST /ops/principal/product-design/runs` | RunProductDesignDraft | problem、components、constraints | DesignDraftReceipt |
| `POST /ops/principal/knowledge/claims` | SubmitKnowledgeClaim | source、claim、license、scope | KnowledgeReviewReceipt |

所有接口请求都必须携带或由网关解析出统一作用域 envelope：`global_id`、`tenant_id`、
`region_id`、`family_id`/`subject_ids`、`purpose`、`consent_version`、`data_class`、
`locale`/`content_locale`/`model_locale`/`policy_locale`、`tenant_policy_version`、
`correlation_id`、`causation_id`。返回 envelope 还必须包含 `request_id`、`status`、
`provenance`、`risk_route`、`human_action_required`、`retryable`、`error_code`。
作用域字段缺失或租户/区域策略不可解析时，统一返回 `SCOPE_DENIED` 或
`TENANT_POLICY_UNAVAILABLE`；UI 不接收原始供应商异常或未校验文本。

## 4. 应用流程

### 4.1 家庭端

```text
OpenSession
 → Consent/Authorization
 → ReadContextProjection
 → ResolvePrincipalProfile
 → RetrieveReviewedKnowledge
 → Generate via ModelGateway
 → Validate/Safety
 → Return Draft/ActionProposal
 → UserConfirm or HumanReview
 → Domain Application Command
 → Receipt + Event
```

### 4.2 运营端服务产品设计

```text
DesignIntent
 → ProductIntelligence evidence
 → Component/Pattern selection
 → ProductDefinition draft
 → Compiler 12 checks
 → Simulation / Eval
 → Human Publish Gate
 → ServiceBlueprintVersion
 → service delivery runtime
```

设计端和家庭端共用 Soul、Knowledge、Gateway、Safety、Trace、Eval，但使用不同 profile、
上下文策略、schema 和 Human Gate 责任人。

## 5. UI 对齐

| UI | 校长能力 | 应用投影 | 权威写入 |
|---|---|---|---|
| UI-03/02-result | 测评解释、假设优先级 | Perspective/Hypothesis Draft | 人工/家庭确认 GrowthIntent |
| UI-04/05 | 90 天计划 | Plan Draft/Preview | ConfirmPlan |
| UI-09/10/11 | 今日行动、今晚怎么说 | ActionCard/Communication Draft | ConfirmAction |
| UI-08/12/29 | 结果/故事解释 | Outcome Perspective | SaveStory/ConfirmOutcome |
| UI-19/20/24/31/34 | 服务匹配、交付复盘 | Recommendation/HumanTask | 分派/验收 Named Action |
| UI-13/14/18/30 | 商品/会员解释 | Catalog/Entitlement Projection | Commerce Command |
| 运营工作台 | 产品设计、知识、运营洞察 | Design/Eval/Ops Projection | Publish/Rollback/Policy Decision |

UI 基线保持不变；业务含义由投影和状态驱动，不能通过前端硬编码“已完成”“已升级”或“AI 已诊断”。

## 6. 依赖规则和错误处理

- Router → Application → Domain Port/AI Port；UI、AI Runtime 均不得访问 ORM。
- 每个写操作必须通过 identity、authorization、consent（适用时）、idempotency、audit、outbox。
- AI 失败只返回 `MODEL_UNAVAILABLE`、`SCHEMA_INVALID`、`SAFETY_REVIEW_REQUIRED` 等稳定错误码，
  不向 UI 泄漏 prompt、家庭文本、密钥或供应商响应。
- 所有环境使用同一接口、作用域解析、状态机、人工闸门和错误码；test 只注入合成投影、
  FakeProvider、sandbox/noop adapter，不删除生产路径上的功能。
- 多租户请求必须在 Router、Context、Knowledge、Cache、Embedding 和 Eval 六个边界分别校验，
  不允许“超级管理员”通过跨租户快捷查询绕过审计。
- 多语言请求必须保留原语言引用，按 canonical concept 检索，缺少可靠政策/知识翻译时降级人工，
  不得静默把敏感建议机翻后继续执行。

## 7. 应用完成定义

一个校长应用用例只有同时具备以下证据才可标为 `IMPLEMENTED_TESTED`：

1. 唯一场景/节点映射和 actor/purpose/consent 规则；
2. DTO、状态机、错误码、幂等、审计和 outbox；
3. Soul/Prompt/Schema/Knowledge/Model provenance；
4. 业务事实写入由 Named Action 完成且 AI 不能绕过；
5. 成功、拒绝、人工升级、超时、重试、死信和补偿测试；
6. UI/运营投影可由事件重建；
7. dev/test/prod 功能等价证据；
8. 删除、导出、回滚和事故接管路径。
