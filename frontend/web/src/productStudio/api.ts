/**
 * Provider-neutral Product Studio API seam.
 *
 * The server owns identity, persistence and model routing. This client only
 * sends product-design intent and accepts immutable DRAFT projections.
 */

export type ProductStudioFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type ProductStudioErrorCode =
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "CONFLICT"
  | "UNAVAILABLE"
  | "TIMEOUT"
  | "INVALID_INPUT"
  | "INVALID_RESPONSE";

export class ProductStudioApiError extends Error {
  readonly code: ProductStudioErrorCode;
  readonly httpStatus?: number;

  constructor(code: ProductStudioErrorCode, message: string, httpStatus?: number) {
    super(message);
    this.name = "ProductStudioApiError";
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

export type ProductAiProvenance = {
  model_ref?: string;
  prompt_use_case_version?: string;
  confidence?: number | null;
  provenance_ref?: string;
  model_attempt_ref?: string;
};

export type ProductDraftResponse = {
  status: "DRAFT";
  provenance_ref: string;
  ai_provenance?: ProductAiProvenance;
  [key: string]: unknown;
};

export type DraftEnvelopeInput = {
  evidence_refs: string[];
  assumptions: string[];
  unknowns: string[];
  next_validation: string;
  expires_at: string;
  provenance_ref?: string;
  model_ref?: string;
  prompt_use_case_version?: string;
  confidence?: number | null;
};

export type DemandFrameInput = DraftEnvelopeInput & {
  statement: string;
  scenario: string;
  source_refs: string[];
  target_segment: string;
  locale?: string;
  purpose?: string;
};

export type MarketInsightInput = DraftEnvelopeInput & {
  demand_ref: string;
  statement: string;
  source_refs: string[];
  competitor_evidence_refs?: string[];
  segment_ref?: string;
};

export type CompetitorEvidenceInput = DraftEnvelopeInput & {
  competitor_ref: string;
  claim: string;
  source_refs: string[];
  evidence_status?: "VERIFIED" | "UNKNOWN" | "STALE" | "CONTRADICTED";
  demand_ref?: string;
  market_insight_ref?: string;
  source_type?: string;
};

export type ProductPackageInput = DraftEnvelopeInput & {
  concept_id: string;
  product_kind: "MICRO_CAMP" | "SCALE_PLAN" | "CUSTOM";
  duration_days: 21 | 90;
  zone: "HOMOGENEOUS" | "ADVANTAGE" | "UNIQUE_CANDIDATE" | "EXCLUSIVE_CANDIDATE";
  primary_contradiction: string;
  demand_ref: string;
  market_insight_refs: string[];
  competitor_evidence_refs: string[];
  component_ids: string[];
  skill_ids: string[];
  success_metric_ids: string[];
  guardrail_ids: string[];
  stop_conditions: string[];
  pause_policy: string;
  human_gate_policy: string;
};

export type ClientOptions = { baseUrl?: string; fetchImpl?: ProductStudioFetch };

export interface ProductStudioApiClient {
  createDemandFrame(input: DemandFrameInput, idempotencyKey: string): Promise<ProductDraftResponse>;
  createMarketInsight(input: MarketInsightInput, idempotencyKey: string): Promise<ProductDraftResponse>;
  createCompetitorEvidence(input: CompetitorEvidenceInput, idempotencyKey: string): Promise<ProductDraftResponse>;
  createProductPackage(input: ProductPackageInput, idempotencyKey: string): Promise<ProductDraftResponse>;
}

const FACTORY_PREFIX = "/product-intelligence/product-factory";

export class HttpProductStudioApiClient implements ProductStudioApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: ProductStudioFetch;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  createDemandFrame(input: DemandFrameInput, idempotencyKey: string): Promise<ProductDraftResponse> {
    return this.postDraft("/demand-frames", input, idempotencyKey);
  }

  createMarketInsight(input: MarketInsightInput, idempotencyKey: string): Promise<ProductDraftResponse> {
    return this.postDraft("/market-insights", input, idempotencyKey);
  }

  createCompetitorEvidence(input: CompetitorEvidenceInput, idempotencyKey: string): Promise<ProductDraftResponse> {
    return this.postDraft("/competitor-evidence", input, idempotencyKey);
  }

  createProductPackage(input: ProductPackageInput, idempotencyKey: string): Promise<ProductDraftResponse> {
    return this.postDraft("/product-packages", input, idempotencyKey);
  }

  private async postDraft(path: string, input: object, idempotencyKey: string): Promise<ProductDraftResponse> {
    if (!idempotencyKey.trim()) {
      throw new ProductStudioApiError("INVALID_INPUT", "缺少幂等键，无法提交产品草案。");
    }
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${FACTORY_PREFIX}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(input),
      });
    } catch {
      throw new ProductStudioApiError("TIMEOUT", "Product Studio API 暂时不可达，请稍后重试。");
    }
    if (!response.ok) throw await mapProductStudioHttpError(response);
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ProductStudioApiError("INVALID_RESPONSE", "Product Studio 返回了不可解析的响应。", response.status);
    }
    return validateDraftResponse(body, response.status);
  }
}

