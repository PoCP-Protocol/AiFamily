import {
  ProductStudioApiError,
  type ProductStudioAccessTokenProvider,
  type ProductStudioFetch,
} from "./api";

export type ProductPackageReviewInput = {
  source_draft_locator: string;
  concept_id: string;
  zone_assessment_id: string;
  product_kind: "MICRO_CAMP" | "SCALE_PLAN" | "CUSTOM";
  duration_days: number;
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
  evidence_locators: string[];
  assumptions: string[];
  unknowns: string[];
  next_validation: string;
  requested_ttl_hours: number;
};

export type ProductPackageEvidenceClaimType =
  | "FAMILY_NEED"
  | "MARKET_EXISTENCE"
  | "COMPETITOR_CAPABILITY"
  | "GROWTH_MECHANISM"
  | "GROWTH_EFFECT"
  | "SAFETY_RISK"
  | "PRIVACY_CONSENT"
  | "CONTENT_ACCURACY"
  | "DELIVERY_FEASIBILITY"
  | "ENGAGEMENT_USABILITY";

export type EvidenceAdmissionProjection = {
  admission_status: "ADMITTED";
  reason_codes: [];
  claim_type: ProductPackageEvidenceClaimType;
  required_claim_refs: string[];
  required_applicability_refs: string[];
  receipt_id: string;
  receipt_hash: string;
  evidence_id: string;
  evidence_version: number;
  evidence_record_hash: string;
  evidence_ref: string;
  claim_scope: string[];
  applicability_scope: string[];
  criteria_refs: string[];
  verification_methods: string[];
  verification_purpose: "product_package_admission";
  verification_policy_version: string;
  receipt_outcome: "VERIFIED";
  integrity_check: "PASS";
  relevance: "RELEVANT";
  task_id: string;
  proposal_id: string;
  decision_id: string;
  verified_at: string;
  valid_until: string;
  admission_policy_version: string;
  admitted_at: string;
};

export type ProductPackageReviewDraft = {
  schema_version: "1.2";
  version: "1.2.0";
  status: "DRAFT";
  draft_id: string;
  version_id: string;
  concept_id: string;
  zone_assessment_id: string;
  approved_zone: "COMMODITY" | "ADVANTAGE" | "UNIQUE";
  product_kind: ProductPackageReviewInput["product_kind"];
  duration_days: number;
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
  evidence_refs: string[];
  evidence_admissions: EvidenceAdmissionProjection[];
  assumptions: string[];
  unknowns: string[];
  next_validation: string;
  source_draft_locator: string;
  source_provenance_ref: string;
  model_ref: string;
  prompt_use_case_version: string;
  intent_hash: string;
  resolved_request_hash: string;
  content_hash: string;
  created_at: string;
  expires_at: string;
};

export type ProductPackageReviewTask = {
  task_id: string;
  status: "OPEN" | "DECIDED" | "EXPIRED";
  proposal_id: string;
  action_name: "ADOPT_PRODUCT_CONCEPT_AS_DEFINITION";
  risk_level: "MEDIUM";
  provenance_ref: string;
  created_at: string;
  expires_at: string;
};

export type ProductPackageReviewResponse = {
  lifecycle_state: "SUBMITTED_FOR_REVIEW";
  draft: ProductPackageReviewDraft;
  review_task: ProductPackageReviewTask;
  etag: string;
  replayed: boolean;
};

export interface ProductPackageReviewApiClient {
  submit(input: ProductPackageReviewInput, idempotencyKey: string): Promise<ProductPackageReviewResponse>;
  get(draftId: string, expectedContentHash?: string): Promise<ProductPackageReviewResponse>;
}

type Options = {
  baseUrl?: string;
  fetchImpl?: ProductStudioFetch;
  accessToken?: string;
  accessTokenProvider?: ProductStudioAccessTokenProvider;
};

const REVIEW_PATH = "/product-intelligence/product-package-review-submissions";
const SHA256 = /^[0-9a-f]{64}$/;
const CLAIM_TYPES = new Set([
  "FAMILY_NEED", "MARKET_EXISTENCE", "COMPETITOR_CAPABILITY", "GROWTH_MECHANISM",
  "GROWTH_EFFECT", "SAFETY_RISK", "PRIVACY_CONSENT", "CONTENT_ACCURACY",
  "DELIVERY_FEASIBILITY", "ENGAGEMENT_USABILITY",
]);
const VERIFICATION_METHODS = new Set([
  "SOURCE_OPENED", "IDENTITY_CONFIRMED", "CROSS_SOURCE_CHECKED", "DOMAIN_EXPERT_REVIEWED",
  "SYSTEM_RECORD_MATCHED", "EVIDENCE_RECORD_HASH_MATCHED",
]);

