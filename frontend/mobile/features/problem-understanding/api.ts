import type {
  AuthorizedMediaAttachment,
  UnderstandingDraft,
  UnderstandingInput,
} from "./model";

export const MAX_AUTHORIZED_VIDEO_BYTES = 50 * 1024 * 1024;

export interface MultimodalDraftRequest {
  run_id: string;
  prompt_version: string;
  schema_version: string;
  payload: {
    expression: string;
    revision: number;
    conversation_turns: {
      input_ref: string;
      kind: UnderstandingInput["kind"];
      text: string;
      created_at: string;
    }[];
    prior_run_id: string | null;
  };
  output_schema: Record<string, unknown>;
  modalities: ("TEXT" | "IMAGE" | "VIDEO")[];
  estimated_input_tokens: number;
  strategy: "balanced";
  input_refs: string[];
  media_inputs: {
    media_type: "IMAGE" | "VIDEO";
    uri: string;
    mime_type: string;
    sha256: string;
  }[];
  session_id: string;
}

export const FAMILY_UNDERSTANDING_OUTPUT_SCHEMA: Record<string, unknown> = {
  type: "object",
  additionalProperties: false,
  required: [
    "understanding",
    "hypotheses",
    "unknowns",
    "follow_up_questions",
    "strengths",
    "desired_change",
    "limitations",
  ],
  properties: {
    understanding: {
      type: "object",
      additionalProperties: false,
      required: ["lived_experience", "central_tension", "care_intent"],
      properties: {
        lived_experience: { type: "string", minLength: 1 },
        central_tension: { type: "string", minLength: 1 },
        care_intent: { type: "string", minLength: 1 },
      },
    },
    hypotheses: {
      type: "array",
      minItems: 1,
      maxItems: 3,
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "hypothesis_id",
          "statement",
          "rationale",
          "evidence",
          "knowledge_refs",
          "confidence",
          "disconfirming_evidence_needed",
        ],
        properties: {
          hypothesis_id: { type: "string", pattern: "^H[1-3]$" },
          statement: { type: "string", minLength: 1 },
          rationale: { type: "string", minLength: 1 },
          evidence: {
            type: "array",
            minItems: 1,
            items: {
              type: "object",
              additionalProperties: false,
              required: ["source_type", "source_ref", "observation"],
              properties: {
                source_type: {
                  type: "string",
                  enum: ["PARENT_TEXT", "AUTHORIZED_IMAGE", "AUTHORIZED_VIDEO"],
                },
                source_ref: { type: "string", minLength: 1 },
                observation: { type: "string", minLength: 1 },
              },
            },
          },
          knowledge_refs: {
            type: "array",
            minItems: 1,
            items: { type: "string", minLength: 1 },
          },
          confidence: { type: "string", enum: ["LOW", "MEDIUM", "HIGH"] },
          disconfirming_evidence_needed: { type: "string", minLength: 1 },
        },
      },
    },
    unknowns: {
      type: "array",
      minItems: 1,
      maxItems: 4,
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "unknown_id",
          "description",
          "why_it_matters",
          "related_hypothesis_ids",
        ],
        properties: {
          unknown_id: { type: "string", pattern: "^U[1-4]$" },
          description: { type: "string", minLength: 1 },
          why_it_matters: { type: "string", minLength: 1 },
          related_hypothesis_ids: {
            type: "array",
            minItems: 1,
            items: { type: "string", pattern: "^H[1-3]$" },
          },
        },
      },
    },
    follow_up_questions: {
      type: "array",
      minItems: 1,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["question_id", "question", "purpose", "answers_unknown_ids"],
        properties: {
          question_id: { type: "string", minLength: 1 },
          question: { type: "string", minLength: 1 },
          purpose: { type: "string", minLength: 1 },
          answers_unknown_ids: {
            type: "array",
            minItems: 1,
            items: { type: "string", pattern: "^U[1-4]$" },
          },
        },
      },
    },
    strengths: {
      type: "array",
      minItems: 1,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["statement", "evidence_refs", "why_it_matters"],
        properties: {
          statement: { type: "string", minLength: 1 },
          evidence_refs: {
            type: "array",
            minItems: 1,
            items: { type: "string", minLength: 1 },
          },
          why_it_matters: { type: "string", minLength: 1 },
        },
      },
    },
    desired_change: {
      type: "object",
      additionalProperties: false,
      required: [
        "statement",
        "basis",
        "observable_signs",
        "confirmation_question",
      ],
      properties: {
        statement: { type: "string", minLength: 1 },
        basis: { type: "string", enum: ["EXPLICIT", "INFERRED"] },
        observable_signs: {
          type: "array",
          minItems: 1,
          items: { type: "string", minLength: 1 },
        },
        confirmation_question: { type: "string", minLength: 1 },
      },
    },
    limitations: {
      type: "array",
      minItems: 1,
      items: { type: "string", minLength: 1 },
    },
  },
};

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
      source_type: "PARENT_TEXT" | "AUTHORIZED_IMAGE" | "AUTHORIZED_VIDEO";
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
  conversationTurns: readonly UnderstandingInput[];
  priorRunId: string | null;
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
    payload: {
      expression: input.expression,
      revision: input.revision,
      conversation_turns: input.conversationTurns.map((turn) => ({
        input_ref: turn.inputRef,
        kind: turn.kind,
        text: turn.text,
        created_at: turn.createdAt,
      })),
      prior_run_id: input.priorRunId,
    },
    output_schema: FAMILY_UNDERSTANDING_OUTPUT_SCHEMA,
    modalities: [
      "TEXT",
      ...new Set(mediaInputs.map((item) => item.media_type)),
    ],
    estimated_input_tokens: Math.max(
      64,
      Math.ceil(input.expression.length * 1.5),
    ),
    strategy: "balanced",
    input_refs: [
      ...input.conversationTurns.map((turn) => turn.inputRef),
      ...mediaInputs.map((item) => item.uri),
    ],
    media_inputs: mediaInputs,
    session_id: input.sessionId,
  };
}

