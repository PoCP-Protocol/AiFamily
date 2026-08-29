import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-12.tsx"), "utf8");
describe("UI-12 original private-story baseline contract", () => {
  it("restores the original blue poster, paired story cards, process summary, marks and lower action hierarchy", () => {
    for (const copy of ["家庭成长故事卡", "我们一起记录家庭的尝试", "当时的感受", "现在想继续", "过程片段", "愿意倾听", "仅保存在这个家庭", "保存家庭故事"]) expect(source).toContain(copy);
  });
  it("reuses existing private story inputs and permits only local private-draft saving", () => {
    expect(source).toContain("buildPrivateGrowthStory");
    expect(source).toContain("savePrivateGrowthStory");
    expect(source).toContain("FAMILY_PRIVATE");
    expect(source).toContain('router.push("/ui/UI-11" as Href)');
  });
  it("excludes a QR code, system/public sharing, and diagnostic capability while explicitly rejecting growth-value claims", () => {
    expect(source).not.toMatch(/QRCode|systemShare|公开分享|儿童诊断|成长成果证明/);
    expect(source).toContain("不是儿童变化、成长值或效果证明");
  });
});
