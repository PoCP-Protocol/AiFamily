# UI-04 + UI-05 Report-to-Plan API Contract 001

## 1. Contract status and implementation boundary

```text
PHASE=FORMAL_API_CONTRACT_AND_GUARDED_IMPLEMENTATION
CONTRACT_PATH=contracts/frontend/UI-04_UI-05_REPORT_TO_PLAN_API_CONTRACT_001.md
SOURCE_GATE_UI04=reports/m2/frontend/UI-04_PHASE_C_PRE_API_GATE_001.md
SOURCE_GATE_UI05=reports/m2/frontend/UI-05_PHASE_C_PRE_API_GATE_001.md
SOURCE_UPSTREAM_CONTRACT=contracts/frontend/UI-02_UI-03_CORE_GROWTH_90_DAY_PLAN_API_CONTRACT_001.md
UI_SCOPE=UI-04,UI-05
SLICE_NAME=Report Explanation to 90-day Plan Draft Preview
CONTRACT_APPROVED_FOR_DRAFTING=YES
IMPLEMENTATION_ALLOWED=YES__UI04_UI05_GUARDED_SLICE_ONLY
BUSINESS_CODE_MODIFIED=YES__UI04_UI05_GUARDED_SLICE_ONLY
OPENAPI_FILES_CREATED=0
EXTERNAL_EFFECTS_ALLOWED=NO
MODEL_GATEWAY_DIRECT_CALL=NO
FORMAL_PLAN_CREATION=NO
```

本 Contract 只授权 UI-04/UI-05 的 **ReportExplanation read projection**、**PlanDraft controlled preview** 和明确标记为受控草稿的家庭审阅状态。它不授权创建正式 GrowthPlan、GrowthJourney、GrowthTask、Intervention、ServiceCase，也不授权预约、支付、通知、直播、社区发布、分享、导出或任何外部效果。

## 2. Upstream lineage and product boundary

UI-04/UI-05 必须消费 UI-02/UI-03 已建立的 onboarding、Perspective、Evidence、GrowthProfileDraft 和 Insight 血缘。报告解释只能表达有限观察、假设和建议草稿；90 天计划只能表达阶段结构与候选行动。它们不证明教育效果，不产生诊断，不把 Perspective、Hypothesis 或 Recommendation 直接写入核心 Ontology。

```text
Family-scoped auth
→ GrowthOnboarding / Perspective / Evidence
→ GrowthProfileDraft / GrowthInsightProjection
→ UI-04 ReportExplanationProjection
→ UI-05 PlanDraftPreviewProjection
→ family review state
→ later, separately approved FamilyDecision / Named Action
```

## 3. Object model and source-of-truth rules

| Object | Role in this slice | May be written now | Prohibited shortcut |
|---|---|---:|---|
| `ReportSnapshot` | 版本化报告解释输入 | No; read only | 不把页面文案当成事实快照 |
| `ReportExplanationProjection` | UI-04 read projection | No; server-derived | 不把解释 headline 当诊断或 Outcome |
| `PlanDraft` | UI-05 controlled draft | Only a bounded draft/preview receipt if existing service supports it | 不创建正式 GrowthPlan 或 Task |
| `GrowthGoalCandidate` | 90 天阶段候选 | No canonical write | Recommendation 不能自动成为 Goal |
| `GrowthActionCandidate` | 第一周候选行动 | No canonical write | Action candidate 不是 GrowthTask |
| `FamilyDecision` | Recommendation→Decision 边界 | No formal decision in this slice | 不把点击查看/确认 preview 当 FamilyDecision |
| `ConsentGrant` | `PLAN_READ`/`PLAN_DECISION`/`CHILD_DATA` policy gate | No implicit grant | 页面 checkbox 不能替代 server consent |
| `Evidence` | provenance reference | No free-text evidence write | Perspective 不能升级为 Fact |
| `HumanGateReview` | 高风险或不完整 provenance 的人工门 | No external effect | 缺门时必须 `REVIEW_REQUIRED`/`HELD` |
| `ModelGatewayRun` | AI metadata/no-op boundary | No direct model call | 模型输出不得直写 Ontology |
| `AuditEvent` / `OutboxEvent` | action/receipt trace | Only for any explicit Named Action | 不允许静默状态变更 |

