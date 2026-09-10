import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { UI01_HOME_TARGETS } from "../lib/family/ui01-home-entry-map";

describe("UI-01 original-home hotspot contract", () => {
  it("keeps every confirmed original hotspot as an entry to its later UI", () => {
    expect(UI01_HOME_TARGETS).toEqual({
      freeAssessment: "UI-02",
      aiInterpretation: "UI-03",
      plan90: "UI-04",
      growthStories: "UI-12",
      expertLive: "UI-19",
      familyAdvisor: "UI-19",
      dailyTasks: "UI-09",
      recommendations: "UI-13",
    });
  });

  it("does not route original UI-01 hotspots to a second home-only workflow", () => {
    expect(Object.values(UI01_HOME_TARGETS)).not.toContain("UI-01");
  });

  it("binds every confirmed hotspot in the real home source and keeps its target page", () => {
    const homeSource = readFileSync(resolve(process.cwd(), "app/(tabs)/index.tsx"), "utf8");
    for (const [key, target] of Object.entries(UI01_HOME_TARGETS)) {
      expect(homeSource).toContain(`UI01_HOME_TARGETS.${key}`);
      expect(existsSync(resolve(process.cwd(), `app/ui/${target}.tsx`))).toBe(true);
    }
  });

  it("keeps the original UI-01 visible feature modules implemented in the home source", () => {
    const homeSource = readFileSync(resolve(process.cwd(), "app/(tabs)/index.tsx"), "utf8");

    expect(homeSource).toContain("AiFamily");
    expect(homeSource).toContain("今天，先照顾好一件事");
    expect(homeSource).toContain("AssessmentBannerArt");
    expect(homeSource).toContain("今天的安排");
    expect(homeSource).toContain("给你的参考");

    for (const label of ["理解家庭", "一起练习", "成长方向", "看看别家", "听听专家", "找人聊聊"]) {
      expect(homeSource).toContain(`label: "${label}"`);
    }
  });

  it("keeps UI-01 module actions wired to the intended later screens", () => {
    const homeSource = readFileSync(resolve(process.cwd(), "app/(tabs)/index.tsx"), "utf8");

    expect(homeSource).toContain('const CHALLENGE_CAMP_TARGET = productRoute("PRODUCT_PARENT_CHILD_CAMP");');
    expect(homeSource).toContain('open(routeForUi(UI01_HOME_TARGETS.freeAssessment))');
    expect(homeSource).toContain('open(routeForUi(UI01_HOME_TARGETS.dailyTasks))');
    expect(homeSource).toContain('open(routeForUi(UI01_HOME_TARGETS.recommendations))');
    expect(homeSource).toContain('routeForUi(item.target_ui === "UI-19" ? "UI-19" : "UI-13")');
  });

  it("mounts the real achievement rail with notification consumption on UI-01", () => {
    const homeSource = readFileSync(resolve(process.cwd(), "app/(tabs)/index.tsx"), "utf8");

    expect(homeSource).toContain('import { AchievementRail } from "@/components/family/achievement-rail";');
    expect(homeSource).toContain("familyApi.getFamilyAchievements");
    expect(homeSource).toContain("familyApi.getFamilyAchievementNotifications");
    expect(homeSource).toContain("normalizeAchievementFeedback");
    expect(homeSource).toContain("normalizeAchievementNotifications");
    expect(homeSource).toContain("markFamilyAchievementNotificationRead");
    expect(homeSource).toContain("<AchievementRail projection={achievementProjection}");
    expect(homeSource).toContain('routeForUi("UI-29")');
  });
});
