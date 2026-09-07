import { describe, expect, it } from "vitest";
import { HttpCourseDeliveryProjectionApiClient } from "./courseDeliveryProjectionApi";

describe("Course delivery projection API", () => {
  it("reads a tenant-scoped projection", async () => {
    let request: RequestInit | undefined;
    const client = new HttpCourseDeliveryProjectionApiClient({
      tenantScope: "tenant-a",
      fetchImpl: async (_input, init) => {
        request = init;
        return {
          ok: true,
          status: 200,
          json: async () => ({
            course_content_id: "course-1",
            course_system_version_ref: "course-system:family-growth@v1",
            product_component_id: null,
            lessons: [{ sequence: 1, lesson_id: "lesson-1", stage_id: "S1", product_outcome: "产出", family_action: "行动", courseware_refs: ["asset-1"], status: "READY" }],
            ready_lessons: 1,
            blocked_lessons: 0,
            publishable_to_service: true,
          }),
        } as Response;
      },
    });
    await client.get("course-1");
    expect(request?.headers).toEqual({ "x-tenant-scope": "tenant-a" });
  });

  it("rejects malformed projection responses", async () => {
    const client = new HttpCourseDeliveryProjectionApiClient({ fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ lessons: [] }) } as Response) });
    await expect(client.get("course-1")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});
