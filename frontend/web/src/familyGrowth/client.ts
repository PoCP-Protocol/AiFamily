export type AssessmentDimension = {
  dimension_ref: string;
  title: string;
  description?: string;
  evidence_refs?: string[];
};

export type AssessmentItem = {
  item_ref: string;
  response_type: "SINGLE_CHOICE" | "TEXT" | "BOOLEAN";
  required: boolean;
  options?: string[] | null;
};

export type AssessmentProjection = {
  projection_version: string;
  availability: string;
  tool_ref?: string;
  tool?: { tool_ref: string; title: string; items: AssessmentItem[] } | null;
  dimensions: AssessmentDimension[];
  subjects?: Array<{ person_id: string; display_name?: string }>;
  active_session?: { session_id: string; status: string } | null;
};

export type AssessmentSessionReceipt = {
  session_id: string;
  status: string;
  replayed?: boolean;
};

export type GrowthHypothesisProjection = {
  projection_version: string;
  availability: string;
  hypothesis?: {
    hypothesis_ref: string;
    title?: string;
    statement?: string;
    understanding?: string;
    evidence_refs?: string[];
    need_refs?: string[];
    action_candidate_refs?: string[];
    focus_ref?: string;
  } | null;
};

export type GrowthPathProjection = {
  family_need_id: string;
  path_id: string;
  run_id: string;
  context_snapshot_ref: string;
  decision_ref: string | null;
  decision_state: string | null;
  next_step: string | null;
  path: unknown[];
  status: "DRAFT";
  requires_human_confirmation: true;
};

export type AssessmentResponseInput = {
  item_ref: string;
  response_type: string;
  response_value: unknown;
};

export type AssessmentDecisionInput = {
  assessment_session_id: string;
  hypothesis_ref: string;
  decision_type: string;
};

export class FamilyGrowthApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "家庭成长服务暂时不可用，请稍后重试。");
    this.name = "FamilyGrowthApiError";
    this.status = status;
    this.detail = detail;
  }
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type FamilyGrowthClientOptions = {
  baseUrl?: string;
  accessToken?: string;
  fetchImpl?: FetchLike;
};

export class FamilyGrowthApiClient {
  private readonly baseUrl: string;
  private readonly accessToken?: string;
  private readonly fetchImpl: FetchLike;

  constructor(options: FamilyGrowthClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.accessToken = options.accessToken?.trim() || undefined;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  async getAssessment(familyId: string): Promise<AssessmentProjection> {
    return this.request<AssessmentProjection>(`/families/${encodeURIComponent(familyId)}/ui/02/assessment`);
  }

  async startAssessment(
    familyId: string,
    body: { subject_person_id: string; tool_ref: string },
    idempotencyKey: string,
  ): Promise<AssessmentSessionReceipt> {
    return this.mutate<AssessmentSessionReceipt>(
      `/families/${encodeURIComponent(familyId)}/assessments/sessions`,
      body,
      idempotencyKey,
    );
  }

  async saveAssessmentResponse(
    familyId: string,
    sessionId: string,
    body: AssessmentResponseInput,
    idempotencyKey: string,
  ): Promise<AssessmentSessionReceipt> {
    return this.mutate<AssessmentSessionReceipt>(
      `/families/${encodeURIComponent(familyId)}/assessments/sessions/${encodeURIComponent(sessionId)}/responses`,
      body,
      idempotencyKey,
    );
  }

  async submitAssessment(
    familyId: string,
    sessionId: string,
    idempotencyKey: string,
  ): Promise<AssessmentSessionReceipt> {
    return this.mutate<AssessmentSessionReceipt>(
      `/families/${encodeURIComponent(familyId)}/assessments/sessions/${encodeURIComponent(sessionId)}/submit`,
      {},
      idempotencyKey,
    );
  }

  async getGrowthHypothesis(familyId: string): Promise<GrowthHypothesisProjection> {
    return this.request<GrowthHypothesisProjection>(
      `/families/${encodeURIComponent(familyId)}/ui/03/growth-hypothesis`,
    );
  }

  async decideGrowthHypothesis(
    familyId: string,
    body: AssessmentDecisionInput,
    idempotencyKey: string,
  ): Promise<AssessmentSessionReceipt> {
    return this.mutate<AssessmentSessionReceipt>(
      `/families/${encodeURIComponent(familyId)}/growth-hypotheses/decisions`,
      body,
      idempotencyKey,
    );
  }

  async getGrowthPath(familyId: string, runId: string): Promise<GrowthPathProjection> {
    return this.request<GrowthPathProjection>(
      `/families/${encodeURIComponent(familyId)}/experience/multimodal/runs/${encodeURIComponent(runId)}/growth-path`,
    );
  }

  private async mutate<T>(path: string, body: Record<string, unknown>, idempotencyKey: string): Promise<T> {
    if (!idempotencyKey.trim()) throw new FamilyGrowthApiError(422, "幂等键不能为空。");
    return this.request<T>(path, {
      method: "POST",
      headers: { "content-type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    });
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response;
    try {
      const headers = new Headers(init.headers);
      headers.set("accept", "application/json");
      if (this.accessToken) {
        headers.set(
          "authorization",
          this.accessToken.toLowerCase().startsWith("bearer ")
            ? this.accessToken
            : `Bearer ${this.accessToken}`,
        );
      }
      response = await this.fetchImpl(`${this.baseUrl}${path}`, { ...init, headers });
    } catch {
      throw new FamilyGrowthApiError(503, "服务暂时不可达。");
    }
    if (!response.ok) {
      let detail: unknown = response.statusText;
      try {
        const payload = (await response.json()) as { detail?: unknown };
        detail = payload.detail ?? detail;
      } catch {
        // Preserve the HTTP status when the server did not return JSON.
      }
      throw new FamilyGrowthApiError(response.status, detail);
    }
    return (await response.json()) as T;
  }
}
