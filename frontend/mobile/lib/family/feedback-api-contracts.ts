import { normalizeAchievementProjection, type FamilyAchievementProjection } from "./achievement-contracts";

export type FamilyAchievementFeedbackResponse = {
  family_id: string;
  visibility: "FAMILY_PRIVATE";
  achievements: Array<{
    achievement_id: string;
    key: string;
    occurrence_id: string;
    title: string;
    message: string;
    evidence_refs: string[];
    earned_at: string;
  }>;
};

export type FamilyAchievementNotificationsResponse = {
  family_id: string;
  visibility: "FAMILY_PRIVATE";
  unread: Array<{
    notification_id: string;
    achievement_id: string;
    title: string;
    message: string;
    status: "UNREAD";
    created_at: string;
  }>;
};

export type FamilyAchievementNotificationReadResponse = {
  notification_id: string;
  achievement_id: string;
  status: "READ";
  read_at: string;
};

export type FamilyExperienceAnalyticsResponse = {
  family_id: string;
  visibility: "FAMILY_PRIVATE";
  metrics: Array<{ metric_key: string; value_count: number }>;
};

export function normalizeAchievementFeedback(
  input: unknown,
): FamilyAchievementProjection {
  return normalizeAchievementProjection(input);
}

export function normalizeAchievementNotifications(
  input: unknown,
): FamilyAchievementNotificationsResponse {
  if (!input || typeof input !== "object") {
    return { family_id: "", visibility: "FAMILY_PRIVATE", unread: [] };
  }
  const value = input as Record<string, unknown>;
  const unread = Array.isArray(value.unread)
    ? value.unread.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const notification = item as Record<string, unknown>;
        if (
          typeof notification.notification_id !== "string" ||
          typeof notification.achievement_id !== "string" ||
          typeof notification.title !== "string" ||
          typeof notification.message !== "string" ||
          notification.status !== "UNREAD" ||
          typeof notification.created_at !== "string"
        ) return [];
        return [{
          notification_id: notification.notification_id,
          achievement_id: notification.achievement_id,
          title: notification.title,
          message: notification.message,
          status: "UNREAD" as const,
          created_at: notification.created_at,
        }];
      })
    : [];
  return {
    family_id: typeof value.family_id === "string" ? value.family_id : "",
    visibility: "FAMILY_PRIVATE",
    unread,
  };
}

export function normalizeAchievementNotificationRead(
  input: unknown,
): FamilyAchievementNotificationReadResponse | null {
  if (!input || typeof input !== "object") return null;
  const value = input as Record<string, unknown>;
  if (
    typeof value.notification_id !== "string" ||
    typeof value.achievement_id !== "string" ||
    value.status !== "READ" ||
    typeof value.read_at !== "string"
  ) return null;
  return {
    notification_id: value.notification_id,
    achievement_id: value.achievement_id,
    status: "READ",
    read_at: value.read_at,
  };
}

export function normalizeExperienceAnalytics(
  input: unknown,
): FamilyExperienceAnalyticsResponse {
  if (!input || typeof input !== "object") {
    return { family_id: "", visibility: "FAMILY_PRIVATE", metrics: [] };
  }
  const value = input as Record<string, unknown>;
  const metrics = Array.isArray(value.metrics)
    ? value.metrics.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const metric = item as Record<string, unknown>;
        return typeof metric.metric_key === "string" &&
          typeof metric.value_count === "number" &&
          Number.isSafeInteger(metric.value_count) &&
          metric.value_count >= 0
          ? [{ metric_key: metric.metric_key, value_count: metric.value_count }]
          : [];
      })
    : [];
  return {
    family_id: typeof value.family_id === "string" ? value.family_id : "",
    visibility: "FAMILY_PRIVATE",
    metrics,
  };
}
