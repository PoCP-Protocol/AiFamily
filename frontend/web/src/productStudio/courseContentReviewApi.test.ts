import { describe, expect, it, vi } from "vitest";
import { HttpCourseContentReviewApiClient } from "./courseContentReviewApi";

describe("CourseContent review API", () => {
  it("submits and decides through separate Human Gate endpoints", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ course: { id: "course-1", status: "UNDER_REVIEW" }, task_id: "task-1" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ course: { id: "course-1", status: "PUBLISHED" }, task_id: "task-1" }), { status: 200 }));
    const client = new HttpCourseContentReviewApiClient({ fetchImpl });
    await expect(client.submitForReview("course-1")).resolves.toMatchObject({ task_id: "task-1" });
    await expect(client.decide("course-1", { task_id: "task-1", approved: true, reason: "证据与安全边界通过" })).resolves.toMatchObject({ course: { status: "PUBLISHED" } });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("fails before network when review input is incomplete", async () => {
    const fetchImpl = vi.fn();
    const client = new HttpCourseContentReviewApiClient({ fetchImpl });
    await expect(client.decide("course-1", { task_id: "", approved: false, reason: "" })).rejects.toMatchObject({ code: "INVALID_INPUT" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