export function toUnderstandingDraft(
  response: MultimodalDraftResponse,
  tenantId: string,
  familyId: string,
  context: {
    revision: number;
    mediaCount: number;
    sourceRefs: readonly string[];
  },
): UnderstandingDraft {
  const { mediaCount, revision, sourceRefs } = context;
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
    unknowns.length === 0 ||
    followUps.length === 0 ||
    !desiredChange ||
    limitations.length === 0 ||
    !generatedAt
  ) {
    throw new Error("UNDERSTANDING_RESPONSE_INVALID");
  }

  assertFamilyUnderstandingOutput(response.output, new Set(sourceRefs));

  const explicitClaims = hypotheses
    .flatMap((item) => (Array.isArray(item?.evidence) ? item.evidence : []))
    .filter((item) => item?.source_type === "PARENT_TEXT")
    .map((item) => readText(item?.observation))
    .filter((item): item is string => item !== null);

  const mappedHypotheses = hypotheses.map((item) => ({
    key: item.hypothesis_id,
    statement: item.statement.trim(),
    rationale: item.rationale.trim(),
    evidenceObservations: item.evidence.map((evidence) =>
      evidence.observation.trim(),
    ),
    knowledgeBasisCount: item.knowledge_refs.length,
    confidence: item.confidence,
    disconfirmingEvidenceNeeded: item.disconfirming_evidence_needed.trim(),
  }));

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
    hypotheses: mappedHypotheses,
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

