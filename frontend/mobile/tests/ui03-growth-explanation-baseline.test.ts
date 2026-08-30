import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "app/ui/UI-03.tsx"), "utf8");

describe("UI-03 family assessment result contract", () => {
  it("reads the family-scoped result projection after submission", () => {
    expect(source).toContain("getLatestAssessmentResult");
    expect(source).toContain('projection_version: "ASSESSMENT_RESULT_V1"');
    expect(source).toContain("family_id: string");
    expect(source).toContain("result: AssessmentResult | null");
    expect(source).toContain("家庭成长解读 · 家庭范围 · 可回看");
  });

  it("shows a clear explanation and provenance without score, ranking, or diagnosis", () => {
    expect(source).toContain("我们听到的家庭关注");
    expect(source).toContain("为什么会卡在这里");
    expect(source).toContain("家庭观察画像");
    expect(source).toContain("知识参考");
    expect(source).toContain("家庭成长方案");
    expect(source).toContain("本次结果依据");
    expect(source).toContain("FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS");
    expect(source).toContain("may_mutate_business_state");
    expect(source).toContain("NOT_INVOKED");
    expect(source).toContain("assessment-human-gate");
    expect(source).toContain("家庭理解卡");
    expect(source).toContain("assessment-observation-toggle");
    expect(source).toContain("assessment-observation-layer");
    expect(source).toContain("依据");
    expect(source).toContain("可能的方向");
    expect(source).toContain("还未知");
    expect(source).toContain("decideGrowthHypothesis");
    expect(source).toContain("确认这份理解");
    expect(source).toContain("暂不采用");
    expect(source).toContain("确认后才会记录为这次家庭关注");
    expect(source).not.toMatch(/overall_score|peer_reference|scorecard|ranking/);
  });

  it("has loading, empty, consent, and read-error states", () => {
    expect(source).toContain('state === "loading"');
    expect(source).toContain('state === "error"');
    expect(source).toContain("CONSENT_REQUIRED");
    expect(source).toContain("还没有已提交的家庭测评");
    expect(source).toContain("暂时无法读取这次整理");
    expect(source).toContain("重新读取");
  });

  it("offers safe restart and exit actions without creating a business action", () => {
    expect(source).toContain('router.replace("/ui/UI-02" as Href)');
    expect(source).toContain("重新开始测评");
    expect(source).toContain("router.back()");
    expect(source).toContain(">退出<");
    expect(source).not.toContain("startGrowthOnboarding");
  });

  it("opens the existing Journey plan only after the adult confirms the draft understanding", () => {
    expect(source).toContain('interpretationDecision === "confirmed"');
    expect(source).toContain('testID="assessment-open-journey-plan"');
    expect(source).toContain('router.push("/ui/UI-04" as Href)');
  });
});
