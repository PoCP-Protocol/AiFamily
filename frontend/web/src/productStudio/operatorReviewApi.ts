export type ReviewOutcome = "ACCEPT" | "REJECT" | "ESCALATE";
export type ReviewTaskStatus = "OPEN" | "DECIDED" | "EXPIRED";

export type ProductDefinitionAdoptionArguments = {
  concept_id: string;
  zone_assessment_id: string;
  source_decision_draft_ref: string;
  product_kind: "MICRO_CAMP" | "SCALE_PLAN" | "CUSTOM";
  duration_days: number;
  primary_contradiction: string;
  demand_ref: string;
  market_insight_refs: string[];
  component_ids: string[];
  skill_ids: string[];
  success_metric_ids: string[];
  guardrail_ids: string[];
  stop_conditions: string[];
  pause_policy: string;
  human_gate_policy: string;
};

export type ProductDefinitionReviewTask = {
  task_id: string;
  status: ReviewTaskStatus;
  proposal_id: string;
  draft_id: string;
  action_name: "ADOPT_PRODUCT_CONCEPT_AS_DEFINITION";
  action_arguments: ProductDefinitionAdoptionArguments;
  risk_level: string;
  provenance_ref: string;
  created_at: string;
  expires_at: string;
  etag: string;
  decision_id: string | null;
  decision_outcome: ReviewOutcome | null;
  decision_reason: string | null;
  decided_at: string | null;
  request_id: string | null;
};

export type ProductDefinitionReviewDecision = {
  task: ProductDefinitionReviewTask;
  actor_id: string;
  execution_status: "PENDING" | "NOT_APPLICABLE";
};

export type OperatorReviewErrorCode =
  | "INVALID_INPUT"
  | "INVALID_RESPONSE"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "CONFLICT"
  | "UNAVAILABLE"
  | "TIMEOUT";

export class OperatorReviewApiError extends Error {
  readonly code: OperatorReviewErrorCode;
  readonly httpStatus?: number;

  constructor(code: OperatorReviewErrorCode, message: string, httpStatus?: number) {
    super(message);
    this.name = "OperatorReviewApiError";
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

export interface OperatorReviewApiClient {
  listOpenTasks(): Promise<ProductDefinitionReviewTask[]>;
  getTask(
    taskId: string,
    expected?: ProductDefinitionReviewTask,
  ): Promise<ProductDefinitionReviewTask>;
  decide(
    task: ProductDefinitionReviewTask,
    outcome: ReviewOutcome,
    reason: string,
    idempotencyKey: string,
  ): Promise<ProductDefinitionReviewDecision>;
}

type OperatorReviewFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
type AccessTokenProvider = () => string | undefined;
type ClientOptions = {
  baseUrl?: string;
  fetchImpl?: OperatorReviewFetch;
  accessToken?: string;
  accessTokenProvider?: AccessTokenProvider;
};

const PREFIX = "/product-intelligence/operator/product-definition-review-tasks";

export class HttpOperatorReviewApiClient implements OperatorReviewApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: OperatorReviewFetch;
  private readonly accessToken?: string;
  private readonly accessTokenProvider?: AccessTokenProvider;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? "";
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.accessToken = options.accessToken;
    this.accessTokenProvider = options.accessTokenProvider;
  }

