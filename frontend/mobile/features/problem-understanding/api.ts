import type { AuthorizedMediaAttachment, UnderstandingDraft } from "./model";

export interface MultimodalDraftRequest {
  run_id: string;
  prompt_version: string;
  schema_version: string;
  payload: { expression: string; revision: number };
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

export interface FamilyUnderstandingOutput {
  understanding: {
    lived_experience: string;
    central_tension: string;
    care_intent: string;
  };
  hypotheses: {
    hypothesis_id: string;
    statement: string;
    rationale: string;
    evidence: {
      source_type: "PARENT_TEXT" | "AUTHORIZED_IMAGE" | "FAMILY_CONTEXT";
      source_ref: string;
      observation: string;
    }[];
    knowledge_refs: string[];
    confidence: "LOW" | "MEDIUM" | "HIGH";
    disconfirming_evidence_needed: string;
  }[];
  unknowns: {
    unknown_id: string;
    description: string;
    why_it_matters: string;
    related_hypothesis_ids: string[];
  }[];
  follow_up_questions: {
    question_id: string;
    question: string;
    purpose: string;
    answers_unknown_ids: string[];
  }[];
  strengths: {
    statement: string;
    evidence_refs: string[];
    why_it_matters: string;
  }[];
  desired_change: {
    statement: string;
    basis: "EXPLICIT" | "INFERRED";
    observable_signs: string[];
    confirmation_question: string;
  };
  limitations: string[];
}

export interface MultimodalDraftResponse {
  run_id: string;
  draft_id: string | null;
  provenance_ref: string | null;
  status: "DRAFT";
  output: FamilyUnderstandingOutput;
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

  const understanding = response.output.understanding;
  const livedExperience = readText(understanding?.lived_experience);
  const centralTension = readText(understanding?.central_tension);
  const careIntent = readText(understanding?.care_intent);
  const hypotheses = Array.isArray(response.output.hypotheses)
    ? response.output.hypotheses
    : [];
  const strengths = Array.isArray(response.output.strengths)
    ? response.output.strengths
    : [];
  const desiredChange = readText(response.output.desired_change?.statement);
  const observableSigns = readTextList(
    response.output.desired_change?.observable_signs,
  );
  const unknowns = Array.isArray(response.output.unknowns)
    ? response.output.unknowns
    : [];
  const followUps = Array.isArray(response.output.follow_up_questions)
    ? response.output.follow_up_questions
    : [];
  const limitations = readTextList(response.output.limitations);
  const generatedAt = readText(response.provenance.generated_at);

  if (
    response.provenance.schema_version !== "family-understanding-draft.v1" ||
    !livedExperience ||
    !centralTension ||
    !careIntent ||
    hypotheses.length === 0 ||
    !desiredChange ||
    limitations.length === 0 ||
    !generatedAt
  ) {
    throw new Error("UNDERSTANDING_RESPONSE_INVALID");
  }

  const hypothesisStatements = hypotheses
    .map((item) => {
      const statement = readText(item?.statement);
      const rationale = readText(item?.rationale);
      return statement && rationale
        ? `${statement}（${rationale}）`
        : statement;
    })
    .filter((item): item is string => item !== null);
  if (hypothesisStatements.length === 0) {
    throw new Error("UNDERSTANDING_RESPONSE_INVALID");
  }

  const explicitClaims = hypotheses
    .flatMap((item) => (Array.isArray(item?.evidence) ? item.evidence : []))
    .filter((item) => item?.source_type === "PARENT_TEXT")
    .map((item) => readText(item?.observation))
    .filter((item): item is string => item !== null);

  return {
    runId: response.run_id,
    signalRef: `understanding:${response.draft_id}`,
    signalVersion: revision,
    scopeRef: `family://${tenantId}/${familyId}/problem-understanding`,
    reviewedDraftRef: response.draft_id,
    draftVersion: revision,
    provenanceRef: response.provenance_ref,
    humanGateReceiptRef: null,
    summary: livedExperience,
    centralTension,
    careIntent,
    explicitClaims: [...new Set(explicitClaims)],
    alternativeExplanations: hypothesisStatements,
    familyStrengths: strengths
      .map((item) => {
        const statement = readText(item?.statement);
        const whyItMatters = readText(item?.why_it_matters);
        return statement && whyItMatters
          ? `${statement}（${whyItMatters}）`
          : statement;
      })
      .filter((item): item is string => item !== null),
    desiredChange,
    desiredChangeBasis: response.output.desired_change.basis,
    observableSigns,
    unknowns: unknowns
      .map((item, index) => {
        const description = readText(item?.description);
        const whyItMatters = readText(item?.why_it_matters);
        if (!description) return null;
        return {
          key: readText(item?.unknown_id) ?? `unknown-${index + 1}`,
          label: whyItMatters
            ? `${description}（这会影响：${whyItMatters}）`
            : description,
        };
      })
      .filter((item): item is { key: string; label: string } => item !== null),
    followUpQuestions: followUps
      .map((item) => readText(item?.question))
      .filter((item): item is string => item !== null),
    limitations,
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
