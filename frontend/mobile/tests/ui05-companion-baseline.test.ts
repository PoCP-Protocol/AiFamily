import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "app/ui/UI-05.tsx"), "utf8");

describe("UI-05 original companion service baseline contract", () => {
  it("rebuilds the original four-service-card area as native components", () => {
    expect(source).toContain("SERVICE_CARDS");
    expect(source).toContain("SERVICE_CARD_ACCESSIBILITY_LABEL");
    expect(source).not.toContain('require("@/assets/images/ui05-service-cards-baseline.png")');
    expect(source).toContain("家庭顾问、班主任陪跑、AI解读草案和专家答疑");
    for (const copy of ["家庭顾问", "班主任陪跑", "AI解读草案", "专家答疑"]) expect(source).toContain(copy);
  });

  it("renders the 21-day mechanism reflection without synthetic progress or check-in language", () => {
    expect(source).toContain("21 天家庭复盘");
    expect(source).toContain("关系机制");
    expect(source).toContain("共同决策");
    expect(source).toContain("冲突修复");
    expect(source).toContain("journey-phase-reflection");
    expect(source).not.toContain("本周完成度");
    expect(source).not.toContain("成长打卡");
    expect(source).not.toContain("本周任务");
    expect(source).not.toContain("完成数量");
  });

  it("uses the existing Journey phase review as the only state-changing action", () => {
    expect(source).toContain("reviewJourneyPhase");
    expect(source).toContain("继续下一阶段");
    expect(source).toContain("先调整节奏");
    expect(source).toContain("暂时暂停");
    expect(source).toContain("请求人工支持");
    expect(source).toContain('reviewPhase("PAUSE")');
    expect(source).toContain('reviewPhase("HUMAN_REVIEW_REQUIRED")');
    expect(source).not.toContain('accessibilityLabel="打卡"');
    expect(source).not.toContain('router.push("/ui/UI-09" as Href)');
  });

  it("reuses the existing service journey read projection without adding payment or outbound actions", () => {
    expect(source).toContain("familyApi.getServiceJourney");
    expect(source).toContain("familyApi.getJourneyPlan");
    expect(source).toContain("familyApi.reviewJourneyPhase");
    expect(source).not.toContain("支付");
    expect(source).not.toContain("购买");
    expect(source).not.toContain("分享");
  });

  it("keeps the phase reflection scoped to family observation and decision", () => {
    expect(source).toContain("只记录家庭自己的观察和决定");
    expect(source).toContain("家庭观察与决定");
    expect(source).not.toContain("progress.completed");
    expect(source).not.toContain("completed_actions");
    expect(source).not.toContain("超过 78% 的伙伴");
    expect(source).not.toContain("看到孩子的变化");
    expect(source).not.toContain("♧ 23");
    expect(source).not.toContain("◯ 8");
  });

  it("uses a lightweight component transition for the service-card area", () => {
    expect(source).toContain("const serviceCardsOpacity");
    expect(source).toContain("const serviceCardsOffset");
    expect(source).toContain("revealServiceCards");
    expect(source).toContain("setTimeout(revealServiceCards");
    expect(source).not.toContain("onLoad={revealServiceCards}");
    expect(source).toContain("serviceCardsTransition");
  });
});