  async listOpenTasks(): Promise<ProductDefinitionReviewTask[]> {
    const body = asRecord(await this.request(PREFIX, { method: "GET" }), "评审队列响应无效。");
    if (!Array.isArray(body.items)) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "评审队列缺少 items。");
    }
    const tasks = body.items.map((item) => validateTask(item));
    if (tasks.some(({ status }) => status !== "OPEN")) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "评审队列只能包含 OPEN 任务。");
    }
    return tasks;
  }

  async getTask(
    taskId: string,
    expected?: ProductDefinitionReviewTask,
  ): Promise<ProductDefinitionReviewTask> {
    const normalized = taskId.trim();
    if (!normalized) throw new OperatorReviewApiError("INVALID_INPUT", "缺少 task_id。");
    const task = validateTask(await this.request(`${PREFIX}/${encodeURIComponent(normalized)}`, {
      method: "GET",
    }));
    if (task.task_id !== normalized) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "评审任务 ID 与请求不一致。");
    }
    if (expected && !sameProposal(task, expected)) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "评审任务提案已变化，请刷新队列。");
    }
    return task;
  }

  async decide(
    task: ProductDefinitionReviewTask,
    outcome: ReviewOutcome,
    reason: string,
    idempotencyKey: string,
  ): Promise<ProductDefinitionReviewDecision> {
    if (!reason.trim() || !idempotencyKey.trim()) {
      throw new OperatorReviewApiError("INVALID_INPUT", "决策理由和幂等键不能为空。");
    }
    const value = asRecord(await this.request(
      `${PREFIX}/${encodeURIComponent(task.task_id)}/decision`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "Idempotency-Key": idempotencyKey,
          "If-Match": task.etag,
        },
        body: JSON.stringify({ outcome, reason: reason.trim() }),
      },
    ), "评审决定响应无效。");
    const decided = validateTask(value.task);
    const actorId = requiredString(value, "actor_id");
    const executionStatus = requiredEnum(value, "execution_status", ["PENDING", "NOT_APPLICABLE"] as const);
    if (
      decided.task_id !== task.task_id
      || decided.proposal_id !== task.proposal_id
      || !sameProposal(decided, task)
      || decided.provenance_ref !== task.provenance_ref
      || decided.status !== "DECIDED"
      || decided.decision_outcome !== outcome
      || decided.decision_reason !== reason.trim()
    ) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "服务端决定与已审阅提案不一致。");
    }
    if (outcome === "ACCEPT" && (!decided.request_id || executionStatus !== "PENDING")) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "接受决定缺少待执行 Named Action。");
    }
    if (outcome !== "ACCEPT" && (decided.request_id || executionStatus !== "NOT_APPLICABLE")) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "非接受决定不得生成 Named Action。");
    }
    return { task: decided, actor_id: actorId, execution_status: executionStatus };
  }

  private async request(path: string, init: RequestInit): Promise<unknown> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers: { ...this.authorizationHeaders(), ...init.headers },
      });
    } catch {
      throw new OperatorReviewApiError("TIMEOUT", "PDM 人工评审服务暂时不可达。");
    }
    if (!response.ok) throw mapHttpError(response.status);
    try {
      return await response.json();
    } catch {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "PDM 人工评审响应无法解析。", response.status);
    }
  }

  private authorizationHeaders(): Record<string, string> {
    const token = (this.accessTokenProvider?.() ?? this.accessToken)?.trim();
    if (!token) return {};
    return { Authorization: token.toLowerCase().startsWith("bearer ") ? token : `Bearer ${token}` };
  }
}

function asRecord(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", message);
  }
  return value as Record<string, unknown>;
}

function requiredString(record: Record<string, unknown>, field: string): string {
  const value = record[field];
  if (typeof value !== "string" || !value.trim()) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", `响应缺少 ${field}。`);
  }
  return value.trim();
}

function nullableString(record: Record<string, unknown>, field: string): string | null {
  const value = record[field];
  if (value === null) return null;
  if (typeof value !== "string" || !value.trim()) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", `响应中的 ${field} 无效。`);
  }
  return value.trim();
}

function requiredEnum<const T extends readonly string[]>(
  record: Record<string, unknown>,
  field: string,
  values: T,
): T[number] {
  const value = requiredString(record, field);
  if (!values.includes(value)) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", `响应中的 ${field} 无效。`);
  }
  return value as T[number];
}

function validateTask(value: unknown): ProductDefinitionReviewTask {
  const task = asRecord(value, "评审任务响应无效。");
  const actionArguments = validateActionArguments(task.action_arguments);
  const actionName = requiredString(task, "action_name");
  if (actionName !== "ADOPT_PRODUCT_CONCEPT_AS_DEFINITION") {
    throw new OperatorReviewApiError("INVALID_RESPONSE", "评审任务不是产品定义采纳动作。");
  }
  const status = requiredEnum(task, "status", ["OPEN", "DECIDED", "EXPIRED"] as const);
  const outcome = task.decision_outcome === null
    ? null
    : requiredEnum(task, "decision_outcome", ["ACCEPT", "REJECT", "ESCALATE"] as const);
  const createdAt = requiredString(task, "created_at");
  const expiresAt = requiredString(task, "expires_at");
  if (!Number.isFinite(Date.parse(createdAt)) || !Number.isFinite(Date.parse(expiresAt))) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", "评审任务时间无效。");
  }
  const result: ProductDefinitionReviewTask = {
    task_id: requiredString(task, "task_id"),
    status,
    proposal_id: requiredString(task, "proposal_id"),
    draft_id: requiredString(task, "draft_id"),
    action_name: actionName,
    action_arguments: actionArguments,
    risk_level: requiredString(task, "risk_level"),
    provenance_ref: requiredString(task, "provenance_ref"),
    created_at: createdAt,
    expires_at: expiresAt,
    etag: requiredString(task, "etag"),
    decision_id: nullableString(task, "decision_id"),
    decision_outcome: outcome,
    decision_reason: nullableString(task, "decision_reason"),
    decided_at: nullableString(task, "decided_at"),
    request_id: nullableString(task, "request_id"),
  };
  const hasDecision = result.decision_id !== null
    || result.decision_outcome !== null
    || result.decision_reason !== null
    || result.decided_at !== null;
  if (result.status === "DECIDED") {
    if (!result.decision_id || !result.decision_outcome || !result.decision_reason || !result.decided_at) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "DECIDED 任务缺少完整人工决定快照。");
    }
    if (!Number.isFinite(Date.parse(result.decided_at))) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "DECIDED 任务的 decided_at 无效。");
    }
    if (result.decision_outcome === "ACCEPT" ? !result.request_id : result.request_id !== null) {
      throw new OperatorReviewApiError("INVALID_RESPONSE", "人工决定与 Named Action 状态不一致。");
    }
  } else if (hasDecision || result.request_id !== null) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", `${result.status} 任务不得携带人工决定。`);
  }
  return result;
}

