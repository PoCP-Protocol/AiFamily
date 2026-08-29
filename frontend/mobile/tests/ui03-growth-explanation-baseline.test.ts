import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "app/ui/UI-03.tsx"), "utf8");

describe("UI-03 family growth explanation baseline contract", () => {
  it("keeps the baseline summary, direction overview, focus, suggestion, and action sequence", () => {
    const summary = source.indexOf("<View style={styles.assessmentSummary}>");
    const overview = source.indexOf("综合成长评估");
    const issues = source.indexOf(">核心问题<");
    const suggestions = source.indexOf(">成长建议<");
    const action = source.indexOf("生成个性化方案");

    expect(summary).toBeGreaterThan(-1);
    expect(overview).toBeGreaterThan(summary);
    expect(issues).toBeGreaterThan(overview);
    expect(suggestions).toBeGreaterThan(issues);
    expect(action).toBeGreaterThan(suggestions);
  });

  it("renders the AI diagnosis upgrade screen from scorecard output with the required boundary", () => {
    expect(source).toContain("GrowthRadarOverview");
    expect(source).toContain("scorecard.dimensions");
    expect(source).toContain("scorecard.overall_score");
    expect(source).toContain("AI成长诊断");
    expect(source).toContain("AI成长诊断报告");
    expect(source).toContain("参考分");
    expect(source).toContain("家庭自查线索");
    expect(source).toContain("参考方向");
    expect(source).toContain('title: "AI成长诊断"');
    expect(source).toContain("SUPPORT_ORIENTATION_SCORE_NOT_CHILD_DIAGNOSIS_OR_RANKING");
    expect(source).toContain("不是儿童诊断结论、能力测验或排名");
    expect(source).not.toMatch(/同龄平均|孩子得分|总分排名|能力排名|智力测验/);
  });

  it("keeps backend model capability embedded in the baseline report hierarchy", () => {
    expect(source).toContain("ai_state");
    expect(source).toContain("formatAiState");
    expect(source).toContain("const aiState = remote.ai_state");
    expect(source).toContain("named_actions.confirm");
    expect(source).toContain("CONFIRM_GROWTH_HYPOTHESIS");
    expect(source).not.toContain("AI解读摘要");
    expect(source).not.toContain("来源与边界");
  });

  it("uses scorecard-backed issue tags and numbered recommendations", () => {
    expect(source).toContain("scorecard.core_issue_tags.slice(0, 3).map");
    expect(source).toContain("scorecard.recommendations.slice(0, 3).map");
    expect(source).toContain("{index + 1}");
    expect(source).not.toContain("function LayerCard");
  });

  it("keeps UI-04 gated by the single generation action and preserves a real empty state", () => {
    expect(source).toContain('router.push("/ui/UI-04" as Href)');
    expect(source).not.toContain('router.push("/ui/UI-08" as Href)');
    expect(source).toContain('decision_type: "CONFIRM"');
    expect(source).not.toContain('decision_type: "DISMISS"');
    expect(source).not.toContain("暂不形成成长方向");
    expect(source).toContain("先完成免费家庭测评");
    expect(source).toContain("AI 会基于你提交的免费测评生成成长诊断报告；这不是儿童诊断结论、能力测验或排名。");
  });

  it("shows only real collected context and hides missing personal fields", () => {
    expect(source).toContain("source_refs.assessment_session_id");
    expect(source).toContain("assessment_submitted_at");
    expect(source).toContain("formatDate");
    expect(source).toContain("filter(Boolean)");
    expect(source).toContain("测评时间：");
    expect(source).not.toContain("10岁");
    expect(source).not.toContain("四年级");
  });

  it("does not render the backend principal persona as an extra visible card", () => {
    expect(source).not.toContain("remote?.hypothesis?.principal");
    expect(source).not.toContain("remote.hypothesis.principal.public_role");
    expect(source).not.toContain("remote.hypothesis.principal.opening");
    expect(source).not.toContain("remote.hypothesis.principal.reading");
    expect(source).not.toContain("remote.hypothesis.principal.boundary");
    expect(source).not.toContain("家庭教育大模型 · 陪你一起看这次测评");
  });
});
