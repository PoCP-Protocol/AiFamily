import {
  ProductStudioApiError,
  type ProductStudioAccessTokenProvider,
  type ProductStudioFetch,
} from "./api";

export type PublishedCourseLesson = {
  lesson_id: string;
  sequence: number;
  title: string;
  knowledge_point: string;
  action_task: string;
  media_asset_ids: string[];
  tool_refs: string[];
};

export type PublishedCourseContent = {
  id: string;
  version: number;
  status: "PUBLISHED";
  tenant_scope: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  title: string;
  product_component_id: string | null;
  problem_statement: string;
  assessment_criteria: string[];
  learning_goal: string;
  lessons: PublishedCourseLesson[];
  ai_coach_prompt_ref: string | null;
  review_cadence: string;
  outcome_metrics: string[];
  content_accuracy_claim_refs: string[];
  reviewed_by: string;
  reviewed_at: string;
  review_reason: string;
  published_at: string;
};

export interface CourseContentReadApiClient {
  listPublished(): Promise<PublishedCourseContent[]>;
  get(courseContentId: string): Promise<PublishedCourseContent>;
}

type Options = {
  baseUrl?: string;
  fetchImpl?: ProductStudioFetch;
  accessToken?: string;
  accessTokenProvider?: ProductStudioAccessTokenProvider;
};

