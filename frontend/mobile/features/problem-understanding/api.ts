import type { UnderstandingDraft } from "./model";

export interface GenerateUnderstandingRequest {
  run_id: string;
  tenant_id: string;
  guardian_input_ref: string;
  guardian_text: string;
  revision: number;
  prior_draft_artifact_hash: string | null;
}

export interface GeneratedUnderstandingResponse {
  run_id: string;
  artifact_hash: string;
  request_hash: string;
  provenance_ref: string;
  version: number;
  prior_draft_artifact_hash: string | null;
  status: string;
  summary: string;
  hypotheses: { statement?: unknown }[];
  unknowns: { question?: unknown; reason?: unknown }[];
  follow_up_questions: string[];
  strengths: { statement?: unknown }[];
  desired_change: { statement?: unknown };
  source_refs: string[];
  knowledge_references: string[];
  provider_id: string;
  model: string;
  model_version: string;
  prompt_version: string;
  schema_version: string;
  context_snapshot_ref: string;
  provenance: Record<string, unknown>;
  requires_guardian_confirmation: boolean;
  may_mutate_business_state: boolean;
}

export function toUnderstandingDraft(
  response: GeneratedUnderstandingResponse,
  tenantId: string,
  familyId: string,
): UnderstandingDraft {
  if (
    response.status !== "DRAFT" ||
    !response.requires_guardian_confirmation ||
    response.may_mutate_business_state
  ) {
    throw new Error("UNDERSTANDING_RESPONSE_INVALID");
  }

  const hypotheses = response.hypotheses
    .map((item) => readText(item.statement))
    .filter((item): item is string => item !== null);
  const strengths = response.strengths
    .map((item) => readText(item.statement))
    .filter((item): item is string => item !== null);
  const desiredChange = readText(response.desired_change.statement);

  if (
    !response.artifact_hash ||
    !response.request_hash ||
    !response.provenance_ref ||
    !response.summary ||
    !desiredChange
  ) {
    throw new Error("UNDERSTANDING_RESPONSE_INVALID");
  }

  return {
    signalRef: `understanding:${response.artifact_hash}`,
    signalVersion: response.version,
    scopeRef: `family://${tenantId}/${familyId}/problem-understanding`,
    reviewedDraftRef: response.artifact_hash,
    draftVersion: response.version,
    provenanceRef: response.provenance_ref,
    humanGateReceiptRef: null,
    summary: response.summary,
    explicitClaims: hypotheses,
    alternativeExplanations: hypotheses,
    familyStrengths: strengths,
    desiredChange,
    unknowns: response.unknowns
      .map((item, index) => {
        const question = readText(item.question);
        return question ? { key: `unknown-${index + 1}`, label: question } : null;
      })
      .filter((item): item is { key: string; label: string } => item !== null),
    lifecycle: "PROPOSED",
  };
}

function readText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
