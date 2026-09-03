/**
 * Privacy-safe interaction telemetry for the family achievement rail.
 *
 * This is an experience signal, not a business fact. The event deliberately
 * has no free-form payload: minor content, dwell-time optimization signals,
 * scores and rankings cannot be accidentally attached by a screen.
 */

export const ACHIEVEMENT_TELEMETRY_EVENT_TYPES = [
  "impression",
  "open",
  "continue",
  "feedback",
] as const;

export type AchievementTelemetryEventType =
  (typeof ACHIEVEMENT_TELEMETRY_EVENT_TYPES)[number];

/** Feedback values are bounded codes; callers must not send free-form text. */
export const ACHIEVEMENT_FEEDBACK_SIGNALS = [
  "helpful",
  "not_helpful",
  "paused",
  "request_human",
] as const;

export type AchievementFeedbackSignal =
  (typeof ACHIEVEMENT_FEEDBACK_SIGNALS)[number];

export type AchievementTelemetryScope = Readonly<{
  /** Tenant boundary is optional for an already tenant-bound mobile session. */
  tenantId?: string;
  /** Region is carried when the session has a region assignment. */
  regionId?: string;
  familyId: string;
  subjectIds: readonly string[];
  /** Fixed purpose prevents an achievement signal becoming a commercial profile. */
  purpose: "experience_achievement";
  consentVersion: string;
  locale?: string;
}>;

export type AchievementExperimentVariant = Readonly<{
  experimentId: string;
  variant: string;
  assignmentId?: string;
}>;

export type AchievementTelemetryInputBase = Readonly<{
  scope: AchievementTelemetryScope;
  requestId: string;
  idempotencyKey: string;
  /** Optional client event id; a deterministic id is derived when omitted. */
  eventId?: string;
  occurredAt?: string;
  experimentVariant?: AchievementExperimentVariant | null;
}>;

export type BuildAchievementTelemetryInput =
  | (AchievementTelemetryInputBase & {
      eventType: "impression";
      achievementId: string;
    })
  | (AchievementTelemetryInputBase & {
      eventType: "open";
      achievementId: string;
    })
  | (AchievementTelemetryInputBase & {
      eventType: "continue";
      achievementId?: string;
    })
  | (AchievementTelemetryInputBase & {
      eventType: "feedback";
      achievementId: string;
      feedbackSignal: AchievementFeedbackSignal;
    });

export type AchievementTelemetryEvent = Readonly<{
  eventId: string;
  eventType: AchievementTelemetryEventType;
  occurredAt: string;
  familyScope: AchievementTelemetryScope;
  experimentVariant: AchievementExperimentVariant | null;
  requestId: string;
  idempotencyKey: string;
  surface: "achievement_rail";
  achievementId: string | null;
  feedbackSignal?: AchievementFeedbackSignal;
}>;

const EVENT_TYPE_SET = new Set<string>(ACHIEVEMENT_TELEMETRY_EVENT_TYPES);
const FEEDBACK_SIGNAL_SET = new Set<string>(ACHIEVEMENT_FEEDBACK_SIGNALS);
const TOKEN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function requireToken(value: string, field: string): string {
  if (typeof value !== "string" || !TOKEN_PATTERN.test(value.trim())) {
    throw new Error(`${field} must be a non-empty identifier token`);
  }
  return value.trim();
}

function requireTimestamp(value: string | undefined): string {
  if (value === undefined) return new Date().toISOString();
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("occurredAt must be a valid timestamp");
  }
  return parsed.toISOString();
}

function normalizeScope(
  scope: AchievementTelemetryScope,
): AchievementTelemetryScope {
  if (!scope || typeof scope !== "object") {
    throw new Error("family scope is required");
  }
  const familyId = requireToken(scope.familyId, "familyId");
  if (!Array.isArray(scope.subjectIds) || scope.subjectIds.length === 0) {
    throw new Error("subjectIds must contain at least one subject");
  }
  const subjectIds = scope.subjectIds.map((subjectId) =>
    requireToken(subjectId, "subjectId"),
  );
  if (new Set(subjectIds).size !== subjectIds.length) {
    throw new Error("subjectIds must not contain duplicates");
  }
  const consentVersion = requireToken(scope.consentVersion, "consentVersion");
  if (scope.tenantId !== undefined) requireToken(scope.tenantId, "tenantId");
  if (scope.regionId !== undefined) requireToken(scope.regionId, "regionId");
  if (scope.locale !== undefined) requireToken(scope.locale, "locale");
  if (scope.purpose !== "experience_achievement") {
    throw new Error("purpose must be experience_achievement");
  }
  return {
    ...(scope.tenantId ? { tenantId: scope.tenantId.trim() } : {}),
    ...(scope.regionId ? { regionId: scope.regionId.trim() } : {}),
    familyId,
    subjectIds,
    purpose: scope.purpose,
    consentVersion,
    ...(scope.locale ? { locale: scope.locale.trim() } : {}),
  };
}

