/**
 * Shared mobile contract for family experience evidence.
 *
 * The first vertical slice keeps the transport adapter behind this shape. The
 * Python API has not frozen upload/transcription/OCR routes yet, so screens
 * must show an explicit unavailable state instead of pretending a media item
 * was stored. Test uses synthetic media through the same state machine.
 */
export type ExperienceMediaKind = "TEXT" | "VOICE" | "IMAGE" | "AUDIO" | "VIDEO" | "INTERACTIVE_CARD";

export type ExperienceMediaStatus =
  | "NOT_REQUESTED"
  | "CONSENT_REQUIRED"
  | "READY_TO_UPLOAD"
  | "UPLOADING"
  | "TRANSCRIBING"
  | "OCR_PROCESSING"
  | "PROCESSING"
  | "READY"
  | "UPLOAD_FAILED"
  | "TRANSCRIPTION_FAILED"
  | "OCR_FAILED"
  | "PLAYBACK_FAILED"
  | "LOW_BANDWIDTH"
  | "REJECTED";

export interface ExperienceMediaAttachment {
  media_id: string;
  kind: ExperienceMediaKind;
  status: ExperienceMediaStatus;
  content_locale: string;
  visibility: "FAMILY_PRIVATE";
  consent_ref: string | null;
  synthetic: boolean;
  provenance_ref: string;
  created_at: string;
}

export interface ExperienceMediaProjection {
  projection_version: "FAMILY_EXPERIENCE_MEDIA_V1";
  allowed_kinds: ExperienceMediaKind[];
  attachments: ExperienceMediaAttachment[];
  upload_enabled: boolean;
  low_bandwidth: boolean;
  accessibility: {
    captions_available: boolean;
    transcript_available: boolean;
    alt_text_required: boolean;
  };
}

/** Frozen mobile transport contract for the governed draft route. */
export type MultimodalDraftModality = "TEXT" | "IMAGE" | "AUDIO" | "VIDEO";
export type MultimodalRouteStrategy = "balanced" | "quality_first" | "latency_first" | "cost_first";

export interface MultimodalDraftRequest {
  run_id: string;
  prompt_version: string;
  schema_version: string;
  payload: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  modalities: readonly MultimodalDraftModality[];
  estimated_input_tokens: number;
  strategy: MultimodalRouteStrategy;
  max_latency_ms?: number;
  max_cost_microusd?: number;
  input_refs?: readonly string[];
  media_inputs?: ReadonlyArray<{
    media_type: "IMAGE" | "AUDIO" | "VIDEO" | "DOCUMENT";
    uri: string;
    mime_type: string;
    sha256: string;
  }>;
  session_id?: string;
}

export interface MultimodalDraftResponse {
  run_id: string;
  /** Null means the runtime returned a draft without a configured registry. */
  draft_id: string | null;
  provenance_ref: string | null;
  status: "DRAFT";
  output: Record<string, unknown>;
  requires_human_confirmation: true;
  scope: {
    tenant_id: string;
    region_id: string;
    family_id: string;
    subject_ids: readonly string[];
    purpose: string;
    consent_version: string;
    consent_granted: true;
    data_class: string;
    locale: string;
  };
  context_snapshot_ref: string;
  context_snapshot_expires_at: string;
  provenance: {
    provider_id: string;
    model: string;
    model_version: string;
    prompt_version: string;
    schema_version: string;
    context_snapshot_ref: string;
    latency_ms: number;
    data_class: string;
    use_case: string;
    confidence: number | null;
    generated_at: string;
  };
  route: {
    provider_id: string;
    vendor: string;
    model: string;
    model_version: string;
    strategy: MultimodalRouteStrategy;
    estimated_latency_ms: number;
    estimated_cost_microusd: number;
    fallback_provider_ids: readonly string[];
  };
}

export type MultimodalRunDecision = "confirm" | "rewrite" | "reject";
export type MultimodalFeedbackSignal = "helpful" | "not_helpful" | "request_human";

export interface MultimodalRunDecisionRequest {
  decision: MultimodalRunDecision;
  draft_version?: string;
  replacement_text?: string;
  reason?: string;
}

export interface MultimodalRunFeedbackRequest {
  signal: MultimodalFeedbackSignal;
  reason?: string;
  draft_version?: string;
  attempt_id?: string;
  candidate_id?: string;
  model_version?: string;
  benchmark_report_ref?: string;
  real_event_refs?: readonly string[];
}

export interface MultimodalRunHumanReviewRequest {
  reason: string;
  impact_scope?: string;
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
  artifact_refs: readonly string[];
  entries: ReadonlyArray<{
    event_id: string;
    interaction_type: string;
    sequence: number;
    payload: Record<string, unknown>;
    occurred_at: string;
  }>;
}

export function isMultimodalRunInteractionResponse(value: unknown): value is MultimodalRunInteractionResponse {
  if (!value || typeof value !== "object") return false;
  const response = value as Record<string, unknown>;
  return typeof response.run_id === "string"
    && typeof response.status === "string"
    && typeof response.interaction_ref === "string"
    && typeof response.idempotency_replayed === "boolean";
}

