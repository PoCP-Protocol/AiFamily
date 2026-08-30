/* 当前契约适配层：只声明 family_api 已挂载的 Assessment 与 Service 路由；AI 输出只允许是建议或草案。 */
export type MomentKind = "TEXT" | "AUDIO" | "IMAGE" | "VIDEO";
export type AssessmentResponseType = "SINGLE_CHOICE" | "TEXT" | "BOOLEAN";
export type HypothesisDecision = "CONFIRM" | "DISMISS";

export interface FamilyMomentDraft {
  kind: MomentKind;
  text?: string;
  localPreviewUrl?: string;
  durationSeconds?: number;
  status: "LOCAL_DRAFT" | "READY_FOR_UPLOAD";
}

export interface ApiSession {
  token: string;
  correlationId?: string;
}

export interface MutationOptions extends ApiSession {
  idempotencyKey: string;
  source?: string;
}

export interface AssessmentToolBoundary {
  truth_class: "FAMILY_PERSPECTIVE";
  not_a_score: true;
  not_a_diagnosis: true;
  no_eligibility_effect: true;
  withdrawable: true;
  training_use: false;
}

export interface AssessmentToolItem {
  item_ref: string;
  response_type: AssessmentResponseType;
  required: boolean;
  options: string[] | null;
}

export interface AssessmentSubject {
  person_id: string;
  display_name: string;
  availability: "AVAILABLE" | "CONSENT_REQUIRED";
}

export interface AssessmentResponse {
  assessment_response_id: string;
  item_ref: string;
  response_type: AssessmentResponseType;
  response_value: string | boolean;
  revision: number;
  captured_at: string;
  visibility: "FAMILY_PRIVATE";
}

export interface AssessmentSession {
  assessment_session_id: string;
  family_id: string;
  subject_person_id: string;
  tool_ref: string;
  tool_version: number;
  status: "IN_PROGRESS" | "SUBMITTED" | "EXITED";
  started_at: string;
  submitted_at: string | null;
  row_version: number;
  responses: AssessmentResponse[];
}

export interface Ui02AssessmentProjection {
  projection_version: "UI02_FAMILY_ASSESSMENT_V1";
  tenant_id: string;
  family_id: string;
  availability: string;
  subjects: AssessmentSubject[];
  tool: null | {
    tool_ref: string;
    version_no: number;
    title: string;
    purpose: string;
    evidence_level: "E1";
    schema_ref: string;
    items: AssessmentToolItem[];
    boundary: AssessmentToolBoundary;
  };
  sessions: AssessmentSession[];
  named_actions: {
    start: "START_ASSESSMENT";
    save_response: "SAVE_ASSESSMENT_RESPONSE";
    submit: "SUBMIT_ASSESSMENT";
  };
}

export interface AssessmentMutationReceipt {
  action: "START_ASSESSMENT" | "SAVE_ASSESSMENT_RESPONSE" | "SUBMIT_ASSESSMENT";
  replayed: boolean;
  session: AssessmentSession;
  evidence_id: string | null;
  boundary: "FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS";
}

export interface GrowthHypothesisProjection {
  projection_version: "UI03_GROWTH_HYPOTHESIS_V1";
  tenant_id: string;
  family_id: string;
  availability: "READY" | "NO_SUBMITTED_ASSESSMENT" | "POLICY_BLOCKED";
  hypothesis: null | {
    hypothesis_ref: string;
    subject_person_id: string;
    subject_display_name: string;
    focus_ref: string;
    need_type_ref: string;
    title: string;
    statement: string;
    required_capability_keys: string[];
    limitations: string[];
    fact_boundary: "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS";
    generator: "DETERMINISTIC_CATALOG_POLICY_NOT_MODEL" | "FAMILY_EDUCATION_ASSESSMENT_MODEL_V0_1";
  };
  named_actions: {
    confirm: "CONFIRM_GROWTH_HYPOTHESIS";
    dismiss: "DISMISS_GROWTH_HYPOTHESIS";
  };
  ai_state: "NOT_INVOKED" | "MODEL_DRAFT_READY" | "MODEL_GATEWAY_BLOCKED";
}

export interface GrowthHypothesisDecisionReceipt {
  action: "CONFIRM_GROWTH_HYPOTHESIS" | "DISMISS_GROWTH_HYPOTHESIS";
  outcome: "INTENT_CREATED" | "NO_ACTION";
  hypothesis_ref: string;
  intent: null | {
    intent_id: string;
    need_type: string;
    status: "OPEN";
    required_capability_keys: string[];
    evidence_refs: string[];
    boundary: "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME";
  };
  replayed: boolean;
}

