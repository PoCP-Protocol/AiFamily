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
  type ReplaySnapshot,
} from "./client";

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type ClientOptions = { baseUrl?: string; fetchImpl?: FetchLike };

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

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
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
      ...(input.session_id ? { session_id: input.session_id } : {}),
    };
    const response = await this.request(
      `/families/${encodeURIComponent(input.scope.family_id)}/experience/multimodal/drafts`,
      {
        method: "POST",
        headers: { "content-type": "application/json", "x-idempotency-key": idempotencyKey },
        body: JSON.stringify(body),
      },
    );
    return mapDraftResponse((await response.json()) as DraftResponse);
  }

  decide(_input: DraftDecisionInput, _idempotencyKey: string): Promise<DecisionReceipt> {
    return Promise.reject(this.unavailable());
  }

  submitFeedback(_input: FeedbackInput, _idempotencyKey: string): Promise<FeedbackReceipt> {
    return Promise.reject(this.unavailable());
  }

  requestHuman(_input: HumanReviewInput, _idempotencyKey: string): Promise<HumanReviewReceipt> {
    return Promise.reject(this.unavailable());
  }

  deleteRun(_runId: string, _idempotencyKey: string): Promise<DeletionReceipt> {
    return Promise.reject(this.unavailable());
  }

  replayRun(_runId: string): Promise<ReplaySnapshot> {
    return Promise.reject(this.unavailable());
  }

  private async request(path: string, init: RequestInit): Promise<Response> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    } catch {
      throw new ExperienceApiError("TIMEOUT", "timeout", "Experience API 暂时不可达，请稍后重试。");
    }
    if (!response.ok) throw await mapHttpError(response);
    return response;
  }

  private unavailable(): ExperienceApiError {
    return new ExperienceApiError(
      "PROVIDER_NOT_ADMITTED",
      "refused",
      "该体验动作尚未接入 Experience API，当前不会在浏览器直接调用模型。",
    );
  }
}
function estimateInputTokens(expression: string): number {
  return Math.max(1, Math.ceil(expression.length / 4));
}

function mapDraftResponse(response: DraftResponse): ExperienceDraft {
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
    media_inputs: [],
    correlation_id: response.run_id,
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
  if (response.status === 503) {
    return new ExperienceApiError("PROVIDER_NOT_ADMITTED", "refused", "当前模型尚未完成家庭数据准入。");
  }
  if (response.status === 422 && detail.toLowerCase().includes("consent")) {
    return new ExperienceApiError("CONSENT_REQUIRED", "refused", "提交前需要有效同意。");
  }
  return new ExperienceApiError("INVALID_INPUT", "refused", detail);
}
