import { describe, expect, it } from "vitest";

import { getAchievementRailViewModel } from "../lib/family/achievement-view-model";
import type { FamilyAchievementProjection } from "../lib/family/achievement-contracts";

const achievement = (achievementId: string) => ({
  achievementId,
  key: "first_step" as const,
  title: `成就 ${achievementId}`,
  message: "完成了一次真实行动。",
  evidenceRefs: [`event:${achievementId}`],
  earnedAt: "2026-08-30T00:00:00Z",
});

describe("getAchievementRailViewModel", () => {
  it("keeps the empty state action-oriented", () => {
    const projection: FamilyAchievementProjection = {
      familyId: "family-1",
      availability: "EMPTY",
      achievements: [],
    };

    const viewModel = getAchievementRailViewModel(projection);

    expect(viewModel.availability).toBe("EMPTY");
    expect(viewModel.prompt).toContain("小行动");
    expect(viewModel.visibleAchievements).toEqual([]);
  });

  it("limits the ready rail to three cards without losing the total", () => {
    const projection: FamilyAchievementProjection = {
      familyId: "family-1",
      availability: "READY",
      achievements: ["a", "b", "c", "d"].map(achievement),
    };

    const viewModel = getAchievementRailViewModel(projection);

    expect(viewModel.subtitle).toContain("4");
    expect(
      viewModel.visibleAchievements.map((item) => item.achievementId),
    ).toEqual(["a", "b", "c"]);
  });

  it("preserves an unavailable state and its recovery prompt", () => {
    const projection: FamilyAchievementProjection = {
      familyId: "family-1",
      availability: "UNAVAILABLE",
      achievements: [],
      nextPrompt: "稍后回来看看。",
    };

    const viewModel = getAchievementRailViewModel(projection);

    expect(viewModel.availability).toBe("UNAVAILABLE");
    expect(viewModel.prompt).toBe("稍后回来看看。");
  });
});