export function isMultimodalRunReplayResponse(value: unknown): value is MultimodalRunReplayResponse {
  if (!value || typeof value !== "object") return false;
  const response = value as Record<string, unknown>;
  return response.status === "DRAFT"
    && typeof response.run_id === "string"
    && typeof response.state === "string"
    && typeof response.event_sequence === "number"
    && (response.deletion_state === "active" || response.deletion_state === "deleted")
    && (response.draft_payload === null || (!!response.draft_payload && typeof response.draft_payload === "object" && !Array.isArray(response.draft_payload)))
    && Array.isArray(response.artifact_refs)
    && response.artifact_refs.every((item) => typeof item === "string")
    && Array.isArray(response.entries)
    && response.entries.every((entry) => {
      if (!entry || typeof entry !== "object") return false;
      const item = entry as Record<string, unknown>;
      return typeof item.event_id === "string"
        && typeof item.interaction_type === "string"
        && typeof item.sequence === "number"
        && !!item.payload && typeof item.payload === "object" && !Array.isArray(item.payload)
        && typeof item.occurred_at === "string";
    });
}

/** Runtime guard: malformed/unsafe responses never enter a screen state. */
export function isMultimodalDraftResponse(value: unknown): value is MultimodalDraftResponse {
  if (!value || typeof value !== "object") return false;
  const response = value as Record<string, unknown>;
  const provenance = response.provenance;
  const scope = response.scope;
  const route = response.route;
  const scopeRecord = scope && typeof scope === "object" ? scope as Record<string, unknown> : null;
  const provenanceRecord = provenance && typeof provenance === "object" ? provenance as Record<string, unknown> : null;
  const routeRecord = route && typeof route === "object" ? route as Record<string, unknown> : null;
  const nonEmptyString = (candidate: unknown): candidate is string => typeof candidate === "string" && candidate.trim().length > 0;
  const stringArray = (candidate: unknown): candidate is readonly string[] => Array.isArray(candidate) && candidate.every(nonEmptyString);
  return response.status === "DRAFT"
    && response.requires_human_confirmation === true
    && nonEmptyString(response.run_id)
    && (nonEmptyString(response.draft_id) || response.draft_id === null)
    && (nonEmptyString(response.provenance_ref) || response.provenance_ref === null)
    && !!response.output && typeof response.output === "object" && !Array.isArray(response.output)
    && nonEmptyString(response.context_snapshot_ref)
    && nonEmptyString(response.context_snapshot_expires_at)
    && !!scopeRecord
    && nonEmptyString(scopeRecord.tenant_id)
    && nonEmptyString(scopeRecord.region_id)
    && nonEmptyString(scopeRecord.family_id)
    && stringArray(scopeRecord.subject_ids)
    && nonEmptyString(scopeRecord.purpose)
    && nonEmptyString(scopeRecord.consent_version)
    && scopeRecord.consent_granted === true
    && nonEmptyString(scopeRecord.data_class)
    && nonEmptyString(scopeRecord.locale)
    && !!provenanceRecord
    && nonEmptyString(provenanceRecord.provider_id)
    && nonEmptyString(provenanceRecord.model)
    && nonEmptyString(provenanceRecord.model_version)
    && nonEmptyString(provenanceRecord.prompt_version)
    && nonEmptyString(provenanceRecord.schema_version)
    && nonEmptyString(provenanceRecord.context_snapshot_ref)
    && typeof provenanceRecord.latency_ms === "number"
    && nonEmptyString(provenanceRecord.data_class)
    && nonEmptyString(provenanceRecord.use_case)
    && typeof provenanceRecord.generated_at === "string"
    && !!routeRecord
    && nonEmptyString(routeRecord.provider_id)
    && nonEmptyString(routeRecord.vendor)
    && nonEmptyString(routeRecord.model)
    && nonEmptyString(routeRecord.model_version)
    && stringArray(routeRecord.fallback_provider_ids);
}

/**
 * Media projection remains adapter-shaped; generation drafts use the frozen
 * Family API route exposed by FamilyApiClient below. Screens must not invent
 * upload/transcription endpoint paths or call providers directly.
 */
export interface MultimodalAdapter {
  getProjection(): Promise<ExperienceMediaProjection>;
  requestConsent(kind: ExperienceMediaKind): Promise<{ consent_ref: string }>;
  upload(input: { kind: ExperienceMediaKind; uri: string; consent_ref: string }): Promise<ExperienceMediaAttachment>;
}

/**
 * Test-only adapter: it follows the production shape while keeping media in
 * memory. It is intentionally opt-in; no screen silently switches to it when
 * a production API fails.
 */
export function createSyntheticMultimodalAdapter(): MultimodalAdapter {
  let attachments: ExperienceMediaAttachment[] = [];
  return {
    async getProjection() {
      return {
        projection_version: "FAMILY_EXPERIENCE_MEDIA_V1",
        allowed_kinds: ["TEXT", "VOICE", "IMAGE", "AUDIO", "VIDEO", "INTERACTIVE_CARD"],
        attachments,
        upload_enabled: true,
        low_bandwidth: false,
        accessibility: { captions_available: true, transcript_available: true, alt_text_required: true },
      };
    },
    async requestConsent(kind) {
      return { consent_ref: `synthetic-consent-${kind.toLowerCase()}` };
    },
    async upload(input) {
      if (!input.uri.trim() || !input.consent_ref.trim()) throw new Error("synthetic media requires uri and consent_ref");
      const attachment: ExperienceMediaAttachment = {
        media_id: `synthetic-media-${attachments.length + 1}`,
        kind: input.kind,
        status: "READY",
        content_locale: "zh-CN",
        visibility: "FAMILY_PRIVATE",
        consent_ref: input.consent_ref,
        synthetic: true,
        provenance_ref: "synthetic-multimodal-adapter.v1",
        created_at: new Date().toISOString(),
      };
      attachments = [...attachments, attachment];
      return attachment;
    },
  };
}
