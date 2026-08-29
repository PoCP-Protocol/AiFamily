# UI-01 + UI-09 Family Today Task Check-in API Contract 001

## 1. Contract status and approval boundary

```text
PHASE=FORMAL_API_CONTRACT_ONLY
CONTRACT_PATH=contracts/frontend/UI-01_UI-09_FAMILY_TODAY_TASK_CHECKIN_API_CONTRACT_001.md
SOURCE_ADMISSION=reports/m2/frontend/UI-01_UI-09_FIRST_REAL_SLICE_ADMISSION_AND_API_CONTRACT_001.md
SOURCE_ADMISSION_COMMIT=10d494c5702cd085697499687e5b4d8ceebf66d3
UI_SCOPE=UI-01,UI-09
SLICE_NAME=Family Today and Daily Task Check-in
CONTRACT_APPROVED_FOR_DRAFTING=YES
IMPLEMENTATION_ALLOWED=YES__UI01_UI09_GUARDED_SLICE_ONLY
BUSINESS_CODE_MODIFIED=YES__UI01_UI09_GUARDED_SLICE_ONLY
OPENAPI_FILES_CREATED=0
FILES_CREATED=1
FILES_UPDATED=1
```

> **Human/Architect decision record summary.** Subsequent Human/Architect approval authorizes the **UI-01/UI-09 guarded implementation only**: family-scoped Today projection, `CompleteGrowthAction` facade, synthetic/dev fixture, associated tests and visual verification. It does not authorize another UI, non-synthetic family data, payment, community, human service, notification/share/export, model invocation, diagnosis, Outcome creation, ranking or total score. D-01 through D-05 remain bounded by the activated implementation rules below: the code must use existing policy guards and synthetic fixture data, while any expansion of semantics or scope requires a separate decision.

This is a formal repository contract in Markdown, not a generated OpenAPI document. No `.yaml`, `.yml`, `.json` or `openapi/*` artifact is created by this contract. The scoped `IMPLEMENTATION_ALLOWED=YES__UI01_UI09_GUARDED_SLICE_ONLY` field authorizes only the implementation stated above; all other UI and high-risk capabilities remain outside this contract.

## 2. Decision record summary

| Decision ID | Contract drafting boundary approved | Implementation activation remains blocked until | Contract consequence |
|---|---|---|---|
| D-01 — baseline + route binding | UI-01 and UI-09 may be named as this contract’s scope; canonical baseline/viewport/route data are contract inputs. | Product/Visual owner freezes baseline version, viewport and state insert regions. | UI component acceptance remains a handoff item; no screenshot claim is permitted. |
| D-02 — task status copy/state semantics | Contract may distinguish machine `task_state` from user-facing display copy. | Domain/Business owner approves the final state-to-copy mapping. | `checked_in` is a proposal for UI copy; it is not an Outcome. |
| D-03 — Consent + role matrix | Contract contains family-scoped authentication, object authorization and purpose checks. | Privacy/child-safety owner approves actor/subject/purpose matrix for runtime. | Missing, revoked, stale or insufficient consent must fail closed. |
| D-04 — Reflection safety/escalation | Contract reserves a bounded optional reflection field and review/error model. | Safety owner approves length, content policy, Human Gate threshold and retention. | Reflection remains Perspective; it cannot create Evidence, Outcome, Plan or Profile. |
| D-05 — DEV synthetic seed policy | Contract permits synthetic fixture semantics for future test/e2e execution. | Test-data/Privacy owner approves fixture identifiers, reset and retention policy. | No production PII or live family may be used in implementation without separate approval. |

```text
D01_TO_D05_CONTRACT_DRAFTING_SCOPE=APPROVED
D01_TO_D05_IMPLEMENTATION_ACTIVATION=NOT_APPROVED
ARCHITECT_HUMAN_IMPLEMENTATION_APPROVAL=NOT_GRANTED
```

## 3. Scope and non-negotiable behavior

The contract binds one internal family workflow:

```text
Authenticated family-scoped guardian
→ UI-01 reads Today projection
→ UI-09 reads same task detail
→ guardian submits one idempotent check-in
→ service validates role/consent/policy/task state
→ transaction writes task state + audit + outbox + idempotency receipt
→ UI consumes returned readback projection
```

The UI must never treat the button press, a local optimistic update or free text as a confirmed state change. Only the API response after the above checks may alter the displayed task state. The check-in state is an operational record and does not prove child/family outcome, causal improvement or any rank/score.

