# UI-02 + UI-03 Core Growth / 90-day Plan API Contract 001

## 1. Contract status and implementation boundary

```text
PHASE=FORMAL_API_CONTRACT_AND_GUARDED_IMPLEMENTATION
CONTRACT_PATH=contracts/frontend/UI-02_UI-03_CORE_GROWTH_90_DAY_PLAN_API_CONTRACT_001.md
SOURCE_GATE_UI02=reports/m2/frontend/UI-02_PHASE_C_PRE_API_GATE_001.md
SOURCE_GATE_UI03=reports/m2/frontend/UI-03_PHASE_C_PRE_API_GATE_001.md
SOURCE_WIDE_RESEARCH=reports/m2/frontend/CONSUMER_UI_WIDE_RESEARCH_TO_DEVELOPMENT_SLICE_001.md
UI_SCOPE=UI-02,UI-03
SLICE_NAME=Core Growth Assessment Entry and 90-day Plan Explanation Draft
CONTRACT_APPROVED_FOR_DRAFTING=YES
IMPLEMENTATION_ALLOWED=YES__UI02_UI03_GUARDED_SLICE_ONLY
BUSINESS_CODE_MODIFIED=YES__UI02_UI03_GUARDED_SLICE_ONLY
OPENAPI_FILES_CREATED=0
EXTERNAL_EFFECTS_ALLOWED=NO
MODEL_GATEWAY_DIRECT_CALL=NO
```

本 Contract 是可执行的 Markdown 规范，不是 OpenAPI 文件。它只授权 UI-02/UI-03 的家庭成长结构化采集、解释投影和 90-day Plan controlled draft 预览。它不授权支付、预约、通知、分享、社区发布、真人服务、儿童诊断、Outcome 因果结论、家庭总分、排名或任何外部效果。

## 2. Slice intent and end-to-end boundary

```text
Family-scoped authenticated guardian
→ UI-02 reads or starts a versioned Growth Assessment / Onboarding
→ guardian records bounded Perspective or selects a synthetic dimension
→ server builds a versioned GrowthProfileDraft
→ UI-03 reads a provenance-bound ReportExplanationProjection
→ guardian may preview a 90-day PlanDraft
→ no Plan, Journey, Task, Outcome, Diagnosis or Intervention is created automatically
```

UI-02 的输入首先属于 **Perspective / Assessment Response / Controlled Draft**。UI-03 的内容属于 **Explanation / Hypothesis / Recommendation draft**，而不是 Fact、诊断或 Outcome。任何正式 GrowthPlan 必须经过独立的 FamilyDecision 与 Named Action；本 Slice 不执行该转换。

## 3. Object model and source-of-truth rules

| Object | Role | Source of truth | This slice may write | Prohibited shortcut |
|---|---|---|---|---|
| `Family` / `Person` / `Relationship` | 家庭与成员范围 | family/person/membership tables | No direct mutation from UI-02/UI-03 | Client-supplied relationship is never authorization. |
| `ConsentGrant` | Assessment/child-data policy gate | consent records + server policy | No implicit grant | Checkbox or stale projection cannot authorize. |
| `GrowthOnboarding` | Assessment journey envelope | onboarding aggregate | Start through existing Named Action only | Cannot be created by an AI explanation. |
| `Perspective` | Actor/subject bounded perspective | provenance-bound perspective record | Controlled, scoped perspective only | Perspective is not Fact or diagnosis. |
| `Evidence` | Source/version/time reference | evidence lineage | Only server-derived links | Free text cannot become evidence conclusion. |
| `GrowthProfileDraft` | Controlled interpretation draft | versioned profile draft | Build and read; confirmation remains gated | Cannot be treated as canonical GrowthProfile without approved action. |
| `GrowthPriority` | Human-confirmed practice focus | priority aggregate | Read confirmed state; confirm only through existing Named Action | Recommendation cannot silently become priority. |
| `ReportExplanationProjection` | UI-03 explanation read model | report/profile/evidence lineage | Read projection only | No free-text model write to ontology. |
| `PlanDraft` | 90-day plan preview | controlled draft/read projection | Preview only | Cannot create formal Plan, Task or Intervention. |
| `AuditEvent` / `OutboxEvent` | Immutable trace | audit/outbox ledger | Every Named Action must record | No silent state mutation. |
| `ModelGatewayRun` | AI boundary | gateway/no-op adapter | Synthetic/no-op metadata only | No direct model call or direct canonical write. |

