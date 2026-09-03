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
  availability: "AVAILABLE" | "CONSENT_REQUIRED" | "NO_SUBJECT" | "POLICY_BLOCKED";
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

export interface Ui03ScoreDimension {
  dimension_ref: string;
  label: string;
  score: number;
  peer_reference: number;
}

export interface Ui03Scorecard {
  generated_by: "FAMILI_PRINCIPAL_FAMILY_EDUCATION_MODEL";
  overall_score: number;
  overall_band: string;
  dimensions: Ui03ScoreDimension[];
  core_issue_tags: string[];
  recommendations: string[];
  score_boundary: "SUPPORT_ORIENTATION_SCORE_NOT_CHILD_DIAGNOSIS_OR_RANKING";
}

export interface Ui03EvidenceCoverage {
  source_response_count: number;
  interpreted_response_count: number;
  coverage_ratio: number;
  mapped_item_refs: string[];
  evidence_summaries: string[];
  uninterpreted_item_refs: string[];
  uncertainty_item_refs: string[];
  uncertainty_reasons: string[];
  support_direction_refs: string[];
  support_direction_labels: string[];
  next_questions?: string[];
}

export interface Ui03GrowthHypothesisProjection {
  projection_version: "UI03_GROWTH_HYPOTHESIS_V1";
  tenant_id: string;
  family_id: string;
  availability:
    | "READY"
    | "CONSENT_REQUIRED"
    | "NO_SUBMITTED_ASSESSMENT"
    | "POLICY_BLOCKED"
    | "CONSENT_WITHDRAWN"
    | "SUBMITTED"
    | "ANALYZING"
    | "ACKNOWLEDGED"
    | "DISMISSED"
    | "ANALYSIS_FAILED";
  ai_state:
    | "NOT_INVOKED"
    | "MODEL_DRAFT_READY"
    | "MODEL_GATEWAY_BLOCKED"
    | "READ_ONLY_PERSISTED";
  latest_assessment_session_id?: string | null;
  named_actions: {
    generate?: "GENERATE_GROWTH_HYPOTHESIS";
    confirm: "CONFIRM_GROWTH_HYPOTHESIS";
    dismiss?: "DISMISS_GROWTH_HYPOTHESIS";
  };
  hypothesis: null | {
    hypothesis_ref: string;
    subject_person_id: string;
    subject_display_name: string;
    focus_ref: string;
    title: string;
    statement: string;
    source_refs: {
      assessment_session_id: string;
      assessment_response_id: string;
      assessment_evidence_id: string;
      tool_ref: string;
      tool_version: number;
      assessment_submitted_at?: string | null;
    };
    limitations: string[];
    fact_boundary: "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS";
    safety_gate?: { required: boolean; reason_refs: string[]; mode: "HUMAN_REVIEW_REQUIRED" };
    evidence_coverage?: Ui03EvidenceCoverage;
    scorecard?: Ui03Scorecard;
  };
}

export interface GrowthHypothesisDecisionReceipt {
  action: "CONFIRM_GROWTH_HYPOTHESIS" | "DISMISS_GROWTH_HYPOTHESIS";
  outcome: "INTENT_CREATED" | "NO_ACTION";
  hypothesis_ref: string;
  intent: { intent_id: string } | null;
  replayed: boolean;
}
