export const ZONE_DIMENSIONS = [
  "customer_scarcity",
  "replaceability",
  "data_advantage",
  "network_effect",
  "learning_effect",
  "switching_cost",
] as const;

export type ZoneDimension = (typeof ZONE_DIMENSIONS)[number];
export type RecommendedZone = "COMMODITY" | "ADVANTAGE" | "UNIQUE";
export type ZoneAssessmentStatus = "SCORED" | "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "RETIRED";

export type ProductConceptSummary = {
  id: string;
  strategy_id: string;
  title: string;
  description: string | null;
  status: "DRAFT" | "UNDER_REVIEW" | "APPROVED" | "RETIRED";
};

export type ZoneDimensionAssessment = {
  dimension: ZoneDimension;
  score: number;
  rationale: string;
  evidence_refs: string[];
  evidence_strength: number;
};

export type ZoneAssessmentSummary = {
  id: string;
  subject_type: "PRODUCT_CONCEPT";
  subject_ref: string;
  zone_policy_version_id: string;
  status: ZoneAssessmentStatus;
  recommended_zone: RecommendedZone;
  approved_zone: RecommendedZone | null;
  override_reason: string | null;
  reviewed_by: string | null;
  review_reason: string | null;
  dimension_assessments: ZoneDimensionAssessment[];
  differentiation_index: number;
  defensibility_index: number;
};

export type ProductConceptCandidate = {
  concept: ProductConceptSummary;
  assessment: ZoneAssessmentSummary;
};

export type CandidateReference = { conceptId: string; assessmentId: string };

export type DecisionApiErrorCode =
  | "INVALID_INPUT"
  | "INVALID_RESPONSE"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "UNAVAILABLE"
  | "TIMEOUT";

export class DecisionApiError extends Error {
  readonly code: DecisionApiErrorCode;
  readonly httpStatus?: number;