## 4. API surface

The repository uses the existing Nest route suffixes without a global `/api` prefix. These paths are the formal semantic contract for this slice.

| Endpoint | UI | Class | Effect |
|---|---|---|---|
| `GET /families/{familyId}/growth/onboarding/active` | UI-02 | `GrowthAssessmentEntryProjection` active journey read | None; resumes an existing canonical onboarding |
| `GET /families/{familyId}/growth/onboardings/{onboardingId}/insight` | UI-03 | `GrowthInsightProjection` read | None |
| `GET /families/{familyId}/growth/onboardings/{onboardingId}/priority` | UI-03 / later UI-04 | `GrowthPriorityProjection` read | None |
| `POST /families/{familyId}/growth/onboarding` | UI-02 | Named Action `StartGrowthOnboarding` | Internal records/audit only |
| `POST /families/{familyId}/growth/onboardings/{onboardingId}/perspectives` | UI-02 | Named Action `RecordPerspective` | Internal evidence lineage only |
| `POST /families/{familyId}/growth/onboardings/{onboardingId}/profile-drafts` | UI-02 → UI-03 | Named Action `BuildGrowthProfileDrafts` | Controlled draft only |
| `POST /families/{familyId}/growth/profile-drafts/{draftId}/confirm` | UI-03 | Named Action `ConfirmGrowthProfileDraft` | Controlled profile transition; no diagnosis/outcome |
| `POST /families/{familyId}/growth/onboardings/{onboardingId}/priority/confirm` | Later handoff | Named Action `ConfirmGrowthPriority` | Out of UI-02/UI-03 implementation unless explicitly used as a read-only handoff |

When `StartGrowthOnboarding` returns `growth_onboarding_already_active`, UI-02 must call the active onboarding read projection and resume the returned canonical journey; it must not create a duplicate journey. UI-02/UI-03 frontends must not call lower-level persistence APIs or invent a second synthetic route when the real route exists. The existing DEV synthetic adapter may be used only as a clearly labelled fallback in tests; it must not mask a failed real API response as success.

## 5. Common command envelope and policy requirements

```ts
type UUID = string;
type ISO8601 = string;
type CorrelationId = string;
type IdempotencyKey = string;

type EntryState =
  | 'READY'
  | 'EMPTY'
  | 'CONSENT_REQUIRED'
  | 'REVIEW_REQUIRED'
  | 'FORBIDDEN'
  | 'STALE'
  | 'ERROR';

type DraftState =
  | 'NOT_STARTED'
  | 'IN_PROGRESS'
  | 'DRAFT_SAVED'
  | 'SUBMITTED'
  | 'REVIEW_REQUIRED'
  | 'EXPLANATION_READY'
  | 'VERSIONED';
```

Every command derives `family_id`, `actor_id`, role, membership and subject scope on the server. `familyId`, `onboardingId`, `draftId`, `subjectPersonId` and `authorPersonId` are revalidated against the authenticated family context. Every mutating command requires a non-empty idempotency key, correlation ID, policy evaluation, audit event and a stored response receipt.

The role/consent matrix is:

