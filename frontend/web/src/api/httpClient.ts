import {
  ExperienceApiError,
  type CreateDraftInput,
  type DecisionReceipt,
  type DraftDecisionInput,
  type ExperienceApiClient,
  type ExperienceDraft,
  type FeedbackInput,
  type FeedbackReceipt,
  type HumanReviewInput,
  type HumanReviewReceipt,
  type DeletionReceipt,
  type MediaInput,
  type ReplaySnapshot,
} from "./client";

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
export type ClientOptions = {
  baseUrl?: string;
  /**
   * Route hint only. The API must bind the family/tenant to this bearer token;
   * the browser never sends a tenant header and this value is not authority.
   */
  familyId?: string;
  /** Raw access token; a `Bearer ` prefix is accepted for convenience. */
  accessToken?: string;
  /** Optional session context propagated to every request. */
  sessionId?: string;
  /** User locale context; the server remains responsible for validation. */
  locale?: string;
  fetchImpl?: FetchLike;
};

type DraftResponse = {
  run_id: string;
  status: "DRAFT";
  output: Record<string, unknown>;
  requires_human_confirmation: true;
  context_snapshot_ref: string;
  provenance: {
    provider_id: string;
    model: string;
    model_version: string;
    prompt_version: string;
    schema_version: string;
    context_snapshot_ref: string;
    latency_ms: number;
    data_class: string;
    use_case: string;
    confidence: number | null;
    generated_at: string;
  };
};

type InteractionResponse = {
  run_id: string;
  status: "recorded" | "replayed" | "deleted";
  interaction_ref: string;
  idempotency_replayed: boolean;
};

type ReplayResponse = {
  run_id: string;
  status: "DRAFT";
  state: string;
  event_sequence: number;
  deletion_state: "active" | "deleted";
  draft_payload: Record<string, unknown> | null;
  artifact_refs: string[];
  entries: Array<{
    event_id: string;
    interaction_type: string;
    sequence: number;
    payload: Record<string, unknown>;
    occurred_at: string;
  }>;
};

const defaultOutputSchema = {
  type: "object",
  properties: {
    understanding: { type: "string" },
    next_step: { type: "string" },
    limitations: { type: "array", items: { type: "string" } },
  },
};

