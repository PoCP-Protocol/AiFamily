import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  familyMobileReducer,
  initialFamilyMobileState,
} from "../lib/family/family-state-core";

const ui02 = readFileSync(resolve(process.cwd(), "app/ui/UI-02.tsx"), "utf8");
const ui02Result = readFileSync(
  resolve(process.cwd(), "app/ui/UI-02-result.tsx"),
  "utf8",
);
const ui03 = readFileSync(resolve(process.cwd(), "app/ui/UI-03.tsx"), "utf8");

describe("UI-02/UI-03 conversation scenario", () => {
  it("keeps the adult's words before consent, reflection, and the three-question minimum", () => {
    expect(ui02.indexOf("你现在最想解决什么？")).toBeLessThan(
      ui02.indexOf("这些信息会怎么用？"),
    );
    expect(ui02.indexOf("这些信息会怎么用？")).toBeLessThan(
      ui02.indexOf("我先这样理解"),
    );
    expect(ui02.indexOf("我先这样理解")).toBeLessThan(
      ui02.indexOf("只问三件小事"),
    );
    expect(ui02).toContain("这句话像你们家吗？");
    expect(ui02).toContain("像我们家，继续");
    expect(ui02).toContain("不太像，改一下");
    expect(ui02).toContain("补充一句");
    expect(ui02).not.toContain("哪一小块最相关？");
    expect(ui02).not.toContain("assessment-focus-");
    expect(ui02).toContain("没有对错");
    expect(ui02).toContain("跳过这一题");
    expect(ui02).toContain("返回上一题");
    expect(ui02).toContain("3 分钟后，你会带走");
    expect(ui02).toContain("STARTER_SCENES");
    expect(ui02).toContain("testID={`assessment-scene-${label}`}");
    expect(ui02).toContain("写作业总吵");
  });

  it("uses ambiguous or unknown wording only to route questions, never as understanding", () => {
    expect(ui02).toContain("INTERNAL_FOCUS_RULES");
    expect(ui02).toContain("INTERNAL_FOCUS_UNKNOWN");
    expect(ui02).toContain("仅用于选择少量问题");
    expect(ui02).toContain("不会生成家庭理解、事实或解释");
    expect(ui02).toContain("ambiguous");
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
    expect(ui03).toContain("assessment-result-feedback");
    expect(ui03).toContain("像我们家");
    expect(ui03).toContain("不太像");
    expect(ui03).toContain("补充");
    expect(ui03).toContain("assessment-feedback-input");
    expect(ui03).toContain("assessment-feedback-submit");
    expect(ui03).toContain("开始尝试这一步");
    expect(ui03).toContain("先保存，明天再看");
    expect(ui03).toContain("测评授权已撤回");
    expect(ui03).toContain("暂时无法读取这次整理");
    expect(ui03).toContain("AI 家庭理解");
    expect(ui03).toContain("assessment-empty-start");
    expect(ui03).toContain("先整理一件家庭小事");
    expect(ui03).toContain("今晚，先让这件事轻一点");
  });

  it("keeps one connected result source and a clearly marked local fallback", () => {
    expect(ui02).toContain("/ui/UI-03");
    expect(ui02).toContain("/ui/UI-02-result");
    expect(ui02Result).toContain("SANDBOX_LOCAL");
    expect(ui02Result).toContain("未写入服务端");
    expect(ui02Result).toContain('assessmentSyncState === "synced"');
    expect(ui02Result).toContain('router.replace("/ui/UI-03" as Href)');
    expect(ui02Result).not.toContain("buildUi02AssessmentResultSummary");
    expect(ui02Result).not.toContain("查看可解释结果");
  });

  it("fails closed when connected feedback or action contracts are unavailable", () => {
    expect(ui03).not.toContain("recordDevFlowEvent");
    expect(ui03).toContain("No canonical feedback contract exists");
    expect(ui03).toContain("No canonical action contract exists");
    expect(ui03).toContain("暂时无法保存反馈，请稍后重试");
    expect(ui03).toContain("不会自动触发其他行动");
    expect(ui03).toContain("const saveForLater");
    expect(ui03).toContain('if (connected) {\n      setSmallStepState("retry")');
    expect(ui03).toContain("SANDBOX/LOCAL");
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