| Operation | Guardian with active family membership | Child subject | Other family / missing consent |
|---|---:|---:|---:|
| Read onboarding/insight projection | Allowed after object scope | Only if explicit subject visibility is granted | `401`/`403`, fail closed |
| Record guardian perspective | Allowed with `ASSESSMENT` and `CHILD_DATA` policy | Only through explicit facilitated flow | `CONSENT_REQUIRED` or `FORBIDDEN` |
| Build profile drafts | Allowed after valid onboarding provenance | Not directly | `REVIEW_REQUIRED`/`FORBIDDEN` |
| Confirm profile draft | Separate controlled action; guardian/Human Gate policy | Not directly | `FORBIDDEN`/`HUMAN_GATE_REQUIRED` |
| Read plan preview | Allowed if report/profile scope allows | Visibility policy required | `403` without disclosure |

## 6. Read projection contracts

### 6.1 `GrowthAssessmentEntryProjection` — UI-02

```ts
interface GrowthAssessmentEntryProjection {
  projection_version: string;
  family_id: UUID;
  onboarding_id: UUID | null;
  entry_state: EntryState;
  subject: {
    person_id: UUID;
    person_type: 'CHILD' | 'PARENT' | 'FAMILY_RELATIONSHIP';
    visibility: 'AUTHORIZED_FAMILY_SCOPE' | 'REVIEW_REQUIRED';
  } | null;
  assessment: {
    assessment_id: UUID | null;
    instrument_id: string;
    instrument_version: string;
    status: 'NOT_STARTED' | 'IN_PROGRESS' | 'DRAFT_SAVED' | 'SUBMITTED' | 'REVIEW_REQUIRED';
    response_count: number;
    required_response_count: number | null;
  } | null;
  available_dimensions: Array<{
    dimension_id: string;
    label: string;
    selection_state: 'AVAILABLE' | 'SELECTED' | 'HELD';
    source_kind: 'RULE_BASED_SYNTHETIC' | 'APPROVED_INSTRUMENT';
  }>;
  consent_state: {
    required_purposes: Array<'ASSESSMENT' | 'CHILD_DATA'>;
    state: 'GRANTED' | 'REQUIRED' | 'REVOKED' | 'REVIEW_REQUIRED';
    policy_version: string;
  };
  provenance: {
    source_refs: string[];
    evidence_refs: string[];
    perspective_refs: string[];
    instrument_version: string;
    as_of: ISO8601;
  };
  ai_ready: {
    fact_boundary: 'PERSPECTIVE_AND_RESPONSE_ARE_NOT_DIAGNOSIS';
    recommendation_source: 'NONE' | 'RULE_BASED_SYNTHETIC_DRAFT';
    model_gateway_status: 'NOOP_NOT_INVOKED' | 'SCHEMA_VALIDATED_NOOP';
    agent_hint: 'AWAIT_GUARDED_ASSESSMENT_INPUT' | 'READ_ONLY';
  };
}
```

The projection is server-derived. It must not expose raw child-sensitive content beyond the authorized scope, must not return a family total score or ranking, and must not fabricate a pending assessment when no valid onboarding exists.

### 6.2 `ReportExplanationProjection` — UI-03