/** Same-origin Experience API adapter; no browser-side provider call. */
export class HttpExperienceApiClient implements ExperienceApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;
  private readonly defaultFamilyId?: string;
  private readonly accessToken?: string;
  private readonly sessionId?: string;
  private readonly locale?: string;
  private readonly familyByRun = new Map<string, string>();

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.defaultFamilyId = options.familyId;
    this.accessToken = options.accessToken?.trim() || undefined;
    this.sessionId = options.sessionId?.trim() || undefined;
    this.locale = options.locale?.trim() || undefined;
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  async createDraft(input: CreateDraftInput, idempotencyKey: string): Promise<ExperienceDraft> {
    const body = {
      run_id: input.run_id,
      prompt_version: input.prompt_version,
      schema_version: input.schema_version,
      payload: input.payload,
      output_schema: input.output_schema ?? defaultOutputSchema,
      modalities: input.modalities ?? (input.media_inputs.length > 0 ? ["TEXT", "IMAGE"] : ["TEXT"]),
      estimated_input_tokens: input.estimated_input_tokens ?? estimateInputTokens(input.payload.expression),
      strategy: input.strategy ?? "balanced",
      ...(input.limits?.max_latency_ms === undefined ? {} : { max_latency_ms: input.limits.max_latency_ms }),
      ...(input.limits?.max_cost_microusd === undefined ? {} : { max_cost_microusd: input.limits.max_cost_microusd }),
      input_refs: input.input_refs,
      media_inputs: input.media_inputs,
      ...(input.session_id || this.sessionId
        ? { session_id: input.session_id ?? this.sessionId }
        : {}),
    };
    const response = await this.request(
      `/families/${encodeURIComponent(input.scope.family_id)}/experience/multimodal/drafts`,
      {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(body),
      },
      { sessionId: input.session_id, locale: input.scope.locale },
    );
    this.familyByRun.set(input.run_id, input.scope.family_id);
    return mapDraftResponse((await response.json()) as DraftResponse, input.media_inputs);
  }

  async decide(input: DraftDecisionInput, idempotencyKey: string): Promise<DecisionReceipt> {
    const familyId = this.familyForRun(input.run_id, input.family_id);
    const body = {
      decision: input.decision,
      ...(input.draft_version ? { draft_version: input.draft_version } : {}),
      ...(input.replacement_text ? { replacement_text: input.replacement_text } : {}),
      ...(input.reason ? { reason: input.reason } : {}),
    };
    const response = await this.mutate<InteractionResponse>(
      `/families/${encodeURIComponent(familyId)}/experience/multimodal/runs/${encodeURIComponent(input.run_id)}/decisions`,
      body,
      idempotencyKey,
    );
    return mapInteractionResponse(response);
  }

  async submitFeedback(input: FeedbackInput, idempotencyKey: string): Promise<FeedbackReceipt> {
    const familyId = this.familyForRun(input.run_id, input.family_id);
    const body = {
      signal: input.signal,
      ...(input.reason ? { reason: input.reason } : {}),
      ...(input.draft_version ? { draft_version: input.draft_version } : {}),
      ...(input.attempt_id ? { attempt_id: input.attempt_id } : {}),
      ...(input.candidate_id ? { candidate_id: input.candidate_id } : {}),
      ...(input.model_version ? { model_version: input.model_version } : {}),
      ...(input.benchmark_report_ref ? { benchmark_report_ref: input.benchmark_report_ref } : {}),
      ...(input.event_refs?.length ? { real_event_refs: input.event_refs } : {}),
    };
    const response = await this.mutate<InteractionResponse>(
      `/families/${encodeURIComponent(familyId)}/experience/multimodal/runs/${encodeURIComponent(input.run_id)}/feedback`,
      body,
      idempotencyKey,
    );
    return { ...mapInteractionResponse(response), recorded: response.status === "recorded" };
  }

  async requestHuman(input: HumanReviewInput, idempotencyKey: string): Promise<HumanReviewReceipt> {
    const familyId = this.familyForRun(input.run_id, input.family_id);
    const body = {
      reason: input.reason,
      ...(input.impact_scope ? { impact_scope: input.impact_scope } : {}),
    };
    const response = await this.mutate<InteractionResponse>(
      `/families/${encodeURIComponent(familyId)}/experience/multimodal/runs/${encodeURIComponent(input.run_id)}/human-review`,
      body,
      idempotencyKey,
    );
    return mapInteractionResponse(response);
  }

  async deleteRun(runId: string, idempotencyKey: string): Promise<DeletionReceipt> {
    const familyId = this.familyForRun(runId);
    const response = await this.mutate<InteractionResponse>(
      `/families/${encodeURIComponent(familyId)}/experience/multimodal/runs/${encodeURIComponent(runId)}`,
      {},
      idempotencyKey,
      "DELETE",
    );
    return mapInteractionResponse(response);
  }

  async replayRun(runId: string): Promise<ReplaySnapshot> {
    const familyId = this.familyForRun(runId);
    const response = await this.request(
      `/families/${encodeURIComponent(familyId)}/experience/multimodal/runs/${encodeURIComponent(runId)}/replay`,
      { method: "GET", headers: { accept: "application/json" } },
    );
    return mapReplayResponse((await response.json()) as ReplayResponse);
  }

  private familyForRun(runId: string, familyId?: string): string {
    const resolved = familyId ?? this.familyByRun.get(runId) ?? this.defaultFamilyId;
    if (!resolved) throw new ExperienceApiError("INVALID_INPUT", "refused", "缺少家庭范围，无法访问体验运行记录。");
    return resolved;
  }

  private async mutate<T>(path: string, body: Record<string, unknown>, idempotencyKey: string, method = "POST"): Promise<T> {
    if (!idempotencyKey.trim()) throw new ExperienceApiError("INVALID_INPUT", "refused", "缺少幂等键，无法提交体验动作。");
    const response = await this.request(path, {
      method,
      headers: { "content-type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    });
    return (await response.json()) as T;
  }

  private contextHeaders(sessionId?: string, locale?: string): Record<string, string> {
    const headers: Record<string, string> = {};
    if (this.accessToken) {
      headers.Authorization = this.accessToken.toLowerCase().startsWith("bearer ")
        ? this.accessToken
        : `Bearer ${this.accessToken}`;
    }
    const resolvedSessionId = sessionId?.trim() || this.sessionId;
    if (resolvedSessionId) headers["X-Session-Id"] = resolvedSessionId;
    // A request's explicit locale wins over the client default.  This keeps a
    // long-lived client safe for a locale switch while retaining a fallback
    // for calls that do not carry a scope locale.
    const resolvedLocale = locale?.trim() || this.locale;
    if (resolvedLocale) headers["X-User-Locale"] = resolvedLocale;
    return headers;
  }

  private async request(
    path: string,
    init: RequestInit,
    context: { sessionId?: string; locale?: string } = {},
  ): Promise<Response> {
    let response: Response;
    try {
      const requestHeaders = {
        ...((init.headers ?? {}) as Record<string, string>),
        ...this.contextHeaders(context.sessionId, context.locale),
      };
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers: requestHeaders,
      });
    } catch {
      throw new ExperienceApiError("TIMEOUT", "timeout", "Experience API 暂时不可达，请稍后重试。");
    }
    if (!response.ok) throw await mapHttpError(response);
    return response;
  }

}
function estimateInputTokens(expression: string): number {
  return Math.max(1, Math.ceil(expression.length / 4));
}