## 4. API surface

The implementation uses the existing Nest controller paths with no configured global `/api` prefix in this repository. Deployments adding a global prefix must preserve the same semantic route suffixes; this contract records the source-tree paths exercised by test and web harnesses.

| Endpoint | UI use | Action class | External effect |
|---|---|---|---|
| `GET /families/{familyId}/today` | UI-01 task summary and UI-09 task detail bootstrap | `FamilyTodayProjection` read projection | None |
| `POST /families/{familyId}/tasks/{taskId}/check-in` | UI-09 submits a guardian task check-in | facade over Named Action: `CompleteGrowthAction` | None; internal audit/outbox only |
| `POST /families/{familyId}/growth/actions/{taskId}/complete` | Existing canonical action endpoint retained for existing consumers | Named Action: `CompleteGrowthAction` | None; internal audit/outbox only |

### 4.1 Common request requirements

| Requirement | GET | POST |
|---|---|---|
| Authentication | Required; actor derives from authenticated server context. | Required; actor derives from authenticated server context. |
| Family scope | `{familyId}` must be authorized for derived actor. | Same; `taskId` must resolve under that family only. |
| Object-level authorization | Required for family and task read. | Required for family, task and allowed completion action. |
| `X-Correlation-Id` | Optional; server may generate. | Required logically; server may generate if absent only when approved server convention permits. |
| `Idempotency-Key` | Not applicable. | Required, non-empty, unique for command/request hash pair. |
| `X-Source` | Optional observability metadata. | Candidate value `ui-01-ui-09-first-slice`; implementation must allowlist/derive rather than trust arbitrary effect metadata. |
| Content type | Not applicable. | `application/json`. |

## 5. Type contract

The following types are normative for the formal contract. Type syntax is descriptive TypeScript, not executable code.

### 5.1 Shared scalar definitions

```ts
type ISO8601 = string;
type UUID = string;
type ProjectionVersion = string;
type PolicyVersion = string;
type CorrelationId = string;
type IdempotencyKey = string;

type EntryState =
  | 'READY'
  | 'EMPTY'
  | 'CONSENT_REQUIRED'
  | 'REVIEW_REQUIRED'
  | 'FORBIDDEN'
  | 'ERROR'
  | 'STALE';

type TaskState =
  | 'NOT_STARTED'
  | 'IN_PROGRESS'
  | 'CHECKED_IN'
  | 'BLOCKED'
  | 'ARCHIVED';
```

`TaskState` is a UI projection taxonomy. Its mapping to existing persistence status is subject to D-02 implementation activation. It must not be mistaken for a new database enum or a promise to add one.

### 5.2 `FamilyTodayProjection`

```ts
interface FamilyTodayProjection {
  projection_version: ProjectionVersion;
  family_id: UUID;
  as_of: ISO8601;
  expires_at: ISO8601 | null;
  entry_state: EntryState;
  family_display: {
    display_name: string | null;
    actor_scope: 'AUTHORIZED_FAMILY_MANAGER';
  };
  consent_state: {
    state: 'COMMAND_POLICY_ENFORCED'; // GET does not claim a consent grant
    required_purposes: Array<'SERVICE' | 'ASSESSMENT' | 'GROWTH_TRACKING'>;
    policy_version: PolicyVersion;
  };
  today_task: TodayTaskProjection | null;
  provenance: {
    source_refs: string[];
    policy_version: PolicyVersion;
    as_of: ISO8601;
  };
  ai_ready: {
    evidence_boundary: 'ACTION_CHECKIN_IS_NOT_OUTCOME_OR_CAUSAL_EFFECT';
    recommendation_source: 'RULE_BASED_SYNTHETIC_NO_RECOMMENDATION';
    model_gateway_status: 'NOOP_NOT_INVOKED';
    agent_hint: 'READ_TODAY_AND_AWAIT_GUARDED_CHECKIN';
  };
}
```

**Source rule.** `family_id`, `actor_scope`, consent-state descriptor, `today_task`, provenance, AI-ready metadata and timestamps are server-derived. Clients must not submit or override any of these fields.

### 5.3 `TodayTaskProjection`

