import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  familyMobileReducer,
  initialFamilyMobileState,
} from "../lib/family/family-state-core";

const ui02 = readFileSync(resolve(process.cwd(), "app/ui/UI-02.tsx"), "utf8");
const ui03 = readFileSync(resolve(process.cwd(), "app/ui/UI-03.tsx"), "utf8");

describe("UI-02/UI-03 conversation scenario", () => {
  it("keeps the adult's words before consent, focus, and the three-question minimum", () => {
    expect(ui02.indexOf("你现在最想解决什么？")).toBeLessThan(
      ui02.indexOf("这些信息会怎么用？"),
    );
    expect(ui02.indexOf("这些信息会怎么用？")).toBeLessThan(
      ui02.indexOf("哪一小块最相关？"),
    );
    expect(ui02.indexOf("哪一小块最相关？")).toBeLessThan(
      ui02.indexOf("只问三件小事"),
    );
    expect(ui02).toContain("我先这样理解");
    expect(ui02).toContain("没有对错");
    expect(ui02).toContain("跳过这一题");
    expect(ui02).toContain("返回上一题");
  });

  it("recovers a saved private draft without making it a canonical family fact", () => {
    const withNeed = familyMobileReducer(initialFamilyMobileState, {
      type: "save_assessment_need",
      text: "晚上写作业总是容易吵起来",
    });
    const inQuestions = familyMobileReducer(withNeed, {
      type: "set_assessment_step",
      step: "questions",
    });

    expect(inQuestions.assessmentNeedText).toBe("晚上写作业总是容易吵起来");
    expect(inQuestions.assessmentFlowStep).toBe("questions");
    expect(inQuestions).not.toHaveProperty("familyNeed");
    expect(inQuestions).not.toHaveProperty("fact");
  });

  it("renders the four comprehension sections and safe recovery actions", () => {
    expect(ui03).toContain("我们听到的家庭关注");
    expect(ui03).toContain("可能的方向");
    expect(ui03).toContain("还不确定的地方");
    expect(ui03).toContain("今天可以尝试的一小步");
    expect(ui03).toContain("返回修改");
    expect(ui03).toContain("重新开始测评");
    expect(ui03).toContain("测评授权已撤回");
    expect(ui03).toContain("暂时无法读取这次整理");
  });

  it("does not regress into exposed scoring, diagnosis, or automated action", () => {
    expect(ui02).not.toMatch(/overall_score|ranking|诊断结论|自动派单/);
    expect(ui03).not.toMatch(
      /overall_score|peer_reference|scorecard|radar|自动派单/,
    );
    expect(ui03).toContain("FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS");
    expect(ui03).toContain("may_mutate_business_state");
  });
});
