export const COURSE_RELEASE_LESSON_COUNT = 24;

export type CourseReleaseLessonBinding = {
  sequence: number;
  lesson_version_ref: string;
  content_spec_version_ref: string;
  asset_bundle_version_ref: string;
  skill_version_refs: string[];
};

export type CourseReleaseBaselineDraft = {
  schema_version: "1.0";
  status: "DRAFT";
  course_system_version_ref: string;
  product_package_version_ref: string;
  product_package_content_hash: string;
  product_definition_version_ref: string;
  course_content_version_ref: string;
  locale: string;
  delivery_channel: string;
  evidence_receipt_refs: string[];
  safety_policy_version_ref: string;
  prompt_bundle_version_ref: string;
  lessons: CourseReleaseLessonBinding[];
  release_notes: string;
  rollback_baseline_ref: null;
};

export type CourseReleaseBaselineForm = Omit<
  CourseReleaseBaselineDraft,
  "schema_version" | "status" | "evidence_receipt_refs" | "rollback_baseline_ref"
> & {
  evidence_receipt_refs: string;
};

const versionedRefPattern = /^\S+@v[1-9]\d*$/;
const sha256Pattern = /^[a-f0-9]{64}$/i;

export function createCourseReleaseBaselineForm(): CourseReleaseBaselineForm {
  return {
    course_system_version_ref: "",
    product_package_version_ref: "",
    product_package_content_hash: "",
    product_definition_version_ref: "",
    course_content_version_ref: "",
    locale: "zh-CN",
    delivery_channel: "WEB",
    evidence_receipt_refs: "",
    safety_policy_version_ref: "",
    prompt_bundle_version_ref: "",
    lessons: Array.from({ length: COURSE_RELEASE_LESSON_COUNT }, (_, index) => ({
      sequence: index + 1,
      lesson_version_ref: "",
      content_spec_version_ref: "",
      asset_bundle_version_ref: "",
      skill_version_refs: [],
    })),
    release_notes: "",
  };
}

const uniqueLines = (value: string) => [
  ...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)),
];

function versionedRef(value: string, code: string): string {
  const normalized = value.trim();
  if (!versionedRefPattern.test(normalized)) throw new Error(code);
  return normalized;
}

export function isReleaseLessonComplete(binding: CourseReleaseLessonBinding): boolean {
  return versionedRefPattern.test(binding.lesson_version_ref.trim())
    && versionedRefPattern.test(binding.content_spec_version_ref.trim())
    && versionedRefPattern.test(binding.asset_bundle_version_ref.trim())
    && binding.skill_version_refs.length > 0
    && binding.skill_version_refs.every((ref) => versionedRefPattern.test(ref.trim()));
}

export function compileCourseReleaseBaseline(form: CourseReleaseBaselineForm): CourseReleaseBaselineDraft {
  if (form.lessons.length !== COURSE_RELEASE_LESSON_COUNT) throw new Error("BASELINE_REQUIRES_24_LESSONS");
  if (!sha256Pattern.test(form.product_package_content_hash.trim())) throw new Error("PRODUCT_PACKAGE_HASH_INVALID");
  const receiptRefs = uniqueLines(form.evidence_receipt_refs);
  if (receiptRefs.length === 0) throw new Error("EVIDENCE_RECEIPTS_REQUIRED");
  const lessons = form.lessons.map((binding, index) => {
    if (binding.sequence !== index + 1 || !isReleaseLessonComplete(binding)) {
      throw new Error(`RELEASE_LESSON_${index + 1}_INCOMPLETE`);
    }
    return {
      sequence: binding.sequence,
      lesson_version_ref: versionedRef(binding.lesson_version_ref, "LESSON_VERSION_REF_INVALID"),
      content_spec_version_ref: versionedRef(binding.content_spec_version_ref, "CONTENT_SPEC_VERSION_REF_INVALID"),
      asset_bundle_version_ref: versionedRef(binding.asset_bundle_version_ref, "ASSET_BUNDLE_VERSION_REF_INVALID"),
      skill_version_refs: [...new Set(binding.skill_version_refs.map((ref) => versionedRef(ref, "SKILL_VERSION_REF_INVALID")))],
    };
  });
  for (const field of ["lesson_version_ref", "content_spec_version_ref", "asset_bundle_version_ref"] as const) {
    if (new Set(lessons.map((lesson) => lesson[field])).size !== lessons.length) {
      throw new Error(`${field.toUpperCase()}_MUST_BE_UNIQUE`);
    }
  }
  const locale = form.locale.trim();
  const deliveryChannel = form.delivery_channel.trim();
  const releaseNotes = form.release_notes.trim();
  if (!locale || !deliveryChannel || !releaseNotes) throw new Error("RELEASE_CONTEXT_INCOMPLETE");
  return {
    schema_version: "1.0",
    status: "DRAFT",
    course_system_version_ref: versionedRef(form.course_system_version_ref, "COURSE_SYSTEM_VERSION_REQUIRED"),
    product_package_version_ref: versionedRef(form.product_package_version_ref, "PRODUCT_PACKAGE_VERSION_REQUIRED"),
    product_package_content_hash: form.product_package_content_hash.trim().toLowerCase(),
    product_definition_version_ref: versionedRef(form.product_definition_version_ref, "PRODUCT_DEFINITION_VERSION_REQUIRED"),
    course_content_version_ref: versionedRef(form.course_content_version_ref, "COURSE_CONTENT_VERSION_REQUIRED"),
    locale,
    delivery_channel: deliveryChannel,
    evidence_receipt_refs: receiptRefs,
    safety_policy_version_ref: versionedRef(form.safety_policy_version_ref, "SAFETY_POLICY_VERSION_REQUIRED"),
    prompt_bundle_version_ref: versionedRef(form.prompt_bundle_version_ref, "PROMPT_BUNDLE_VERSION_REQUIRED"),
    lessons,
    release_notes: releaseNotes,
    rollback_baseline_ref: null,
  };
}