```ts
interface TodayTaskProjection {
  task_id: UUID;
  family_id: UUID;
  day_index: number;
  assignment_text: string;
  due_date: string; // date-only ISO-8601
  task_state: TaskState;
  persisted_status: string; // existing controlled status, not client-owned
  completion_status: string | null;
  completed_at: ISO8601 | null;
  reflection_boundary: 'REFLECTION_IS_RAW_MATERIAL_NOT_OUTCOME' | null;
  reflection_present: boolean;
  checkin_allowed: boolean;
  blocking_state: 'NONE' | 'CONSENT_REQUIRED' | 'REVIEW_REQUIRED' | 'FORBIDDEN' | 'STALE';
  task_version: null; // existing growth_actions has no version column in this slice
  as_of: ISO8601;
}
```

`assignment_text` is a task assignment display field; it is not an AI directive, diagnosis, prescription or outcome claim. `reflection_present` does not expose reflection contents on list/home surfaces by default.

### 5.4 `CompleteGrowthActionRequest`

```ts
interface CompleteGrowthActionRequest {
  completion_status: 'COMPLETED'; // activation requires D-02 mapping approval
  reflection?: string;            // activation requires D-04 safety/retention approval
  occurred_at: ISO8601;
}
```

Route and header values are part of the command envelope:

```ts
interface CompleteGrowthActionEnvelope {
  family_id: UUID;           // derived from route; server authorizes
  task_id: UUID;             // derived from route; server resolves within family
  actor_id: UUID;            // derived from authentication; never request body
  idempotency_key: IdempotencyKey;
  correlation_id: CorrelationId;
  source: 'ui-01-ui-09-first-slice';
  body: CompleteGrowthActionRequest;
}
```

### 5.5 `TaskCheckinResultProjection`

```ts
interface TaskCheckinResultProjection {
  result_state:
    | 'SUCCESS'
    | 'REPLAYED'
    | 'CONFLICT'
    | 'CONSENT_REQUIRED'
    | 'REVIEW_REQUIRED'
    | 'FORBIDDEN'
    | 'VALIDATION_ERROR'
    | 'ERROR';
  action: TodayTaskProjection | null;
  reflection_boundary: 'REFLECTION_IS_RAW_MATERIAL_NOT_OUTCOME' | null;
  correlation_id: CorrelationId;
  idempotency_key_ref: string;
  audit_status: 'RECORDED' | 'NOT_RECORDED';
  next_hint: {
    source: 'RULE_BASED_SYNTHETIC_NOOP';
    text_key: 'REFRESH_TODAY_AFTER_CHECKIN';
    model_gateway_status: 'NOOP_NOT_INVOKED';
  };
}
```

A successful response must use `audit_status='RECORDED'`. The API must fail closed rather than return `SUCCESS` if its required audit write fails. `REPLAYED` returns the stored prior command result after idempotency hash match; it must not execute a second state transition.

### 5.6 `ApiError`

```ts
interface ApiError {
  code:
    | 'UNAUTHENTICATED'
    | 'FAMILY_FORBIDDEN'
    | 'TASK_NOT_FOUND'
    | 'TASK_ARCHIVED'
    | 'TASK_ALREADY_CHECKED_IN'
    | 'CONSENT_REQUIRED'
    | 'REVIEW_REQUIRED'
    | 'HUMAN_GATE_REQUIRED'
    | 'IDEMPOTENCY_KEY_REQUIRED'
    | 'IDEMPOTENCY_CONFLICT'
    | 'VALIDATION_ERROR'
    | 'STALE_PROJECTION'
    | 'INTERNAL_ERROR';
  message: string; // user-safe allowlisted text, no sensitive data
  correlation_id: CorrelationId | null;
  retryable: boolean;
  details?: Record<string, string>; // only allowlisted non-sensitive keys
}
```

## 6. Endpoint contract

### 6.1 Read today projection

```http
GET /families/{familyId}/today
```

| Condition | HTTP status | Body | UI obligation |
|---|---:|---|---|
| Authorized family with pending task | `200` | `FamilyTodayProjection` with `entry_state='READY'` and non-null task | UI-01 renders summary; UI-09 renders task detail. |
| Authorized family with no pending task | `200` | `FamilyTodayProjection` with `entry_state='EMPTY'`, `today_task=null` | Render canonical empty state; no fabricated task. |
| Valid actor with missing/revoked command consent | `200` read projection; `consent_state='COMMAND_POLICY_ENFORCED'` | `FamilyTodayProjection` does not claim a grant. | Preserve visual frame; command revalidates Consent and fails closed before write. |
| Unauthorized / cross-family | `401` or `403` | `ApiError` | Do not disclose task/family existence beyond approved safe code. |
| Invalid/missing family/task data | `404` | `ApiError` | Render safe non-sensitive error/empty route as approved. |
| Projection stale/internal fault | `409` or `500` | `ApiError` | Do not fall back to static success data. |

