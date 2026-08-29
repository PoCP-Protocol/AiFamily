import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "app/ui/UI-04.tsx"), "utf8");

describe("UI-04 original 90-day plan baseline contract", () => {
  it("rebuilds the warm plan summary as native components and keeps the original 3/12/36/90 overview", () => {
    expect(source).toContain("function PlanSummaryCard");
    expect(source).toContain("PLAN_SUMMARY_STATS");
    expect(source).not.toContain('require("@/assets/images/ui04-plan-summary-baseline.png")');
    expect(source).toContain("当前阶段、目标、累计时长、难度与计划统计");
    for (const copy of ["当前阶段", "今日任务", "累计时长", "计划周期", "温和进阶"]) expect(source).toContain(copy);
  });

  it("keeps the original four-week coloured timeline in its visual order", () => {
    const week1 = source.indexOf('week: "第1周"');
    const week2 = source.indexOf('week: "第2周"');
    const week3 = source.indexOf('week: "第3周"');
    const week4 = source.indexOf('week: "第4周"');

    expect(week1).toBeGreaterThan(-1);
    expect(week2).toBeGreaterThan(week1);
    expect(week3).toBeGreaterThan(week2);
    expect(week4).toBeGreaterThan(week3);
    expect(source).toContain("mint:");
    expect(source).toContain("blue:");
    expect(source).toContain("orange:");
    expect(source).toContain("gray:");
  });

  it("renders phase-backed completion states while keeping the fixed orange primary action", () => {
    expect(source).toContain("getPhaseStatus");
    expect(source).toContain('status === "completed"');
    expect(source).toContain('backgroundColor: "#FF8A1F"');
    expect(source).toContain("开始执行计划");
  });

  it("does not present an unconfirmed or missing plan as already in progress", () => {
    expect(source).toContain('if (!plan?.plan_id || plan.status === "DRAFT") return "pending" as const;');
    expect(source).toContain("const planIsActive = !!plan?.plan_id && plan.status !== \"DRAFT\";");
    expect(source).toContain("{ value: \"待确认\", label: \"当前阶段\" }");
    expect(source).toContain("{planIsActive ? \"进行中\" : \"待确认\"}");
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
  });
});