function validateDraftResponse(value: unknown, httpStatus?: number): ProductDraftResponse {
  if (!value || typeof value !== "object") {
    throw new ProductStudioApiError("INVALID_RESPONSE", "Product Studio 响应不是对象。", httpStatus);
  }
  const body = value as Record<string, unknown>;
  if (body.status !== "DRAFT") {
    throw new ProductStudioApiError("INVALID_RESPONSE", "产品工厂响应必须保持 DRAFT 状态。", httpStatus);
  }
  const provenance = body.provenance_ref;
  const aiProvenance = body.ai_provenance;
  const nestedRef = aiProvenance && typeof aiProvenance === "object"
    ? (aiProvenance as Record<string, unknown>).provenance_ref
    : undefined;
  const topLevelRef = typeof provenance === "string" && provenance.trim() ? provenance.trim() : undefined;
  const nestedProvenanceRef = typeof nestedRef === "string" && nestedRef.trim() ? nestedRef.trim() : undefined;
  if (!topLevelRef && !nestedProvenanceRef) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "产品草案缺少 ai_provenance/provenance_ref。", httpStatus);
  }
  return {
    ...body,
    status: "DRAFT",
    provenance_ref: topLevelRef ?? nestedProvenanceRef!,
    ...(aiProvenance && typeof aiProvenance === "object" ? { ai_provenance: aiProvenance as ProductAiProvenance } : {}),
  };
}

async function mapProductStudioHttpError(response: Response): Promise<ProductStudioApiError> {
  let detail = "Product Studio 请求被拒绝。";
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    // Keep a stable, non-sensitive message when the server has no JSON body.
  }
  switch (response.status) {
    case 401:
      return new ProductStudioApiError("UNAUTHORIZED", "当前会话未登录。", response.status);
    case 403:
      return new ProductStudioApiError("FORBIDDEN", "当前会话无权访问产品工厂。", response.status);
    case 404:
      return new ProductStudioApiError("NOT_FOUND", "找不到产品工厂资源。", response.status);
    case 409:
      return new ProductStudioApiError("CONFLICT", "幂等键与既有产品草案冲突。", response.status);
    case 408:
    case 504:
      return new ProductStudioApiError("TIMEOUT", "产品工厂响应超时，请稍后重试。", response.status);
    case 503:
      return new ProductStudioApiError("UNAVAILABLE", "产品工厂当前不可用或尚未完成准入。", response.status);
    case 422:
      return new ProductStudioApiError("INVALID_INPUT", detail, response.status);
    default:
      return new ProductStudioApiError("INVALID_INPUT", detail, response.status);
  }
}
