import { ProductStudioApiError, type ProductStudioFetch } from "./api";

export type LessonDeliveryProjection = {
  sequence: number;
  lesson_id: string;
  stage_id: string;
  product_outcome: string;
  family_action: string;
  courseware_refs: string[];
  status: "READY" | "MISSING_COURSEWARE" | "INCOMPLETE_LINEAGE";
};

export type CourseDeliveryProjection = {
  course_content_id: string;
  course_system_version_ref: string;
  product_component_id: string | null;
  lessons: LessonDeliveryProjection[];
  ready_lessons: number;
  blocked_lessons: number;
  publishable_to_service: boolean;
};

export interface CourseDeliveryProjectionApiClient {
  get(courseContentId: string): Promise<CourseDeliveryProjection>;
}

type Options = { baseUrl?: string; fetchImpl?: ProductStudioFetch; tenantScope?: string };

function validate(value: unknown): CourseDeliveryProjection {
  if (!value || typeof value !== "object") throw new ProductStudioApiError("INVALID_RESPONSE", "课程交付投影响应无效。");
  const row = value as Record<string, unknown>;
  if (typeof row.course_content_id !== "string" || typeof row.course_system_version_ref !== "string"
    || !Array.isArray(row.lessons) || !Number.isInteger(row.ready_lessons)
    || !Number.isInteger(row.blocked_lessons) || typeof row.publishable_to_service !== "boolean") {
    throw new ProductStudioApiError("INVALID_RESPONSE", "课程交付投影字段无效。");
  }
  const lessons = row.lessons.map((item, index) => {
    if (!item || typeof item !== "object") throw new ProductStudioApiError("INVALID_RESPONSE", `第${index + 1}节交付数据无效。`);
    const lesson = item as Record<string, unknown>;
    if (!Number.isInteger(lesson.sequence) || typeof lesson.lesson_id !== "string" || typeof lesson.stage_id !== "string"
      || typeof lesson.product_outcome !== "string" || typeof lesson.family_action !== "string"
      || !Array.isArray(lesson.courseware_refs) || !lesson.courseware_refs.every((ref) => typeof ref === "string")
      || !["READY", "MISSING_COURSEWARE", "INCOMPLETE_LINEAGE"].includes(String(lesson.status))) {
      throw new ProductStudioApiError("INVALID_RESPONSE", `第${index + 1}节交付字段无效。`);
    }
    return { sequence: Number(lesson.sequence), lesson_id: lesson.lesson_id, stage_id: lesson.stage_id, product_outcome: lesson.product_outcome, family_action: lesson.family_action, courseware_refs: lesson.courseware_refs as string[], status: lesson.status as LessonDeliveryProjection["status"] };
  });
  return { course_content_id: row.course_content_id, course_system_version_ref: row.course_system_version_ref, product_component_id: typeof row.product_component_id === "string" ? row.product_component_id : null, lessons, ready_lessons: Number(row.ready_lessons), blocked_lessons: Number(row.blocked_lessons), publishable_to_service: row.publishable_to_service };
}

export class HttpCourseDeliveryProjectionApiClient implements CourseDeliveryProjectionApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: ProductStudioFetch;
  private readonly tenantScope?: string;
  constructor(options: Options = {}) { this.baseUrl = options.baseUrl ?? ""; this.fetchImpl = options.fetchImpl ?? fetch; this.tenantScope = options.tenantScope?.trim() || undefined; }
  async get(courseContentId: string): Promise<CourseDeliveryProjection> {
    const response = await this.fetchImpl(`${this.baseUrl}/product-intelligence/courses/${encodeURIComponent(courseContentId)}/delivery-projection`, { headers: this.tenantScope ? { "x-tenant-scope": this.tenantScope } : undefined });
    if (!response.ok) throw new ProductStudioApiError(response.status === 404 ? "NOT_FOUND" : "UNAVAILABLE", "课程服务交付投影暂不可读取。", response.status);
    return validate(await response.json());
  }
}

