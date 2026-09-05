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
  version: number;
  strategy_id: string;
  title: string;
  description: string | null;
  status: "DRAFT" | "UNDER_REVIEW" | "APPROVED" | "RETIRED";
};

export type OpportunityLineage = {
  market_signal: {
    id: string;
    status: "DRAFT" | "ACTIVE" | "RETIRED";
    version: number;
    raw_text: string;
    source_ref: string | null;
    evidence_refs: string[];
  } | null;
  customer_insight: {
    id: string;
    status: "DRAFT" | "ACTIVE" | "RETIRED";
    version: number;
    statement: string;
    signal_id: string | null;
    evidence_refs: string[];
    ai_provenance: AiProvenance | null;
  } | null;
  opportunity: {
    id: string;
    status: "INVEST" | "EXPERIMENT" | "WATCH" | "MAINTAIN" | "EXIT";
    version: number;
    statement: string;
    insight_id: string;
    evidence_refs: string[];
    ai_provenance: AiProvenance | null;
  } | null;
  growth_problem: {
    id: string;
    status: "DRAFT" | "ACTIVE" | "RETIRED";
    version: number;
    symptom: string;
    opportunity_id: string | null;
    evidence_refs: string[];
  };
  growth_strategy: {
    id: string;
    status: "DRAFT" | "UNDER_REVIEW" | "APPROVED" | "RETIRED";
    version: number;
    statement: string;
    problem_id: string;
  };
  completeness: "STRUCTURALLY_COMPLETE_TO_OPPORTUNITY" | "INCOMPLETE_UPSTREAM";
  review_state: "NEEDS_HUMAN_DECISION";
  reason_codes: string[];
};

export type AiProvenance = {
  generated_by: string;
  model_ref: string;
  prompt_use_case_version: string;
  confidence: number;
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
  version: number;
  subject_type: "PRODUCT_CONCEPT";
  subject_ref: string;
  zone_policy_version_id: string;
  status: ZoneAssessmentStatus;
  recommended_zone: RecommendedZone;
  approved_zone: RecommendedZone | null;
  override_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_reason: string | null;
  dimension_assessments: ZoneDimensionAssessment[];
  differentiation_index: number;
  defensibility_index: number;
};

export type ProductConceptCandidate = {
  concept: ProductConceptSummary;
  assessment: ZoneAssessmentSummary;
  lineage: OpportunityLineage;
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
    const candidates = await Promise.all(normalized.map(async ({ conceptId, assessmentId }) => {
      const [chain, assessmentValue] = await Promise.all([
        this.getJson(`/product-intelligence/product-concepts/${encodeURIComponent(conceptId)}/chain`),
        this.getJson(`/product-intelligence/zone-assessments/${encodeURIComponent(assessmentId)}`),
      ]);
      const { concept, lineage } = validateConceptChain(chain, conceptId);
      const assessment = validateAssessment(assessmentValue, assessmentId, conceptId);
      return { concept, assessment, lineage };
    }));
    const opportunityScopes = new Set(candidates.map(({ lineage }) => lineage.opportunity
      ? `${lineage.opportunity.id}@v${lineage.opportunity.version}`
      : "MISSING"));
    if (opportunityScopes.size !== 1) {
      throw new DecisionApiError("INVALID_RESPONSE", "候选不属于同一个 Opportunity 决策范围。");
    }
    const zonePolicies = new Set(candidates.map(({ assessment }) => assessment.zone_policy_version_id));
    if (zonePolicies.size !== 1) {
      throw new DecisionApiError("INVALID_RESPONSE", "候选使用了不同的三区评估策略版本。");
    }
    return candidates;
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

function requiredVersion(record: Record<string, unknown>): number {
  const value = record.version;
  if (!Number.isInteger(value) || Number(value) < 1) {
    throw new DecisionApiError("INVALID_RESPONSE", "响应中的 version 无效。");
  }
  return Number(value);
}

function stringList(record: Record<string, unknown>, field: string): string[] {
  const value = record[field];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item.trim())) {
    throw new DecisionApiError("INVALID_RESPONSE", `响应中的 ${field} 无效。`);
  }
  const result = value.map((item) => (item as string).trim());
  if (new Set(result).size !== result.length) {
    throw new DecisionApiError("INVALID_RESPONSE", `响应中的 ${field} 包含重复引用。`);
  }
  return result;
}

