import { describe, expect, it } from "vitest";
import {
  compileCourseContentDraft,
  COURSE_LESSON_COUNT,
  createCourseContentTemplate,
} from "./courseContentTemplate";

function completeTemplate() {
  const state = createCourseContentTemplate();
  state.title = "家庭学习行动营";
  state.problem_statement = "家庭缺少稳定的学习协作节奏";
  state.assessment_criteria = "能复述共同约定";
  state.learning_goal = "建立可持续的家庭学习协作";
  state.review_cadence = "每 6 节人工复盘";
  state.outcome_metrics = "共同约定被家庭确认";
  state.content_accuracy_claim_refs = "claim:learning-routine";
  state.lessons = state.lessons.map((lesson) => ({
    ...lesson,
    title: `第 ${lesson.sequence} 节`,
    knowledge_point: "一个经过引用的知识点",
    action_task: "完成一次家庭共同练习",
  }));
  return state;
}

describe("24 lesson course template", () => {
  it("creates stable contiguous lesson identities", () => {
    const state = createCourseContentTemplate();
    expect(state.lessons).toHaveLength(COURSE_LESSON_COUNT);
    expect(state.lessons[0]).toMatchObject({ lesson_id: "lesson-01", sequence: 1 });
    expect(state.lessons[23]).toMatchObject({ lesson_id: "lesson-24", sequence: 24 });
  });

  it("compiles only browser-owned design fields", () => {
    const input = compileCourseContentDraft(completeTemplate());
    expect(input.lessons).toHaveLength(24);
    expect(input.product_component_id).toBeNull();
    expect(input).not.toHaveProperty("status");
    expect(input).not.toHaveProperty("tenant_scope");
    expect(input).not.toHaveProperty("published_at");
  });

  it("rejects an incomplete lesson and a non-24 template", () => {
    const incomplete = completeTemplate();
    incomplete.lessons[6].action_task = "";
    expect(() => compileCourseContentDraft(incomplete)).toThrow("COURSE_LESSON_7_INCOMPLETE");

    const short = completeTemplate();
    short.lessons.pop();
    expect(() => compileCourseContentDraft(short)).toThrow("COURSE_REQUIRES_24_LESSONS");
  });
});
