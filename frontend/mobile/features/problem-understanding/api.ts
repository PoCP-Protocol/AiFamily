import type { AuthorizedMediaAttachment, UnderstandingDraft } from "./model";

export interface MultimodalDraftRequest {
  run_id: string;
  prompt_version: string;
  schema_version: string;
  payload: { expression: string; revision: number };
  output_schema: Record<string, unknown>;
  modalities: ("TEXT" | "IMAGE")[];
  estimated_input_tokens: number;
  strategy: "balanced";
  input_refs: string[];
  media_inputs: {
    media_type: "IMAGE";
    uri: string;
    mime_type: string;
    sha256: string;
  }[];
  session_id: string;
}

export interface MultimodalDraftResponse {
  run_id: string;
  draft_id: string | null;
  provenance_ref: string | null;
  status: "DRAFT";
  output: Record<string, unknown>;
  requires_human_confirmation: true;
  context_snapshot_ref: string;
  context_snapshot_expires_at: string;
  provenance: {
    schema_version: string;
    generated_at: string;
  };
}

export interface MultimodalRunInteractionResponse {
  run_id: string;
  status: string;
  interaction_ref: string;
  idempotency_replayed: boolean;
}

export interface MultimodalRunReplayResponse {
  run_id: string;
  status: "DRAFT";
  state: string;
  event_sequence: number;
  deletion_state: "active" | "deleted";
  draft_payload: Record<string, unknown> | null;
  artifact_refs: string[];
}

export const FAMILY_UNDERSTANDING_OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: [
    "summary",
    "hypotheses",
    "unknowns",
    "follow_up_questions",
    "strengths",
    "desired_change",
  ],
  properties: {
    summary: { type: "string" },
    hypotheses: {
      type: "array",
      items: { type: "string" },
      minItems: 1,
      maxItems: 3,
    },
    unknowns: { type: "array", items: { type: "string" } },
    follow_up_questions: { type: "array", items: { type: "string" } },
    strengths: { type: "array", items: { type: "string" } },
    desired_change: { type: "string" },
  },
} as const;

export function buildMultimodalDraftRequest(input: {
  runId: string;
  sessionId: string;
  expression: string;
  revision: number;
  attachments: readonly AuthorizedMediaAttachment[];
}): MultimodalDraftRequest {
  const mediaInputs = input.attachments.map((attachment) => ({
    media_type: attachment.mediaType,
    uri: attachment.uri,
    mime_type: attachment.mimeType,
    sha256: attachment.sha256,
  }));
  return {
    run_id: input.runId,
    prompt_version: "family-understanding-multimodal.v1",
    schema_version: "family-understanding-draft.v1",
    payload: { expression: input.expression, revision: input.revision },
    output_schema: FAMILY_UNDERSTANDING_OUTPUT_SCHEMA,
    modalities: mediaInputs.length > 0 ? ["TEXT", "IMAGE"] : ["TEXT"],
    estimated_input_tokens: Math.max(
      64,
      Math.ceil(input.expression.length * 1.5),
    ),
    strategy: "balanced",
    input_refs: mediaInputs.map((item) => item.uri),
    media_inputs: mediaInputs,
    session_id: input.sessionId,
  };
}

export function toUnderstandingDraft(
  response: MultimodalDraftResponse,
  tenantId: string,
  familyId: string,
  revision: number,
  mediaCount: number,
): UnderstandingDraft {
  if (
    response.status !== "DRAFT" ||
    !response.requires_human_confirmation ||
    !response.draft_id ||
    !response.provenance_ref
  ) {
    throw new Error("UNDERSTANDING_RESPONSE_INVALID");
  }

  const summary = readText(response.output.summary);
  const hypotheses = readTextList(response.output.hypotheses);
  const strengths = readTextList(response.output.strengths);
  const desiredChange = readText(response.output.desired_change);
  const unknowns = readTextList(response.output.unknowns);
  const followUps = readTextList(response.output.follow_up_questions);
  const generatedAt = readText(response.provenance.generated_at);

  if (!summary || hypotheses.length === 0 || !desiredChange || !generatedAt) {
    throw new Error("UNDERSTANDING_RESPONSE_INVALID");
  }

  return {
    runId: response.run_id,
    signalRef: `understanding:${response.draft_id}`,
    signalVersion: revision,
    scopeRef: `family://${tenantId}/${familyId}/problem-understanding`,
    reviewedDraftRef: response.draft_id,
    draftVersion: revision,
    provenanceRef: response.provenance_ref,
    humanGateReceiptRef: null,
    summary,
    explicitClaims: hypotheses,
    alternativeExplanations: hypotheses,
    familyStrengths: strengths,
    desiredChange,
    unknowns: (unknowns.length > 0 ? unknowns : followUps).map(
      (label, index) => ({ key: `unknown-${index + 1}`, label }),
    ),
    sourceSummary:
      mediaCount > 0
        ? `根据你写下的内容和 ${mediaCount} 张已授权图片整理`
        : "根据你写下的内容整理",
    generatedAt,
    mediaCount,
    lifecycle: "PROPOSED",
  };
}

export function isAuthorizedMediaAttachment(
  attachment: AuthorizedMediaAttachment,
): boolean {
  return (
    attachment.mediaType === "IMAGE" &&
    /^(?:media|asset|object|opaque):[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/i.test(
      attachment.uri,
    ) &&
    attachment.mimeType.startsWith("image/") &&
    /^[a-f0-9]{64}$/i.test(attachment.sha256)
  );
}

function readText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function readTextList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(readText).filter((item): item is string => item !== null);
}
