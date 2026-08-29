import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-08.tsx"), "utf8");
describe("UI-08 original growth-report baseline contract", () => {
  it("keeps the five observation directions, process rows, and 7/30/90 optional path", () => {
    for (const copy of ["家庭过程回顾", "五个观察方向", "亲子沟通", "学习习惯", "情绪管理", "自律能力", "手机依赖", "已看见的行动", "继续观察", "下一步可试", "7天", "30天", "90天", "查看可选支持方案"]) expect(source).toContain(copy);
  });
  it("uses the original bottom route to UI-04 while explicitly rejecting score, rank, and diagnostic conclusions", () => {
    expect(source).toContain('router.push("/ui/UI-04" as Href)');
    expect(source).toContain("不是儿童诊断、家庭总分或效果结论");
    expect(source).not.toMatch(/综合分|排名第|风险等级|诊断结果/);
  });
  it("keeps process records and remote review hints as input rather than rewriting a core result", () => {
    expect(source).toContain("getFamilyReviewReadback");
    expect(source).toContain("已记录");
  });
  it("does not present process review as an evaluation report or generated plan", () => {
    expect(source).not.toContain("成长综合评估");
    expect(source).not.toContain("生成个性化方案");
    expect(source).not.toContain("推荐成长路径");
  });
});
