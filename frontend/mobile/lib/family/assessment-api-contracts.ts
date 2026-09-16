/**
 * Mobile-side contracts for the first Python vertical slice (UI-02 / UI-03).
 *
 * These types mirror the FastAPI request/response models. Keeping them outside
 * screen components makes the API boundary reusable and prevents UI code from
 * inventing a second, subtly different response shape.
 */

export type AssessmentResponseType = "SINGLE_CHOICE" | "TEXT" | "BOOLEAN";

export interface AssessmentResponseDto {
  assessment_response_id: string;
  item_ref: string;
  response_type: AssessmentResponseType;
  response_value: string | boolean;
  revision: number;
  captured_at: string;
  visibility: "FAMILY_PRIVATE";
}

export interface AssessmentSessionDto {
  assessment_session_id: string;
  family_id: string;
  subject_person_id: string;
  tool_ref: string;
  tool_version: number;
  status: "IN_PROGRESS" | "SUBMITTED" | "EXITED";
  started_at: string;
  submitted_at: string | null;
  row_version: number;
  responses: AssessmentResponseDto[];
}

export interface Ui02AssessmentProjection {
  projection_version: "UI02_FAMILY_ASSESSMENT_V1";
  tenant_id: string;
  family_id: string;
  availability:
    | "AVAILABLE"
    | "CONSENT_REQUIRED"
    | "NO_SUBJECT"
    | "POLICY_BLOCKED";
  subjects: Array<{
    person_id: string;
    display_name: string;
    availability: "AVAILABLE" | "CONSENT_REQUIRED";
  }>;
  tool: {
    tool_ref: string;
    version_no: number;
    title: string;
    purpose: string;
    evidence_level: "E1";
    schema_ref: string;
    items: Array<{
      item_ref: string;
      response_type: AssessmentResponseType;
      required: boolean;
      options: string[] | null;
    }>;
    boundary: {
      truth_class: "FAMILY_PERSPECTIVE";
      not_a_score: true;
      not_a_diagnosis: true;
      no_eligibility_effect: true;
      withdrawable: true;
      training_use: false;
    };
  } | null;
  sessions: AssessmentSessionDto[];
  named_actions: {
    start: "START_ASSESSMENT";
    save_response: "SAVE_ASSESSMENT_RESPONSE";
    submit: "SUBMIT_ASSESSMENT";
  };
}

export interface AssessmentMutationReceipt {
  action: "START_ASSESSMENT" | "SAVE_ASSESSMENT_RESPONSE" | "SUBMIT_ASSESSMENT";
  replayed: boolean;
  session: AssessmentSessionDto;
  evidence_id: string | null;
  boundary: "FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS";
}

/**
 * The runtime UI-03 scorecard is an execution/review envelope, not a score.
 * The similarly named legacy OpenAPI hint still contains family scoring
 * fields; those fields are intentionally not represented in the mobile
 * contract and are rejected by the parser below.
 */
export interface Ui03ReviewEnvelope {
  generator: "MODEL_GATEWAY";
  agent_run_ref: string;
  provider_ref: string;
  model_ref: string;
  model_version: string;
  prompt_version: string;
  schema_version: string;
  context_snapshot_ref: string;
  input_refs: string[];
  draft_status: "DRAFT";
  human_task_ref: string;
  review_status: "REVIEW_REQUIRED";
}

export interface Ui03GrowthHypothesisProjection {
  projection_version: "UI03_GROWTH_HYPOTHESIS_V1";
  tenant_id: string;
  family_id: string;
  availability: "READY" | "NO_SUBMITTED_ASSESSMENT" | "POLICY_BLOCKED";
  ai_state: "NOT_INVOKED" | "MODEL_DRAFT_READY" | "MODEL_GATEWAY_BLOCKED";
  latest_assessment_session_id?: string | null;
  named_actions: {
    confirm: "CONFIRM_GROWTH_HYPOTHESIS";
    dismiss: "DISMISS_GROWTH_HYPOTHESIS";
  };
  hypothesis: null | {
    hypothesis_ref: string;
    subject_person_id: string;
    subject_display_name: string;
    focus_ref: string;
    need_type_ref: string;
    need_type_version: number;
    title: string;
    statement: string;
    required_capability_keys: string[];
    source_refs: {
      assessment_session_id: string;
      assessment_response_id: string;
      assessment_evidence_id: string;
      tool_ref: string;
      tool_version: number;
      assessment_submitted_at?: string | null;
    };
    limitations: string[];
    generator:
      | "DETERMINISTIC_CATALOG_POLICY_NOT_MODEL"
      | "FAMILY_EDUCATION_ASSESSMENT_MODEL_V0_1";
    model_draft_ref?: string | null;
    model_generator?:
      | "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC"
      | "FAMILY_EDUCATION_MODEL_RUNTIME_GATEWAY"
      | null;
    model_component_ref?: string | null;
    model_boundary_labels?: string[] | null;
    need_refs?: string[] | null;
    construct_refs?: string[] | null;
    action_candidate_refs?: string[] | null;
    fact_boundary: "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS";
    scorecard: Ui03ReviewEnvelope;
  };
}

