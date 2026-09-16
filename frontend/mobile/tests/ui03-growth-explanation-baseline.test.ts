import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "app/ui/UI-03.tsx"), "utf8");
const flow = readFileSync(
  resolve(process.cwd(), "lib/family/ui03-human-task-flow.ts"),
  "utf8",
);
const contracts = readFileSync(
  resolve(process.cwd(), "lib/family/assessment-api-contracts.ts"),
  "utf8",
);

describe("UI-03 family growth explanation baseline contract", () => {
  it("keeps the baseline summary, support direction, review boundary, and explicit action sequence", () => {
    const summary = source.indexOf("<View style={styles.assessmentSummary}>");
    const overview = source.indexOf("证据与支持方向");
    const issues = source.indexOf("核心问题");
    const boundary = source.indexOf("理解边界");
    const action = source.indexOf("接受这份支持方向并继续");

    expect(summary).toBeGreaterThan(-1);
    expect(overview).toBeGreaterThan(summary);
    expect(issues).toBeGreaterThan(overview);
    expect(boundary).toBeGreaterThan(issues);
    expect(action).toBeGreaterThan(boundary);
  });

  it("renders evidence-backed support direction without a family score or radar", () => {
    expect(source).not.toContain("GrowthRadarOverview");
    expect(source).not.toContain("scorecard.dimensions");
    expect(source).not.toContain("overall_score");
    expect(source).not.toContain("peer_reference");
    expect(source).toContain("家庭支持理解");
    expect(source).toContain("可审阅支持假设");
    expect(source).toContain("证据与支持方向");
    expect(source).toContain("理解边界");
    expect(source).toContain('title: "家庭支持理解"');
    expect(source).toContain("不是儿童诊断结论、能力测验或排名");
    expect(source).not.toContain("PREVIEW_SCORECARD");
    expect(source).toContain("这里不会预填家庭分数");
    expect(source).not.toMatch(/同龄平均|孩子得分|总分排名|能力排名|智力测验/);
  });

  it("keeps backend model capability embedded in the baseline report hierarchy", () => {
    expect(source).toContain("ai_state");
    expect(source).toContain("formatAiState");
    expect(flow).toContain("parseAssessmentHumanTaskDecisionReceipt");
    expect(flow).toContain("parseConfirmedGrowthHypothesisReceipt");
    expect(contracts).toContain('confirm: "CONFIRM_GROWTH_HYPOTHESIS"');
    expect(source).not.toContain("AI解读摘要");
    expect(source).not.toContain("来源与边界");
  });

  it("uses the server hypothesis and limitations without retaining the legacy score model", () => {
    expect(source).toContain("hypothesis.statement");
    expect(source).toContain("hypothesis.limitations.map");
    expect(contracts).not.toContain("interface Ui03ScoreDimension");
    expect(contracts).not.toContain("interface Ui03Scorecard");
    expect(contracts).not.toContain("peer_reference: number");
  });

  it("keeps UI-04 gated by the two-step human receipt flow and preserves a real empty state", () => {
    expect(source).toContain('router.push("/ui/UI-04" as Href)');
    expect(source).not.toContain('router.push("/ui/UI-08" as Href)');
    expect(flow).toContain('decision_type: "CONFIRM"');
    expect(flow).not.toContain('decision_type: "DISMISS"');
    expect(source).toContain('remoteState === "empty"');
    expect(source).toContain('remoteState === "denied"');
    expect(source).toContain('remoteState === "contract_blocked"');
    expect(source).toContain("只有服务端同时返回人工任务凭据时，才能继续确认");
  });

  it("does not continue into UI-04 before INTENT_CREATED and onboarding receipt", () => {
    const intentCheck = flow.indexOf("parseConfirmedGrowthHypothesisReceipt");
    const onboarding = flow.indexOf("startGrowthOnboarding<unknown>");
    const returnContext = flow.lastIndexOf('status: "ONBOARDING_STARTED"');
    expect(intentCheck).toBeGreaterThan(-1);
    expect(onboarding).toBeGreaterThan(intentCheck);
    expect(returnContext).toBeGreaterThan(onboarding);
    expect(source).toContain("setUi03FlowContext(result)");
  });

  it("shows only real collected context and hides missing personal fields", () => {
    expect(flow).toContain("hypothesis.source_refs.assessment_session_id");
    expect(source).toContain("assessment_submitted_at");
    expect(source).toContain("formatDate");
    expect(source).toContain(".filter((row): row is string => Boolean(row))");
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

  it("keeps reject distinct from defer and requires a typed reason", () => {
    expect(source).toContain('onPress={() => void decide("REJECT")}');
    expect(source).toContain("!rejectionReason.trim()");
    expect(source).toContain("提交拒绝并终止");
    expect(source).toContain("先放一放，不提交决定");
    expect(flow).toContain('status: "REJECTED"');
  });
});