### 6.2 Submit task check-in

```http
POST /families/{familyId}/tasks/{taskId}/check-in
Idempotency-Key: 4d21b42f-5c9a-42d4-8e49-7bda4c8eece4
X-Correlation-Id: 9a15ec90-446f-4462-aea9-27af42a01f4a
X-Source: ui-01-ui-09-first-slice
Content-Type: application/json

{
  "completion_status": "COMPLETED",
  "reflection": "Optional bounded perspective pending D-04 approval.",
  "occurred_at": "2026-08-18T10:00:00.000Z"
}
```

| Validation stage | Required behavior | Failure response |
|---|---|---|
| Authentication and route scope | Derive actor from server auth; verify actor belongs to `{familyId}`. | `UNAUTHENTICATED` / `FAMILY_FORBIDDEN`. |
| Object-level authorization | Resolve `{taskId}` under `{familyId}` and active task ownership. | `TASK_NOT_FOUND` without cross-family detail. |
| Role matrix | Enforce D-03 activated guardian role policy; no client role assertion. | `FAMILY_FORBIDDEN` / `HUMAN_GATE_REQUIRED`. |
| Consent | Verify required grants have permitted subject/purpose/status/version. Revocation immediately blocks action. | `CONSENT_REQUIRED` / `REVIEW_REQUIRED`. |
| State machine | Task must be actionable under approved mapping. | `TASK_ARCHIVED` / `TASK_ALREADY_CHECKED_IN` / `STALE_PROJECTION`. |
| Reflection safety | Enforce D-04 approved length/content/escalation rule before persistence. | `VALIDATION_ERROR` / `REVIEW_REQUIRED` / `HUMAN_GATE_REQUIRED`. |
| Idempotency | Lock action + key + request hash. Same hash replays stored receipt; different hash conflicts. | `IDEMPOTENCY_KEY_REQUIRED` / `IDEMPOTENCY_CONFLICT`. |
| Transaction/audit/outbox | Persist state/readback, audit and internal outbox atomically; store response receipt. | `INTERNAL_ERROR`; no success state. |

**Success response:** `201 TaskCheckinResultProjection` with `result_state='SUCCESS'` or `result_state='REPLAYED'`. The `action` field is the authoritative UI readback. No response may include an Outcome, diagnosis, score, ranking, provider recommendation, payment state or external-effect result.

## 7. State machine

The following is the contract’s UI state machine. It is a proposal for mapping existing task status to UI behavior; it does not alter persistence schemas in this contract-only phase.

```text
NOT_STARTED --Start/visible activity (future, out of scope)--> IN_PROGRESS
NOT_STARTED --approved CompleteGrowthAction--> CHECKED_IN
IN_PROGRESS --approved CompleteGrowthAction--> CHECKED_IN
NOT_STARTED/IN_PROGRESS --policy/consent/risk issue--> BLOCKED
BLOCKED --approved policy/consent resolution--> prior actionable state
CHECKED_IN --read only--> CHECKED_IN
NOT_STARTED/IN_PROGRESS/BLOCKED --source plan/task closure--> ARCHIVED
ARCHIVED --no check-in action--> ARCHIVED
```

| State | Projection meaning | Allowed operation in this slice | Proposal / activation note |
|---|---|---|---|
| `NOT_STARTED` | Existing task is pending and has no recorded check-in. | Read; `CompleteGrowthAction` candidate. | Existing storage mapping requires D-02 activation review. |
| `IN_PROGRESS` | A future approved task state may indicate engagement. | Read only in this slice. | `StartTask` is out of scope. |
| `CHECKED_IN` | A permitted check-in was recorded and audited. | Read only; duplicate uses idempotency replay/conflict. | UI copy must not assert growth/Outcome. |
| `BLOCKED` | Consent, role, safety or review policy prevents action/read detail. | Read safe blocked state only. | Resolution action is out of scope. |
| `ARCHIVED` | Task is no longer actionable. | Read safe historical indicator only if authorized. | Archive source/mapping requires D-02 review. |

## 8. Security, privacy and policy contract

