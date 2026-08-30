import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "app/ui/UI-04.tsx"), "utf8");

describe("UI-04 original 90-day plan baseline contract", () => {
  it("renders the real 21-day three-phase mechanism summary without synthetic metrics", () => {
    expect(source).toContain("function PlanSummaryCard");
    expect(source).toContain("21天家庭计划");
    expect(source).toContain("关系机制");
    expect(source).toContain("共同决策");
    expect(source).toContain("冲突修复");
    expect(source).toContain("可观察的家庭变化");
    expect(source).not.toContain("PLAN_SUMMARY_STATS");
    expect(source).not.toContain("今日任务");
    expect(source).not.toContain("累计时长");
    expect(source).not.toContain("每周 3-4 次");
  });

  it("keeps the original four-week coloured timeline in its visual order", () => {
    const week1 = source.indexOf('phase: "第 1 阶段"');
    const week2 = source.indexOf('phase: "第 2 阶段"');
    const week3 = source.indexOf('phase: "第 3 阶段"');

    expect(week1).toBeGreaterThan(-1);
    expect(week2).toBeGreaterThan(week1);
    expect(week3).toBeGreaterThan(week2);
    expect(source).toContain("mint:");
    expect(source).toContain("blue:");
    expect(source).toContain("orange:");
    expect(source).toContain("gray:");
  });

  it("renders phase-backed review states while keeping the family confirmation action", () => {
    expect(source).toContain("getPhaseStatus");
    expect(source).toContain('status === "completed"');
    expect(source).toContain('backgroundColor: "#FF8A1F"');
    expect(source).toContain("确认并进入 21 天计划");
  });

  it("does not present an unconfirmed or missing plan as already in progress", () => {
    expect(source).toContain('if (!plan?.plan_id || plan.status === "DRAFT") return "pending" as const;');
    expect(source).toContain("const planIsActive = !!plan?.plan_id && plan.status !== \"DRAFT\";");
    expect(source).toContain("{planIsActive ? \"家庭已确认\" : \"等待确认\"}");
  });

  it("requires confirmed growth priority and server-side plan confirmation before moving to UI-05", () => {
    expect(source).toContain("if (!activeOnboardingId)");
    expect(source).toContain("请先完成家庭测评和成长解读，再开始计划。");
    expect(source).toContain('router.push("/ui/UI-02" as Href)');
    expect(source).toContain("familyApi.getGrowthPriority");
    expect(source).toContain("remotePriority?.active_priority?.priority_id");
    expect(source).toContain("GROWTH_PRIORITY_REQUIRED");
    expect(source).toContain("familyApi.createJourneyPlan");
    expect(source).toContain("familyApi.confirmJourneyPlan");
    expect(source).toContain("`ui04-create-${activeOnboardingId}`");
    expect(source).toContain("`ui04-confirm-${currentPlan.plan_id}`");
    expect(source).toContain('getUiActionPolicy("UI-04")');
    expect(source).toContain("recordUiAction(policy, \"家庭已确认并开始执行当前成长计划\")");
  });

  it("keeps the single plan exit to accompanying service and preserves safety boundaries", () => {
    expect(source).toContain('router.push("/ui/UI-05" as Href)');
    expect(source).not.toContain("总分");
    expect(source).not.toContain("儿童诊断");
    expect(source).not.toContain("90天成长方案");
    expect(source).not.toContain("36h");
    expect(source).not.toContain("开始执行计划");
  });

  it("makes loading, empty, blocked, error, and retry states visible without changing Journey ownership", () => {
    expect(source).toContain('testID="journey-plan-loading"');
    expect(source).toContain('testID={`journey-plan-${projectionState}`}');
    expect(source).toContain('projectionState === "blocked" || projectionState === "empty"');
    expect(source).toContain('testID="journey-plan-error"');
    expect(source).toContain('testID="journey-plan-retry"');
    expect(source).toContain("journeyPlanErrorCopy");
    expect(source).toContain("familyApi.getJourneyPlan");
    expect(source).not.toContain("backend/domains/journey");
  });
});