function statusValue<T extends string>(record: Record<string, unknown>, allowed: readonly T[], field = "status"): T {
  const value = requiredString(record, field);
  if (!allowed.includes(value as T)) throw new DecisionApiError("INVALID_RESPONSE", `响应中的 ${field} 无效。`);
  return value as T;
}

function aiProvenance(record: Record<string, unknown>): AiProvenance | null {
  const values = [record.generated_by, record.model_ref, record.prompt_use_case_version, record.confidence];
  if (values.every((value) => value === null || value === undefined)) return null;
  if (values.some((value) => value === null || value === undefined)) {
    throw new DecisionApiError("INVALID_RESPONSE", "AI provenance 不完整。");
  }
  if (typeof record.confidence !== "number" || record.confidence < 0 || record.confidence > 1) {
    throw new DecisionApiError("INVALID_RESPONSE", "AI confidence 无效。");
  }
  return {
    generated_by: requiredString(record, "generated_by"),
    model_ref: requiredString(record, "model_ref"),
    prompt_use_case_version: requiredString(record, "prompt_use_case_version"),
    confidence: record.confidence as number,
  };
}

function nullableRecord(parent: Record<string, unknown>, field: string, label: string): Record<string, unknown> | null {
  if (!Object.prototype.hasOwnProperty.call(parent, field)) {
    throw new DecisionApiError("INVALID_RESPONSE", `${label} 字段缺失。`);
  }
  const value = parent[field];
  if (value === null || value === undefined) return null;
  return asRecord(value, `${label} 无效。`);
}