```ts
interface ReportExplanationProjection {
  projection_version: string;
  family_id: UUID;
  onboarding_id: UUID;
  report_snapshot_id: UUID | null;
  entry_state: EntryState;
  state: 'REPORT_REQUESTED' | 'EXTRACTING' | 'REVIEW_REQUIRED' | 'EXPLANATION_READY' | 'FAMILY_VIEWED' | 'VERSIONED';
  title: string;
  explanation: {
    headline: string;
    summary: string;
    observations: Array<{ label: string; detail: string; kind: 'PERSPECTIVE' | 'EVIDENCE_BOUND_OBSERVATION' }>;
    hypotheses: Array<{ text: string; uncertainty: 'LOW' | 'MEDIUM' | 'HIGH' }>;
    recommendations: Array<{ text: string; source: 'RULE_BASED' | 'MODEL_GATEWAY_NOOP'; status: 'DRAFT' | 'HELD' }>;
  } | null;
  evidence_lineage: Array<{
    evidence_id: UUID | string;
    source_ref: string;
    source_version: string;
    provenance_kind: 'PERSPECTIVE' | 'ASSESSMENT_RESPONSE' | 'STRUCTURED_EVIDENCE';
  }>;
  visibility: 'AUTHORIZED_FAMILY_SCOPE' | 'REVIEW_REQUIRED';
  consent_state: {
    required_purposes: Array<'REPORT_READ' | 'ASSESSMENT_READ' | 'CHILD_DATA'>;
    state: 'GRANTED' | 'REQUIRED' | 'REVOKED' | 'REVIEW_REQUIRED';
    policy_version: string;
  };
  ai_ready: {
    evidence_boundary: 'EXPLANATION_IS_NOT_FACT_DIAGNOSIS_OR_OUTCOME';
    recommendation_source: 'RULE_BASED_SYNTHETIC' | 'MODEL_GATEWAY_SCHEMA_VALIDATED_NOOP';
    model_gateway_status: 'NOOP_NOT_INVOKED' | 'SCHEMA_VALIDATED_NOOP' | 'HELD_FOR_REVIEW';
    agent_hint: 'OFFER_PLAN_DRAFT_PREVIEW_ONLY' | 'HUMAN_REVIEW_REQUIRED' | 'READ_ONLY';
  };
}
```

The projection must reject or hold unsupported labels such as diagnosis, ranking, total score, same-age average, causal outcome or guaranteed effect. Missing provenance, version, consent or safety policy produces `REVIEW_REQUIRED`, not a successful explanation.

### 6.3 `PlanDraftPreviewProjection` — bounded UI-03 handoff

```ts
interface PlanDraftPreviewProjection {
  draft_id: UUID | string;
  state: 'DRAFT' | 'REVIEW_REQUIRED' | 'HELD';
  source_report_snapshot_id: UUID | string | null;
  focus: { dimension_id: string; label: string } | null;
  stages: Array<{ stage_id: string; label: string; intent: string; day_range: string }>;
  first_week_action: { text: string; boundary: 'ACTION_IS_NOT_OUTCOME' } | null;
  source_refs: string[];
  model_gateway_status: 'NOOP_NOT_INVOKED' | 'HELD_FOR_REVIEW';
  next_allowed_action: 'REQUEST_FAMILY_DECISION' | 'READ_ONLY' | 'HUMAN_REVIEW_REQUIRED';
}
```

A plan preview is not a confirmed 90-day plan. It cannot grant tasks, start an intervention, send a message, book a service or create an Outcome.

## 7. Named Action contracts

### 7.1 `StartGrowthOnboarding`

Input contains the authorized child/subject, structured safety signals and an idempotency key. The server validates family scope, guardian role, `ASSESSMENT`/`CHILD_DATA` consent, safety policy and duplicate active onboarding. It writes onboarding plus audit/outbox and returns an onboarding projection. High-risk signals return `REVIEW_REQUIRED` and do not proceed to explanation.

### 7.2 `RecordPerspective`

Input is a bounded subject, author, perspective type, capture mode, related dimensions, structured safety signals and controlled content. The server validates author role, subject relationship, consent, provenance and safety. The resulting record is a Perspective and may be linked to Evidence lineage; it is never stored or returned as Fact, diagnosis or Outcome.

### 7.3 `BuildGrowthProfileDrafts`

The command is idempotent by family/onboarding/instrument version. It reads approved responses, perspectives and evidence references, produces versioned controlled drafts, records source lineage and emits an audit/outbox receipt. It may return `REVIEW_REQUIRED` when evidence or policy is incomplete. It must not call a raw model or write canonical diagnosis/Outcome.

### 7.4 `ConfirmGrowthProfileDraft`

This action is a guarded handoff. It requires an authorized guardian, active consent, profile-draft version match, policy approval and audit. In UI-02/UI-03 implementation it may be exposed only as a controlled confirmation of the profile draft; it must not silently create a Plan, Task, Intervention, Outcome or external effect. A separate Plan Decision contract is required for formal plan creation.