export interface SubmitBookingBody {
  service_offering_id: string;
  availability_slot_id: string;
  booking_ref: string;
  source_page_id: string;
  subject_person_id: string;
  consent_ref: string;
}

export class FamilyApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`FAMILY_API_${status}:${detail}`);
  }
}

class FamilyApiClient {
  readonly baseUrl = (import.meta.env.VITE_FAMILY_API_BASE_URL ?? "").replace(/\/+$/, "");
  readonly configured = this.baseUrl.length > 0;
  readonly devServiceContractEnabled = import.meta.env.VITE_ENABLE_DEV_SERVICE_CONTRACT === "true";

  private async request<T>(path: string, session: ApiSession, options: RequestInit = {}): Promise<T> {
    if (!this.configured) throw new FamilyApiError(0, "FAMILY_API_NOT_CONFIGURED");
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      credentials: "omit",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.token}`,
        ...(session.correlationId ? { "X-Correlation-Id": session.correlationId } : {}),
        ...(options.headers ?? {}),
      },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({ detail: "unknown_error" }));
      throw new FamilyApiError(response.status, String(payload.detail ?? "unknown_error"));
    }
    return response.json() as Promise<T>;
  }

  private mutationHeaders(options: MutationOptions) {
    return {
      "Idempotency-Key": options.idempotencyKey,
      ...(options.source ? { "X-Source": options.source } : {}),
    };
  }

  getAssessmentProjection(familyId: string, session: ApiSession) {
    return this.request<Ui02AssessmentProjection>(`/families/${familyId}/ui/02/assessment`, session);
  }

  startAssessment(familyId: string, body: { subject_person_id: string; tool_ref?: string | null }, options: MutationOptions) {
    return this.request<AssessmentMutationReceipt>(`/families/${familyId}/assessments/sessions`, options, {
      method: "POST",
      headers: this.mutationHeaders(options),
      body: JSON.stringify(body),
    });
  }

  saveAssessmentResponse(familyId: string, sessionId: string, body: { item_ref: string; response_type: AssessmentResponseType; response_value: string | boolean }, options: MutationOptions) {
    return this.request<AssessmentMutationReceipt>(`/families/${familyId}/assessments/sessions/${sessionId}/responses`, options, {
      method: "POST",
      headers: this.mutationHeaders(options),
      body: JSON.stringify(body),
    });
  }

  submitAssessment(familyId: string, sessionId: string, options: MutationOptions) {
    return this.request<AssessmentMutationReceipt>(`/families/${familyId}/assessments/sessions/${sessionId}/submit`, options, {
      method: "POST",
      headers: this.mutationHeaders(options),
    });
  }

  getGrowthHypothesis(familyId: string, session: ApiSession) {
    return this.request<GrowthHypothesisProjection>(`/families/${familyId}/ui/03/growth-hypothesis`, session);
  }

  decideGrowthHypothesis(familyId: string, body: { assessment_session_id: string; hypothesis_ref: string; decision_type: HypothesisDecision }, options: MutationOptions) {
    return this.request<GrowthHypothesisDecisionReceipt>(`/families/${familyId}/growth-hypotheses/decisions`, options, {
      method: "POST",
      headers: this.mutationHeaders(options),
      body: JSON.stringify(body),
    });
  }

  private assertDevServiceContract() {
    if (!this.devServiceContractEnabled) throw new FamilyApiError(0, "DEV_SERVICE_CONTRACT_DISABLED");
  }

  getServiceOfferings<T>(familyId: string, session: ApiSession) {
    this.assertDevServiceContract();
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/services/offerings`, session);
  }

  getServiceSlots<T>(familyId: string, serviceOfferingId: string, session: ApiSession) {
    this.assertDevServiceContract();
    const query = new URLSearchParams({ service_offering_id: serviceOfferingId });
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/services/slots?${query}`, session);
  }

  getServiceCustomerProjection<T>(familyId: string, session: ApiSession) {
    this.assertDevServiceContract();
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/services/customer-projection`, session);
  }

  submitServiceBooking<T>(familyId: string, body: SubmitBookingBody, options: MutationOptions) {
    this.assertDevServiceContract();
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/services/booking-requests`, options, {
      method: "POST",
      headers: this.mutationHeaders(options),
      body: JSON.stringify(body),
    });
  }

  createPrivateCheckinDraft<T>(familyId: string, onboardingId: string, actionRef: string, options: MutationOptions) {
    return this.request<T>(`/families/${familyId}/growth/onboardings/${onboardingId}/service-journey/checkin-drafts`, options, {
      method: "POST",
      headers: this.mutationHeaders(options),
      body: JSON.stringify({ action_ref: actionRef }),
    });
  }
}

export const familyApi = new FamilyApiClient();
