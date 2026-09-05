import { describe, expect, it } from "vitest";

import {
  normalizeAchievementFeedback,
  normalizeAchievementNotificationRead,
  normalizeAchievementNotifications,
  normalizeExperienceAnalytics,
} from "../lib/family/feedback-api-contracts";

describe("AI experience feedback contracts", () => {
  it("keeps occurrence identity and evidence references", () => {
    const result = normalizeAchievementFeedback({
      family_id: "family-a",
      achievements: [
        {
          achievement_id: "achievement:one",
          key: "ai_evidence_moment",
          occurrence_id: "evidence:abc",
          title: "一次成长时刻",
          message: "我们完成了一步。",
          evidence_refs: ["experience-event:event-1"],
          earned_at: "2026-08-30T10:00:00Z",
        },
      ],
    });
    expect(result.achievements[0]?.occurrenceId).toBe("evidence:abc");
    expect(result.achievements[0]?.key).toBe("ai_evidence_moment");
  });

  it("drops malformed notifications and negative metrics", () => {
    expect(
      normalizeAchievementNotifications({
        family_id: "family-a",
        unread: [
          {
            notification_id: "n-1",
            achievement_id: "a-1",
            title: "提醒",
            message: "看看刚刚的成长时刻",
            status: "UNREAD",
            created_at: "2026-08-30T10:00:00Z",
          },
          { notification_id: "bad", status: "READ" },
        ],
      }).unread,
    ).toHaveLength(1);
    expect(
      normalizeExperienceAnalytics({
        family_id: "family-a",
        metrics: [
          { metric_key: "event:action_completed", value_count: 2 },
          { metric_key: "event:bad", value_count: -1 },
        ],
      }).metrics,
    ).toEqual([{ metric_key: "event:action_completed", value_count: 2 }]);
  });

  it("normalizes an idempotent READ receipt", () => {
    expect(
      normalizeAchievementNotificationRead({
        notification_id: "n-1",
        achievement_id: "a-1",
        status: "READ",
        read_at: "2026-08-30T11:00:00Z",
      }),
    ).toEqual({
      notification_id: "n-1",
      achievement_id: "a-1",
      status: "READ",
      read_at: "2026-08-30T11:00:00Z",
    });
    expect(normalizeAchievementNotificationRead({ status: "UNREAD" })).toBeNull();
  });
});
