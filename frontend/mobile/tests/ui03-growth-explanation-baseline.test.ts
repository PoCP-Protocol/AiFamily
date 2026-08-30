import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "app/ui/UI-03.tsx"), "utf8");

describe("UI-03 VS-GROWTH-01 canonical projection boundary", () => {
  it("declares and maps all ten required states", () => {
    const requiredStates = [
      "loading",
      "empty",
      "success",
      "denied",
      "withdrawn",
      "expired",
      "unauthorized",
      "forbidden",
      "conflict",
      "error",
    ];

    for (const state of requiredStates) {
      expect(source).toContain(`| "${state}"`);
      expect(source).toContain(`return "${state}"`);
    }
  });

  it("reads the canonical family assessment and UI-03 projections", () => {
    expect(source).toContain("familyApi.getFamilyAssessment<Ui03AssessmentProjection>");
    expect(source).toContain("familyApi.getGrowthHypothesis<Ui03HypothesisProjection>");
    expect(source).toContain("Promise.all");
    expect(source).toContain("getPurposeText(assessmentResult, projectionResult)");
    expect(source).toContain("processing_purposes");
    expect(source).toContain("authorized_context");
    expect(source).toContain("consent_state");
  });

  it("keeps family selection server-scoped and refuses local family creation", () => {
    expect(source).toContain("session.contexts");
    expect(source).toContain("onSelect={session.selectFamily}");
    expect(source).toContain("创建家庭（需 Family API）");
    expect(source).toContain("disabled");
    expect(source).toContain("不在本地创建家庭或伪造家庭上下文");
    expect(source).not.toContain("setContexts(");
    expect(source).not.toContain("family_id: \"FAMILY-");
  });

  it("does not turn a checkbox or local state into a consent fact", () => {
    expect(source).toContain("同意 / 拒绝 / 撤回");
    expect(source).toContain("页面勾选不能替代 ConsentGrant");
    expect(source).toContain("三个动作保持停止态");
    expect(source).toContain("不会改变授权事实");
    expect(source).toContain("canonical API 未返回可用 authorized context");
    expect(source).not.toContain("setConsent");
    expect(source).not.toContain("consentGranted");
    expect(source).not.toContain("grantConsent");
    expect(source).not.toContain("withdrawConsent");
  });

  it("keeps API errors visible and recoverable", () => {
    expect(source).toContain('errorStatus === 401');
    expect(source).toContain('errorStatus === 403');
    expect(source).toContain('errorStatus === 409');
    expect(source).toContain('errorStatus === 410');
    expect(source).toContain("401 UNAUTHENTICATED");
    expect(source).toContain("403 FAMILY_FORBIDDEN");
    expect(source).toContain("409 VERSION_CONFLICT");
    expect(source).toContain("不会把错误静默成空态或成功");
    expect(source).toContain("PROVENANCE_INCOMPLETE");
    expect(source).toContain("重新读取");
  });

  it("marks the disconnected path DEMO_ONLY without creating synthetic facts", () => {
    expect(source).toContain("DEMO_ONLY");
    expect(source).toContain("未连接 canonical API");
    expect(source).toContain("不提供 synthetic Family、Consent、处理目的或 authorized context");
    expect(source).not.toContain("PREVIEW_SCORECARD");
    expect(source).not.toContain("router.push");
    expect(source).not.toContain("router.replace");
  });
});
