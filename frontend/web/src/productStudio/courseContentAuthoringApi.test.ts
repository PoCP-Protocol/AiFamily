import { describe, expect, it, vi } from "vitest";
import {
  assertCourseDraftReadBack,
  HttpCourseContentAuthoringApiClient,
  validateCourseContentDraftResponse,
} from "./courseContentAuthoringApi";
import { completeCourseInput, courseDraftResponse } from "./courseContentAuthoringTestFixture";

describe("CourseContent authoring contract", () => {
  it("posts only design intent and supports strict GET readback", async () => {
    const response = courseDraftResponse();
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(response), { status: 200 }));
    const client = new HttpCourseContentAuthoringApiClient({ baseUrl: "https://api.example", accessToken: "token", fetchImpl });
    const input = completeCourseInput();
    const created = await client.createDraft(input);
    const readBack = await client.getDraft(created.id);
    expect(assertCourseDraftReadBack(input, created, readBack)).toEqual(response);
    const posted = JSON.parse(String(fetchImpl.mock.calls[0][1]?.body));
    expect(posted).toEqual(input);
    expect(posted).not.toHaveProperty("status");
    expect(fetchImpl.mock.calls[1][0]).toBe("https://api.example/product-intelligence/courses/course%3Adraft-1");
  });

  it("rejects fake lifecycle metadata and readback drift", () => {
    expect(() => validateCourseContentDraftResponse({ ...courseDraftResponse(), status: "PUBLISHED" })).toThrow("初始 DRAFT");
    expect(() => validateCourseContentDraftResponse({ ...courseDraftResponse(), reviewed_by: "reviewer:1" })).toThrow("伪造");
    const created = courseDraftResponse();
    expect(() => assertCourseDraftReadBack(completeCourseInput(), created, { ...created, title: "漂移" })).toThrow("回读不一致");
  });

  it("marks a failed POST as unknown outcome and never retries", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("offline"));
    const client = new HttpCourseContentAuthoringApiClient({ fetchImpl });
    await expect(client.createDraft(completeCourseInput())).rejects.toMatchObject({ code: "UNKNOWN_OUTCOME" });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