export interface AssessmentHumanTaskDecisionBody {
  outcome: "ACCEPT" | "REJECT";
  reason?: string;
}

export interface AssessmentHumanTaskConfirmationBinding {
  subject_person_id: string;
  assessment_session_id: string;
  hypothesis_ref: string;
  scope_ref: string;
  signal_version: number;
  reviewed_draft_ref: string;
  draft_version: number;
  provenance_ref: string;
  human_gate_receipt_ref: string;
}

export interface AssessmentHumanTaskDecisionReceipt {
  task_id: string;
  decision_id: string;
  status: "DECIDED";
  outcome: "ACCEPT" | "REJECT";
  reason: string | null;
  decided_at: string;
  binding: AssessmentHumanTaskConfirmationBinding | null;
}

export interface ConfirmGrowthHypothesisBody extends Omit<
  AssessmentHumanTaskConfirmationBinding,
  "subject_person_id"
> {
  decision_type: "CONFIRM";
}

export interface GrowthHypothesisDecisionReceipt {
  action:
    | "CONFIRM_GROWTH_HYPOTHESIS"
    | "CALIBRATE_GROWTH_HYPOTHESIS"
    | "DISMISS_GROWTH_HYPOTHESIS";
  outcome: "INTENT_CREATED" | "FEEDBACK_RECORDED" | "NO_ACTION";
  hypothesis_ref: string;
  intent: {
    intent_id: string;
    need_type: string;
    status: "OPEN";
    required_capability_keys: string[];
    evidence_refs: string[];
    boundary: "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME";
  } | null;
  replayed: boolean;
  parent_note?: string | null;
}

export class AssessmentApiContractError extends Error {
  readonly code = "UI03_CONTRACT_BLOCKED";

  constructor(
    message: string,
    readonly payload: unknown,
  ) {
    super(message);
    this.name = "AssessmentApiContractError";
  }
}

export function parseUi03GrowthHypothesisProjection(
  payload: unknown,
  expectedFamilyId: string,
): Ui03GrowthHypothesisProjection {
  const projection = record(payload, "UI-03 projection");
  assertEqual(
    projection.projection_version,
    "UI03_GROWTH_HYPOTHESIS_V1",
    payload,
  );
  assertText(projection.tenant_id, "tenant_id", payload);
  assertEqual(projection.family_id, expectedFamilyId, payload);
  assertOneOf(
    projection.availability,
    ["READY", "NO_SUBMITTED_ASSESSMENT", "POLICY_BLOCKED"],
    payload,
  );
  assertOneOf(
    projection.ai_state,
    ["NOT_INVOKED", "MODEL_DRAFT_READY", "MODEL_GATEWAY_BLOCKED"],
    payload,
  );

  const actions = record(projection.named_actions, "named_actions");
  assertEqual(actions.confirm, "CONFIRM_GROWTH_HYPOTHESIS", payload);
  assertEqual(actions.dismiss, "DISMISS_GROWTH_HYPOTHESIS", payload);

  if (projection.availability !== "READY") {
    return projection as unknown as Ui03GrowthHypothesisProjection;
  }

  const hypothesis = record(projection.hypothesis, "hypothesis");
  for (const field of [
    "hypothesis_ref",
    "subject_person_id",
    "title",
    "statement",
  ] as const) {
    assertText(hypothesis[field], field, payload);
  }
  assertEqual(
    hypothesis.fact_boundary,
    "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS",
    payload,
  );
  const sourceRefs = record(hypothesis.source_refs, "source_refs");
  assertText(
    sourceRefs.assessment_session_id,
    "assessment_session_id",
    payload,
  );
  assertPositiveInteger(sourceRefs.tool_version, "tool_version", payload);
  assertStringArray(
    hypothesis.required_capability_keys,
    "required_capability_keys",
    payload,
  );
  assertStringArray(hypothesis.limitations, "limitations", payload);
  for (const optionalRefs of [
    "model_boundary_labels",
    "need_refs",
    "construct_refs",
    "action_candidate_refs",
  ] as const) {
    const value = hypothesis[optionalRefs];
    if (value !== undefined && value !== null) {
      assertStringArray(value, optionalRefs, payload);
    }
  }

  const scorecard = record(hypothesis.scorecard, "scorecard");
  for (const forbidden of [
    "overall_score",
    "overall_band",
    "dimensions",
    "peer_reference",
    "score_boundary",
  ]) {
    if (Object.prototype.hasOwnProperty.call(scorecard, forbidden)) {
      fail(`scorecard contains retired field ${forbidden}`, payload);
    }
  }
  assertEqual(scorecard.generator, "MODEL_GATEWAY", payload);
  assertEqual(scorecard.draft_status, "DRAFT", payload);
  assertEqual(scorecard.review_status, "REVIEW_REQUIRED", payload);
  assertStringArray(scorecard.input_refs, "scorecard.input_refs", payload);
  for (const field of [
    "agent_run_ref",
    "provider_ref",
    "model_ref",
    "model_version",
    "prompt_version",
    "schema_version",
    "context_snapshot_ref",
    "human_task_ref",
  ] as const) {
    assertText(scorecard[field], field, payload);
  }
  return projection as unknown as Ui03GrowthHypothesisProjection;
}

