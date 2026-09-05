export type DataClass =
  | "SYNTHETIC"
  | "OPERATIONAL_TEXT"
  | "FAMILY_PRIVATE_TEXT"
  | "MINOR_PERSONAL_DATA";

export type RunStatus =
  | "idle"
  | "validating"
  | "running"
  | "partial"
  | "success"
  | "refused"
  | "timeout"
  | "retrying"
  | "human_review"
  | "deleted";

export type ExperienceErrorCode =
  | "CONSENT_REQUIRED"
  | "PROVIDER_NOT_ADMITTED"
  | "TIMEOUT"
  | "MEDIA_DELETED"
  | "RUN_NOT_FOUND"
  | "CONFLICT"
  | "SCOPE_MISMATCH"
  | "INVALID_INPUT";

export type MediaInput = {
  media_type: "IMAGE";
  uri: string;
  mime_type: string;
  sha256: string;
};

export type ExperienceScope = {
  tenant_id: string;
  region_id: string;
  family_id: string;
  subject_ids: string[];
  purpose: string;
  consent_version: string;
  consent_granted: boolean;
  locale: string;
};

export type CreateDraftInput = {
  run_id: string;
  use_case: string;
  prompt_version: string;
  schema_version: string;
  data_class: DataClass;
  context_snapshot_ref: string;
  payload: { expression: string };
  input_refs: string[];
  media_inputs: MediaInput[];
  scope: ExperienceScope;
  output_schema?: Record<string, unknown>;
  modalities?: Array<"TEXT" | "IMAGE" | "AUDIO" | "VIDEO">;
  estimated_input_tokens?: number;
  strategy?: "balanced" | "quality_first" | "latency_first" | "cost_first";
  limits?: { max_latency_ms?: number; max_cost_microusd?: number };
  session_id?: string;
};

export type ExperienceProvenance = {
  provenance_ref: string | null;
  kind: "AI_DRAFT" | "SYNTHETIC_TEST";
  model_attempt_ref: string | null;
  context_snapshot_ref: string;
  prompt_version: string;
  schema_version: string;
  captured_at: string;
  provider_id?: string;
  model?: string;
  model_version?: string;
  latency_ms?: number;
  confidence?: number | null;
  data_class?: string;
  use_case?: string;
  generated_at?: string;
};

export type BenchmarkMetadata = {
  benchmark_report_ref: string;
  benchmark_case_version: string;
  candidate_id: string;
  provider_id: string;
  model: string;
  model_version: string;
  quality_score?: number | null;
  safety_score?: number | null;
  cost_score?: number | null;
  latency_score?: number | null;
  composite_score?: number | null;
  score_weights?: Record<string, number>;
  benchmark_gate_status: "ADMITTED" | "PILOT_CANDIDATE" | "BLOCKED" | "UNKNOWN";
  benchmark_gate_failures?: string[];
  education_outcome_status: "NOT_MEASURED" | "MEASURED";
};

export type ExperienceDraft = {
  run_id: string;
  draft_version: string;
  status: "DRAFT";
  output: { understanding: string; next_step: string };
  limitations: string[];
  provenance: ExperienceProvenance;
  requires_human_confirmation: true;
  media_inputs: MediaInput[];
  correlation_id: string;
  benchmark?: BenchmarkMetadata;
};

export type DraftDecisionInput = {
  run_id: string;
  family_id?: string;
  decision: "confirm" | "reject" | "rewrite";
  draft_version?: string;
  replacement_text?: string;
  reason?: string;
};

export type FeedbackInput = {
  run_id: string;
  family_id?: string;
  signal: "helpful" | "not_helpful" | "request_human";
  reason?: string;
  draft_version?: string;
  candidate_id?: string;
  model_version?: string;
  attempt_id?: string;
  benchmark_report_ref?: string;
  event_refs?: string[];
};

export type HumanReviewInput = { run_id: string; family_id?: string; reason: string; impact_scope?: string };
export type InteractionStatus = "recorded" | "replayed" | "deleted";
export type InteractionReceipt = {
  run_id: string;
  status: InteractionStatus;
  interaction_ref: string;
  idempotency_replayed: boolean;
};
export type DecisionReceipt = Omit<InteractionReceipt, "status"> & {
  // Kept for the development fake's explicit human-gate wording.
  status: InteractionStatus | "pending_human_confirmation" | "rejected";
};
export type FeedbackReceipt = InteractionReceipt & { recorded: boolean };
export type HumanReviewReceipt = Omit<InteractionReceipt, "status"> & { status: InteractionStatus | "human_review" };
export type DeletionReceipt = InteractionReceipt;
export type ReplayEntry = {
  label: string;
  at: string;
  event_id?: string;
  interaction_type?: string;
  sequence?: number;
  payload?: Record<string, unknown>;
};
export type ReplaySnapshot = {
  run_id: string;
  status: "DRAFT";
  state: string;
  event_sequence: number;
  deletion_state: "active" | "deleted";
  draft_payload: Record<string, unknown> | null;
  artifact_refs: string[];
  entries: ReplayEntry[];
  benchmark?: Pick<BenchmarkMetadata, "benchmark_report_ref" | "benchmark_case_version" | "model_version" | "benchmark_gate_status">;
};

export class ExperienceApiError extends Error {
  readonly code: ExperienceErrorCode;
  readonly status: RunStatus;

  constructor(code: ExperienceErrorCode, status: RunStatus, message: string) {
    super(message);
    this.name = "ExperienceApiError";
    this.code = code;
    this.status = status;
  }
}

export interface ExperienceApiClient {
  createDraft(input: CreateDraftInput, idempotencyKey: string): Promise<ExperienceDraft>;
  decide(input: DraftDecisionInput, idempotencyKey: string): Promise<DecisionReceipt>;
  submitFeedback(input: FeedbackInput, idempotencyKey: string): Promise<FeedbackReceipt>;
  requestHuman(input: HumanReviewInput, idempotencyKey: string): Promise<HumanReviewReceipt>;
  deleteRun(runId: string, idempotencyKey: string): Promise<DeletionReceipt>;
  replayRun(runId: string): Promise<ReplaySnapshot>;
}
