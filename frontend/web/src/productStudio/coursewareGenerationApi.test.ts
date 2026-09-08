import { describe, expect, it } from "vitest";
import { buildCoursewareGenerationPlan, validateCoursewareDraftCandidate } from "./coursewareGenerationApi";
import { compileCourseContentDraft, createCourseContentTemplate } from "./courseContentTemplate";

describe("courseware generation contract", () => {
  it("accepts only a governed DRAFT candidate", () => {
    expect(validateCoursewareDraftCandidate({ draft_id: "draft:1", lesson_sequence: 1, kind: "DECK", status: "DRAFT", prompt_ref: "prompt:v1", model_provenance_ref: "model:v1", evidence_refs: ["claim:1", "claim:1"], output_locator: "draft://1" }).evidence_refs).toEqual(["claim:1"]);
  });
  it("rejects a promoted candidate", () => {
    expect(() => validateCoursewareDraftCandidate({ draft_id: "draft:1", lesson_sequence: 1, kind: "DECK", status: "APPROVED", prompt_ref: "prompt:v1", model_provenance_ref: "model:v1", evidence_refs: ["claim:1"], output_locator: "draft://1" })).toThrow("课件候选治理字段无效");
  });

  it("compiles three explicit Model Gateway requests for every lesson", () => {
    const state = createCourseContentTemplate({ withCurriculumBaseline: true });
    state.title = "家庭成长课程";
    state.problem_statement = "家庭协作";
    state.learning_goal = "形成可复盘行动";
    state.assessment_criteria = "可观察";
    state.outcome_metrics = "行动记录";
    state.review_cadence = "每周";
    state.content_accuracy_claim_refs = "claim:curriculum";
    const plan = buildCoursewareGenerationPlan(compileCourseContentDraft(state));
    expect(plan).toHaveLength(72);
    expect(plan[0]).toMatchObject({ lesson_sequence: 1, kind: "DECK", model_provenance_ref: "model-gateway:pending" });
    expect(plan.at(-1)).toMatchObject({ lesson_sequence: 24, kind: "DOCUMENT" });
  });
});