function assertFamilyUnderstandingOutput(
  output: FamilyUnderstandingOutput,
  allowedSourceRefs: ReadonlySet<string>,
): void {
  const hypothesisIds = new Set<string>();
  for (const hypothesis of output.hypotheses) {
    const id = readText(hypothesis?.hypothesis_id);
    const statement = readText(hypothesis?.statement);
    const rationale = readText(hypothesis?.rationale);
    const disconfirmingEvidence = readText(
      hypothesis?.disconfirming_evidence_needed,
    );
    const evidence = Array.isArray(hypothesis?.evidence)
      ? hypothesis.evidence
      : [];
    const knowledgeRefs = readTextList(hypothesis?.knowledge_refs);
    if (
      !id ||
      !/^H[1-3]$/.test(id) ||
      hypothesisIds.has(id) ||
      !statement ||
      !rationale ||
      !disconfirmingEvidence ||
      !["LOW", "MEDIUM", "HIGH"].includes(hypothesis?.confidence) ||
      evidence.length === 0 ||
      knowledgeRefs.length === 0 ||
      evidence.some(
        (item) =>
          !["PARENT_TEXT", "AUTHORIZED_IMAGE", "AUTHORIZED_VIDEO"].includes(
            item?.source_type,
          ) ||
          !readText(item?.source_ref) ||
          !allowedSourceRefs.has(item.source_ref) ||
          !readText(item?.observation),
      )
    ) {
      throw new Error("UNDERSTANDING_RESPONSE_INVALID");
    }
    hypothesisIds.add(id);
  }

  const unknownIds = new Set<string>();
  for (const unknown of output.unknowns) {
    const id = readText(unknown?.unknown_id);
    const relatedIds = readTextList(unknown?.related_hypothesis_ids);
    if (
      !id ||
      !/^U[1-4]$/.test(id) ||
      unknownIds.has(id) ||
      !readText(unknown?.description) ||
      !readText(unknown?.why_it_matters) ||
      relatedIds.length === 0 ||
      relatedIds.some((relatedId) => !hypothesisIds.has(relatedId))
    ) {
      throw new Error("UNDERSTANDING_RESPONSE_INVALID");
    }
    unknownIds.add(id);
  }

  for (const question of output.follow_up_questions) {
    const answeredUnknownIds = readTextList(question?.answers_unknown_ids);
    if (
      !readText(question?.question_id) ||
      !readText(question?.question) ||
      !readText(question?.purpose) ||
      answeredUnknownIds.length === 0 ||
      answeredUnknownIds.some((unknownId) => !unknownIds.has(unknownId))
    ) {
      throw new Error("UNDERSTANDING_RESPONSE_INVALID");
    }
  }

  if (
    output.strengths.some(
      (strength) =>
        !readText(strength?.statement) ||
        readTextList(strength?.evidence_refs).length === 0 ||
        readTextList(strength?.evidence_refs).some(
          (evidenceRef) => !allowedSourceRefs.has(evidenceRef),
        ) ||
        !readText(strength?.why_it_matters),
    ) ||
    !["EXPLICIT", "INFERRED"].includes(output.desired_change?.basis) ||
    readTextList(output.desired_change?.observable_signs).length === 0 ||
    !readText(output.desired_change?.confirmation_question)
  ) {
    throw new Error("UNDERSTANDING_RESPONSE_INVALID");
  }
}

export function isAuthorizedMediaAttachment(
  attachment: AuthorizedMediaAttachment,
): boolean {
  const mimeMatchesType =
    (attachment.mediaType === "IMAGE" &&
      /^(?:image\/(?:gif|jpeg|png|webp))$/i.test(attachment.mimeType)) ||
    (attachment.mediaType === "VIDEO" &&
      /^(?:video\/(?:mp4|quicktime|webm))$/i.test(attachment.mimeType));
  const videoSizeIsAllowed =
    attachment.mediaType !== "VIDEO" ||
    (Number.isSafeInteger(attachment.byteSize) &&
      (attachment.byteSize ?? 0) > 0 &&
      (attachment.byteSize ?? 0) <= MAX_AUTHORIZED_VIDEO_BYTES);
  return (
    mimeMatchesType &&
    videoSizeIsAllowed &&
    /^(?:media|asset|object|opaque):[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/i.test(
      attachment.uri,
    ) &&
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
