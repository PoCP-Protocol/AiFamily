import { ProductStudioApiError } from "./api";

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

export function validateCoursewareDraftCandidate(value: unknown): CoursewareDraftCandidate {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new ProductStudioApiError("INVALID_RESPONSE", "课件候选不是对象。");
  const row = value as Record<string, unknown>;
  const kinds = ["DECK", "WORKSHEET", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"];
  if (typeof row.draft_id !== "string" || !row.draft_id.trim() || !Number.isInteger(row.lesson_sequence) || Number(row.lesson_sequence) < 1 || Number(row.lesson_sequence) > 24 || !kinds.includes(String(row.kind)) || row.status !== "DRAFT" || typeof row.prompt_ref !== "string" || !row.prompt_ref.trim() || typeof row.model_provenance_ref !== "string" || !row.model_provenance_ref.trim() || typeof row.output_locator !== "string" || !row.output_locator.trim() || !Array.isArray(row.evidence_refs) || !row.evidence_refs.length || !row.evidence_refs.every((ref) => typeof ref === "string" && ref.trim())) throw new ProductStudioApiError("INVALID_RESPONSE", "课件候选治理字段无效。");
  return { draft_id: row.draft_id, lesson_sequence: Number(row.lesson_sequence), kind: row.kind as CoursewareDraftCandidate["kind"], status: "DRAFT", prompt_ref: row.prompt_ref, model_provenance_ref: row.model_provenance_ref, evidence_refs: [...new Set(row.evidence_refs as string[])], output_locator: row.output_locator };
}