const COURSE_PREFIX = "/product-intelligence/courses";
const COURSE_KEYS = new Set([
  "id", "version", "status", "tenant_scope", "created_by", "created_at", "updated_at",
  "title", "product_component_id", "problem_statement", "assessment_criteria", "learning_goal",
  "lessons", "ai_coach_prompt_ref", "review_cadence", "outcome_metrics",
  "content_accuracy_claim_refs", "reviewed_by", "reviewed_at", "review_reason", "published_at",
]);
const LESSON_KEYS = new Set([
  "lesson_id", "sequence", "title", "knowledge_point", "action_task", "media_asset_ids", "tool_refs",
]);

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 不是对象。`);
  }
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, allowed: Set<string>, label: string) {
  const unknown = Object.keys(value).filter((key) => !allowed.has(key));
  if (unknown.length) throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 含未知字段：${unknown.join("、")}。`);
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 缺失。`);
  }
  return value.trim();
}

function nullableText(value: unknown, label: string): string | null {
  if (value === null) return null;
  return text(value, label);
}

function textList(value: unknown, label: string, allowEmpty = false): string[] {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 必须是${allowEmpty ? "" : "非空"}数组。`);
  }
  const normalized = value.map((item) => text(item, label));
  if (new Set(normalized).size !== normalized.length) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 存在重复引用。`);
  }
  return normalized;
}

function instant(value: unknown, label: string): string {
  const normalized = text(value, label);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(normalized) || Number.isNaN(Date.parse(normalized))) {
    throw new ProductStudioApiError("INVALID_RESPONSE", `${label} 必须是带时区时间。`);
  }
  return normalized;
}

function lesson(value: unknown, index: number): PublishedCourseLesson {
  const item = record(value, `第 ${index + 1} 个课时`);
  exactKeys(item, LESSON_KEYS, `第 ${index + 1} 个课时`);
  if (!Number.isInteger(item.sequence) || Number(item.sequence) < 1) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "课时 sequence 无效。");
  }
  return {
    lesson_id: text(item.lesson_id, "lesson_id"),
    sequence: Number(item.sequence),
    title: text(item.title, "课时标题"),
    knowledge_point: text(item.knowledge_point, "知识点"),
    action_task: text(item.action_task, "行动任务"),
    media_asset_ids: textList(item.media_asset_ids, "课件资产引用", true),
    tool_refs: textList(item.tool_refs, "工具引用", true),
  };
}

export function validatePublishedCourse(value: unknown): PublishedCourseContent {
  const item = record(value, "CourseContent");
  exactKeys(item, COURSE_KEYS, "CourseContent");
  if (item.status !== "PUBLISHED" || !Number.isInteger(item.version) || Number(item.version) < 1) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "课程不是有效的 PUBLISHED 版本。");
  }
  if (!Array.isArray(item.lessons) || item.lessons.length === 0) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "课程没有课时。");
  }
  const lessons = item.lessons.map(lesson);
  const lessonIds = lessons.map((entry) => entry.lesson_id);
  const sequences = lessons.map((entry) => entry.sequence);
  if (new Set(lessonIds).size !== lessons.length || new Set(sequences).size !== lessons.length
    || sequences.some((sequence, index) => index > 0 && sequence <= sequences[index - 1])) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "课程课时身份或顺序不可信。");
  }
  const createdAt = instant(item.created_at, "created_at");
  const updatedAt = instant(item.updated_at, "updated_at");
  const reviewedAt = instant(item.reviewed_at, "reviewed_at");
  const publishedAt = instant(item.published_at, "published_at");
  if (Date.parse(createdAt) > Date.parse(updatedAt)
    || Date.parse(reviewedAt) > Date.parse(updatedAt)
    || Date.parse(publishedAt) > Date.parse(updatedAt)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "课程发布时间线不一致。");
  }
  return {
    id: text(item.id, "课程 ID"),
    version: Number(item.version),
    status: "PUBLISHED",
    tenant_scope: text(item.tenant_scope, "tenant_scope"),
    created_by: text(item.created_by, "created_by"),
    created_at: createdAt,
    updated_at: updatedAt,
    title: text(item.title, "课程名称"),
    product_component_id: nullableText(item.product_component_id, "product_component_id"),
    problem_statement: text(item.problem_statement, "问题陈述"),
    assessment_criteria: textList(item.assessment_criteria, "评估标准"),
    learning_goal: text(item.learning_goal, "学习目标"),
    lessons,
    ai_coach_prompt_ref: nullableText(item.ai_coach_prompt_ref, "ai_coach_prompt_ref"),
    review_cadence: text(item.review_cadence, "复盘节奏"),
    outcome_metrics: textList(item.outcome_metrics, "结果指标"),
    content_accuracy_claim_refs: textList(item.content_accuracy_claim_refs, "内容准确性 claim 引用"),
    reviewed_by: text(item.reviewed_by, "reviewed_by"),
    reviewed_at: reviewedAt,
    review_reason: text(item.review_reason, "review_reason"),
    published_at: publishedAt,
  };
}

export function validatePublishedCourseList(value: unknown): PublishedCourseContent[] {
  if (!Array.isArray(value)) throw new ProductStudioApiError("INVALID_RESPONSE", "已发布课程响应不是数组。");
  const courses = value.map(validatePublishedCourse);
  if (new Set(courses.map((course) => course.id)).size !== courses.length) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "已发布课程存在重复 ID。");
  }
  return courses;
}

export class HttpCourseContentReadApiClient implements CourseContentReadApiClient {
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

  listPublished(): Promise<PublishedCourseContent[]> {
    return this.read(`${COURSE_PREFIX}/published`, validatePublishedCourseList);
  }

  get(courseContentId: string): Promise<PublishedCourseContent> {
    const id = courseContentId.trim();
    if (!id) return Promise.reject(new ProductStudioApiError("INVALID_INPUT", "缺少课程 ID。"));
    return this.read(`${COURSE_PREFIX}/${encodeURIComponent(id)}`, validatePublishedCourse);
  }

  private async read<T>(path: string, validate: (value: unknown) => T): Promise<T> {
    let response: Response;
    try {
      const token = this.accessTokenProvider?.() ?? this.accessToken;
      response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: "GET",
        headers: token ? { authorization: `Bearer ${token}` } : {},
      });
    } catch {
      throw new ProductStudioApiError("TIMEOUT", "课程目录暂时不可达。");
    }
    if (!response.ok) {
      const code = response.status === 401 ? "UNAUTHORIZED"
        : response.status === 403 ? "FORBIDDEN"
          : response.status === 404 ? "NOT_FOUND" : response.status >= 500 ? "UNAVAILABLE" : "INVALID_RESPONSE";
      throw new ProductStudioApiError(code, `课程目录请求失败（HTTP ${response.status}）。`, response.status);
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ProductStudioApiError("INVALID_RESPONSE", "课程目录返回了不可解析的响应。", response.status);
    }
    return validate(body);
  }
}