## 4. API surface

仓库没有 global `/api` prefix，以下路径是本切片的正式语义 Contract。UI-04/UI-05 只能使用 family-scoped authenticated routes。

| Method and path | UI | Kind | Effect |
|---|---|---|---|
| `GET /families/{familyId}/growth/onboardings/{onboardingId}/insight` | UI-04 | Existing upstream read projection | None |
| `GET /families/{familyId}/growth/onboardings/{onboardingId}/report-explanation` | UI-04 | ReportExplanation read projection | None |
| `GET /families/{familyId}/growth/onboardings/{onboardingId}/plan-preview` | UI-05 | PlanDraftPreview read projection | None; preview only |
| `POST /families/{familyId}/growth/onboardings/{onboardingId}/plan-preview/refresh` | UI-05 | Named Action `RefreshPlanDraftPreview` | Controlled draft receipt only; no formal plan |
| `POST /families/{familyId}/growth/onboardings/{onboardingId}/plan-decision/propose` | UI-05 later handoff | Named Action candidate | Held in this slice; no formal decision |

When a route has no valid report provenance, consent, safety policy or version, the server must return a typed `REVIEW_REQUIRED`, `CONSENT_REQUIRED`, `PROVENANCE_INCOMPLETE` or `HUMAN_GATE_REQUIRED` response. It must not manufacture a successful synthetic projection in `real-api` mode.

## 5. Read projection contracts

### 5.1 `ReportExplanationProjection`

```ts
interface ReportExplanationProjection {
  projection_version: string;
  family_id: string;
  onboarding_id: string;
  report_snapshot_id: string | null;
  source_insight_version: string;
  entry_state: 'READY' | 'EMPTY' | 'CONSENT_REQUIRED' | 'REVIEW_REQUIRED' | 'FORBIDDEN' | 'STALE' | 'ERROR';
  state: 'REPORT_REQUESTED' | 'EXPLANATION_READY' | 'REVIEW_REQUIRED' | 'FAMILY_VIEWED';
  title: string;
  observations: Array<{
    label: string;
    detail: string;
    kind: 'PERSPECTIVE' | 'EVIDENCE_BOUND_OBSERVATION';
    evidence_refs: string[];
  }>;
  hypotheses: Array<{
    text: string;
    uncertainty: 'LOW' | 'MEDIUM' | 'HIGH';
    source_refs: string[];
  }>;
  recommendations: Array<{
    text: string;
    source: 'RULE_BASED' | 'MODEL_GATEWAY_NOOP';
    status: 'DRAFT' | 'HELD';
    next_allowed_action: 'READ_ONLY' | 'REQUEST_FAMILY_DECISION' | 'HUMAN_REVIEW_REQUIRED';
  }>;
  evidence_lineage: Array<{
    evidence_id: string;
    source_ref: string;
    source_version: string;
    provenance_kind: 'PERSPECTIVE' | 'ASSESSMENT_RESPONSE' | 'STRUCTURED_EVIDENCE';
  }>;
  consent_state: {
    required_purposes: Array<'PLAN_READ' | 'CHILD_DATA'>;
    state: 'GRANTED' | 'REQUIRED' | 'REVOKED' | 'REVIEW_REQUIRED';
    policy_version: string;
  };
  ai_ready: {
    evidence_boundary: 'EXPLANATION_IS_NOT_FACT_DIAGNOSIS_OR_OUTCOME';
    recommendation_source: 'RULE_BASED' | 'MODEL_GATEWAY_SCHEMA_VALIDATED_NOOP';
    model_gateway_status: 'NOOP_NOT_INVOKED' | 'SCHEMA_VALIDATED_NOOP' | 'HELD_FOR_REVIEW';
    agent_hint: 'OFFER_PLAN_PREVIEW_ONLY' | 'HUMAN_REVIEW_REQUIRED' | 'READ_ONLY';
  };
}
```

