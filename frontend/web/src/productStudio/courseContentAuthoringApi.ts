import {
  ProductStudioApiError,
  type ProductStudioAccessTokenProvider,
  type ProductStudioFetch,
} from "./api";
import type { CourseContentDraftInput, CourseLessonDraft } from "./courseContentTemplate";

export type CourseContentDraftResponse = CourseContentDraftInput & {
  id: string;
  version: 1;
  status: "DRAFT";
  tenant_scope: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  reviewed_by: null;
  reviewed_at: null;
  review_reason: null;
  published_at: null;
};

export interface CourseContentAuthoringApiClient {
  createDraft(input: CourseContentDraftInput): Promise<CourseContentDraftResponse>;
  getDraft(courseContentId: string): Promise<CourseContentDraftResponse>;
}

type Options = {
  baseUrl?: string;
  fetchImpl?: ProductStudioFetch;
  accessToken?: string;
  accessTokenProvider?: ProductStudioAccessTokenProvider;
};

const COURSE_PREFIX = "/product-intelligence/courses";
const COURSE_KEYS = new Set([
  "id", "version", "status", "tenant_scope", "created_by", "created_at", "updated_at", "title",
  "product_component_id", "problem_statement", "assessment_criteria", "learning_goal", "lessons",
  "ai_coach_prompt_ref", "review_cadence", "outcome_metrics", "content_accuracy_claim_refs",
  "reviewed_by", "reviewed_at", "review_reason", "published_at",
]);
const LESSON_KEYS = new Set([
  "lesson_id", "sequence", "title", "knowledge_point", "action_task", "media_asset_ids", "tool_refs",
]);

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 不是对象。`);
  }
  return value as Record<string, unknown>;
}

function requireExactKeys(value: Record<string, unknown>, keys: Set<string>, label: string) {
  const unknown = Object.keys(value).filter((key) => !keys.has(key));
  const missing = [...keys].filter((key) => !(key in value));
  if (unknown.length || missing.length) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 字段集合不可信。`);
  }
}

function requiredText(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 缺失。`);
  }
  return value.trim();
}

function optionalText(value: unknown, label: string): string | null {
  return value === null ? null : requiredText(value, label);
}

function requiredTextList(value: unknown, label: string, allowEmpty = false): string[] {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 数组无效。`);
  }
  const values = value.map((item) => requiredText(item, label));
  if (new Set(values).size !== values.length) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 存在重复项。`);
  }
  return values;
}

function requiredInstant(value: unknown, label: string): string {
  const instant = requiredText(value, label);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(instant) || Number.isNaN(Date.parse(instant))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 必须是带时区时间。`);
  }
  return instant;
}

function validateLesson(value: unknown, index: number): CourseLessonDraft {
  const lesson = asRecord(value, `第 ${index + 1} 个课时`);
  requireExactKeys(lesson, LESSON_KEYS, `第 ${index + 1} 个课时`);
  if (!Number.isInteger(lesson.sequence) || Number(lesson.sequence) !== index + 1) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "DRAFT 课时顺序发生漂移。");
  }
  return {
    lesson_id: requiredText(lesson.lesson_id, "lesson_id"),
    sequence: Number(lesson.sequence),
    title: requiredText(lesson.title, "课时标题"),
    knowledge_point: requiredText(lesson.knowledge_point, "知识点"),
    action_task: requiredText(lesson.action_task, "行动任务"),
    media_asset_ids: requiredTextList(lesson.media_asset_ids, "课件资产引用", true),
    tool_refs: requiredTextList(lesson.tool_refs, "工具引用", true),
  };
}