export class HttpProductPackageReviewApiClient implements ProductPackageReviewApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: ProductStudioFetch;
  private readonly accessToken?: string;
  private readonly accessTokenProvider?: ProductStudioAccessTokenProvider;

  constructor(options: Options = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.accessToken = options.accessToken;
    this.accessTokenProvider = options.accessTokenProvider;
  }

  async submit(
    input: ProductPackageReviewInput,
    idempotencyKey: string,
  ): Promise<ProductPackageReviewResponse> {
    if (!idempotencyKey.trim()) {
      throw new ProductStudioApiError("INVALID_INPUT", "缺少幂等键，不能提交产品包评审。");
    }
    return this.request(REVIEW_PATH, {
      method: "POST",
      headers: {
        ...this.headers(),
        "content-type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(browserSafeBody(input)),
    }, input);
  }

  async get(draftId: string, expectedContentHash?: string): Promise<ProductPackageReviewResponse> {
    const normalized = draftId.trim();
    if (!normalized) {
      throw new ProductStudioApiError("INVALID_INPUT", "缺少 ProductPackage DRAFT ID。");
    }
    return this.request(`${REVIEW_PATH}/${encodeURIComponent(normalized)}`, {
      method: "GET",
      headers: this.headers(),
    }, undefined, normalized, expectedContentHash);
  }

  private headers(): Record<string, string> {
    const rawToken = this.accessTokenProvider?.() ?? this.accessToken;
    const token = rawToken?.trim();
    if (!token) return {};
    return { Authorization: token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}` };
  }

  private async request(
    path: string,
    init: RequestInit,
    expectedInput?: ProductPackageReviewInput,
    expectedDraftId?: string,
    expectedContentHash?: string,
  ): Promise<ProductPackageReviewResponse> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    } catch {
      throw new ProductStudioApiError("TIMEOUT", "ProductPackage 评审服务暂时不可达。");
    }
    if (!response.ok) throw await mapError(response);
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ProductStudioApiError("INVALID_RESPONSE", "ProductPackage 返回了不可解析的响应。", response.status);
    }
    return validateResponse(body, response.status, expectedInput, expectedDraftId, expectedContentHash);
  }
}

function browserSafeBody(input: ProductPackageReviewInput): ProductPackageReviewInput {
  return {
    source_draft_locator: input.source_draft_locator,
    concept_id: input.concept_id,
    zone_assessment_id: input.zone_assessment_id,
    product_kind: input.product_kind,
    duration_days: input.duration_days,
    primary_contradiction: input.primary_contradiction,
    demand_ref: input.demand_ref,
    market_insight_refs: input.market_insight_refs,
    competitor_evidence_refs: input.competitor_evidence_refs,
    component_ids: input.component_ids,
    skill_ids: input.skill_ids,
    success_metric_ids: input.success_metric_ids,
    guardrail_ids: input.guardrail_ids,
    stop_conditions: input.stop_conditions,
    pause_policy: input.pause_policy,
    human_gate_policy: input.human_gate_policy,
    evidence_locators: input.evidence_locators,
    assumptions: input.assumptions,
    unknowns: input.unknowns,
    next_validation: input.next_validation,
    requested_ttl_hours: input.requested_ttl_hours,
  };
}

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 不是对象。`);
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 缺失。`);
  }
  return value.trim();
}

function strings(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 缺失。`);
  }
  const items = value.map((item) => string(item, label));
  if (new Set(items).size !== items.length) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 包含重复项。`);
  }
  return items;
}

function timestamp(value: unknown, label: string): string {
  const normalized = string(value, label);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(normalized) || Number.isNaN(Date.parse(normalized))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 不是带时区的时间。`);
  }
  return normalized;
}

function sameInstant(left: string, right: string): boolean {
  return Date.parse(left) === Date.parse(right);
}

