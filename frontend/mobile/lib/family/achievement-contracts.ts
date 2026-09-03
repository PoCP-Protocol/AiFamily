export const ACHIEVEMENT_KEYS = [
  "first_step",
  "pause_and_return",
  "service_intent_expressed",
  "ai_evidence_moment",
] as const;

export type AchievementKey = (typeof ACHIEVEMENT_KEYS)[number];

export type AchievementAvailability = "READY" | "EMPTY" | "UNAVAILABLE";

export type FamilyAchievement = {
  achievementId: string;
  key: AchievementKey;
  occurrenceId?: string;
  title: string;
  message: string;
  evidenceRefs: string[];
  earnedAt: string;
};

export type FamilyAchievementProjection = {
  familyId: string;
  availability: AchievementAvailability;
  achievements: FamilyAchievement[];
  nextPrompt?: string;
};

const KEY_SET = new Set<string>(ACHIEVEMENT_KEYS);

export function normalizeAchievementProjection(
  input: unknown,
): FamilyAchievementProjection {
  if (!input || typeof input !== "object") {
    return { familyId: "", availability: "UNAVAILABLE", achievements: [] };
  }
  const record = input as Record<string, unknown>;
  const familyId = typeof record.family_id === "string" ? record.family_id : "";
  const rawAchievements = Array.isArray(record.achievements)
    ? record.achievements
    : [];
  const achievements = rawAchievements.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const value = item as Record<string, unknown>;
    const key =
      typeof value.key === "string" && KEY_SET.has(value.key)
        ? (value.key as AchievementKey)
        : null;
    const achievementId =
      typeof value.achievement_id === "string" ? value.achievement_id : "";
    const occurrenceId =
      typeof value.occurrence_id === "string" && value.occurrence_id.length > 0
        ? value.occurrence_id
        : undefined;
    const title = typeof value.title === "string" ? value.title : "";
    const message = typeof value.message === "string" ? value.message : "";
    const earnedAt = typeof value.earned_at === "string" ? value.earned_at : "";
    const evidenceRefs = Array.isArray(value.evidence_refs)
      ? value.evidence_refs.filter(
          (ref): ref is string => typeof ref === "string" && ref.length > 0,
        )
      : [];
    if (
      !key ||
      !achievementId ||
      !title ||
      !message ||
      !earnedAt ||
      evidenceRefs.length === 0
    )
      return [];
    return [
      {
        achievementId,
        key,
        occurrenceId,
        title,
        message,
        earnedAt,
        evidenceRefs,
      },
    ];
  });
  const availability: AchievementAvailability =
    achievements.length > 0 ? "READY" : "EMPTY";
  return {
    familyId,
    availability,
    achievements: achievements.sort((left, right) =>
      left.earnedAt.localeCompare(right.earnedAt),
    ),
    nextPrompt:
      typeof record.next_prompt === "string" ? record.next_prompt : undefined,
  };
}