function validateConceptChain(value: unknown, requestedId: string): { concept: ProductConceptSummary; lineage: OpportunityLineage } {
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
  const conceptSummary: ProductConceptSummary = {
    id,
    version: requiredVersion(concept),
    strategy_id: requiredString(concept, "strategy_id"),
    title: requiredString(concept, "title"),
    description: typeof description === "string" ? description : null,
    status: status as ProductConceptSummary["status"],
  };
  const strategy = asRecord(chain.growth_strategy, "ProductConcept chain 缺少 growth_strategy。");
  const problem = asRecord(chain.growth_problem, "ProductConcept chain 缺少 growth_problem。");
  const opportunity = nullableRecord(chain, "opportunity", "Opportunity");
  const insight = nullableRecord(chain, "customer_insight", "CustomerInsight");
  const signal = nullableRecord(chain, "market_signal", "MarketSignal");
  const strategyId = requiredString(strategy, "id");
  const problemId = requiredString(problem, "id");
  if (conceptSummary.strategy_id !== strategyId || requiredString(strategy, "problem_id") !== problemId) {
    throw new DecisionApiError("INVALID_RESPONSE", "ProductConcept 到 GrowthProblem 的血缘冲突。");
  }
  const problemOpportunityId = optionalString(problem, "opportunity_id");
  if ((opportunity === null) !== (problemOpportunityId === null)) {
    throw new DecisionApiError("INVALID_RESPONSE", "GrowthProblem 与 Opportunity 血缘不完整。");
  }
  if (!opportunity && (insight || signal)) {
    throw new DecisionApiError("INVALID_RESPONSE", "上游 Opportunity 缺失但仍返回 Insight 或 Signal。");
  }
  const opportunityId = opportunity ? requiredString(opportunity, "id") : null;
  if (opportunityId && problemOpportunityId !== opportunityId) {
    throw new DecisionApiError("INVALID_RESPONSE", "GrowthProblem 与 Opportunity ID 不匹配。");
  }
  if (opportunity && !insight) {
    throw new DecisionApiError("INVALID_RESPONSE", "Opportunity 缺少其 CustomerInsight。");
  }
  const insightId = insight ? requiredString(insight, "id") : null;
  if (opportunity && requiredString(opportunity, "insight_id") !== insightId) {
    throw new DecisionApiError("INVALID_RESPONSE", "Opportunity 与 CustomerInsight ID 不匹配。");
  }
  const signalId = insight ? optionalString(insight, "signal_id") : null;
  if ((signal === null) !== (signalId === null)) {
    throw new DecisionApiError("INVALID_RESPONSE", "CustomerInsight 与 MarketSignal 血缘不完整。");
  }
  if (signal && requiredString(signal, "id") !== signalId) {
    throw new DecisionApiError("INVALID_RESPONSE", "CustomerInsight 与 MarketSignal ID 不匹配。");
  }
  const genericStatuses = ["DRAFT", "ACTIVE", "RETIRED"] as const;
  const lineage: OpportunityLineage = {
    market_signal: signal ? {
      id: requiredString(signal, "id"),
      status: statusValue(signal, genericStatuses),
      version: requiredVersion(signal),
      raw_text: requiredString(signal, "raw_text"),
      source_ref: optionalString(signal, "source_ref"),
      evidence_refs: stringList(signal, "evidence_refs"),
    } : null,
    customer_insight: insight ? {
      id: requiredString(insight, "id"),
      status: statusValue(insight, genericStatuses),
      version: requiredVersion(insight),
      statement: requiredString(insight, "statement"),
      signal_id: signalId,
      evidence_refs: stringList(insight, "evidence_refs"),
      ai_provenance: aiProvenance(insight),
    } : null,
    opportunity: opportunity ? {
      id: requiredString(opportunity, "id"),
      status: statusValue(opportunity, ["INVEST", "EXPERIMENT", "WATCH", "MAINTAIN", "EXIT"] as const),
      version: requiredVersion(opportunity),
      statement: requiredString(opportunity, "statement"),
      insight_id: requiredString(opportunity, "insight_id"),
      evidence_refs: stringList(opportunity, "evidence_refs"),
      ai_provenance: aiProvenance(opportunity),
    } : null,
    growth_problem: {
      id: problemId,
      status: statusValue(problem, genericStatuses),
      version: requiredVersion(problem),
      symptom: requiredString(problem, "symptom"),
      opportunity_id: problemOpportunityId,
      evidence_refs: stringList(problem, "evidence_refs"),
    },
    growth_strategy: {
      id: strategyId,
      status: statusValue(strategy, ["DRAFT", "UNDER_REVIEW", "APPROVED", "RETIRED"] as const),
      version: requiredVersion(strategy),
      statement: requiredString(strategy, "statement"),
      problem_id: requiredString(strategy, "problem_id"),
    },
    completeness: opportunity && insight && signal ? "STRUCTURALLY_COMPLETE_TO_OPPORTUNITY" : "INCOMPLETE_UPSTREAM",
    review_state: "NEEDS_HUMAN_DECISION",
    reason_codes: [
      "EVIDENCE_RECEIPT_HEALTH_NOT_IN_CONTRACT",
      "IMMUTABLE_OPPORTUNITY_DECISION_NOT_IN_CONTRACT",
      "PRODUCT_PACKAGE_BACKLINK_NOT_IN_CONTRACT",
    ],
  };
  return { concept: conceptSummary, lineage };
}

