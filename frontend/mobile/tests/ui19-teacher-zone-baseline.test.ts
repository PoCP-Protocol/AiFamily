import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-19.tsx"), "utf8");
describe("UI-19 original teacher-zone baseline", () => {
  it("restores title, search, blue hero, domains and teacher consultation cards", () => {
    for (const copy of ["名师专区", "搜名师 / 领域 / 问题关键词", "名师在线，帮您解决家庭教育难题", "立即咨询", "热门领域", "推荐名师"]) expect(source).toContain(copy);
  });
  it("keeps expert projection and confirmed UI-20/UI-21 exits", () => {
    expect(source).toContain("getServiceOfferings");
    expect(source).toContain("UI-20?offeringRef=");
    expect(source).toContain("UI-21?offeringRef=");
  });
});
