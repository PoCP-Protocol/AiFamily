import { describe, expect, it } from "vitest";
import { HttpCourseSystemApiClient } from "./courseSystemApi";

const response = (body: unknown, ok = true, status = 200) => ({ ok, status, json: async () => body }) as Response;

describe("CourseSystem API client", () => {
  it("reads a versioned six-stage system", async () => {
    const client = new HttpCourseSystemApiClient({
      fetchImpl: async () => response({ system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })) }),
    });
    const result = await client.get("course-system:family-growth");
    expect(result.version).toBe("v1");
    expect(result.stages).toHaveLength(6);
  });

  it("turns missing master data into a typed error", async () => {
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response({}, false, 404) });
    await expect(client.get("missing")).rejects.toMatchObject({ code: "NOT_FOUND" });
  });
});
