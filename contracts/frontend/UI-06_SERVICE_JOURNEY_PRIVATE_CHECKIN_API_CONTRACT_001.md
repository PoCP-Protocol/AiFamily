# UI-06 服务旅程与私有打卡 API Contract 001

```text
PHASE=FORMAL_API_CONTRACT_AND_IMPLEMENTATION_HANDOFF
CONTRACT_PATH=contracts/frontend/UI-06_SERVICE_JOURNEY_PRIVATE_CHECKIN_API_CONTRACT_001.md
UI_SCOPE=UI-06
SLICE_NAME=Service Journey Projection and Private Check-in Draft
UPSTREAM_UI_LINEAGE=UI-01,UI-02,UI-03,UI-04,UI-05,UI-09
EXTERNAL_EFFECT=NO
MODEL_GATEWAY_DIRECT_CALL=NO
FORMAL_PLAN_OR_TASK_WRITE=NO
```

## 1. Contract Purpose and Decision Boundary

UI-06 continues the family-owned 90-day growth journey after the UI-04 report explanation and UI-05 plan preview. It provides an explicitly **private**, family-scoped, read-only service journey projection and allows a guardian to create a **private check-in draft**. Neither operation proves educational effectiveness, creates a formal task or plan, reserves a service, contacts a human provider, posts to a community, sends a notification, or creates an Outcome.

The authoritative user-facing distinction is: the journey projection reads a bounded snapshot; a check-in draft records an action candidate; a family decision or a real-world service effect requires a separate named action and Human Gate. `Fact`, `Perspective`, `Recommendation`, `Decision`, and `Action` remain separate.

| Type | UI-06 representation | Prohibited upgrade |
|---|---|---|
| Fact | family scope, issued projection version, route-safe service catalog fixture | Effectiveness, diagnosis, score, rank |
| Perspective | guardian-owned draft check-in text or selection | Child fact, Outcome evidence |
| Recommendation | deterministic next hint with provenance boundary | Decision or automatically assigned task |
| Action | `CreatePrivateCheckinDraft` command and receipt | Community publication, service booking, notification |
| Decision | not implemented in this slice | Auto-confirmed continue/pause/amend |

## 2. Upstream and Downstream Data Lineage

```text
UI-01/UI-09: FamilyTodayProjection + completed action receipt
  → UI-02: GrowthOnboarding + perspective provenance
  → UI-03/UI-04: GrowthInsight + ReportExplanationProjection
  → UI-05: PlanDraftPreviewProjection
  → UI-06: ServiceJourneyProjection + PrivateCheckinDraft
```

`ServiceJourneyProjection` may read the active onboarding ID, UI-05 plan draft identifier, the latest action receipt, service catalog fixture, and private process summary. It must expose provenance and visibility labels. It must not infer a child outcome from task completion, reflection, completion count, or service-card display.

## 3. Read Projection Contract

### 3.1 GET `/families/{familyId}/service-journey`

The route is family scoped and reads the current UI-06 companion surface. Its implementation must obtain the person ID from authenticated account context, not from the client payload or query string.

```ts
interface ServiceJourneyProjection {
  projection_version: 'UI06_SERVICE_JOURNEY_V1';
  family_id: string;
  onboarding_id: string;
  source_plan_draft_id: string | null;
  state: 'READY' | 'CONSENT_REQUIRED' | 'REVIEW_REQUIRED' | 'NOT_FOUND';
  visibility: 'FAMILY_PRIVATE';
  as_of: string;
  expires_at: string | null;
  service_cards: Array<{
    service_ref: string;
    label: string;
    state: 'READ_ONLY' | 'HOLD';
    boundary: 'CATALOG_FIXTURE_NOT_HUMAN_COMMITMENT';
  }>;
  process_summary: {
    label: string;
    completed_actions: number;
    boundary: 'PROCESS_PROJECTION_NOT_SCORE_OR_OUTCOME';
  };
  private_feed: Array<{
    entry_id: string;
    kind: 'ACTION_RECEIPT' | 'CHECKIN_DRAFT';
    visibility: 'FAMILY_PRIVATE';
    text: string;
    provenance_ref: string;
  }>;
  next_hint: {
    text: string;
    source: 'RULE_BASED';
    boundary: 'RECOMMENDATION_NOT_DECISION_OR_ACTION';
  };
  consent: {
    purpose: 'SERVICE_JOURNEY_READ' | 'CHILD_DATA';
    state: 'GRANTED' | 'REQUIRED' | 'REVOKED';
    policy_version: string;
  };
  ai_ready: {
    model_gateway_status: 'NOOP_NOT_INVOKED';
    evidence_boundary: 'PROCESS_NOT_OUTCOME_OR_DIAGNOSIS';
    agent_hint: 'OFFER_PRIVATE_CHECKIN_DRAFT_ONLY';
  };
}
```

The route is read-only. It returns no external provider contact details, live-video links, booking slots, community visibility controls, notification destinations, or arbitrary model output.

## 4. Named Action Contract

