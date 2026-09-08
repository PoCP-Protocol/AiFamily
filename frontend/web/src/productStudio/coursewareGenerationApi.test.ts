import { describe, expect, it } from "vitest";
import { validateCoursewareDraftCandidate } from "./coursewareGenerationApi";

describe("courseware generation contract", () => {
  it("accepts only a governed DRAFT candidate", () => {
    expect(validateCoursewareDraftCandidate({ draft_id: "draft:1", lesson_sequence: 1, kind: "DECK", status: "DRAFT", prompt_ref: "prompt:v1", model_provenance_ref: "model:v1", evidence_refs: ["claim:1", "claim:1"], output_locator: "draft://1" }).evidence_refs).toEqual(["claim:1"]);
  });
  it("rejects a promoted candidate", () => {
    expect(() => validateCoursewareDraftCandidate({ draft_id: "draft:1", lesson_sequence: 1, kind: "DECK", status: "APPROVED", prompt_ref: "prompt:v1", model_provenance_ref: "model:v1", evidence_refs: ["claim:1"], output_locator: "draft://1" })).toThrow("课件候选治理字段无效");
  });
});
