import { ProductStudioApiError, type ProductStudioAccessTokenProvider, type ProductStudioFetch } from "./api";
import type { CourseLessonDraft } from "./courseContentTemplate";
import { validateCoursewareDraftCandidate, type CoursewareDraftCandidate } from "./coursewareGenerationApi";

export interface CoursewareGenerationClient {
  generate(systemId: string, request: CoursewareGenerationRequest): Promise<CoursewareDraftCandidate>;
}
export type CoursewareGenerationRequest = {
  lesson: CourseLessonDraft;
  evidence_refs: string[];
  context_snapshot_ref: string;
  provider_id: string;
  product_package_version_ref: string;
  course_system_version_ref: string;
  asset_bundle_version_ref: string;
  kind: CoursewareDraftCandidate["kind"];
};

export class HttpCoursewareGenerationClient implements CoursewareGenerationClient {
  constructor(private readonly options: { baseUrl?: string; fetchImpl?: ProductStudioFetch; accessToken?: string; accessTokenProvider?: ProductStudioAccessTokenProvider } = {}) {}
  async generate(systemId: string, request: CoursewareGenerationRequest): Promise<CoursewareDraftCandidate> {
    if (!systemId.trim()) throw new ProductStudioApiError("INVALID_INPUT", "缺少课程体系 ID。");
    let response: Response;
    try {
      const token = this.options.accessTokenProvider?.() ?? this.options.accessToken;
      const baseUrl = this.options.baseUrl ?? (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010");
      response = await (this.options.fetchImpl ?? globalThis.fetch.bind(globalThis))(`${baseUrl}/product-intelligence/courses/system/${encodeURIComponent(systemId)}/courseware-drafts`, { method: "POST", headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(request) });
    } catch { throw new ProductStudioApiError("UNAVAILABLE", "课件生成服务暂时不可达。"); }
    if (!response.ok) throw new ProductStudioApiError(response.status >= 500 ? "UNAVAILABLE" : "INVALID_RESPONSE", `课件生成请求失败（HTTP ${response.status}）。`, response.status);
    const body = await response.json() as { courseware_draft?: unknown };
    return validateCoursewareDraftCandidate(body.courseware_draft);
  }
}
