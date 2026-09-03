import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-11.tsx"), "utf8");
describe("UI-11 original rhythm baseline contract", () => {
  it("uses a same-family three-stage timeline instead of a ranking podium", () => {
    for (const copy of ["本周", "本月", "我的过程", "上周", "现在", "下次", "最近家庭过程", "我们的过程", "整理成家庭私有故事"]) expect(source).toContain(copy);
    expect(source).toContain("rhythmTimeline");
    expect(source).not.toContain("podium");
  });
  it("reuses same-family rhythm events and provides the existing UI-12 exit", () => {
    expect(source).toContain("buildFamilyRhythmEvents");
    expect(source).toContain("getDevPlatformSurfaces");
    expect(source).toContain('router.push("/ui/UI-12" as Href)');
  });
  it("explicitly removes cross-family ranking, scores, percentiles, and titles", () => {
    expect(source).toContain("不比较他人");
    expect(source).not.toMatch(/排名第|超过.*家庭|积分|百分位|成长行动家/);
  });
});
