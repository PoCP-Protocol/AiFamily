import type {
  DraftBinding,
  UnderstandingDraft,
  UnderstandingReceipt,
  ViewedDraftBinding,
} from "./model";

export interface GenerateUnderstandingRequest {
  run_id: string;
  tenant_id: string;
  guardian_input_ref: string;
  guardian_text: string;
  revision: number;
  prior_draft_artifact_hash: string | null;
}

export function toViewedDraftBinding(
  response: ViewedUnderstandingResponse,
  draft: DraftBinding,
): ViewedDraftBinding {
  if (
    response.status !== "VIEWED" ||
    response.scope_ref !== draft.scopeRef ||
    response.artifact_ref !== draft.reviewedDraftRef ||
    response.artifact_version !== draft.draftVersion ||
    response.provenance_ref !== draft.provenanceRef ||
    !response.view_event_ref
  ) {
    throw new Error("UNDERSTANDING_VIEW_INVALID");
  }
  return {
    signalRef: draft.signalRef,
    signalVersion: draft.signalVersion,
    scopeRef: draft.scopeRef,
    reviewedDraftRef: draft.reviewedDraftRef,
    draftVersion: draft.draftVersion,
    provenanceRef: draft.provenanceRef,
    viewEventRef: response.view_event_ref,
  };
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

export interface ReviewUnderstandingRequest {
  artifact_version: number;
  provenance_ref: string;
  view_event_ref: string;
}

export interface ViewedUnderstandingResponse {
  view_event_ref: string;
  status: "VIEWED";
  scope_ref: string;
  artifact_ref: string;
  artifact_version: number;
  provenance_ref: string;
  viewed_at: string;
}

export interface ConfirmedUnderstandingResponse {
  receipt_ref: string;
  status: "EFFECTIVE";
  scope_ref: string;
  artifact_ref: string;
  artifact_version: number;
  provenance_ref: string;
  expires_at: string;
  growth_intent_ref?: string | null;
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

export async function recordUnderstandingView(
  baseUrl: string,
  token: string,
  familyId: string,
  artifactRef: string,
  body: ReviewUnderstandingRequest,
  fetcher: typeof fetch = fetch,
): Promise<ViewedUnderstandingResponse> {
  return postReview<ViewedUnderstandingResponse>(
    baseUrl,
    token,
    familyId,
    artifactRef,
    "views",
    body,
    fetcher,
  );
}

export async function confirmUnderstanding(
  baseUrl: string,
  token: string,
  familyId: string,
  artifactRef: string,
  body: ReviewUnderstandingRequest,
  fetcher: typeof fetch = fetch,
): Promise<ConfirmedUnderstandingResponse> {
  return postReview<ConfirmedUnderstandingResponse>(
    baseUrl,
    token,
    familyId,
    artifactRef,
    "confirmations",
    body,
    fetcher,
  );
}

export function toUnderstandingReceipt(
  response: ConfirmedUnderstandingResponse,
  viewed: ViewedDraftBinding,
): UnderstandingReceipt {
  if (
    response.status !== "EFFECTIVE" ||
    response.scope_ref !== viewed.scopeRef ||
    response.artifact_ref !== viewed.reviewedDraftRef ||
    response.artifact_version !== viewed.draftVersion ||
    response.provenance_ref !== viewed.provenanceRef ||
    !response.receipt_ref
  ) {
    throw new Error("UNDERSTANDING_CONFIRMATION_INVALID");
  }
  return {
    ...viewed,
    humanGateReceiptRef: response.receipt_ref,
    receiptRef: response.receipt_ref,
    growthIntentRef: response.growth_intent_ref ?? null,
  };
}

async function postReview<T>(
  baseUrl: string,
  token: string,
  familyId: string,
  artifactRef: string,
  action: "views" | "confirmations",
  body: ReviewUnderstandingRequest,
  fetcher: typeof fetch,
): Promise<T> {
  const response = await fetcher(
    `${baseUrl.replace(/\/+$/, "")}/v1/families/${encodeURIComponent(familyId)}` +
      `/understanding-drafts/${encodeURIComponent(artifactRef)}/${action}`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "x-correlation-id": body.view_event_ref,
        "x-source": "family-ai-mobile",
      },
      body: JSON.stringify(body),
    },
  );
  const payload = (await response.json()) as unknown;
  if (!response.ok) {
    throw new Error(readErrorCode(payload) ?? `HTTP_${response.status}`);
  }
  return payload as T;
}

function readErrorCode(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object") return null;
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" && code ? code : null;
}

function readText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
