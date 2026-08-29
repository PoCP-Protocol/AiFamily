import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

function source(id: string) {
  return readFileSync(resolve(__dirname, `../app/ui/${id}.tsx`), "utf8");
}

describe("UI-06 至 UI-12 原图对齐后的跨页面回归", () => {
  it("保留会员中心到报告与计划的既有功能入口", () => {
    const ui06 = source("UI-06");
    expect(ui06).toContain('{ id: "report", label: "我的报告",');
    expect(ui06).toContain('target: "UI-08"');
    expect(ui06).toContain('{ id: "plan", label: "我的计划",');
    expect(ui06).toContain('target: "UI-04"');
  });

  it("保留测评入口、报告方案和今日任务的受控主链路", () => {
    expect(source("UI-07")).toContain('router.push("/ui/UI-02" as Href)');
    expect(source("UI-08")).toContain('router.push("/ui/UI-04" as Href)');
    const ui09 = source("UI-09");
    expect(ui09).toContain("startAction()");
    expect(ui09).toContain("completeAction(reflection)");
  });

  it("保留孩子挑战到今日任务、成长节奏到私有故事及其回读链路", () => {
    expect(source("UI-10")).toContain('router.push("/ui/UI-09" as Href)');
    expect(source("UI-11")).toContain('router.push("/ui/UI-12" as Href)');
    expect(source("UI-12")).toContain('router.push("/ui/UI-11" as Href)');
  });

  it("整批页面不重新引入实际排名名次、量化总分或系统公开分享", () => {
    const batch = ["UI-07", "UI-08", "UI-09", "UI-10", "UI-11", "UI-12"].map(source).join("\n");
    expect(batch).not.toMatch(/排名第|超过.*家庭|综合分.*[0-9]|systemShare/);
    expect(batch).toContain("不是儿童诊断、家庭总分或效果结论");
    expect(batch).toContain("不比较他人");
  });
});
