import { describe, expect, it, vi } from "vitest";
import { HttpCourseReleaseLifecycleApiClient } from "./courseReleaseLifecycleApi";
import { compileCourseReleaseBaseline, createCourseReleaseBaselineForm } from "./courseReleaseBaseline";

function completeReleaseBaselineForm() {
  const form = createCourseReleaseBaselineForm();
  Object.assign(form, {
    course_system_version_ref: "course-system:learning-growth@v1",
    product_package_version_ref: "product-package:family-rhythm@v2",
    product_package_content_hash: "a".repeat(64),
    product_definition_version_ref: "product-definition:family-rhythm@v1",
    course_content_version_ref: "course-content:family-rhythm@v2",
    evidence_receipt_refs: "receipt:1",
    safety_policy_version_ref: "safety-policy:family@v1",
    prompt_bundle_version_ref: "prompt-bundle:course@v1",
    release_notes: "测试发布基线",
  });
  form.lessons = form.lessons.map((lesson) => ({
    ...lesson,
    lesson_version_ref: `lesson:${lesson.sequence}@v1`,
    content_spec_version_ref: `content-spec:${lesson.sequence}@v1`,
    asset_bundle_version_ref: `asset-bundle:${lesson.sequence}@v1`,
    skill_version_refs: ["skill:course@v1"],
  }));
  return form;
}

const response = (body: unknown, ok = true, status = 200) => ({
  ok,
  status,
  json: async () => body,
} as Response);

describe("course release lifecycle API", () => {
  it("persists a draft and restores it by release id", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(response({ release_id: "course-release:content@v1", status: "DRAFT" }))
      .mockResolvedValueOnce(response({ release_id: "course-release:content@v1", status: "DRAFT" }));
    const client = new HttpCourseReleaseLifecycleApiClient({ baseUrl: "https://api.example", fetchImpl });
    const draft = compileCourseReleaseBaseline(completeReleaseBaselineForm());
    await expect(client.compile(draft)).resolves.toMatchObject({ status: "DRAFT" });
    await expect(client.get("course-release:content@v1")).resolves.toMatchObject({ status: "DRAFT" });
    expect(fetchImpl.mock.calls[1][0]).toBe("https://api.example/product-intelligence/courses/release-baselines/course-release%3Acontent%40v1");
  });

  it("maps evidence receipts into an explicit approve request", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(response({ baseline: { status: "REVIEWED" }, audit: { action: "APPROVE", to_status: "REVIEWED", evidence_ids: ["receipt:1"] } }));
    const client = new HttpCourseReleaseLifecycleApiClient({ fetchImpl });
    await expect(client.approve("course-release:content@v1", ["receipt:1"], "task:1")).resolves.toMatchObject({ audit: { to_status: "REVIEWED" } });
    const request = JSON.parse(String(fetchImpl.mock.calls[0][1]?.body));
    expect(request).toMatchObject({ action: "APPROVE", task_id: "task:1", evidence: [{ evidence_id: "receipt:1" }] });
  });

  it("surfaces server detail instead of claiming success", async () => {
    const client = new HttpCourseReleaseLifecycleApiClient({ fetchImpl: async () => response({ detail: "COURSE_RELEASE_BASELINE_NOT_FOUND" }, false, 404) });
    await expect(client.get("missing")).rejects.toMatchObject({ code: "HTTP_ERROR", status: 404, message: "COURSE_RELEASE_BASELINE_NOT_FOUND" });
  });
});
