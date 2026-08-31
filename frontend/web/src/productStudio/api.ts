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

export type ProductCompilerCheck = {
  passed: boolean;
  detail: string;
  check_name?: string;
};

export type ProductCompilerReport = {
  checks?: Record<string, ProductCompilerCheck | null | undefined>;
  passed?: boolean;
};

export type ProductDraftResponse = {
  status: "DRAFT";
  provenance_ref: string;
  evidence_refs?: string[];
  assumptions?: string[];
  unknowns?: string[];
  next_validation?: string;
  expires_at?: string;
  draft_id?: string;
  product_definition_id?: string | null;
  ai_provenance?: ProductAiProvenance;
  model_ref?: string;
  prompt_use_case_version?: string;
  confidence?: number | null;
  compiler_report?: ProductCompilerReport;
  [key: string]: unknown;
};

export type CompetitorEvidenceDraftResponse = ProductDraftResponse & {
  evidence_id: string;
  competitor_ref: string;
  claim: string;
  source_refs: string[];
  evidence_status: "VERIFIED" | "UNKNOWN" | "STALE" | "CONTRADICTED";
  source_type: string;
  evidence_refs: string[];
  assumptions: string[];
  unknowns: string[];
  next_validation: string;
  expires_at: string;
  demand_ref?: string | null;
  market_insight_ref?: string | null;
};

export type MarketInsightDraftResponse = ProductDraftResponse & {
  insight_id: string;
  demand_ref: string;
  statement: string;
  source_refs: string[];
  competitor_evidence_refs: string[];
  evidence_refs: string[];
  assumptions: string[];
  unknowns: string[];
  next_validation: string;
  expires_at: string;
  segment_ref?: string | null;
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

export type ProductStudioAccessTokenProvider = () => string | undefined;

export type ClientOptions = {
  baseUrl?: string;
  fetchImpl?: ProductStudioFetch;
  accessToken?: string;
  accessTokenProvider?: ProductStudioAccessTokenProvider;
};

export interface ProductStudioApiClient {
  createDemandFrame(input: DemandFrameInput, idempotencyKey: string): Promise<ProductDraftResponse>;
  createMarketInsight(input: MarketInsightInput, idempotencyKey: string): Promise<MarketInsightDraftResponse>;
  createCompetitorEvidence(input: CompetitorEvidenceInput, idempotencyKey: string): Promise<CompetitorEvidenceDraftResponse>;
  getCompetitorEvidence?(evidenceId: string): Promise<CompetitorEvidenceDraftResponse>;
}

const FACTORY_PREFIX = "/product-intelligence/product-factory";

export class HttpProductStudioApiClient implements ProductStudioApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: ProductStudioFetch;
  private readonly accessToken?: string;
  private readonly accessTokenProvider?: ProductStudioAccessTokenProvider;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.accessToken = options.accessToken;
    this.accessTokenProvider = options.accessTokenProvider;
  }

  createDemandFrame(input: DemandFrameInput, idempotencyKey: string): Promise<ProductDraftResponse> {
    return this.postDraft("/demand-frames", input, idempotencyKey);
  }

  async createMarketInsight(input: MarketInsightInput, idempotencyKey: string): Promise<MarketInsightDraftResponse> {
    return validateMarketInsightResponse(await this.postDraft("/market-insights", input, idempotencyKey));
  }

  async createCompetitorEvidence(input: CompetitorEvidenceInput, idempotencyKey: string): Promise<CompetitorEvidenceDraftResponse> {
    return validateCompetitorEvidenceResponse(await this.postDraft("/competitor-evidence", input, idempotencyKey));
  }

  async getCompetitorEvidence(evidenceId: string): Promise<CompetitorEvidenceDraftResponse> {
    const normalizedId = evidenceId.trim();
    if (!normalizedId) {
      throw new ProductStudioApiError("INVALID_INPUT", "缺少竞品证据 ID，无法回读。");
    }
    let response: Response;
    try {
      response = await this.fetchImpl(
        `${this.baseUrl}${FACTORY_PREFIX}/competitor-evidence/${encodeURIComponent(normalizedId)}`,
        { method: "GET", headers: this.authorizationHeaders() },
      );
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
    return validateCompetitorEvidenceResponse(validateDraftResponse(body, response.status));
  }

  private async postDraft(path: string, input: object, idempotencyKey: string): Promise<ProductDraftResponse> {
    if (!idempotencyKey.trim()) {
      throw new ProductStudioApiError("INVALID_INPUT", "缺少幂等键，无法提交产品草案。");
    }
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${FACTORY_PREFIX}${path}`, {
        method: "POST",
        headers: {
          ...this.authorizationHeaders(),
          "content-type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
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

  private authorizationHeaders(): Record<string, string> {
    const rawToken = this.accessTokenProvider?.() ?? this.accessToken;
    const token = rawToken?.trim();
    if (!token) return {};
    return {
      Authorization: token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}`,
    };
  }
}

function requireResponseString(body: ProductDraftResponse, field: string): string {
  const value = body[field];
  if (typeof value !== "string" || !value.trim()) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `产品草案缺少 ${field}。`);
  }
  return value.trim();
}

function requireResponseStrings(body: ProductDraftResponse, field: string): string[] {
  const value = body[field];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item.trim())) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `产品草案的 ${field} 无效。`);
  }
  return value.map((item) => item.trim());
}

function validateCompetitorEvidenceResponse(body: ProductDraftResponse): CompetitorEvidenceDraftResponse {
  const evidenceStatus = body.evidence_status;
  if (!["VERIFIED", "UNKNOWN", "STALE", "CONTRADICTED"].includes(String(evidenceStatus))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "竞品证据状态无效。");
  }
  return {
    ...body,
    evidence_id: requireResponseString(body, "evidence_id"),
    competitor_ref: requireResponseString(body, "competitor_ref"),
    claim: requireResponseString(body, "claim"),
    source_refs: requireResponseStrings(body, "source_refs"),
    evidence_refs: requireResponseStrings(body, "evidence_refs"),
    assumptions: requireResponseStrings(body, "assumptions"),
    unknowns: requireResponseStrings(body, "unknowns"),
    next_validation: requireResponseString(body, "next_validation"),
    expires_at: requireResponseString(body, "expires_at"),
    evidence_status: evidenceStatus as CompetitorEvidenceDraftResponse["evidence_status"],
    source_type: requireResponseString(body, "source_type"),
  };
}

function validateMarketInsightResponse(body: ProductDraftResponse): MarketInsightDraftResponse {
  return {
    ...body,
    insight_id: requireResponseString(body, "insight_id"),
    demand_ref: requireResponseString(body, "demand_ref"),
    statement: requireResponseString(body, "statement"),
    source_refs: requireResponseStrings(body, "source_refs"),
    competitor_evidence_refs: requireResponseStrings(body, "competitor_evidence_refs"),
    evidence_refs: requireResponseStrings(body, "evidence_refs"),
    assumptions: requireResponseStrings(body, "assumptions"),
    unknowns: requireResponseStrings(body, "unknowns"),
    next_validation: requireResponseString(body, "next_validation"),
    expires_at: requireResponseString(body, "expires_at"),
  };
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
