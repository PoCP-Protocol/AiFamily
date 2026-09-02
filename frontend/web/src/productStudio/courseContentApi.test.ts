import { describe, expect, it, vi } from "vitest";
import { HttpCourseContentReadApiClient, validatePublishedCourse } from "./courseContentApi";
import { publishedCourse } from "./courseContentTestFixture";

describe("CourseContent read contract", () => {
  it("reads a strict published list with bearer auth", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify([publishedCourse]), { status: 200 }));
    const client = new HttpCourseContentReadApiClient({ baseUrl: "https://api.example", accessToken: "token", fetchImpl });
    await expect(client.listPublished()).resolves.toEqual([publishedCourse]);
    expect(fetchImpl).toHaveBeenCalledWith("https://api.example/product-intelligence/courses/published", {
      method: "GET", headers: { authorization: "Bearer token" },
    });
  });

  it("fails closed for draft, unknown fields, invalid time, or duplicate lessons", () => {
    expect(() => validatePublishedCourse({ ...publishedCourse, status: "DRAFT" })).toThrow("PUBLISHED");
    expect(() => validatePublishedCourse({ ...publishedCourse, system: "学习成长" })).toThrow("未知字段");
    expect(() => validatePublishedCourse({ ...publishedCourse, published_at: "2026-09-02" })).toThrow("带时区时间");
    expect(() => validatePublishedCourse({ ...publishedCourse, lessons: [publishedCourse.lessons[0], publishedCourse.lessons[0]] })).toThrow("身份或顺序不可信");
  });

  it("does not hide server and transport failures", async () => {
    const unavailable = new HttpCourseContentReadApiClient({ fetchImpl: vi.fn().mockResolvedValue(new Response("", { status: 503 })) });
    await expect(unavailable.listPublished()).rejects.toMatchObject({ code: "UNAVAILABLE", httpStatus: 503 });
    const timeout = new HttpCourseContentReadApiClient({ fetchImpl: vi.fn().mockRejectedValue(new Error("offline")) });
    await expect(timeout.listPublished()).rejects.toMatchObject({ code: "TIMEOUT" });
  });
});
