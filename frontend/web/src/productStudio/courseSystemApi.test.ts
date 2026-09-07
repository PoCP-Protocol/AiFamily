import { describe, expect, it } from "vitest";
import { HttpCourseSystemApiClient } from "./courseSystemApi";

const response = (body: unknown, ok = true, status = 200) => ({ ok, status, json: async () => body }) as Response;

describe("CourseSystem API client", () => {
  it("reads a versioned six-stage system", async () => {
    const client = new HttpCourseSystemApiClient({
      fetchImpl: async () => response({ system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [{ lesson_sequence: 1, artifacts: [{ artifact_id: "a1", version_ref: "a1@v1", provenance_ref: "source:a1", qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" }] }] }),
    });
    const result = await client.get("course-system:family-growth");
    expect(result.version).toBe("v1");
    expect(result.stages).toHaveLength(6);
    expect(result.bom_lesson_sequences).toEqual([1]);
    expect(result.bom_lesson_statuses?.[1]).toMatchObject({ qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" });
  });

  it("turns missing master data into a typed error", async () => {
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response({}, false, 404) });
    await expect(client.get("missing")).rejects.toMatchObject({ code: "NOT_FOUND" });
  });

  it("rejects duplicate or out-of-range BOM lesson sequences", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [{ lesson_sequence: 1 }, { lesson_sequence: 1 }] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects unknown governance status values", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [{ lesson_sequence: 1, artifacts: [{ qa_status: "PASSED", rights_status: "CLEARED", safety_status: "CLEARED" }] }] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects BOM rows without courseware assets", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [{ lesson_sequence: 1, artifacts: [] }] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("aggregates every asset before declaring governance ready", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [{ lesson_sequence: 1, artifacts: [{ artifact_id: "a1", version_ref: "a1@v1", provenance_ref: "source:a1", qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" }, { artifact_id: "a2", version_ref: "a2@v1", provenance_ref: "source:a2", qa_status: "DRAFT", rights_status: "CLEARED", safety_status: "CLEARED" }] }] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).resolves.toMatchObject({ bom_lesson_statuses: { 1: { qa_status: "REVIEW_REQUIRED" } } });
  });

  it("rejects malformed courseware asset entries", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [{ lesson_sequence: 1, artifacts: ["bad"] }] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects courseware assets without lineage fields", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [{ lesson_sequence: 1, artifacts: [{ qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" }] }] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects a non-array BOM container", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: {} };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects blank identity and package references", async () => {
    const payload = { system_id: " ", tenant_scope: "dev", version: 0, product_package_version_ref: "", stages: [] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects stage lesson gaps", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1 + (i === 2 ? 1 : 0), lesson_end: i * 4 + 4 + (i === 2 ? 1 : 0), outcome: "产出" })), bom: [] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects duplicate stage identities", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: i === 1 ? "S1" : `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects non-canonical stage IDs", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "dev", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `stage-${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [] };
    const client = new HttpCourseSystemApiClient({ fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects a response from another tenant scope", async () => {
    const payload = { system_id: "course-system:family-growth", tenant_scope: "tenant-b", version: 1, product_package_version_ref: "package@v1", stages: Array.from({ length: 6 }, (_, i) => ({ stage_id: `S${i + 1}`, title: `阶段${i + 1}`, lesson_start: i * 4 + 1, lesson_end: i * 4 + 4, outcome: "产出" })), bom: [] };
    const client = new HttpCourseSystemApiClient({ tenantScope: "tenant-a", fetchImpl: async () => response(payload) });
    await expect(client.get("course-system:family-growth")).rejects.toMatchObject({ code: "FORBIDDEN" });
  });
});
