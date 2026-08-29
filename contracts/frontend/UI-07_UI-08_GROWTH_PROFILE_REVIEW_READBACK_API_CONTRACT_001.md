# UI-07 / UI-08 Growth Profile and Review Readback API Contract 001

```text
PHASE=FORMAL_API_CONTRACT_AND_IMPLEMENTATION
UI_SCOPE=UI-07,UI-08
SLICE_NAME=Family Growth Profile and Private Review Readback
SOURCE_SLICES=UI-01,UI-02,UI-03,UI-04,UI-05,UI-06,UI-09
IMPLEMENTATION_BOUNDARY=FAMILY_SCOPED_READ_PROJECTION_ONLY
EXTERNAL_EFFECT=NONE
MODEL_GATEWAY_DIRECT_CALL=NO
ONTOLOGY_WRITE=NO
```

## 1. Purpose and Scope

UI-07 presents a **family-private growth profile readback**. It gives the guardian a traceable view of the family’s selected focus, current plan-preview context, and available navigation choices. UI-08 presents a **family-private action review readback**. It shows that an action or private check-in was recorded, while explicitly separating action records, perspectives, recommendations, and any possible future outcome evidence.

Neither projection is a diagnosis, a family score, a ranking, a child label, a verified education effect, or a decision to create a GrowthPlan, GrowthTask, intervention, booking, notification, or external service.

| UI | Route | Projection | State boundary | Primary upstream lineage |
|---|---|---|---|---|
| UI-07 | `core-mine` | `GrowthProfileReadbackProjection` | Read-only | UI-02 focus selection; UI-04/05 preview context; evidence-backed insight |
| UI-08 | `growth-report` | `FamilyReviewReadbackProjection` | Read-only | UI-09 check-in; UI-06 private draft; UI-04/05 plan-preview context; evidence-backed insight |

## 2. HTTP Contract

### 2.1 GET Growth Profile Readback

```text
GET /api/families/{familyId}/growth/onboardings/{onboardingId}/growth-profile-readback
```

The endpoint requires a valid family-scoped guardian context and the existing `ReadFamily` policy. It fails closed for missing authentication, invalid IDs, cross-family access, missing onboarding provenance, missing required profile evidence, or missing consent.

```ts
interface GrowthProfileReadbackProjection {
  projection_version: 'UI07_GROWTH_PROFILE_READBACK_V1';
  family_id: string;
  onboarding_id: string;
  visibility: 'FAMILY_PRIVATE';
  state: 'READY' | 'REVIEW_REQUIRED';
  focus: { dimension_id: string; label: string } | null;
  plan_context: { draft_id: string; state: string; horizon_days: 90 } | null;
  evidence_lineage: ReadonlyArray<{ evidence_id: string; source_version: 'GROWTH_INSIGHT_V1' }>;
  fact_boundary: 'FOCUS_AND_PLAN_CONTEXT_ARE_NOT_OUTCOME_OR_DIAGNOSIS';
  consent: { purpose: 'GROWTH_PROFILE_READ'; state: 'GRANTED'; policy_version: 'UI07_GROWTH_PROFILE_V1' };
  ai_ready: { model_gateway_status: 'NOOP_NOT_INVOKED'; recommendation_boundary: 'READBACK_ONLY' };
}
```

### 2.2 GET Family Review Readback

```text
GET /api/families/{familyId}/growth/onboardings/{onboardingId}/family-review-readback
```

The endpoint uses the same family and consent rules. It only summarizes already recorded named actions and private drafts; it never transforms a reflection or recorded action into a fact, diagnosis, or outcome.