const ADOPTION_ARGUMENT_KEYS = [
  "concept_id",
  "zone_assessment_id",
  "source_decision_draft_ref",
  "product_kind",
  "duration_days",
  "primary_contradiction",
  "demand_ref",
  "market_insight_refs",
  "component_ids",
  "skill_ids",
  "success_metric_ids",
  "guardrail_ids",
  "stop_conditions",
  "pause_policy",
  "human_gate_policy",
] as const;

function stringArray(
  record: Record<string, unknown>,
  field: string,
  allowEmpty = false,
): string[] {
  const value = record[field];
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0)
    || value.some((item) => typeof item !== "string" || !item.trim())) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", `action_arguments.${field} 无效。`);
  }
  const normalized = value.map((item) => String(item).trim());
  if (new Set(normalized).size !== normalized.length) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", `action_arguments.${field} 不得重复。`);
  }
  return normalized;
}

function validateActionArguments(value: unknown): ProductDefinitionAdoptionArguments {
  const args = asRecord(value, "评审任务缺少只读 action_arguments。");
  const keys = Object.keys(args).sort();
  const allowed = [...ADOPTION_ARGUMENT_KEYS].sort();
  if (keys.length !== allowed.length || keys.some((key, index) => key !== allowed[index])) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", "action_arguments 字段集合无效。");
  }
  const kind = requiredEnum(args, "product_kind", ["MICRO_CAMP", "SCALE_PLAN", "CUSTOM"] as const);
  const duration = args.duration_days;
  if (typeof duration !== "number" || !Number.isInteger(duration) || duration < 1 || duration > 180) {
    throw new OperatorReviewApiError("INVALID_RESPONSE", "action_arguments.duration_days 无效。");
  }
  return {
    concept_id: requiredString(args, "concept_id"),
    zone_assessment_id: requiredString(args, "zone_assessment_id"),
    source_decision_draft_ref: requiredString(args, "source_decision_draft_ref"),
    product_kind: kind,
    duration_days: duration,
    primary_contradiction: requiredString(args, "primary_contradiction"),
    demand_ref: requiredString(args, "demand_ref"),
    market_insight_refs: stringArray(args, "market_insight_refs"),
    component_ids: stringArray(args, "component_ids"),
    skill_ids: stringArray(args, "skill_ids"),
    success_metric_ids: stringArray(args, "success_metric_ids"),
    guardrail_ids: stringArray(args, "guardrail_ids", true),
    stop_conditions: stringArray(args, "stop_conditions"),
    pause_policy: requiredString(args, "pause_policy"),
    human_gate_policy: requiredString(args, "human_gate_policy"),
  };
}

function sameProposal(
  left: ProductDefinitionReviewTask,
  right: ProductDefinitionReviewTask,
): boolean {
  return left.task_id === right.task_id
    && left.proposal_id === right.proposal_id
    && left.draft_id === right.draft_id
    && left.action_name === right.action_name
    && left.risk_level === right.risk_level
    && left.provenance_ref === right.provenance_ref
    && left.created_at === right.created_at
    && left.expires_at === right.expires_at
    && JSON.stringify(left.action_arguments) === JSON.stringify(right.action_arguments);
}

function mapHttpError(status: number): OperatorReviewApiError {
  if (status === 401) return new OperatorReviewApiError("UNAUTHORIZED", "请先登录。", status);
  if (status === 403) return new OperatorReviewApiError("FORBIDDEN", "没有 PDM 人工评审权限。", status);
  if (status === 404) return new OperatorReviewApiError("NOT_FOUND", "评审任务不存在或不可见。", status);
  if (status === 409 || status === 412) {
    return new OperatorReviewApiError("CONFLICT", "任务已变化，请刷新后重新审阅。", status);
  }
  return new OperatorReviewApiError("UNAVAILABLE", "PDM 人工评审服务暂时不可用。", status);
}