function normalizeExperimentVariant(
  variant: AchievementExperimentVariant | null | undefined,
): AchievementExperimentVariant | null {
  if (variant == null) return null;
  return {
    experimentId: requireToken(variant.experimentId, "experimentId"),
    variant: requireToken(variant.variant, "variant"),
    ...(variant.assignmentId
      ? { assignmentId: requireToken(variant.assignmentId, "assignmentId") }
      : {}),
  };
}

/**
 * Build one allow-listed event. Unknown input fields are intentionally ignored
 * so a raw child message cannot leak into the telemetry envelope.
 */
export function buildAchievementTelemetryEvent(
  input: BuildAchievementTelemetryInput,
): AchievementTelemetryEvent {
  if (!input || !EVENT_TYPE_SET.has(input.eventType)) {
    throw new Error("unsupported achievement telemetry event type");
  }
  const familyScope = normalizeScope(input.scope);
  const requestId = requireToken(input.requestId, "requestId");
  const idempotencyKey = requireToken(input.idempotencyKey, "idempotencyKey");
  const achievementId = input.achievementId
    ? requireToken(input.achievementId, "achievementId")
    : null;

  if (
    (input.eventType === "impression" || input.eventType === "open") &&
    !achievementId
  ) {
    throw new Error(`${input.eventType} requires achievementId`);
  }
  if (input.eventType === "feedback") {
    if (!achievementId) throw new Error("feedback requires achievementId");
    if (!FEEDBACK_SIGNAL_SET.has(input.feedbackSignal)) {
      throw new Error("unsupported achievement feedback signal");
    }
  }

  const eventId = input.eventId
    ? requireToken(input.eventId, "eventId")
    : `achievement:${input.eventType}:${idempotencyKey}`;
  const event: {
    eventId: string;
    eventType: AchievementTelemetryEventType;
    occurredAt: string;
    familyScope: AchievementTelemetryScope;
    experimentVariant: AchievementExperimentVariant | null;
    requestId: string;
    idempotencyKey: string;
    surface: "achievement_rail";
    achievementId: string | null;
    feedbackSignal?: AchievementFeedbackSignal;
  } = {
    eventId,
    eventType: input.eventType,
    occurredAt: requireTimestamp(input.occurredAt),
    familyScope,
    experimentVariant: normalizeExperimentVariant(input.experimentVariant),
    requestId,
    idempotencyKey,
    surface: "achievement_rail",
    achievementId,
  };
  if (input.eventType === "feedback") {
    event.feedbackSignal = input.feedbackSignal;
  }
  return event;
}

export function buildAchievementImpressionEvent(
  input: Omit<
    Extract<BuildAchievementTelemetryInput, { eventType: "impression" }>,
    "eventType"
  >,
): AchievementTelemetryEvent {
  return buildAchievementTelemetryEvent({ ...input, eventType: "impression" });
}

export function buildAchievementOpenEvent(
  input: Omit<
    Extract<BuildAchievementTelemetryInput, { eventType: "open" }>,
    "eventType"
  >,
): AchievementTelemetryEvent {
  return buildAchievementTelemetryEvent({ ...input, eventType: "open" });
}

export function buildAchievementContinueEvent(
  input: Omit<
    Extract<BuildAchievementTelemetryInput, { eventType: "continue" }>,
    "eventType"
  >,
): AchievementTelemetryEvent {
  return buildAchievementTelemetryEvent({ ...input, eventType: "continue" });
}

export function buildAchievementFeedbackEvent(
  input: Omit<
    Extract<BuildAchievementTelemetryInput, { eventType: "feedback" }>,
    "eventType"
  >,
): AchievementTelemetryEvent {
  return buildAchievementTelemetryEvent({ ...input, eventType: "feedback" });
}
