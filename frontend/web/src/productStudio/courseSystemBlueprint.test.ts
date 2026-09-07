import { describe, expect, it } from "vitest";
import {
  COURSE_SYSTEM_LESSON_COUNT,
  COURSE_SYSTEM_STAGES,
  buildLessonDeliveryMatrix,
  summarizeLessonDelivery,
  validateCourseSystemBlueprint,
} from "./courseSystemBlueprint";

describe("course system blueprint", () => {
  it("covers 24 lessons in six product stages", () => {
    const blueprint = validateCourseSystemBlueprint({
      system_id: "course-system:family-growth",
      version: "v1",
      product_package_version_ref: "product-package:family-growth@v1",
      stages: [...COURSE_SYSTEM_STAGES],
    });
    expect(blueprint.stages.at(-1)?.lesson_end).toBe(COURSE_SYSTEM_LESSON_COUNT);
  });

  it("blocks stage gaps instead of silently publishing an incomplete system", () => {
    const stages = COURSE_SYSTEM_STAGES.map((stage) => ({ ...stage }));
    stages[2].lesson_start = 10;
    expect(() => validateCourseSystemBlueprint({
      system_id: "course-system:family-growth",
      version: "v1",
      product_package_version_ref: "product-package:family-growth@v1",
      stages,
    })).toThrow("COURSE_SYSTEM_STAGE_COVERAGE_INVALID");
  });

  it("derives one governed delivery row for every lesson", () => {
    const rows = buildLessonDeliveryMatrix(COURSE_SYSTEM_STAGES);
    expect(rows).toHaveLength(24);
    expect(rows[0]).toMatchObject({ sequence: 1, stage_id: "S1", courseware_status: "BOM_REQUIRED" });
    expect(rows.at(-1)).toMatchObject({ sequence: 24, stage_id: "S6" });
  });

  it("blocks release readiness while any lesson lacks a courseware BOM", () => {
    const readiness = summarizeLessonDelivery(buildLessonDeliveryMatrix(COURSE_SYSTEM_STAGES));
    expect(readiness).toMatchObject({ total_lessons: 24, bom_ready_lessons: 0, blocked_lessons: 24, publish_ready: false });
  });
});
