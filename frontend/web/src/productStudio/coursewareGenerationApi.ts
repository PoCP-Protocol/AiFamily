import { ProductStudioApiError } from "./api";
import type { CourseContentDraftInput } from "./courseContentTemplate";

export type CoursewareDraftCandidate = {
  draft_id: string;
  lesson_sequence: number;
  kind: "DECK" | "WORKSHEET" | "IMAGE" | "VIDEO" | "AUDIO" | "DOCUMENT";
  status: "DRAFT";
  prompt_ref: string;
  model_provenance_ref: string;
  evidence_refs: string[];
  output_locator: string;
};

export type CoursewareGenerationRequest = {
  lesson_sequence: number;
  lesson_id: string;
  kind: CoursewareDraftCandidate["kind"];
  prompt_ref: string;
  asset_bundle_version_ref: string;
  model_provenance_ref: string;
  evidence_refs: string[];
};

/**
 * Compile an explicit, deterministic generation plan for Model Gateway.
 * This does not call a provider and does not claim that an asset exists.
 */
export function buildCoursewareGenerationPlan(input: CourseContentDraftInput): CoursewareGenerationRequest[] {
  if (!input.lessons.length) throw new ProductStudioApiError("INVALID_INPUT", "课程没有课时，无法编译课件生成计划。");
  return input.lessons.flatMap((lesson) => (['DECK', 'WORKSHEET', 'DOCUMENT'] as const).map((kind) => ({
    lesson_sequence: lesson.sequence,
    lesson_id: lesson.lesson_id,
    kind,
    prompt_ref: `prompt:courseware-${kind.toLowerCase()}@v1`,
    asset_bundle_version_ref: `courseware:family-growth:lesson-${String(lesson.sequence).padStart(2, "0")}:${kind.toLowerCase()}@v1`,
    model_provenance_ref: "model-gateway:pending",
    evidence_refs: [...input.content_accuracy_claim_refs],
  })));
}

export function validateCoursewareDraftCandidate(value: unknown): CoursewareDraftCandidate {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new ProductStudioApiError("INVALID_RESPONSE", "课件候选不是对象。");
  const row = value as Record<string, unknown>;
  const kinds = ["DECK", "WORKSHEET", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"];
  if (typeof row.draft_id !== "string" || !row.draft_id.trim() || !Number.isInteger(row.lesson_sequence) || Number(row.lesson_sequence) < 1 || Number(row.lesson_sequence) > 24 || !kinds.includes(String(row.kind)) || row.status !== "DRAFT" || typeof row.prompt_ref !== "string" || !row.prompt_ref.trim() || typeof row.model_provenance_ref !== "string" || !row.model_provenance_ref.trim() || typeof row.output_locator !== "string" || !row.output_locator.trim() || !Array.isArray(row.evidence_refs) || !row.evidence_refs.length || !row.evidence_refs.every((ref) => typeof ref === "string" && ref.trim())) throw new ProductStudioApiError("INVALID_RESPONSE", "课件候选治理字段无效。");
  return { draft_id: row.draft_id, lesson_sequence: Number(row.lesson_sequence), kind: row.kind as CoursewareDraftCandidate["kind"], status: "DRAFT", prompt_ref: row.prompt_ref, model_provenance_ref: row.model_provenance_ref, evidence_refs: [...new Set(row.evidence_refs as string[])], output_locator: row.output_locator };
}
