import type {
  AssessmentMutationReceipt,
  AssessmentResponseType,
  GrowthHypothesisDecisionReceipt,
  Ui02AssessmentProjection,
  Ui03GrowthHypothesisProjection,
} from "./assessment-api-contracts";
import type {
  AvailabilitySlotDto,
  ServiceBookingReceipt,
  ServiceCustomerProjection,
  ServiceOfferingDto,
  SubmitServiceBookingBody,
} from "./service-api-contracts";
import type {
  GrowthPriorityProjection,
  GrowthPriorityDecision,
  JourneyPhaseDecision,
  JourneyPlanProjection,
  PlanPreviewProjection,
} from "./growth-api-contracts";
import {
  isMultimodalDraftResponse,
  isMultimodalRunInteractionResponse,
  isMultimodalRunReplayResponse,
  type MultimodalDraftRequest,
  type MultimodalDraftResponse,
  type MultimodalRunDecisionRequest,
  type MultimodalRunFeedbackRequest,
  type MultimodalRunHumanReviewRequest,
  type MultimodalRunInteractionResponse,
  type MultimodalRunReplayResponse,
} from "./multimodal-api-contracts";
import type {
  FamilyAchievementFeedbackResponse,
  FamilyAchievementNotificationReadResponse,
  FamilyAchievementNotificationsResponse,
  FamilyExperienceAnalyticsResponse,
} from "./feedback-api-contracts";

const DEFAULT_TIMEOUT_MS = 8_000;

export interface FamilyApiRequestSnapshot {
  activeCount: number;
  lastPath: string | null;
  lastError: string | null;
  lastResult: "unknown" | "data" | "empty";
  revision: number;
}

let requestSnapshot: FamilyApiRequestSnapshot = { activeCount: 0, lastPath: null, lastError: null, lastResult: "unknown", revision: 0 };
const requestListeners = new Set<() => void>();

export function getFamilyApiRequestSnapshot() {
  return requestSnapshot;
}

export function subscribeFamilyApiRequestSnapshot(listener: () => void) {
  requestListeners.add(listener);
  return () => requestListeners.delete(listener);
}

function updateRequestSnapshot(change: Partial<Omit<FamilyApiRequestSnapshot, "revision">>) {
  requestSnapshot = { ...requestSnapshot, ...change, revision: requestSnapshot.revision + 1 };
  requestListeners.forEach((listener) => listener());
}

const projectionCollectionKeys = new Set([
  "items", "entries", "records", "products", "offerings", "plans", "bookings", "entitlements", "activities", "contents", "posts", "orders", "assets", "services", "events", "milestones", "tasks",
]);

export function isProjectionPayloadEmpty(payload: unknown): boolean {
  if (payload === null || payload === undefined) return true;
  if (Array.isArray(payload)) return payload.length === 0;
  if (typeof payload !== "object") return false;
  const entries = Object.entries(payload as Record<string, unknown>);
  if (entries.length === 0) return true;
  const collections = entries.filter(([key, value]) => projectionCollectionKeys.has(key) && Array.isArray(value));
  return collections.length > 0 && collections.every(([, value]) => (value as unknown[]).length === 0);
}

export interface FamilyContextSummary {
  type: "FAMILY";
  tenant_id: string;
  family_id: string;
  person_id: string;
  membership_id: string;
  role: string;
}

export interface AccountSessionResponse {
  token: string;
  expires_at: string;
  account_id: string;
}

export interface FamilyContextsResponse {
  account_id: string;
  contexts: FamilyContextSummary[];
}

export interface ActiveOnboarding {
  onboarding_id?: string;
  family_id?: string;
  status?: string;
  [key: string]: unknown;
}

export class FamilyApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly payload: unknown,
  ) {
    super(message);
    this.name = "FamilyApiError";
  }
}

interface FamilyApiRequestOptions {
  method?: "DELETE" | "GET" | "POST";
  token?: string | null;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
}

function trimBaseUrl(value: string | undefined) {
  return (value ?? "").trim().replace(/\/+$/, "");
}

