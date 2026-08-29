import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-10.tsx"), "utf8");
describe("UI-10 original child-assistant baseline contract", () => {
  it("restores the welcome banner, energy, four activity cards, challenge, collection, and start CTA", () => {
    for (const copy of ["Hi，乐乐小朋友！", "成长能量", "专注力训练", "阅读打卡", "情绪小日记", "今日目标", "今日挑战", "我的小收藏", "开始挑战"]) expect(source).toContain(copy);
  });
  it("keeps the original single primary route to UI-09 and reads the existing child prompt projection", () => {
    expect(source).toContain('router.push("/ui/UI-09" as Href)');
    expect(source).toContain("getDevCoreGrowth");
    expect(source).toContain("selectChildActionPrompt");
  });
  it("does not claim child ability, score, diagnosis, ranking, or an educational result", () => {
    expect(source).toContain("不记录能力、分数或成长结果");
    expect(source).not.toMatch(/儿童诊断|家庭排名|总分/);
  });
});
