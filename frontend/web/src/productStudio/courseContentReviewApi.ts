import { ProductStudioApiError, type ProductStudioAccessTokenProvider, type ProductStudioFetch } from "./api";

export type CourseReviewSubmission = { course: { id: string; status: "UNDER_REVIEW" }; task_id: string };
export type CourseReviewDecision = { course: { id: string; status: "DRAFT" | "PUBLISHED" }; task_id: string };

export interface CourseContentReviewApiClient {
  submitForReview(courseContentId: string): Promise<CourseReviewSubmission>;
  decide(courseContentId: string, input: { task_id: string; approved: boolean; reason: string }): Promise<CourseReviewDecision>;
}

type Options = { baseUrl?: string; fetchImpl?: ProductStudioFetch; accessToken?: string; accessTokenProvider?: ProductStudioAccessTokenProvider };
const PREFIX = "/product-intelligence/courses";

export class HttpCourseContentReviewApiClient implements CourseContentReviewApiClient {
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

  submitForReview(courseContentId: string) {
    const id = this.requireId(courseContentId);
    return this.request<CourseReviewSubmission>(`/${encodeURIComponent(id)}/submit-for-review`, { method: "POST", body: JSON.stringify({}) });
  }

  decide(courseContentId: string, input: { task_id: string; approved: boolean; reason: string }) {
    const id = this.requireId(courseContentId);
    if (!input.task_id.trim() || !input.reason.trim()) return Promise.reject(new ProductStudioApiError("INVALID_INPUT", "审核任务和理由不能为空。"));
    return this.request<CourseReviewDecision>(`/${encodeURIComponent(id)}/review-decision`, { method: "POST", body: JSON.stringify(input) });
  }

  private requireId(value: string) { const id = value.trim(); if (!id) throw new ProductStudioApiError("INVALID_INPUT", "缺少课程 ID。"); return id; }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    let response: Response;
    try {
      const token = this.accessTokenProvider?.() ?? this.accessToken;
      response = await this.fetchImpl(`${this.baseUrl}${PREFIX}${path}`, { ...init, headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) } });
    } catch { throw new ProductStudioApiError("UNKNOWN_OUTCOME", "审核请求结果未知，请先回读课程状态。", undefined); }
    if (!response.ok) throw new ProductStudioApiError(response.status === 403 ? "FORBIDDEN" : response.status >= 500 ? "UNAVAILABLE" : "INVALID_RESPONSE", `课程审核请求失败（HTTP ${response.status}）。`, response.status);
    try { return await response.json() as T; } catch { throw new ProductStudioApiError("INVALID_RESPONSE", "课程审核响应不可解析。", response.status); }
  }
}
