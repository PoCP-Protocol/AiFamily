import { describe, expect, it } from "vitest";

import {
  buildAchievementContinueEvent,
  buildAchievementFeedbackEvent,
  buildAchievementImpressionEvent,
  buildAchievementOpenEvent,
} from "../lib/family/achievement-telemetry";

const scope = {
  tenantId: "tenant-a",
  regionId: "CN",
  familyId: "family-a",
  subjectIds: ["child-a", "guardian-a"],
  purpose: "experience_achievement" as const,
  consentVersion: "consent-v1",
  locale: "zh-CN",
};

const common = {
  scope,
  requestId: "request-1",
  idempotencyKey: "idem-1",
  occurredAt: "2026-08-30T00:00:00+08:00",
  experimentVariant: {
    experimentId: "achievement-rail-v1",
    variant: "warm-blue",
    assignmentId: "assignment-1",
  },
};

describe("achievement telemetry contract", () => {
  it("builds a scoped impression with experiment and request metadata", () => {
    const event = buildAchievementImpressionEvent({
      ...common,
      achievementId: "achievement:first-step",
    });

    expect(event).toMatchObject({
      eventId: "achievement:impression:idem-1",
      eventType: "impression",
      achievementId: "achievement:first-step",
      requestId: "request-1",
      idempotencyKey: "idem-1",
      surface: "achievement_rail",
      familyScope: {
        familyId: "family-a",
        subjectIds: ["child-a", "guardian-a"],
      },
      experimentVariant: {
        experimentId: "achievement-rail-v1",
        variant: "warm-blue",
      },
    });
    expect(event.occurredAt).toBe("2026-08-29T16:00:00.000Z");
  });

  it("supports open, continue and bounded feedback events", () => {
    expect(
      buildAchievementOpenEvent({
        ...common,
        achievementId: "achievement:pause",
      }).eventType,
    ).toBe("open");
    expect(buildAchievementContinueEvent({ ...common })).toMatchObject({
      eventType: "continue",
      achievementId: null,
    });
    expect(
      buildAchievementFeedbackEvent({
        ...common,
        achievementId: "achievement:first-step",
        feedbackSignal: "helpful",
      }),
    ).toMatchObject({ eventType: "feedback", feedbackSignal: "helpful" });
  });

  it("fails closed for invalid scope, ids and feedback values", () => {
    expect(() =>
      buildAchievementImpressionEvent({
        ...common,
        scope: { ...scope, subjectIds: [] },
        achievementId: "achievement:first-step",
      }),
    ).toThrow("subjectIds");
    expect(() =>
      buildAchievementOpenEvent({
        ...common,
        achievementId: "contains whitespace",
      }),
    ).toThrow("achievementId");
    expect(() =>
      buildAchievementFeedbackEvent({
        ...common,
        achievementId: "achievement:first-step",
        feedbackSignal: "raw child message" as never,
      }),
    ).toThrow("feedback signal");
  });

  it("does not expose raw content, dwell time, ranking or score fields", () => {
    const unsafeInput = Object.assign({}, common, {
      rawText: "child private message",
      dwellTimeMs: 5000,
      familyScore: 99,
      familyRank: 1,
    }) as Parameters<typeof buildAchievementContinueEvent>[0];
    const event = buildAchievementContinueEvent(unsafeInput);

    expect(Object.keys(event)).not.toEqual(
      expect.arrayContaining([
        "rawText",
        "dwellTimeMs",
        "durationMs",
        "familyScore",
        "familyRank",
        "ranking",
        "score",
      ]),
    );
  });
});