function mapDraftResponse(response: DraftResponse, mediaInputs: MediaInput[]): ExperienceDraft {
  const understanding = response.output.understanding;
  const nextStep = response.output.next_step;
  const limitations = response.output.limitations;
  return {
    run_id: response.run_id,
    draft_version: response.provenance.schema_version,
    status: "DRAFT",
    output: {
      understanding: typeof understanding === "string" ? understanding : "后端未提供可展示的理解文本。",
      next_step: typeof nextStep === "string" ? nextStep : "请等待人工确认后再决定下一步。",
    },
    limitations: Array.isArray(limitations) && limitations.every((item) => typeof item === "string")
      ? limitations
      : ["后端未提供限制清单，请在人工确认前核对。"],
    provenance: {
      provenance_ref: null,
      kind: "AI_DRAFT",
      model_attempt_ref: null,
      context_snapshot_ref: response.provenance.context_snapshot_ref || response.context_snapshot_ref,
      prompt_version: response.provenance.prompt_version,
      schema_version: response.provenance.schema_version,
      captured_at: response.provenance.generated_at,
      provider_id: response.provenance.provider_id,
      model: response.provenance.model,
      model_version: response.provenance.model_version,
      latency_ms: response.provenance.latency_ms,
      confidence: response.provenance.confidence,
      data_class: response.provenance.data_class,
      use_case: response.provenance.use_case,
      generated_at: response.provenance.generated_at,
    },
    requires_human_confirmation: true,
    media_inputs: mediaInputs,
    correlation_id: response.run_id,
  };
}

function mapInteractionResponse(response: InteractionResponse): InteractionResponse {
  return {
    run_id: response.run_id,
    status: response.status,
    interaction_ref: response.interaction_ref,
    idempotency_replayed: response.idempotency_replayed,
  };
}

function mapReplayResponse(response: ReplayResponse): ReplaySnapshot {
  return {
    run_id: response.run_id,
    status: response.status,
    state: response.state,
    event_sequence: response.event_sequence,
    deletion_state: response.deletion_state,
    draft_payload: response.draft_payload,
    artifact_refs: response.artifact_refs,
    entries: response.entries.map((entry) => ({
      label: entry.interaction_type,
      at: entry.occurred_at,
      event_id: entry.event_id,
      interaction_type: entry.interaction_type,
      sequence: entry.sequence,
      payload: entry.payload,
    })),
  };
}

async function mapHttpError(response: Response): Promise<ExperienceApiError> {
  let detail = "Experience API 请求被拒绝。";
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    // Keep a stable, non-sensitive error when the server has no JSON body.
  }
  if (response.status === 408 || response.status === 504) {
    return new ExperienceApiError("TIMEOUT", "timeout", "Experience API 响应超时，请稍后重试。");
  }
  if (response.status === 403) {
    return new ExperienceApiError("SCOPE_MISMATCH", "refused", "当前家庭无权访问这次体验。");
  }
  if (response.status === 404) {
    return new ExperienceApiError("RUN_NOT_FOUND", "refused", "找不到这次体验运行记录。");
  }
  if (response.status === 409) {
    return new ExperienceApiError("CONFLICT", "refused", "请求幂等键与既有体验动作冲突。");
  }
  if (response.status === 410) {
    return new ExperienceApiError("MEDIA_DELETED", "deleted", "这次体验已删除，无法继续访问。");
  }
  if (response.status === 503) {
    return new ExperienceApiError("PROVIDER_NOT_ADMITTED", "refused", "当前模型尚未完成家庭数据准入。");
  }
  if (response.status === 422 && detail.toLowerCase().includes("consent")) {
    return new ExperienceApiError("CONSENT_REQUIRED", "refused", "提交前需要有效同意。");
  }
  return new ExperienceApiError("INVALID_INPUT", "refused", detail);
}
