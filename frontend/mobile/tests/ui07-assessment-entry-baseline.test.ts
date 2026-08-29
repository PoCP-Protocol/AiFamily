import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(__dirname, "../app/ui/UI-07.tsx"), "utf8");

describe("UI-07 original assessment-entry baseline contract", () => {
  it("restores the three-minute hero, first-of-five step and five original visual dimensions", () => {
    for (const copy of ["家庭成长体检", "3分钟了解", "孩子成长状态", "第 1 / 5 步", "5大维度快速评估", "亲子沟通", "学习习惯", "情绪管理", "自律能力", "手机依赖"]) {
      expect(source).toContain(copy);
    }
  });

  it("keeps the example question read-only and provides one primary route to UI-02", () => {
    expect(source).toContain("示例问题");
    expect(source).toContain("立即开始测评");
    expect(source).toContain('router.push("/ui/UI-02" as Href)');
    expect(source).not.toContain("answer_assessment");
  });

  it("does not introduce diagnosis, rankings, or family total scores", () => {
    expect(source).not.toMatch(/诊断|排名|总分/);
  });

  it("does not add extra consent cards that alter the screenshot baseline", () => {
    for (const copy of ["测评前确认", "历史测评状态会在正式测评页同步", "本页不编造记录"]) {
      expect(source).not.toContain(copy);
    }
  });
});