| Control | Contract requirement |
|---|---|
| Family-scoped authentication | API derives actor from authenticated context; `{familyId}` is not sufficient authority. |
| Object-level authorization | Every task lookup binds both `family_id` and `task_id`; no raw task lookup may bypass family scope. This addresses object-level access risk. [3] |
| Role matrix | Contract minimum for activation is server-derived ACTIVE `OWNER`/`GUARDIAN` write permission, subject to D-03 sign-off. Child/coach write capability is excluded. |
| Consent matrix | Candidate required purposes are `SERVICE`, `ASSESSMENT`, `GROWTH_TRACKING`, each `GRANTED`, unrevoked and in applicable subject scope; D-03 must confirm the final purpose set before implementation. |
| Fail closed | Missing/expired/revoked/ambiguous consent, membership, task ownership, audit success, policy result or action state blocks read/write as applicable. |
| Reflection data | Reflection is Perspective-only. D-04 approval controls data minimization, max length, sensitive-content handling, retention and Human Gate escalation. |
| Audit/outbox | Successful action requires correlation ID, idempotency key, actor, action name, resource reference, policy result and internal outbox event. The outbox is not a notification. |
| Model/adapter boundary | No Model Gateway call, AI decision or external adapter call is permitted by either endpoint. |
| Privacy communication | UI uses safe allowlisted error messages and does not reveal child/task/family detail when scope check fails. |

## 9. No external effect guarantee

```text
PAYMENT=NO
REFUND=NO
ORDER_OR_ENTITLEMENT_CHANGE=NO
REAL_BOOKING_OR_CALENDAR=NO
NOTIFICATION_EMAIL_SMS_PUSH=NO
EXTERNAL_SHARE_OR_EXPORT=NO
COMMUNITY_PUBLICATION=NO
HUMAN_SERVICE_CONTACT=NO
MODEL_CALL=NO
OUTCOME_OR_PROFILE_WRITE=NO
```

The only allowed downstream record after a successful command is an internal audit/outbox event within the same protected transaction. The contract does not authorize any outbox consumer to issue an external effect.

## 10. Test contract

| Test class | Contract proof | Required negative cases |
|---|---|---|
| Unit | projection mapping, state copy mapping, request validator, reflection boundary, error mapper. | Outcome/profile/plan mutation attempts; client actor/family overrides. |
| Policy unit | family membership, owner/guardian roles, consent purpose/version/revocation, safety escalation. | child/coach write when unapproved; missing/revoked consent; unsafe reflection. |
| API contract | GET/POST schemas, headers, safe error envelope, `null`/empty semantics, response projection fields. | malformed `occurred_at`, unsupported completion state, missing idempotency key, unexpected properties. |
| Integration / e2e | isolated synthetic fixture reads pending task; check-in writes state/audit/outbox; same idempotency key replays. | cross-family access, same key different payload, already completed task, transaction/audit failure, no external call. |
| Web/page-object | UI-01 summary → UI-09 navigation; loading/empty/blocked/error; UI-09 submit/readback/replay. | no local success before response; no success fallback after error. |
| Playwright screenshot diff | capture runtime UI-01/UI-09 at approved baseline viewport, compare against frozen baseline and register deviations. | static shell, raw baseline, PPT/report image or fixture screenshot cannot be treated as runtime evidence. |

```text
RUNTIME_SCREENSHOT_READY=PENDING_DEV_SERVER_AND_SYNTHETIC_AUTH_FIXTURE
PIXEL_DIFF_READY=NO
FE_BE_CONSISTENCY=UNIT_AND_WEB_CONTRACT_TESTED__REAL_POSTGRES_E2E_PENDING_ENVIRONMENT
```

## 11. Implementation handoff checklist — not executed in this phase

After a separate guarded implementation approval, the implementation owner must review and alter only the minimum files confirmed by actual architecture inspection. The following list is a candidate checklist, not an authorization to edit now.

| Area | Candidate files/locations to inspect or modify after approval | Required outcome |
|---|---|---|
| API controller | `apps/api/src/modules/family/family.controller.ts` | Bind approved projection and command response/error mapping without changing route semantics accidentally. |
| API service/policy | `apps/api/src/modules/family/growth-action.service.ts`; family permission, consent, reflection-safety and normal-safety policies | Apply D-02/D-03/D-04 activated rules and fail-closed behavior. |
| Contracts | `packages/contracts/src/*` relevant growth action types | Align DTOs, error envelope and fixture contract; no field drift. |
| Database / seed | `database/migrations/*` and test seed tooling only if gap is proven | Prefer no migration; otherwise add only approved projection/draft/fixture schema with rollback/check. |
| Web | `apps/web/src/test-loop.js` or admitted replacement route/component and page-object tests | Replace only the approved UI-01/UI-09 state surface; preserve visual baseline. |
| Tests | API unit/integration/e2e specs; web page-object tests; Playwright capture plan | Prove policy, idempotency, audit/outbox and baseline diff. |