### 5.2 `PlanDraftPreviewProjection`

```ts
interface PlanDraftPreviewProjection {
  projection_version: string;
  family_id: string;
  onboarding_id: string;
  draft_id: string;
  state: 'DRAFT_READ' | 'FAMILY_REVIEW' | 'DECISION_PENDING' | 'REVIEW_REQUIRED' | 'HELD';
  source_report_snapshot_id: string | null;
  source_insight_version: string;
  focus: { dimension_id: string; label: string } | null;
  structure: {
    horizon_days: 90;
    checkpoints: Array<'3' | '12' | '36' | '90'>;
    stages: Array<{
      stage_id: 'SEE' | 'PARENT_FIRST' | 'CO_CREATE' | 'STABILIZE';
      label: string;
      week_range: string;
      intent: string;
      action_candidate: string;
    }>;
  };
  next_action: {
    text: string;
    boundary: 'ACTION_CANDIDATE_IS_NOT_GROWTH_TASK_OR_OUTCOME';
  } | null;
  consent_state: {
    required_purposes: Array<'PLAN_READ' | 'PLAN_DECISION' | 'CHILD_DATA'>;
    state: 'GRANTED' | 'REQUIRED' | 'REVOKED' | 'REVIEW_REQUIRED';
    policy_version: string;
  };
  provenance: {
    source_refs: string[];
    evidence_refs: string[];
    uncertainty: 'LOW' | 'MEDIUM' | 'HIGH';
    as_of: string;
  };
  model_gateway_status: 'NOOP_NOT_INVOKED' | 'SCHEMA_VALIDATED_NOOP' | 'HELD_FOR_REVIEW';
  next_allowed_action: 'READ_ONLY' | 'REQUEST_FAMILY_DECISION' | 'HUMAN_REVIEW_REQUIRED';
}
```

`3/12/36/90` 是计划结构 checkpoint，不是分数、排名、成功率或效果指标。Stages 是受控 draft 的可读结构；在本切片中不生成正式任务、不建立干预、不触发服务或外部通信。

## 6. Named Action contracts

### 6.1 `RefreshPlanDraftPreview`

输入至少包括 `family_id`、`onboarding_id`、`source_insight_version`、`idempotency_key`、`correlation_id` 和 `source`。服务端重新验证 family scope、guardian role、`PLAN_READ`/`CHILD_DATA` consent、onboarding provenance、report version 和 safety policy。动作最多生成或更新一个 controlled preview receipt，并返回 `PlanDraftPreviewProjection`；它不得创建 `GrowthPlan`、`GrowthJourney`、`GrowthTask`、`Intervention`、`ServiceCase`、`Booking`、`Order` 或 `Entitlement`。

### 6.2 `ProposeFamilyDecision`（本切片保留候选）

该动作只有在独立 Human/Architect decision 批准后才能实现。当前 UI-05 只能展示 `REQUEST_FAMILY_DECISION`，不能把查看、点击或页面确认写成正式 FamilyDecision。任何未来确认动作必须有独立 Contract、Consent、Human Gate、版本匹配、审计和幂等策略。

## 7. Security, Consent and Human Gate

所有路径使用 account-scoped bearer、family membership 和 object-level authorization。客户端提供的 `familyId`、`onboardingId`、`draftId`、subject 或 actor 只作为候选值，服务端必须从可信上下文重新解析。缺少家庭范围、Guardian 权限、儿童数据 Consent、来源版本或安全 provenance 时 fail closed，不返回跨家庭对象存在信息。