function validateAssessment(value: unknown, requestedId: string, conceptId: string): ZoneAssessmentSummary {
  const assessment = asRecord(value, "三区评估响应无效。");
  for (const field of ["approved_zone", "override_reason", "reviewed_by", "reviewed_at", "review_reason"]) {
    if (!Object.prototype.hasOwnProperty.call(assessment, field)) {
      throw new DecisionApiError("INVALID_RESPONSE", `三区评估缺少 ${field} 字段。`);
    }
  }
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
    throw new DecisionApiError("INVALID_RESPONSE", "三区评估状态不在允许的规则评估合同中。");
  }
  const recommendedZone = validateZone(assessment.recommended_zone, "recommended_zone");
  const approvedZone = assessment.approved_zone === null || assessment.approved_zone === undefined
    ? null
    : validateZone(assessment.approved_zone, "approved_zone");
  if (status === "APPROVED" && approvedZone === null) {
    throw new DecisionApiError("INVALID_RESPONSE", "已批准的三区评估缺少 approved_zone。");
  }
  const reviewedBy = optionalString(assessment, "reviewed_by");
  const reviewedAt = optionalTimestamp(assessment, "reviewed_at");
  const reviewReason = optionalString(assessment, "review_reason");
  const reviewFields = [reviewedBy, reviewedAt, reviewReason];
  if (reviewFields.some(Boolean) && !reviewFields.every(Boolean)) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区人工评审血缘必须同时包含 reviewer、时间和理由。");
  }
  if (["APPROVED", "REJECTED"].includes(status) && (!reviewedBy || !reviewedAt || !reviewReason)) {
    throw new DecisionApiError("INVALID_RESPONSE", "已完成的三区评审缺少 reviewer、时间或理由。");
  }
  if (status !== "APPROVED" && approvedZone !== null) {
    throw new DecisionApiError("INVALID_RESPONSE", "非 APPROVED 评估不得携带 approved_zone。");
  }
  const overrideReason = optionalString(assessment, "override_reason");
  if (status === "APPROVED" && approvedZone !== recommendedZone && !overrideReason) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区人工覆盖规则推荐时必须提供 override_reason。");
  }
  if (!Array.isArray(assessment.dimension_assessments) || assessment.dimension_assessments.length !== 6) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区评估必须包含完整六维规则评估。");
  }
  const dimensions = assessment.dimension_assessments.map(validateDimension);
  if (new Set(dimensions.map(({ dimension }) => dimension)).size !== 6
    || ZONE_DIMENSIONS.some((dimension) => !dimensions.some((item) => item.dimension === dimension))) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区评估六维规则评估存在缺失或重复。");
  }
  return {
    id,
    version: requiredVersion(assessment),
    subject_type: "PRODUCT_CONCEPT",
    subject_ref: subjectRef,
    zone_policy_version_id: requiredString(assessment, "zone_policy_version_id"),
    status: status as ZoneAssessmentStatus,
    recommended_zone: recommendedZone,
    approved_zone: approvedZone,
    override_reason: overrideReason,
    reviewed_by: reviewedBy,
    reviewed_at: reviewedAt,
    review_reason: reviewReason,
    dimension_assessments: dimensions,
    differentiation_index: requiredNumber(assessment, "differentiation_index"),
    defensibility_index: requiredNumber(assessment, "defensibility_index"),
  };
}

function optionalTimestamp(record: Record<string, unknown>, field: string): string | null {
  const value = optionalString(record, field);
  if (value === null) return null;
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(value) || Number.isNaN(Date.parse(value))) {
    throw new DecisionApiError("INVALID_RESPONSE", `响应中的 ${field} 必须是带时区时间。`);
  }
  return value;
}

function validateDimension(value: unknown): ZoneDimensionAssessment {
  const dimension = asRecord(value, "三区维度规则评估无效。");
  const name = requiredString(dimension, "dimension");
  if (!(ZONE_DIMENSIONS as readonly string[]).includes(name)) {
    throw new DecisionApiError("INVALID_RESPONSE", "三区维度名称无效。");
  }
  const evidenceRefs = dimension.evidence_refs;
  if (!Array.isArray(evidenceRefs) || evidenceRefs.length === 0
    || evidenceRefs.some((ref) => typeof ref !== "string" || !ref.trim())) {
    throw new DecisionApiError("INVALID_RESPONSE", `三区维度 ${name} 缺少有效 FACT_REF evidence_refs。`);
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