### 4.1 POST `/families/{familyId}/service-journey/checkin-drafts`

`CreatePrivateCheckinDraft` is a bounded named action. The guardian may request a private draft created from an allowlisted action selection. Free-text is not accepted in this first slice.

```ts
interface CreatePrivateCheckinDraftRequest {
  onboarding_id: string;
  action_ref: 'WEEKLY_ACTION_SEE' | 'WEEKLY_ACTION_ADJUST' | 'PAUSE_AND_RETURN';
  idempotency_key: string;
}

interface PrivateCheckinDraftReceipt {
  receipt_id: string;
  family_id: string;
  onboarding_id: string;
  state: 'CREATED' | 'REPLAYED';
  visibility: 'FAMILY_PRIVATE';
  draft_kind: 'PRIVATE_CHECKIN_DRAFT';
  external_effect: false;
  ontology_write: false;
  audit_event_ref: string;
  correlation_id: string;
  boundary: 'DRAFT_IS_NOT_TASK_OUTCOME_COMMUNITY_POST_OR_SERVICE_RECORD';
}
```

The service must validate family scope, guardian membership, active consent, active onboarding provenance, allowlisted `action_ref`, and idempotency. It must append an audit event and a no-external-effect receipt. Duplicate `(family_id, idempotency_key)` requests return the same receipt with `REPLAYED`.

### 4.2 Explicitly rejected effects

The following remain outside this Contract and must fail closed or remain `HOLD`: formal plan confirmation, task creation, child assessment, Outcome evidence, public posting, comment/like, booking, calendar update, payment, expert notification, live-stream enrollment, share/export, and model-generated free-text ontology writes.

## 5. Authorization, Consent, Human Gate, and Adapter Policy

| Requirement | GET service journey | POST private check-in draft |
|---|---|---|
| Family-scoped authenticated account | Required | Required |
| Active guardian membership | Required | Required |
| Child-data/service-journey consent | Required | Required |
| Onboarding/plan provenance | Required | Required |
| Idempotency key | N/A | Required |
| Audit event | Read trace optional | Required |
| Human Gate | `HOLD` for human service, live, booking | `HOLD` for decision confirmation or external service |
| Model Gateway | No direct call; `NOOP_NOT_INVOKED` | No direct call; no free text |
| External adapter | No invocation | No invocation |

Missing/revoked consent, ambiguous account context, wrong-family access, missing provenance, expired projection, unsupported action reference, and a request for any external effect must fail closed with a typed error.

## 6. Error Model

| HTTP | Code | Meaning |
|---:|---|---|
| 401 | `bearer_token_required` / `invalid_or_expired_session` | No valid account session |
| 403 | `account_has_no_active_membership_in_family` | Account is not an active family member |
| 403 | `consent_required_or_revoked` | Service journey/child-data purpose unavailable |
| 404 | `active_growth_onboarding_not_found` | Required journey provenance unavailable |
| 409 | `service_journey_review_required` | Projection cannot safely bind to plan/action lineage |
| 409 | `idempotency_key_reused_with_conflicting_payload` | Same key used for a different command |
| 422 | `unsupported_private_checkin_action_ref` | Action is outside allowlist |
| 423 | `external_effect_hold` | Booking, messaging, sharing, live, payment, or human-service effect requested |

## 7. UI Contract

The UI-06 static visual baseline remains intact. Dynamic content is appended after the baseline as a family-private service journey panel. The panel must show source/state/visibility boundaries without showing engineering terms to families. It supports `LOADING`, `READY`, `CONSENT_REQUIRED`, `REVIEW_REQUIRED`, `CHECKIN_DRAFT_CREATED`, and `ERROR` states.

The floating “＋打卡” control invokes only `CreatePrivateCheckinDraft`; it must show a family-private receipt and never present the receipt as an achievement, score, or proof of outcome. Service cards, live information, and community tabs are read-only/HOLD fixtures in this slice.

## 8. Test Matrix

| Layer | Required scenario |
|---|---|
| Unit | Service journey transforms allowed upstream lineage into a private projection without outcome/score fields |
| Integration | Fixture seed creates service journey provenance and repeatably cleans draft/audit rows |
| HTTP E2E | GET happy path, wrong-family denial, consent denial, missing onboarding, POST created, replayed idempotency, unsupported action |
| Web | UI-06 static baseline plus projection; draft receipt; no public/external action route |
| Browser | Authenticated family: UI-05 plan preview → UI-06 service journey → private check-in draft → receipt |
| Regression | UI-01/UI-09 check-in and UI-02..UI-05 report/plan chain stay green |

## 9. Non-goals

This Contract does not authorize Outcome conclusions, diagnosis, ranking, family scores, payment/refund, public community publication, real booking, service delivery, external notification, sharing/export, video/live participation, or direct AI model invocation.

```text
IMPLEMENTATION_BOUNDARY=READ_PROJECTION_PLUS_PRIVATE_DRAFT_ONLY
RUNTIME_SCREENSHOT_READY=NO
PIXEL_DIFF_READY=NO
```
