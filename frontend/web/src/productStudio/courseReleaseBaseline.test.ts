import { describe, expect, it } from "vitest";
import {
  compileCourseReleaseBaseline,
  createCourseReleaseBaselineForm,
  COURSE_RELEASE_LESSON_COUNT,
} from "./courseReleaseBaseline";

export function completeReleaseBaselineForm() {
  const form = createCourseReleaseBaselineForm();
  Object.assign(form, {
    course_system_version_ref: "course-system:learning-growth@v1",
    product_package_version_ref: "product-package:family-rhythm@v2",
    product_package_content_hash: "a".repeat(64),
    product_definition_version_ref: "product-definition:family-rhythm@v1",
    course_content_version_ref: "course-content:family-rhythm@v2",
    evidence_receipt_refs: "verification-receipt:content-accuracy\nverification-receipt:safety",
    safety_policy_version_ref: "safety-policy:family-education@v3",
    prompt_bundle_version_ref: "prompt-bundle:course-coach@v2",
    release_notes: "首个24课时发布基线候选，仅进入人工发布门禁。",
  });
  form.lessons = form.lessons.map((lesson) => ({
    ...lesson,
    lesson_version_ref: `lesson:family-rhythm-${lesson.sequence}@v1`,
    content_spec_version_ref: `content-spec:family-rhythm-${lesson.sequence}@v1`,
    asset_bundle_version_ref: `asset-bundle:family-rhythm-${lesson.sequence}@v1`,
    skill_version_refs: ["skill:family-dialogue@v1"],
  }));
  return form;
}

describe("CourseReleaseBaseline compiler", () => {
  it("creates a 24 lesson immutable DRAFT baseline", () => {
    const baseline = compileCourseReleaseBaseline(completeReleaseBaselineForm());
    expect(baseline.status).toBe("DRAFT");
    expect(baseline.lessons).toHaveLength(COURSE_RELEASE_LESSON_COUNT);
    expect(baseline.rollback_baseline_ref).toBeNull();
    expect(baseline).not.toHaveProperty("decision");
    expect(baseline).not.toHaveProperty("released_at");
  });

  it("rejects incomplete lesson BOM, unversioned refs, and invalid package hash", () => {
    const incomplete = completeReleaseBaselineForm();
    incomplete.lessons[4].asset_bundle_version_ref = "";
    expect(() => compileCourseReleaseBaseline(incomplete)).toThrow("RELEASE_LESSON_5_INCOMPLETE");
    const unversioned = completeReleaseBaselineForm();
    unversioned.course_system_version_ref = "course-system:learning-growth";
    expect(() => compileCourseReleaseBaseline(unversioned)).toThrow("COURSE_SYSTEM_VERSION_REQUIRED");
    const invalidHash = completeReleaseBaselineForm();
    invalidHash.product_package_content_hash = "not-a-hash";
    expect(() => compileCourseReleaseBaseline(invalidHash)).toThrow("PRODUCT_PACKAGE_HASH_INVALID");
  });

  it("rejects duplicate immutable lesson references", () => {
    const form = completeReleaseBaselineForm();
    form.lessons[1].lesson_version_ref = form.lessons[0].lesson_version_ref;
    expect(() => compileCourseReleaseBaseline(form)).toThrow("LESSON_VERSION_REF_MUST_BE_UNIQUE");
  });
});
