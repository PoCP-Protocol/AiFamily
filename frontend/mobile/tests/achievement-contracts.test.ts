import { describe, expect, it } from "vitest";

import { normalizeAchievementProjection } from "../lib/family/achievement-contracts";

describe("family achievement projection", () => {
  it("normalizes evidence-bound achievements in earned order", () => {
    const projection = normalizeAchievementProjection({
      family_id: "family-a",
      achievements: [
        {
          achievement_id: "achievement:two",
          key: "pause_and_return",
          title: "按自己的节奏回来",
          message: "暂停不是退步。",
          evidence_refs: ["experience-event:two"],
          earned_at: "2026-08-30T10:00:00Z",
        },
        {
          achievement_id: "achievement:one",
          key: "first_step",
          title: "第一步已完成",
          message: "我们完成了一个小行动。",
          evidence_refs: ["experience-event:one"],
          earned_at: "2026-08-30T09:00:00Z",
        },
      ],
    });

    expect(projection.availability).toBe("READY");
    expect(projection.achievements.map((item) => item.key)).toEqual([
      "first_step",
      "pause_and_return",
    ]);
  });

  it("drops malformed or unsupported records instead of showing fake badges", () => {
    const projection = normalizeAchievementProjection({
      family_id: "family-a",
      achievements: [
        {
          achievement_id: "bad",
          key: "family_rank",
          title: "排名",
          message: "x",
        },
        {
          achievement_id: "missing-proof",
          key: "first_step",
          title: "第一步",
          message: "x",
          earned_at: "now",
        },
      ],
    });

    expect(projection.availability).toBe("EMPTY");
    expect(projection.achievements).toEqual([]);
  });
});
