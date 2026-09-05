import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(__dirname, "../components/family/family-experience-list.tsx"), "utf8");
const servicesRoute = readFileSync(resolve(__dirname, "../app/(tabs)/services.tsx"), "utf8");

describe("semantic family service experience list", () => {
  it("uses semantic icons, stages and invitations for every service journey entry", () => {
    for (const label of ["认识支持", "了解边界", "说出需要", "探索活动", "选择方式", "回看安排", "继续同行", "记录成长"]) expect(source).toContain(label);
    for (const icon of ["person.crop.circle.fill", "book.fill", "message.fill", "calendar.fill", "headphones.fill", "checkmark.seal.fill"]) expect(source).toContain(icon);
    expect(source).toContain("serviceExperienceMeta");
  });

  it("never renders internal UI identifiers while retaining registry-id navigation", () => {
    expect(source).toContain("routeForUi(screen.id)");
    expect(source).not.toContain("idBadge");
    expect(source).not.toContain("idText");
    expect(source).not.toMatch(/<Text[^>]*>\s*\{(?:item|screen)\.id\}\s*<\/Text>/);
    expect(source).toContain("accessibilityLabel={`${screen.title}");
    expect(servicesRoute).toContain("FamilyExperienceList");
    expect(servicesRoute).not.toContain("FamilyScreenList");
  });

  it("adds a lightweight self-paced game loop without scores, ranks, or comparison", () => {
    for (const text of ["第 {step} 步", "完成这一步，下一步会更清楚", "家庭小成就", "只和自己的节奏比"]) expect(source).toContain(text);
    expect(source).toContain("不展示家庭总分、排名或横向比较");
    expect(source).not.toMatch(/家庭总分\s*[:：]\s*\d/);
    expect(source).not.toMatch(/排名\s*[:：]\s*\d/);
  });

  it("keeps loading, empty, error and paused states explicit and accessible", () => {
    for (const state of ["loading", "ready", "empty", "error", "paused"]) expect(source).toContain(`state === "${state}"`);
    expect(source).toContain("ActivityIndicator");
    expect(source).toContain("重新试试");
    expect(source).toContain("这段同行已暂停");
    expect(source).toContain("accessibilityRole=\"button\"");
    expect(source).toContain("accessibilityLabel");
  });

  it("keeps i18n and platform boundaries in the presentation layer", () => {
    expect(source).toContain("FamilyScreenDefinition");
    expect(source).toContain("getScreensForTab(tab)");
    expect(source).toContain("useColors()");
    expect(source).not.toMatch(/Platform\.OS|FamilyApi|fetch\(|payment|checkout/);
  });
});
