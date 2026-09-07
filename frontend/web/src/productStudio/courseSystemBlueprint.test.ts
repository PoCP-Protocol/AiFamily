import { describe, expect, it } from "vitest";
import {
  COURSE_SYSTEM_LESSON_COUNT,
  COURSE_SYSTEM_STAGES,
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
});