```ts
interface FamilyReviewReadbackProjection {
  projection_version: 'UI08_FAMILY_REVIEW_READBACK_V1';
  family_id: string;
  onboarding_id: string;
  visibility: 'FAMILY_PRIVATE';
  state: 'ACTION_RECORDED' | 'NO_ACTION_RECORDED' | 'REVIEW_REQUIRED';
  recorded_actions: ReadonlyArray<{
    receipt_id: string;
    source_ui: 'UI-06' | 'UI-09';
    kind: 'PRIVATE_CHECKIN_DRAFT' | 'ACTION_RECEIPT';
    occurred_at: string;
  }>;
  reflection_prompt: string | null;
  next_hint: { text: string; source: 'RULE_BASED'; boundary: 'RECOMMENDATION_NOT_DECISION_OR_ACTION' } | null;
  evidence_lineage: ReadonlyArray<{ evidence_id: string; source_version: 'GROWTH_INSIGHT_V1' }>;
  fact_boundary: 'ACTION_RECORDED_NOT_OUTCOME_OR_CHILD_DIAGNOSIS';
  consent: { purpose: 'GROWTH_REVIEW_READ'; state: 'GRANTED'; policy_version: 'UI08_GROWTH_REVIEW_V1' };
  ai_ready: { model_gateway_status: 'NOOP_NOT_INVOKED'; reflection_boundary: 'PERSPECTIVE_NOT_FACT' };
}
```

## 3. Policy, Privacy, and Error Model

| Condition | HTTP status | Stable error code | Required behavior |
|---|---:|---|---|
| Missing/invalid account session | 401 | `actor_is_authenticated` | Do not reveal family data |
| Family or onboarding ID invalid | 400 | `invalid_schema` | Do not query/read projection |
| Actor lacks family membership | 403 | `family_scope_forbidden` | Fail closed |
| Onboarding/provenance unavailable | 404 | `growth_onboarding_not_found` | No fallback fabricated record |
| Consent/policy unavailable | 403 | `consent_required` | Do not return child-related readback |
| No prior action | 200 | n/a | Return `NO_ACTION_RECORDED`; never convert absence to failure |

There is no write endpoint in this slice. Any future parent feedback, correction request, data withdrawal, report acknowledgement, task creation, plan decision, notification, or human service handoff must use a separately admitted Named Action, idempotency policy, consent matrix, audit event, and Human Gate.

## 4. Readback Lineage and Separation

```text
UI-01/UI-09 Today action/check-in ─┐
UI-02 focus Perspective ───────────┼─> evidence-backed insight → UI-04 report → UI-05 plan preview
UI-06 private check-in draft ──────┘                                  │
                                                                       ├─> UI-07 GrowthProfileReadbackProjection
                                                                       └─> UI-08 FamilyReviewReadbackProjection
```

> `Fact` remains limited to authenticated, scoped records and structured evidence. `Perspective`, `Recommendation`, and `Action` retain separate fields and are never upgraded to an outcome conclusion by these projections.

## 5. Test Contract

The implementation must cover the following cases:

| Test layer | Required evidence |
|---|---|
| API E2E | Read profile/review after valid UI-01..UI-06 lineage; verify family ID, onboarding ID, visibility, evidence lineage, state boundary, and model gateway no-op |
| Negative API | Reject cross-family, unauthenticated, missing consent/provenance, invalid schema; return no child data |
| Readback | UI-02 selected focus reads on UI-07; UI-09 and UI-06 receipts read on UI-08 without outcome/diagnosis text |
| Web | Preserve static baselines; append formal panels after baseline; support loading, empty, error, and ready states |
| Browser | Authenticated Dev browser verifies UI-01/UI-09 action, UI-06 private draft, then UI-07/UI-08 private readback |
| Regression | Run API typecheck, Web typecheck, full API E2E, PostgreSQL integration, and full Web tests |

## 6. Explicit Non-goals

This contract does not authorize AI model calls, total scores, rankings, diagnostic conclusions, causal outcome claims, payments, refunds, entitlement changes, community publishing, personal-data export, notifications, external sharing, booking, or human-service execution.

```text
NO_FAMILY_RANKING=TRUE
NO_TOTAL_SCORE=TRUE
NO_CHILD_DIAGNOSIS=TRUE
NO_OUTCOME_CAUSALITY=TRUE
NO_EXTERNAL_EFFECT=TRUE
```