Before editing any of those files, the implementation task must state: `IMPLEMENTATION_APPROVAL_REFERENCE`, `D01_TO_D05_ACTIVATION_DECISIONS`, `SYNTHETIC_SEED_APPROVAL`, `VISUAL_BASELINE_FREEZE`, `NO_EXTERNAL_EFFECT_TEST_PLAN`, and `ROLLBACK_SCOPE`.

## 12. Non-goals

This formal contract excludes AI or model calls, Outcome creation, diagnosis, family ranking, family total score, peer comparison, payment, refund, order or entitlement change, community publishing/interactions, media upload, real booking, human service contact, external notifications, sharing, exporting, downloading and external system synchronization. It also excludes creating, amending, pausing or archiving tasks/plans; it only reads one controlled task and submits the approved check-in command after policy validation.

## 13. Implementation verdict

```text
CONTRACT_APPROVED_FOR_DRAFTING=YES
IMPLEMENTATION_ALLOWED=YES__UI01_UI09_GUARDED_SLICE_ONLY
BUSINESS_CODE_MODIFIED=YES__UI01_UI09_GUARDED_SLICE_ONLY
OPENAPI_FILES_CREATED=0
IMPLEMENTATION_SCOPE=FamilyTodayProjection_to_CompleteGrowthAction_to_TaskCheckinResultProjection
NEXT_APPROVAL_REQUIRED=NONE_FOR_CURRENT_GUARDED_SLICE__SEPARATE_APPROVAL_REQUIRED_FOR_ANY_OTHER_UI_OR_HIGH_RISK_EFFECT
```

## 14. References

[1] `reports/m2/frontend/UI-01_UI-09_FIRST_REAL_SLICE_ADMISSION_AND_API_CONTRACT_001.md` (candidate admission, commit `10d494c5702cd085697499687e5b4d8ceebf66d3`).

[2] `apps/api/src/modules/family/family.controller.ts`, lines 408–435; `apps/api/src/modules/family/growth-action.service.ts` (existing route/action facts only, not implementation approval).

[3] [OWASP API Security Project, API1:2023 / API3:2023](https://owasp.org/www-project-api-security/) (object- and property-level authorization context).

[4] `reports/m2/frontend/PHASE_D_API_CONTRACT_ENTRY_CRITERIA_AND_BLOCKERS_001.md` (contract entry criteria and implementation hold).


## 15. Runtime visual verification — guarded implementation evidence

| Surface | Runtime URL/state | Evidence path | Result | Boundary interpretation |
|---|---|---|---|---|
| UI-01 Home baseline | `/?product=test-loop&page=home` | `/home/ubuntu/screenshots/localhost_2026-08-18_15-30-04_6621.webp` | Opened successfully with supplied reference canvas and Today-task hotspot. | This is a runtime shell capture, not proof of a successful check-in. |
| UI-09 Task baseline | `/?product=test-loop&page=growth-daily-task` | `/home/ubuntu/screenshots/localhost_2026-08-18_15-30-14_2978.webp` | Opened successfully with supplied task canvas and guarded completion CTA. | The visual master remains intact when synthetic API mode is disabled. |
| UI-09 synthetic-api failure | `/?product=test-loop&page=growth-daily-task&firstSliceApi=synthetic-api` with no reachable API | `/home/ubuntu/screenshots/localhost_2026-08-18_15-30-26_8783.webp` | Fail-closed panel states that no local substitute task is shown. | This proves the UI does not fabricate read or command success when the API is unavailable. |

```text
RUNTIME_SHELL_UI01=OPENED
RUNTIME_SHELL_UI09=OPENED
SYNTHETIC_API_FAIL_CLOSED=VERIFIED
SUCCESSFUL_API_BROWSER_SCREENSHOT=BLOCKED_BY_REAL_POSTGRES_TEST_AUTH_ENVIRONMENT
PIXEL_DIFF=NOT_CLAIMED__RUNTIME_VIEWPORT_AND_BASELINE_DIMENSIONS_NOT_YET_NORMALIZED
```

The image files above remain untracked validation evidence and are not part of this commit. Browser-level successful API check-in requires a disposable authenticated synthetic family against the real PostgreSQL E2E environment. The API unit/controller tests and Web contract test currently provide the positive path, while the browser proves the no-fallback runtime behavior.