function sameItems(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function hash(value: unknown, label: string): string {
  const normalized = string(value, label);
  if (!SHA256.test(normalized)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 不是有效 SHA-256。`);
  }
  return normalized;
}

function admission(value: unknown): EvidenceAdmissionProjection {
  const item = object(value, "证据准入");
  if (item.admission_status !== "ADMITTED") {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据准入状态不是 ADMITTED。");
  }
  if (!Array.isArray(item.reason_codes) || item.reason_codes.length !== 0) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "ADMITTED 证据包含拒绝原因。");
  }
  const claimType = string(item.claim_type, "claim_type");
  if (!CLAIM_TYPES.has(claimType)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "claim_type 不在产品证据合同中。");
  }
  const requiredClaimRefs = strings(item.required_claim_refs, "required_claim_refs");
  const requiredApplicabilityRefs = strings(item.required_applicability_refs, "required_applicability_refs");
  const claimScope = strings(item.claim_scope, "claim_scope");
  const applicabilityScope = strings(item.applicability_scope, "applicability_scope");
  if (!requiredClaimRefs.every((ref) => claimScope.includes(ref))
    || !requiredApplicabilityRefs.every((ref) => applicabilityScope.includes(ref))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据凭证未覆盖产品包要求的主张或适用边界。");
  }
  const methods = strings(item.verification_methods, "verification_methods");
  if (methods.some((method) => !VERIFICATION_METHODS.has(method))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据验证方法不在允许合同中。");
  }
  if (!methods.includes("SOURCE_OPENED") || !methods.includes("EVIDENCE_RECORD_HASH_MATCHED")) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据验证缺少来源打开或记录哈希校验。");
  }
  if (item.verification_purpose !== "product_package_admission"
    || item.receipt_outcome !== "VERIFIED"
    || item.integrity_check !== "PASS"
    || item.relevance !== "RELEVANT"
    || item.verification_policy_version !== "product-evidence-verification:v1"
    || item.admission_policy_version !== "family-education-evidence-admission:v1") {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据准入治理结果不完整或无效。");
  }
  const verifiedAt = timestamp(item.verified_at, "verified_at");
  const admittedAt = timestamp(item.admitted_at, "admitted_at");
  const validUntil = timestamp(item.valid_until, "valid_until");
  if (Date.parse(verifiedAt) > Date.parse(admittedAt) || Date.parse(admittedAt) >= Date.parse(validUntil)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据准入时间窗口无效。");
  }
  const evidenceVersion = item.evidence_version;
  if (!Number.isInteger(evidenceVersion) || Number(evidenceVersion) < 1) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据版本无效。");
  }
  return {
    admission_status: "ADMITTED",
    reason_codes: [],
    claim_type: claimType as ProductPackageEvidenceClaimType,
    required_claim_refs: requiredClaimRefs,
    required_applicability_refs: requiredApplicabilityRefs,
    receipt_id: string(item.receipt_id, "receipt_id"),
    receipt_hash: hash(item.receipt_hash, "receipt_hash"),
    evidence_id: string(item.evidence_id, "evidence_id"),
    evidence_version: Number(evidenceVersion),
    evidence_record_hash: hash(item.evidence_record_hash, "evidence_record_hash"),
    evidence_ref: string(item.evidence_ref, "evidence_ref"),
    claim_scope: claimScope,
    applicability_scope: applicabilityScope,
    criteria_refs: strings(item.criteria_refs, "criteria_refs"),
    verification_methods: methods,
    verification_purpose: "product_package_admission",
    verification_policy_version: string(item.verification_policy_version, "verification_policy_version"),
    receipt_outcome: "VERIFIED",
    integrity_check: "PASS",
    relevance: "RELEVANT",
    task_id: string(item.task_id, "verification task_id"),
    proposal_id: string(item.proposal_id, "verification proposal_id"),
    decision_id: string(item.decision_id, "verification decision_id"),
    verified_at: verifiedAt,
    valid_until: validUntil,
    admission_policy_version: "family-education-evidence-admission:v1",
    admitted_at: admittedAt,
  };
}

function validateResponse(
  value: unknown,
  httpStatus?: number,
  expectedInput?: ProductPackageReviewInput,
  expectedDraftId?: string,
  expectedContentHash?: string,
): ProductPackageReviewResponse {
  const body = object(value, "ProductPackage 响应");
  if (body.lifecycle_state !== "SUBMITTED_FOR_REVIEW" || typeof body.replayed !== "boolean") {
    throw new ProductStudioApiError("INVALID_RESPONSE", "ProductPackage 生命周期响应无效。", httpStatus);
  }
  const rawDraft = object(body.draft, "ProductPackage DRAFT");
  if (rawDraft.status !== "DRAFT" || rawDraft.schema_version !== "1.2" || rawDraft.version !== "1.2.0") {
    throw new ProductStudioApiError("INVALID_RESPONSE", "ProductPackage 必须是 v1.2 DRAFT。", httpStatus);
  }
  const approvedZone = rawDraft.approved_zone;
  const productKind = rawDraft.product_kind;
  if (!["COMMODITY", "ADVANTAGE", "UNIQUE"].includes(String(approvedZone))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "服务端批准三区无效。", httpStatus);
  }
  if (!["MICRO_CAMP", "SCALE_PLAN", "CUSTOM"].includes(String(productKind))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "产品形态无效。", httpStatus);
  }
  const rawAdmissions = rawDraft.evidence_admissions;
  if (!Array.isArray(rawAdmissions) || rawAdmissions.length === 0) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "ProductPackage 缺少证据准入快照。", httpStatus);
  }
  const admissions = rawAdmissions.map(admission);
  const evidenceRefs = strings(rawDraft.evidence_refs, "evidence_refs");
  if (new Set(evidenceRefs).size !== evidenceRefs.length
    || evidenceRefs.length !== admissions.length
    || evidenceRefs.some((ref) => !admissions.some(({ receipt_id }) => receipt_id === ref))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据引用与准入快照不一致。", httpStatus);
  }
  const rawTask = object(body.review_task, "人工评审任务");
  if (!["OPEN", "DECIDED", "EXPIRED"].includes(String(rawTask.status))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "人工评审任务状态无效。", httpStatus);
  }
  const contentHash = hash(rawDraft.content_hash, "content_hash");
  if (expectedContentHash && contentHash !== expectedContentHash) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "回读的 ProductPackage 内容哈希发生漂移。", httpStatus);
  }
  const etag = string(body.etag, "etag");
  if (etag !== `"${contentHash}"`) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "ETag 与内容哈希不一致。", httpStatus);
  }
  const durationDays = rawDraft.duration_days;
  if (!Number.isInteger(durationDays) || Number(durationDays) < 1 || Number(durationDays) > 180) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "产品周期无效。", httpStatus);
  }
  const draftId = string(rawDraft.draft_id, "draft_id");
  const createdAt = timestamp(rawDraft.created_at, "created_at");
  const expiresAt = timestamp(rawDraft.expires_at, "expires_at");
  if (Date.parse(createdAt) >= Date.parse(expiresAt)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "ProductPackage 有效期窗口无效。", httpStatus);
  }
  if (admissions.some((item) => Date.parse(item.valid_until) < Date.parse(expiresAt)
    || !sameInstant(item.admitted_at, createdAt))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "证据凭证未覆盖 ProductPackage 的完整评审窗口。", httpStatus);
  }
  const taskCreatedAt = timestamp(rawTask.created_at, "review created_at");
  const taskExpiresAt = timestamp(rawTask.expires_at, "review expires_at");
  if (rawTask.action_name !== "ADOPT_PRODUCT_CONCEPT_AS_DEFINITION"
    || rawTask.risk_level !== "MEDIUM"
    || rawTask.provenance_ref !== `product-package-draft:${draftId}:${contentHash}`
    || !sameInstant(taskCreatedAt, createdAt)
    || !sameInstant(taskExpiresAt, expiresAt)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "人工评审任务与 ProductPackage DRAFT 血缘不一致。", httpStatus);
  }
  if (expectedDraftId && draftId !== expectedDraftId) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "回读结果与请求的 ProductPackage DRAFT 不一致。", httpStatus);
  }
  const draft = {
    schema_version: "1.2" as const,
    version: "1.2.0" as const,
    status: "DRAFT" as const,
    draft_id: draftId,
    version_id: string(rawDraft.version_id, "version_id"),
    concept_id: string(rawDraft.concept_id, "concept_id"),
    zone_assessment_id: string(rawDraft.zone_assessment_id, "zone_assessment_id"),
    approved_zone: approvedZone as ProductPackageReviewDraft["approved_zone"],
    product_kind: productKind as ProductPackageReviewDraft["product_kind"],
    duration_days: Number(durationDays),
    primary_contradiction: string(rawDraft.primary_contradiction, "primary_contradiction"),
    demand_ref: string(rawDraft.demand_ref, "demand_ref"),
    market_insight_refs: strings(rawDraft.market_insight_refs, "market_insight_refs"),
    competitor_evidence_refs: strings(rawDraft.competitor_evidence_refs, "competitor_evidence_refs"),
    component_ids: strings(rawDraft.component_ids, "component_ids"),
    skill_ids: strings(rawDraft.skill_ids, "skill_ids"),
    success_metric_ids: strings(rawDraft.success_metric_ids, "success_metric_ids"),
    guardrail_ids: strings(rawDraft.guardrail_ids, "guardrail_ids"),
    stop_conditions: strings(rawDraft.stop_conditions, "stop_conditions"),
    pause_policy: string(rawDraft.pause_policy, "pause_policy"),
    human_gate_policy: string(rawDraft.human_gate_policy, "human_gate_policy"),
    evidence_refs: evidenceRefs,
    evidence_admissions: admissions,
    assumptions: strings(rawDraft.assumptions, "assumptions"),
    unknowns: strings(rawDraft.unknowns, "unknowns"),
    next_validation: string(rawDraft.next_validation, "next_validation"),
    source_draft_locator: string(rawDraft.source_draft_locator, "source_draft_locator"),
    source_provenance_ref: string(rawDraft.source_provenance_ref, "source_provenance_ref"),
    model_ref: string(rawDraft.model_ref, "model_ref"),
    prompt_use_case_version: string(rawDraft.prompt_use_case_version, "prompt_use_case_version"),
    intent_hash: hash(rawDraft.intent_hash, "intent_hash"),
    resolved_request_hash: hash(rawDraft.resolved_request_hash, "resolved_request_hash"),
    content_hash: contentHash,
    created_at: createdAt,
    expires_at: expiresAt,
  };
  if (expectedInput && (
    draft.source_draft_locator !== expectedInput.source_draft_locator
    || draft.concept_id !== expectedInput.concept_id
    || draft.zone_assessment_id !== expectedInput.zone_assessment_id
    || draft.product_kind !== expectedInput.product_kind
    || draft.duration_days !== expectedInput.duration_days
    || draft.primary_contradiction !== expectedInput.primary_contradiction
    || draft.demand_ref !== expectedInput.demand_ref
    || draft.pause_policy !== expectedInput.pause_policy
    || draft.human_gate_policy !== expectedInput.human_gate_policy
    || draft.next_validation !== expectedInput.next_validation
    || !sameItems(draft.market_insight_refs, expectedInput.market_insight_refs)
    || !sameItems(draft.competitor_evidence_refs, expectedInput.competitor_evidence_refs)
    || !sameItems(draft.component_ids, expectedInput.component_ids)
    || !sameItems(draft.skill_ids, expectedInput.skill_ids)
    || !sameItems(draft.success_metric_ids, expectedInput.success_metric_ids)
    || !sameItems(draft.guardrail_ids, expectedInput.guardrail_ids)
    || !sameItems(draft.stop_conditions, expectedInput.stop_conditions)
    || !sameItems(draft.assumptions, expectedInput.assumptions)
    || !sameItems(draft.unknowns, expectedInput.unknowns)
    || !sameItems(draft.evidence_refs, expectedInput.evidence_locators)
    || Date.parse(draft.expires_at) > Date.parse(draft.created_at) + expectedInput.requested_ttl_hours * 60 * 60 * 1000
  )) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "服务端冻结的 ProductPackage 与本次设计意图不一致。", httpStatus);
  }
  return {
    lifecycle_state: "SUBMITTED_FOR_REVIEW",
    replayed: body.replayed,
    etag,
    draft,
    review_task: {
      task_id: string(rawTask.task_id, "review task_id"),
      status: rawTask.status as ProductPackageReviewTask["status"],
      proposal_id: string(rawTask.proposal_id, "review proposal_id"),
      action_name: "ADOPT_PRODUCT_CONCEPT_AS_DEFINITION",
      risk_level: "MEDIUM",
      provenance_ref: string(rawTask.provenance_ref, "review provenance_ref"),
      created_at: taskCreatedAt,
      expires_at: taskExpiresAt,
    },
  };
}

async function mapError(response: Response): Promise<ProductStudioApiError> {
  let detail = "ProductPackage 评审请求被拒绝。";
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) detail = body.detail;
  } catch {
    // Preserve a stable public message for non-JSON errors.
  }
  const code = response.status === 401 ? "UNAUTHORIZED"
    : response.status === 403 ? "FORBIDDEN"
      : response.status === 404 ? "NOT_FOUND"
        : response.status === 409 ? "CONFLICT"
          : response.status === 500 || response.status === 502 || response.status === 503 ? "UNAVAILABLE"
            : response.status === 408 || response.status === 504 ? "TIMEOUT"
              : "INVALID_INPUT";
  return new ProductStudioApiError(code, detail, response.status);
}