export function createMobileRequestId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export class FamilyApiClient {
  readonly baseUrl: string;

  constructor(
    baseUrl = process.env.EXPO_PUBLIC_FAMILY_API_BASE_URL,
    private readonly fetcher: typeof fetch = fetch,
  ) {
    this.baseUrl = trimBaseUrl(baseUrl);
  }

  get configured() {
    return this.baseUrl.length > 0;
  }

  private async request<T>(path: string, options: FamilyApiRequestOptions = {}): Promise<T> {
    if (!this.configured) {
      throw new FamilyApiError("Family API 尚未配置", 0, "FAMILY_API_NOT_CONFIGURED", null);
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...options.headers,
    };
    if (options.token) headers.Authorization = `Bearer ${options.token}`;
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    updateRequestSnapshot({ activeCount: requestSnapshot.activeCount + 1, lastPath: path, lastError: null, lastResult: "unknown" });

    try {
      const response = await this.fetcher(`${this.baseUrl}${path}`, {
        method: options.method ?? "GET",
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: "omit",
        signal: controller.signal,
      });
      const raw = await response.text();
      const payload = raw ? safeJson(raw) : null;
      if (!response.ok) {
        const code = readErrorCode(payload) ?? `HTTP_${response.status}`;
        throw new FamilyApiError(code, response.status, code, payload);
      }
      updateRequestSnapshot({ activeCount: Math.max(0, requestSnapshot.activeCount - 1), lastPath: path, lastError: null, lastResult: isProjectionPayloadEmpty(payload) ? "empty" : "data" });
      return payload as T;
    } catch (error) {
      if (error instanceof FamilyApiError) {
        updateRequestSnapshot({ activeCount: Math.max(0, requestSnapshot.activeCount - 1), lastPath: path, lastError: error.code });
        throw error;
      }
      if (error instanceof Error && error.name === "AbortError") {
        const timeoutError = new FamilyApiError("Family API 请求超时", 0, "FAMILY_API_TIMEOUT", null);
        updateRequestSnapshot({ activeCount: Math.max(0, requestSnapshot.activeCount - 1), lastPath: path, lastError: timeoutError.code });
        throw timeoutError;
      }
      const networkError = new FamilyApiError(error instanceof Error ? error.message : "Family API 网络错误", 0, "FAMILY_API_NETWORK_ERROR", null);
      updateRequestSnapshot({ activeCount: Math.max(0, requestSnapshot.activeCount - 1), lastPath: path, lastError: networkError.code });
      throw networkError;
    } finally {
      clearTimeout(timer);
    }
  }

  issueDevAccountSession(externalRef: string) {
    return this.request<AccountSessionResponse>("/auth/account-session", {
      method: "POST",
      body: { external_ref: externalRef },
    });
  }

  getAccount(token: string) {
    return this.request<{ account_id: string; session_id: string }>("/auth/me", { token });
  }

  getContexts(token: string) {
    return this.request<FamilyContextsResponse>("/auth/contexts", { token });
  }

  revokeSession(token: string) {
    return this.request<{ revoked: boolean }>("/auth/session/revoke", { method: "POST", token });
  }

  getActiveOnboarding(token: string, familyId: string) {
    return this.request<ActiveOnboarding | null>(`/families/${familyId}/growth/onboarding/active`, { token });
  }

  startGrowthOnboarding<T>(token: string, familyId: string, body: { childId: string; guardianPersonId: string; structuredSafetySignals: string[] }, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/growth/onboarding`, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-onboarding-start"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  getDevCoreGrowth<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/dev/core-growth`, { token });
  }

  getDevPlatformSurfaces<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/dev/platform-surfaces`, { token });
  }

  getCommerceProducts<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/commerce/products`, { token });
  }

  submitCommerceIntent<T>(token: string, familyId: string, body: { page_id: "UI-14"; product_ref: string; product_version: number; attributes?: Record<string, unknown> }, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/commerce/order-intents`, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-commerce"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  getCommerceCustomerProjection<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/commerce/customer-projection`, { token });
  }

  getMembershipPlans<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/membership/plans`, { token });
  }

  getMembershipCustomerProjection<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/membership/customer-projection`, { token });
  }

  getServiceOfferings(token: string, familyId: string, _legacyFilters?: unknown) {
    return this.request<ServiceOfferingDto[]>(`/families/${familyId}/orchestration/test-loop/services/offerings`, { token });
  }

  getActivityCatalog<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/orchestration/test-loop/services/activities`, { token });
  }

  getServiceSlots(token: string, familyId: string, serviceOfferingId: string, _legacyVersion?: number) {
    const query = new URLSearchParams({ service_offering_id: serviceOfferingId });
    return this.request<AvailabilitySlotDto[]>(`/families/${familyId}/orchestration/test-loop/services/slots?${query.toString()}`, { token });
  }

  submitServiceBooking(
    token: string,
    familyId: string,
    body: SubmitServiceBookingBody | {
      page_id: "UI-21";
      service_offering_ref: string;
      service_offering_version: number;
      availability_slot_ref: string;
      attributes?: Record<string, unknown>;
    },
    idempotencyKey: string,
  ) {
    if (!("service_offering_id" in body)) {
      throw new FamilyApiError("SERVICE Mobile 契约需要内部 offering/slot id", 0, "SERVICE_CONTRACT_MIGRATION_REQUIRED", body);
    }
    return this.request<ServiceBookingReceipt>(`/families/${familyId}/orchestration/test-loop/services/booking-requests`, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-service"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  async getServiceCustomerProjection(token: string, familyId: string) {
    const projection = await this.request<Omit<ServiceCustomerProjection, "bookings"> & { bookings: Array<Omit<ServiceCustomerProjection["bookings"][number], "status">> }>(`/families/${familyId}/orchestration/test-loop/services/customer-projection`, { token });
    return { ...projection, bookings: projection.bookings.map((item) => ({ ...item, status: item.booking_status })) } satisfies ServiceCustomerProjection;
  }

  recordDevFlowEvent<T>(token: string, familyId: string, body: { ui_id: string; command: string; selection?: string }, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/dev/flow-events`, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-correlation"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  getReportExplanation<T>(token: string, familyId: string, onboardingId: string) {
    return this.request<T>(`/families/${familyId}/growth/onboardings/${onboardingId}/report-explanation`, { token });
  }

  getPlanPreview(token: string, familyId: string, onboardingId: string) {
    return this.request<PlanPreviewProjection>(`/families/${familyId}/growth/onboardings/${onboardingId}/plan-preview`, { token });
  }

  refreshPlanPreview<T>(token: string, familyId: string, onboardingId: string, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/growth/onboardings/${onboardingId}/plan-preview/refresh`, {
      method: "POST",
      token,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-plan"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  getServiceJourney<T>(token: string, familyId: string, onboardingId: string) {
    return this.request<T>(`/families/${familyId}/growth/onboardings/${onboardingId}/service-journey`, { token });
  }

  createPrivateCheckinDraft<T>(token: string, familyId: string, onboardingId: string, actionRef: "WEEKLY_ACTION_SEE" | "WEEKLY_ACTION_ADJUST" | "PAUSE_AND_RETURN", idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/growth/onboardings/${onboardingId}/service-journey/checkin-drafts`, {
      method: "POST",
      token,
      body: { action_ref: actionRef },
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-checkin"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  getGrowthProfileReadback<T>(token: string, familyId: string, onboardingId: string) {
    return this.request<T>(`/families/${familyId}/growth/onboardings/${onboardingId}/growth-profile-readback`, { token });
  }

  getFamilyReviewReadback<T>(token: string, familyId: string, onboardingId: string) {
    return this.request<T>(`/families/${familyId}/growth/onboardings/${onboardingId}/family-review-readback`, { token });
  }

  getJourneyPlan(token: string, familyId: string) {
    return this.request<JourneyPlanProjection>(`/families/${familyId}/growth/journey-plan`, { token });
  }

  getGenerativeGrowthPlan<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/growth/generative-plan`, { token });
  }

  adoptGenerativeGrowthPlan<T>(
    token: string,
    familyId: string,
    body: {
      draft_ref: string;
      draft_version?: string;
      selected_choices: Record<string, string>;
      parent_note?: string;
    },
    idempotencyKey: string,
  ) {
    return this.request<T>(`/families/${familyId}/growth/generative-plan/adopt`, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-generative-plan"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  getGrowthPriority(token: string, familyId: string, onboardingId: string) {
    return this.request<GrowthPriorityProjection>(`/families/${familyId}/growth/onboardings/${onboardingId}/priority`, { token });
  }

  createJourneyPlan(token: string, familyId: string, onboardingId: string, priorityId: string, idempotencyKey: string) {
    return this.request<JourneyPlanProjection>(`/families/${familyId}/growth/onboardings/${onboardingId}/journey-plan`, {
      method: "POST",
      token,
      body: { priority_id: priorityId },
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-journey-plan"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  confirmJourneyPlan(token: string, familyId: string, planId: string, idempotencyKey: string) {
    return this.request<JourneyPlanProjection>(`/families/${familyId}/growth/journey-plans/${planId}/confirm`, {
      method: "POST",
      token,
      body: {},
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-journey-plan-confirm"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  reviewJourneyPhase(token: string, familyId: string, planId: string, decision: JourneyPhaseDecision, idempotencyKey: string) {
    return this.request<JourneyPlanProjection>(`/families/${familyId}/growth/journey-plans/${planId}/phase-review`, {
      method: "POST",
      token,
      body: { decision },
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-journey-review"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  getTodayGrowthAction<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/growth/actions/today`, { token });
  }

  getFamilyToday<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/today`, { token });
  }

  changeTodayTaskState<T>(token: string, familyId: string, taskId: string, body: { action: "START" | "PAUSE" | "RESUME" | "CANCEL"; occurred_at: string }, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/tasks/${taskId}/state`, {
      method: "POST", token, body,
      headers: { "idempotency-key": idempotencyKey, "x-correlation-id": createMobileRequestId("family-mobile-task-state"), "x-source": "family-ai-mobile" },
    });
  }

  getFamilyHome<T>(token: string, familyId: string) {
    return this.request<T>(`/families/${familyId}/ui/01/home`, { token });
  }

  getFamilyAssessment(token: string, familyId: string) {
    return this.request<Ui02AssessmentProjection>(`/families/${familyId}/ui/02/assessment`, { token });
  }

  getFamilyAchievements(token: string, familyId: string) {
    return this.request<FamilyAchievementFeedbackResponse>(
      `/families/${familyId}/experience/achievements`,
      { token },
    );
  }

  getFamilyAchievementNotifications(token: string, familyId: string) {
    return this.request<FamilyAchievementNotificationsResponse>(
      `/families/${familyId}/experience/notifications`,
      { token },
    );
  }

  markFamilyAchievementNotificationRead(
    token: string,
    familyId: string,
    notificationId: string,
    idempotencyKey: string,
  ) {
    return this.request<FamilyAchievementNotificationReadResponse>(
      `/families/${familyId}/experience/notifications/${encodeURIComponent(notificationId)}/read`,
      {
        method: "POST",
        token,
        headers: {
          "idempotency-key": idempotencyKey,
          "x-correlation-id": createMobileRequestId("family-mobile-notification-read"),
          "x-source": "family-ai-mobile",
        },
      },
    );
  }

  getFamilyExperienceAnalytics(token: string, familyId: string) {
    return this.request<FamilyExperienceAnalyticsResponse>(
      `/families/${familyId}/experience/analytics`,
      { token },
    );
  }

  confirmGrowthPriority(token: string, familyId: string, onboardingId: string, draftId: string, decision: GrowthPriorityDecision, idempotencyKey: string) {
    return this.request<{ priority: GrowthPriorityProjection["active_priority"]; decision: GrowthPriorityDecision }>(`/families/${familyId}/growth/onboardings/${onboardingId}/priority/confirm`, {
      method: "POST",
      token,
      body: { draft_id: draftId, decision },
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-priority-confirm"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  startFamilyAssessment(token: string, familyId: string, body: { subject_person_id: string; tool_ref?: string }, idempotencyKey: string) {
    return this.request<AssessmentMutationReceipt>(`/families/${familyId}/assessments/sessions`, {
      method: "POST", token, body,
      headers: { "idempotency-key": idempotencyKey, "x-correlation-id": createMobileRequestId("ui02-start-assessment"), "x-source": "family-ai-mobile" },
    });
  }

  saveFamilyAssessmentResponse(token: string, familyId: string, sessionId: string, body: { item_ref: string; response_type: AssessmentResponseType; response_value: string | boolean }, idempotencyKey: string) {
    return this.request<AssessmentMutationReceipt>(`/families/${familyId}/assessments/sessions/${sessionId}/responses`, {
      method: "POST", token, body,
      headers: { "idempotency-key": idempotencyKey, "x-correlation-id": createMobileRequestId("ui02-save-response"), "x-source": "family-ai-mobile" },
    });
  }

  submitFamilyAssessment(token: string, familyId: string, sessionId: string, idempotencyKey: string) {
    return this.request<AssessmentMutationReceipt>(`/families/${familyId}/assessments/sessions/${sessionId}/submit`, {
      method: "POST", token, body: {},
      headers: { "idempotency-key": idempotencyKey, "x-correlation-id": createMobileRequestId("ui02-submit-assessment"), "x-source": "family-ai-mobile" },
    });
  }

  getGrowthHypothesis(token: string, familyId: string) {
    return this.request<Ui03GrowthHypothesisProjection>(`/families/${familyId}/ui/03/growth-hypothesis`, { token });
  }

  /**
   * Call the provider-neutral Experience API. Scope, consent and provider
   * selection are deliberately absent from the request body and resolved by
   * the server composition root. A malformed response fails closed before a
   * screen can render model output.
   */
  async createMultimodalDraft(token: string, familyId: string, body: MultimodalDraftRequest, idempotencyKey: string) {
    const payload = await this.request<unknown>(`/families/${familyId}/experience/multimodal/drafts`, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-experience-draft"),
        "x-source": "family-ai-mobile",
      },
    });
    if (!isMultimodalDraftResponse(payload) || payload.scope.family_id !== familyId) {
      throw new FamilyApiError("多模态草稿响应不符合安全契约", 502, "MULTIMODAL_DRAFT_INVALID_RESPONSE", payload);
    }
    return payload as MultimodalDraftResponse;
  }

  async decideMultimodalRun(token: string, familyId: string, runId: string, body: MultimodalRunDecisionRequest, idempotencyKey: string) {
    return this.appendMultimodalRunInteraction<MultimodalRunDecisionRequest>(
      token,
      `/families/${familyId}/experience/multimodal/runs/${runId}/decisions`,
      runId,
      body,
      idempotencyKey,
      "family-mobile-experience-decision",
    );
  }

  async recordMultimodalFeedback(token: string, familyId: string, runId: string, body: MultimodalRunFeedbackRequest, idempotencyKey: string) {
    return this.appendMultimodalRunInteraction<MultimodalRunFeedbackRequest>(
      token,
      `/families/${familyId}/experience/multimodal/runs/${runId}/feedback`,
      runId,
      body,
      idempotencyKey,
      "family-mobile-experience-feedback",
    );
  }

  async requestMultimodalHumanReview(token: string, familyId: string, runId: string, body: MultimodalRunHumanReviewRequest, idempotencyKey: string) {
    return this.appendMultimodalRunInteraction<MultimodalRunHumanReviewRequest>(
      token,
      `/families/${familyId}/experience/multimodal/runs/${runId}/human-review`,
      runId,
      body,
      idempotencyKey,
      "family-mobile-experience-human-review",
    );
  }

  async deleteMultimodalRun(token: string, familyId: string, runId: string, reason: string | undefined, idempotencyKey: string) {
    const payload = await this.request<unknown>(`/families/${familyId}/experience/multimodal/runs/${runId}`, {
      method: "DELETE",
      token,
      body: reason ? { reason } : undefined,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-experience-delete"),
        "x-source": "family-ai-mobile",
      },
    });
    return this.assertMultimodalInteraction(payload, runId);
  }

  async replayMultimodalRun(token: string, familyId: string, runId: string) {
    const payload = await this.request<unknown>(`/families/${familyId}/experience/multimodal/runs/${runId}/replay`, { token });
    if (!isMultimodalRunReplayResponse(payload) || payload.run_id !== runId) {
      throw new FamilyApiError("多模态回放响应不符合安全契约", 502, "MULTIMODAL_RUN_REPLAY_INVALID_RESPONSE", payload);
    }
    return payload as MultimodalRunReplayResponse;
  }

  private async appendMultimodalRunInteraction<TBody>(token: string, path: string, runId: string, body: TBody, idempotencyKey: string, correlationPrefix: string) {
    const payload = await this.request<unknown>(path, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId(correlationPrefix),
        "x-source": "family-ai-mobile",
      },
    });
    return this.assertMultimodalInteraction(payload, runId);
  }

  private assertMultimodalInteraction(payload: unknown, expectedRunId: string): MultimodalRunInteractionResponse {
    if (!isMultimodalRunInteractionResponse(payload) || payload.run_id !== expectedRunId) {
      throw new FamilyApiError("多模态运行交互响应不符合安全契约", 502, "MULTIMODAL_RUN_INTERACTION_INVALID_RESPONSE", payload);
    }
    return payload;
  }

  generateGrowthHypothesis<T>(token: string, familyId: string, sessionId: string, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/assessments/${sessionId}/growth-hypothesis`, {
      method: "POST", token, body: {},
      headers: { "idempotency-key": idempotencyKey, "x-correlation-id": createMobileRequestId("ui03-generate-hypothesis"), "x-source": "family-ai-mobile" },
    });
  }

  decideGrowthHypothesis(token: string, familyId: string, body: { assessment_session_id: string; hypothesis_ref: string; decision_type: "CONFIRM" | "DISMISS" }, idempotencyKey: string) {
    return this.request<GrowthHypothesisDecisionReceipt>(`/families/${familyId}/growth-hypotheses/decisions`, {
      method: "POST", token, body,
      headers: { "idempotency-key": idempotencyKey, "x-correlation-id": createMobileRequestId("ui03-hypothesis-decision"), "x-source": "family-ai-mobile" },
    });
  }

  requestGrowthHelp<T>(token: string, familyId: string, body: { subject_person_id: string; raw_text: string }, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/orchestration/needs`, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-growth-help"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  confirmGrowthIntent<T>(token: string, familyId: string, body: { signal_id: string; goal_text: string }, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/orchestration/intents`, {
      method: "POST", token, body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-growth-intent"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  requestGrowthRecommendation<T>(token: string, familyId: string, intentId: string, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/orchestration/intents/${intentId}/recommendations`, {
      method: "POST", token, body: {},
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-growth-recommendation"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  decideGrowthService<T>(token: string, familyId: string, body: { intent_id: string; recommendation_id: string; recommendation_version: number; decision_type: "ACCEPT_RECOMMENDATION" | "SELECT_ALTERNATIVE" | "DISMISS"; selected_offer_refs: string[] }, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/orchestration/decisions`, {
      method: "POST", token, body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-growth-decision"),
        "x-source": "family-ai-mobile",
      },
    });
  }

  checkInTodayTask<T>(token: string, familyId: string, taskId: string, body: { completion_status: "COMPLETED" | "PARTIAL" | "NOT_COMPLETED"; reflection: string; occurred_at: string }, idempotencyKey: string) {
    return this.request<T>(`/families/${familyId}/tasks/${taskId}/check-in`, {
      method: "POST",
      token,
      body,
      headers: {
        "idempotency-key": idempotencyKey,
        "x-correlation-id": createMobileRequestId("family-mobile-task-checkin"),
        "x-source": "family-ai-mobile",
      },
    });
  }
}

function safeJson(raw: string) {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return { message: raw };
  }
}

export function readErrorCode(payload: unknown) {
  if (!payload || typeof payload !== "object") return null;
  const value = payload as Record<string, unknown>;
  if (typeof value.detail === "string") return value.detail;
  if (Array.isArray(value.detail)) {
    const first = value.detail[0];
    if (first && typeof first === "object") {
      const issue = first as Record<string, unknown>;
      if (typeof issue.type === "string") return `VALIDATION_${issue.type.toUpperCase()}`;
      if (typeof issue.msg === "string") return "VALIDATION_ERROR";
    }
  }
  if (typeof value.message === "string") return value.message;
  if (typeof value.error === "string") return value.error;
  return null;
}

export const familyApi = new FamilyApiClient();