| Operation | Guardian in family scope | Child subject | Other family / missing consent |
|---|---:|---:|---:|
| Read report explanation | Allowed after `PLAN_READ` + object scope | Visibility policy required | `401`/`403`/`REVIEW_REQUIRED` |
| Read plan preview | Allowed after `PLAN_READ` + `CHILD_DATA` | Visibility policy required | `401`/`403`/`CONSENT_REQUIRED` |
| Refresh preview | Allowed with active consent and idempotency | Not directly | `FORBIDDEN`/`HUMAN_GATE_REQUIRED` |
| Propose family decision | Held in this slice | Not directly | `HUMAN_GATE_REQUIRED` |

真人服务、预约、支付、通知、直播、分享、日历/视频、社区公开发布均为 `EXTERNAL_EFFECTS_ALLOWED=NO`，必须经过之后的 Adapter、Consent 和 Human Gate；本切片不执行。

## 8. Error and idempotency model

```ts
interface ApiError {
  code:
    | 'UNAUTHENTICATED'
    | 'FAMILY_FORBIDDEN'
    | 'ONBOARDING_NOT_FOUND'
    | 'INSIGHT_NOT_FOUND'
    | 'PLAN_PREVIEW_NOT_FOUND'
    | 'CONSENT_REQUIRED'
    | 'HUMAN_GATE_REQUIRED'
    | 'REVIEW_REQUIRED'
    | 'PROVENANCE_INCOMPLETE'
    | 'VERSION_CONFLICT'
    | 'IDEMPOTENCY_KEY_REQUIRED'
    | 'IDEMPOTENCY_CONFLICT'
    | 'UNSUPPORTED_AI_OUTPUT'
    | 'VALIDATION_ERROR'
    | 'INTERNAL_ERROR';
  message: string;
  correlation_id: string | null;
  retryable: boolean;
  details?: Record<string, string>;
}
```

`RefreshPlanDraftPreview` requires a non-empty `Idempotency-Key`. The key is bound to the action name, family, onboarding, source version and request hash. Same key and same request replays the stored receipt; same key with a different request returns `IDEMPOTENCY_CONFLICT`. Every non-read action writes an audit event and an outbox event describing a controlled draft receipt, with `external_effect=false`.

## 9. AI-native boundary

`ReportExplanationProjection` and `PlanDraftPreviewProjection` expose structured fact boundary, perspective/evidence provenance, recommendation source and Model Gateway status. The gateway is `NOOP_NOT_INVOKED` or `SCHEMA_VALIDATED_NOOP` in this Dev slice. No raw model client is called from a controller or service, and no model output can directly write `GrowthPlan`, `GrowthTask`, `Outcome`, `Diagnosis` or `Intervention`.

> Fact metadata is server-derived context; Perspective is a bounded family statement; Hypothesis is uncertain interpretation; Recommendation is a controlled draft; Decision and Action require separately authorized Named Actions.

## 10. Tests and implementation handoff

Before merge, tests must cover projection provenance, family authorization, guardian visibility, missing/revoked consent, stale insight version, human-gate hold, idempotent refresh, audit/outbox receipt, no formal plan/task creation, no external effect, Model Gateway schema rejection, API contract serialization, Web loading/empty/review states, and authenticated browser navigation from UI-03 to UI-04 to UI-05.

If implementation is approved, the minimal handoff is to add or extend the family growth projection service/controller, shared contract types, a deterministic Dev fixture derived from existing onboarding/profile/evidence data, Web projection helpers, and focused integration/E2E/Web tests. No OpenAPI YAML/JSON is created in this slice.

```text
CONTRACT_APPROVED_FOR_DRAFTING=YES
IMPLEMENTATION_ALLOWED=YES__UI04_UI05_GUARDED_SLICE_ONLY
BUSINESS_CODE_MODIFIED=YES__UI04_UI05_GUARDED_SLICE_ONLY
FORMAL_PLAN_CREATION=NO
EXTERNAL_EFFECTS_ALLOWED=NO
PIXEL_DIFF_READY=NO
```
