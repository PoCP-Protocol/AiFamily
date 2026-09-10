import type { CourseReleaseBaselineDraft } from "./courseReleaseBaseline";

export type CourseReleaseLifecycleResult = {
  baseline: { release_id: string; status: string };
  audit: { action: string; to_status: string; evidence_ids: string[] };
};

export interface CourseReleaseLifecycleApiClient {
  compile(payload: CourseReleaseBaselineDraft): Promise<{ release_id: string; status: string }>;
  get(releaseId: string): Promise<CourseReleaseBaselineDraft & { release_id: string; status: string }>;
  approve(releaseId: string, evidenceRefs: string[], taskId: string): Promise<CourseReleaseLifecycleResult>;
}

export class CourseReleaseLifecycleApiError extends Error {
  constructor(public readonly code: string, message: string, public readonly status?: number) {
    super(message);
  }
}

const prefix = "/product-intelligence/courses/release-baselines";

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `课程发布请求失败（HTTP ${response.status}）。`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch { /* preserve the transport error */ }
    throw new CourseReleaseLifecycleApiError("HTTP_ERROR", detail, response.status);
  }
  return response.json() as Promise<T>;
}

export class HttpCourseReleaseLifecycleApiClient implements CourseReleaseLifecycleApiClient {
  constructor(private readonly options: { baseUrl?: string; fetchImpl?: typeof fetch } = {}) {}

  private get fetchImpl() { return this.options.fetchImpl ?? fetch; }
  private get baseUrl() { return this.options.baseUrl ?? ""; }

  async compile(payload: CourseReleaseBaselineDraft) {
    return json<{ release_id: string; status: string }>(await this.fetchImpl(`${this.baseUrl}${prefix}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ payload }),
    }));
  }

  async get(releaseId: string) {
    return json<CourseReleaseBaselineDraft & { release_id: string; status: string }>(await this.fetchImpl(
      `${this.baseUrl}${prefix}/${encodeURIComponent(releaseId)}`,
    ));
  }

  async approve(releaseId: string, evidenceRefs: string[], taskId: string) {
    const evidence = evidenceRefs.map((reference, index) => ({
      evidence_id: reference, kind: "RELEASE_RECEIPT", reference, summary: `课程发布证据 ${index + 1}`,
    }));
    return json<CourseReleaseLifecycleResult>(await this.fetchImpl(`${this.baseUrl}${prefix}/${encodeURIComponent(releaseId)}/lifecycle`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "APPROVE", decision_id: `decision:${taskId}`, task_id: taskId, evidence }),
    }));
  }
}
