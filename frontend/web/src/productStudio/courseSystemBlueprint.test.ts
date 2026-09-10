import { describe, expect, it } from "vitest";
import {
  COURSE_SYSTEM_LESSON_COUNT,
  COURSE_SYSTEM_STAGES,
  buildLessonDeliveryMatrix,
  summarizeLessonDelivery,
  evaluateCoursewareGovernance,
  summarizeStageDelivery,
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
    expect(readiness).toMatchObject({ total_lessons: 24, bom_ready_lessons: 0, blocked_lessons: 24, publish_ready: false, blocked_by_reason: { NO_ASSET: 24, QA: 0, RIGHTS: 0, SAFETY: 0 } });
  });

  it("requires QA, rights, and safety clearance before a lesson is READY", () => {
    const rows = buildLessonDeliveryMatrix(COURSE_SYSTEM_STAGES, [1, 2], {
      1: { qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" },
      2: { qa_status: "APPROVED", rights_status: "UNKNOWN", safety_status: "CLEARED" },
    });
    expect(rows[0].courseware_status).toBe("READY");
    expect(rows[0].governance_reason).toBe("READY");
    expect(rows[1].courseware_status).toBe("REVIEW_REQUIRED");
    expect(rows[1].governance_reason).toBe("RIGHTS");
  });

  it("explains the first failing courseware governance gate", () => {
    expect(evaluateCoursewareGovernance(undefined).reason).toBe("NO_ASSET");
    expect(evaluateCoursewareGovernance([{ qa_status: "DRAFT", rights_status: "CLEARED", safety_status: "CLEARED" }]).reason).toBe("QA");
    expect(evaluateCoursewareGovernance([{ qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" }]).governed).toBe(true);
  });

  it("summarizes readiness per product stage", () => {
    const rows = buildLessonDeliveryMatrix(COURSE_SYSTEM_STAGES, [1, 2, 3, 4], {
      1: { qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" },
      2: { qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" },
      3: { qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" },
      4: { qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" },
    });
    expect(summarizeStageDelivery(rows)[0]).toMatchObject({ stage_id: "S1", ready_lessons: 4, blocked_lessons: 0, publish_ready: true, next_action: "进入阶段发布评审" });
    expect(summarizeStageDelivery(rows)[1]).toMatchObject({ stage_id: "S2", ready_lessons: 0, blocked_lessons: 4, publish_ready: false, next_action: "优先处理NO_ASSET门禁" });
  });
});
