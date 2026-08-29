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

    expect(homeSource).toContain("家庭成长平台");
    expect(homeSource).toContain("今天也一起陪孩子成长");
    expect(homeSource).toContain("AssessmentBannerArt");
    expect(homeSource).toContain("今日成长任务");
    expect(homeSource).toContain("推荐内容/服务");

    for (const label of ["AI诊断", "21天挑战营", "90天成长计划", "成长案例", "专家直播", "家庭顾问"]) {
      expect(homeSource).toContain(`label: "${label}"`);
    }
  });

  it("keeps UI-01 module actions wired to the intended later screens", () => {
    const homeSource = readFileSync(resolve(process.cwd(), "app/(tabs)/index.tsx"), "utf8");

    expect(homeSource).toContain('const CHALLENGE_CAMP_TARGET = "/ui/UI-14?productRef=PRODUCT_PARENT_CHILD_CAMP" as Href;');
    expect(homeSource).toContain('onPress={() => open(`/ui/${UI01_HOME_TARGETS.freeAssessment}` as Href)}');
    expect(homeSource).toContain('onPress={() => open(`/ui/${UI01_HOME_TARGETS.dailyTasks}` as Href)}');
    expect(homeSource).toContain('onPress={() => open(`/ui/${UI01_HOME_TARGETS.recommendations}` as Href)}');
    expect(homeSource).toContain('open((item.target_ui === "UI-19" ? "/ui/UI-19" : "/ui/UI-13") as Href)');
  });
});