## 8. Error model

```ts
interface ApiError {
  code:
    | 'UNAUTHENTICATED'
    | 'FAMILY_FORBIDDEN'
    | 'ONBOARDING_NOT_FOUND'
    | 'ASSESSMENT_NOT_FOUND'
    | 'CONSENT_REQUIRED'
    | 'HUMAN_GATE_REQUIRED'
    | 'REVIEW_REQUIRED'
    | 'PROVENANCE_INCOMPLETE'
    | 'VERSION_CONFLICT'
    | 'IDEMPOTENCY_KEY_REQUIRED'
    | 'IDEMPOTENCY_CONFLICT'
    | 'INVALID_PERSPECTIVE'
    | 'UNSUPPORTED_AI_OUTPUT'
    | 'PLAN_DRAFT_HELD'
    | 'VALIDATION_ERROR'
    | 'INTERNAL_ERROR';
  message: string;
  correlation_id: CorrelationId | null;
  retryable: boolean;
  details?: Record<string, string>;
}
```

Errors must be user-safe and must not disclose cross-family object existence. A missing provenance or failed Model Gateway schema validation is fail-closed. No UI may replace a real error with a successful synthetic card when `real-api` mode is active.

## 9. AI-native and safety contract

All AI-related fields are metadata or controlled drafts. `ModelGateway` is represented as `NOOP_NOT_INVOKED` or `SCHEMA_VALIDATED_NOOP` during this slice. No raw model client may be called from a controller, and no model output may write GrowthProfile, Need, Plan, Task, Outcome, Diagnosis or Intervention directly. Any future model call must pass through a gateway, schema validator, policy evaluator, provenance binder and—when required—a Human Gate.

The fact/perspective/recommendation/action boundary is explicit:

| Layer | UI-02/UI-03 meaning | May change canonical state? |
|---|---|---:|
| Fact | Server-derived family/person/version metadata only | No, projection only |
| Perspective | Guardian/child bounded self-report or observation | Only through `RecordPerspective`; not a fact claim |
| Hypothesis | Uncertain interpretation with source and uncertainty | No |
| Recommendation | Rule/model-gateway draft with provenance | No; requires later decision |
| Action | Named Action command such as start, record, build, confirm | Yes, only after policy/consent/audit/idempotency |

## 10. Testing and implementation handoff

The implementation must add or extend unit tests for DTO validation, provenance, safety route, consent and AI schema rejection. Integration tests must cover family scope, child-data consent, repeatable seed, idempotency replay/conflict, version conflict, missing evidence and Human Gate. API E2E must exercise the real route chain from onboarding through insight and profile draft. Web tests must verify loading, empty, consent-required, review-required, real projection, controlled draft and no-success-on-real-api-error states. Browser validation must cover UI-02 → UI-03 navigation, projection lineage, no diagnostic/ranking/total-score copy and desktop/mobile runtime screenshots; no pixel-diff claim is valid without normalized baseline comparison.

The next implementation files are limited to the existing Family controller/service, `DevCoreGrowthService` only where a clearly labelled no-op projection is needed, `apps/web/src/app.js`/`test-loop.js` route handlers, relevant `@family/contracts` types, fixed Dev fixture/seed and focused tests. No payment, community, booking, notification, share/export or direct model integration may be added.

```text
CONTRACT_SCOPE_CLOSED=UI-02,UI-03
IMPLEMENTATION_SCOPE_CLOSED=UI-02,UI-03_ONLY
EXTERNAL_EFFECT_ADAPTERS=NOOP_OR_FAIL_CLOSED
DIRECT_MODEL_CALL=NO
FAMILY_RANKING=FORBIDDEN
FAMILY_TOTAL_SCORE=FORBIDDEN
CHILD_DIAGNOSIS=FORBIDDEN
OUTCOME_CAUSALITY=FORBIDDEN
```