export function parseAssessmentHumanTaskDecisionReceipt(
  payload: unknown,
  expected: {
    familyId: string;
    tenantId: string;
    taskId: string;
    outcome: "ACCEPT" | "REJECT";
    hypothesisRef: string;
    assessmentSessionId: string;
    subjectPersonId: string;
    signalVersion: number;
  },
): AssessmentHumanTaskDecisionReceipt {
  const receipt = record(payload, "human-task decision receipt");
  assertEqual(receipt.task_id, expected.taskId, payload);
  assertText(receipt.decision_id, "decision_id", payload);
  assertEqual(receipt.status, "DECIDED", payload);
  assertEqual(receipt.outcome, expected.outcome, payload);
  assertText(receipt.decided_at, "decided_at", payload);
  if (receipt.reason !== null && typeof receipt.reason !== "string") {
    fail("human-task receipt reason must be string or null", payload);
  }

  if (expected.outcome === "REJECT") {
    if (receipt.binding !== null) {
      fail(
        "rejection receipt must not contain a confirmation binding",
        payload,
      );
    }
    return receipt as unknown as AssessmentHumanTaskDecisionReceipt;
  }

  const binding = record(receipt.binding, "confirmation binding");
  assertEqual(binding.subject_person_id, expected.subjectPersonId, payload);
  assertEqual(
    binding.assessment_session_id,
    expected.assessmentSessionId,
    payload,
  );
  assertEqual(binding.hypothesis_ref, expected.hypothesisRef, payload);
  assertEqual(
    binding.scope_ref,
    `family://${expected.tenantId}/${expected.familyId}/assessment`,
    payload,
  );
  assertEqual(binding.human_gate_receipt_ref, expected.taskId, payload);
  assertPositiveInteger(binding.signal_version, "signal_version", payload);
  if (binding.signal_version !== expected.signalVersion) {
    fail("signal_version does not match the reviewed projection", payload);
  }
  assertPositiveInteger(binding.draft_version, "draft_version", payload);
  assertText(binding.reviewed_draft_ref, "reviewed_draft_ref", payload);
  assertText(binding.provenance_ref, "provenance_ref", payload);
  return receipt as unknown as AssessmentHumanTaskDecisionReceipt;
}

export function parseConfirmedGrowthHypothesisReceipt(
  payload: unknown,
  expectedHypothesisRef: string,
): GrowthHypothesisDecisionReceipt {
  const receipt = record(payload, "growth-hypothesis decision receipt");
  assertEqual(receipt.action, "CONFIRM_GROWTH_HYPOTHESIS", payload);
  assertEqual(receipt.outcome, "INTENT_CREATED", payload);
  assertEqual(receipt.hypothesis_ref, expectedHypothesisRef, payload);
  if (typeof receipt.replayed !== "boolean")
    fail("replayed must be boolean", payload);
  const intent = record(receipt.intent, "growth intent");
  assertText(intent.intent_id, "intent_id", payload);
  assertText(intent.need_type, "need_type", payload);
  assertEqual(intent.status, "OPEN", payload);
  assertEqual(intent.boundary, "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME", payload);
  assertStringArray(
    intent.required_capability_keys,
    "intent.required_capability_keys",
    payload,
  );
  assertStringArray(intent.evidence_refs, "intent.evidence_refs", payload);
  return receipt as unknown as GrowthHypothesisDecisionReceipt;
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail(`${label} must be an object`, value);
  }
  return value as Record<string, unknown>;
}

function assertText(
  value: unknown,
  field: string,
  payload: unknown,
): asserts value is string {
  if (!isNonBlankText(value))
    fail(`${field} must be a non-empty string`, payload);
}

function assertPositiveInteger(
  value: unknown,
  field: string,
  payload: unknown,
): asserts value is number {
  if (!Number.isInteger(value) || (value as number) < 1) {
    fail(`${field} must be a positive integer`, payload);
  }
}

function assertStringArray(
  value: unknown,
  field: string,
  payload: unknown,
): asserts value is string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    fail(`${field} must be an array of strings`, payload);
  }
}

function assertEqual(value: unknown, expected: string, payload: unknown): void {
  if (value !== expected) fail(`expected ${expected}`, payload);
}

function assertOneOf(
  value: unknown,
  expected: readonly string[],
  payload: unknown,
): void {
  if (typeof value !== "string" || !expected.includes(value)) {
    fail(`expected one of ${expected.join(", ")}`, payload);
  }
}

function isNonBlankText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function fail(message: string, payload: unknown): never {
  throw new AssessmentApiContractError(message, payload);
}