  constructor(code: DecisionApiErrorCode, message: string, httpStatus?: number) {
    super(message);
    this.name = "DecisionApiError";
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

export interface ProductDecisionApiClient {
  loadCandidates(references: CandidateReference[]): Promise<ProductConceptCandidate[]>;
}

type AccessTokenProvider = () => string | undefined;
type DecisionFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type DecisionClientOptions = {
  baseUrl?: string;
  fetchImpl?: DecisionFetch;
  accessToken?: string;
  accessTokenProvider?: AccessTokenProvider;
};

export class HttpProductDecisionApiClient implements ProductDecisionApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: DecisionFetch;
  private readonly accessToken?: string;
  private readonly accessTokenProvider?: AccessTokenProvider;

  constructor(options: DecisionClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.accessToken = options.accessToken;
    this.accessTokenProvider = options.accessTokenProvider;
  }

  async loadCandidates(references: CandidateReference[]): Promise<ProductConceptCandidate[]> {
    const normalized = normalizeReferences(references);
    return Promise.all(normalized.map(async ({ conceptId, assessmentId }) => {
      const [chain, assessmentValue] = await Promise.all([
        this.getJson(`/product-intelligence/product-concepts/${encodeURIComponent(conceptId)}/chain`),
        this.getJson(`/product-intelligence/zone-assessments/${encodeURIComponent(assessmentId)}`),
      ]);
      const concept = validateConceptChain(chain, conceptId);
      const assessment = validateAssessment(assessmentValue, assessmentId, conceptId);
      return { concept, assessment };
    }));
  }

  private async getJson(path: string): Promise<unknown> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: "GET",
        headers: this.authorizationHeaders(),
      });
    } catch {
      throw new DecisionApiError("TIMEOUT", "产品决策服务暂时不可达，请稍后重试。");
    }
    if (!response.ok) throw mapHttpError(response.status);
    try {
      return await response.json();
    } catch {
      throw new DecisionApiError("INVALID_RESPONSE", "产品决策服务返回了不可解析的响应。", response.status);
    }
  }

  private authorizationHeaders(): Record<string, string> {
    const token = (this.accessTokenProvider?.() ?? this.accessToken)?.trim();
    if (!token) return {};
    return { Authorization: token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}` };
  }
}

function normalizeReferences(references: CandidateReference[]): CandidateReference[] {
  if (references.length < 2 || references.length > 5) {
    throw new DecisionApiError("INVALID_INPUT", "候选数量必须为 2–5 个。");
  }
  const normalized = references.map(({ conceptId, assessmentId }) => ({
    conceptId: conceptId.trim(),
    assessmentId: assessmentId.trim(),
  }));
  if (normalized.some(({ conceptId, assessmentId }) => !conceptId || !assessmentId)) {
    throw new DecisionApiError("INVALID_INPUT", "每个候选都必须提供 concept_id 和 assessment_id。");
  }
  if (new Set(normalized.map(({ conceptId }) => conceptId)).size !== normalized.length
    || new Set(normalized.map(({ assessmentId }) => assessmentId)).size !== normalized.length) {
    throw new DecisionApiError("INVALID_INPUT", "候选 concept_id 与 assessment_id 不得重复。");
  }
  return normalized;
}

function asRecord(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new DecisionApiError("INVALID_RESPONSE", message);
  }
  return value as Record<string, unknown>;
}

function requiredString(record: Record<string, unknown>, field: string): string {
  const value = record[field];
  if (typeof value !== "string" || !value.trim()) {
    throw new DecisionApiError("INVALID_RESPONSE", `响应缺少 ${field}。`);
  }
  return value.trim();
}

function optionalString(record: Record<string, unknown>, field: string): string | null {
  const value = record[field];
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" || !value.trim()) {
    throw new DecisionApiError("INVALID_RESPONSE", `响应中的 ${field} 无效。`);
  }
  return value.trim();
}

function requiredNumber(record: Record<string, unknown>, field: string, min = 0, max = 100): number {
  const value = record[field];
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    throw new DecisionApiError("INVALID_RESPONSE", `响应中的 ${field} 无效。`);
  }
  return value;
}

function validateConceptChain(value: unknown, requestedId: string): ProductConceptSummary {
  const chain = asRecord(value, "ProductConcept chain 响应无效。");
  const concept = asRecord(chain.product_concept, "ProductConcept chain 缺少 product_concept。");
  const id = requiredString(concept, "id");
  if (id !== requestedId) throw new DecisionApiError("INVALID_RESPONSE", "ProductConcept ID 与请求不一致。");
  const description = concept.description;
  if (description !== null && description !== undefined && typeof description !== "string") {
    throw new DecisionApiError("INVALID_RESPONSE", "ProductConcept description 无效。");
  }
  const status = requiredString(concept, "status");
  if (!["DRAFT", "UNDER_REVIEW", "APPROVED", "RETIRED"].includes(status)) {
    throw new DecisionApiError("INVALID_RESPONSE", "ProductConcept status 无效。");
  }
  return {
    id,
    strategy_id: requiredString(concept, "strategy_id"),
    title: requiredString(concept, "title"),
    description: typeof description === "string" ? description : null,
    status: status as ProductConceptSummary["status"],
  };
}

function validateAssessment(value: unknown, requestedId: string, conceptId: string): ZoneAssessmentSummary {
  const assessment = asRecord(value, "三区评估响应无效。");
  const id = requiredString(assessment, "id");
  if (assessment.subject_type !== "PRODUCT_CONCEPT") {
    throw new DecisionApiError("INVALID_RESPONSE", "三区评估 subject_type 必须为 PRODUCT_CONCEPT。");
  }
  const subjectRef = requiredString(assessment, "subject_ref");
  if (id !== requestedId || subjectRef !== conceptId) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区评估与 ProductConcept ID 不匹配。");
  }
  const status = requiredString(assessment, "status");
  if (!["SCORED", "UNDER_REVIEW", "APPROVED", "REJECTED", "RETIRED"].includes(status)) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区评估尚未完成真实证据评分。");
  }
  const recommendedZone = validateZone(assessment.recommended_zone, "recommended_zone");
  const approvedZone = assessment.approved_zone === null || assessment.approved_zone === undefined
    ? null
    : validateZone(assessment.approved_zone, "approved_zone");
  if (status === "APPROVED" && approvedZone === null) {
    throw new DecisionApiError("INVALID_RESPONSE", "已批准的三区评估缺少 approved_zone。");
  }
  if (!Array.isArray(assessment.dimension_assessments) || assessment.dimension_assessments.length !== 6) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区评估必须包含完整六维证据。");
  }
  const dimensions = assessment.dimension_assessments.map(validateDimension);
  if (new Set(dimensions.map(({ dimension }) => dimension)).size !== 6
    || ZONE_DIMENSIONS.some((dimension) => !dimensions.some((item) => item.dimension === dimension))) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区评估六维证据存在缺失或重复。");
  }
  return {
    id,
    subject_type: "PRODUCT_CONCEPT",
    subject_ref: subjectRef,
    zone_policy_version_id: requiredString(assessment, "zone_policy_version_id"),
    status: status as ZoneAssessmentStatus,
    recommended_zone: recommendedZone,
    approved_zone: approvedZone,
    override_reason: optionalString(assessment, "override_reason"),
    reviewed_by: optionalString(assessment, "reviewed_by"),
    review_reason: optionalString(assessment, "review_reason"),
    dimension_assessments: dimensions,
    differentiation_index: requiredNumber(assessment, "differentiation_index"),
    defensibility_index: requiredNumber(assessment, "defensibility_index"),
  };
}

function validateDimension(value: unknown): ZoneDimensionAssessment {
  const dimension = asRecord(value, "三区维度证据无效。");
  const name = requiredString(dimension, "dimension");
  if (!(ZONE_DIMENSIONS as readonly string[]).includes(name)) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区维度名称无效。");
  }
  const evidenceRefs = dimension.evidence_refs;
  if (!Array.isArray(evidenceRefs) || evidenceRefs.length === 0
    || evidenceRefs.some((ref) => typeof ref !== "string" || !ref.trim())) {
    throw new DecisionApiError("INVALID_RESPONSE", `三区维度 ${name} 缺少有效 evidence_refs。`);
  }
  return {
    dimension: name as ZoneDimension,
    score: requiredNumber(dimension, "score"),
    rationale: requiredString(dimension, "rationale"),
    evidence_refs: evidenceRefs.map((ref) => (ref as string).trim()),
    evidence_strength: requiredNumber(dimension, "evidence_strength", 0, 1),
  };
}

function validateZone(value: unknown, field: string): RecommendedZone {
  if (value !== "COMMODITY" && value !== "ADVANTAGE" && value !== "UNIQUE") {
    throw new DecisionApiError("INVALID_RESPONSE", `三区评估 ${field} 无效。`);
  }
  return value;
}

function mapHttpError(status: number): DecisionApiError {
  if (status === 401) return new DecisionApiError("UNAUTHORIZED", "当前会话未登录。", status);
  if (status === 403) return new DecisionApiError("FORBIDDEN", "当前会话无权查看产品候选。", status);
  if (status === 404) return new DecisionApiError("NOT_FOUND", "找不到产品候选或三区评估。", status);
  if (status === 503) return new DecisionApiError("UNAVAILABLE", "三区评估服务尚未完成准入。", status);
  if (status === 408 || status === 504) return new DecisionApiError("TIMEOUT", "产品决策服务响应超时。", status);
  return new DecisionApiError("INVALID_RESPONSE", "产品决策服务拒绝了请求。", status);
}