export function validateCourseContentDraftResponse(value: unknown): CourseContentDraftResponse {
  const draft = asRecord(value, "CourseContent DRAFT");
  requireExactKeys(draft, COURSE_KEYS, "CourseContent DRAFT");
  if (draft.status !== "DRAFT" || draft.version !== 1) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "服务端未返回初始 DRAFT 版本。");
  }
  if (draft.reviewed_by !== null || draft.reviewed_at !== null
    || draft.review_reason !== null || draft.published_at !== null) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "服务端伪造了尚未发生的审核或发布时间。");
  }
  if (draft.product_component_id !== null) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "服务端改变了尚未开放的产品组件血缘字段。");
  }
  if (!Array.isArray(draft.lessons) || draft.lessons.length !== 24) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "服务端回读不是24课时模板。");
  }
  const lessons = draft.lessons.map(validateLesson);
  if (new Set(lessons.map((lesson) => lesson.lesson_id)).size !== lessons.length) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "服务端回读存在重复课时 ID。");
  }
  const createdAt = requiredInstant(draft.created_at, "created_at");
  const updatedAt = requiredInstant(draft.updated_at, "updated_at");
  if (Date.parse(createdAt) > Date.parse(updatedAt)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "DRAFT 时间线无效。");
  }
  return {
    id: requiredText(draft.id, "课程 ID"),
    version: 1,
    status: "DRAFT",
    tenant_scope: requiredText(draft.tenant_scope, "tenant_scope"),
    created_by: requiredText(draft.created_by, "created_by"),
    created_at: createdAt,
    updated_at: updatedAt,
    title: requiredText(draft.title, "课程名称"),
    product_component_id: null,
    problem_statement: requiredText(draft.problem_statement, "问题陈述"),
    assessment_criteria: requiredTextList(draft.assessment_criteria, "评估标准"),
    learning_goal: requiredText(draft.learning_goal, "学习目标"),
    lessons,
    ai_coach_prompt_ref: optionalText(draft.ai_coach_prompt_ref, "ai_coach_prompt_ref"),
    review_cadence: requiredText(draft.review_cadence, "复盘节奏"),
    outcome_metrics: requiredTextList(draft.outcome_metrics, "结果指标"),
    content_accuracy_claim_refs: requiredTextList(draft.content_accuracy_claim_refs, "内容 claim 引用"),
    reviewed_by: null,
    reviewed_at: null,
    review_reason: null,
    published_at: null,
  };
}

function designProjection(draft: CourseContentDraftResponse): CourseContentDraftInput {
  return {
    title: draft.title,
    problem_statement: draft.problem_statement,
    assessment_criteria: draft.assessment_criteria,
    learning_goal: draft.learning_goal,
    lessons: draft.lessons,
    review_cadence: draft.review_cadence,
    outcome_metrics: draft.outcome_metrics,
    content_accuracy_claim_refs: draft.content_accuracy_claim_refs,
    product_component_id: null,
    ai_coach_prompt_ref: draft.ai_coach_prompt_ref,
  };
}

export function assertCourseDraftReadBack(
  input: CourseContentDraftInput,
  created: CourseContentDraftResponse,
  readBack: CourseContentDraftResponse,
): CourseContentDraftResponse {
  if (created.id !== readBack.id || created.tenant_scope !== readBack.tenant_scope
    || created.created_by !== readBack.created_by || JSON.stringify(created) !== JSON.stringify(readBack)
    || JSON.stringify(input) !== JSON.stringify(designProjection(readBack))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "CourseContent DRAFT 创建结果与持久化回读不一致。");
  }
  return readBack;
}

export class HttpCourseContentAuthoringApiClient implements CourseContentAuthoringApiClient {
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

  createDraft(input: CourseContentDraftInput): Promise<CourseContentDraftResponse> {
    return this.request("", { method: "POST", body: JSON.stringify(input) }, true);
  }

  async getDraft(courseContentId: string): Promise<CourseContentDraftResponse> {
    const id = courseContentId.trim();
    if (!id) throw new ProductStudioApiError("INVALID_INPUT", "缺少课程 ID，无法回读。");
    return this.request(`/${encodeURIComponent(id)}`, { method: "GET" }, false);
  }

  private async request(path: string, init: RequestInit, createsState: boolean): Promise<CourseContentDraftResponse> {
    let response: Response;
    try {
      const token = this.accessTokenProvider?.() ?? this.accessToken;
      response = await this.fetchImpl(`${this.baseUrl}${COURSE_PREFIX}${path}`, {
        ...init,
        headers: {
          ...(init.body ? { "content-type": "application/json" } : {}),
          ...(token ? { authorization: `Bearer ${token}` } : {}),
        },
      });
    } catch {
      throw new ProductStudioApiError(
        createsState ? "UNKNOWN_OUTCOME" : "TIMEOUT",
        createsState
          ? "创建请求的结果未知；为避免重复课程，请勿自动重试，等待恢复查询能力后核查。"
          : "CourseContent DRAFT 回读暂时不可达。",
      );
    }
    if (!response.ok) {
      const code = response.status === 401 ? "UNAUTHORIZED"
        : response.status === 403 ? "FORBIDDEN"
          : response.status === 404 ? "NOT_FOUND"
            : response.status >= 500 ? "UNAVAILABLE" : "INVALID_RESPONSE";
      throw new ProductStudioApiError(code, `CourseContent 请求失败（HTTP ${response.status}）。`, response.status);
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ProductStudioApiError("INVALID_RESPONSE", "CourseContent 返回了不可解析的响应。", response.status);
    }
    return validateCourseContentDraftResponse(body);
  }
}
