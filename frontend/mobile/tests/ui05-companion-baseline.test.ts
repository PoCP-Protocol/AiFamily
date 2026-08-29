import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(resolve(process.cwd(), "app/ui/UI-05.tsx"), "utf8");

describe("UI-05 original companion service baseline contract", () => {
  it("rebuilds the original four-service-card area as native components", () => {
    expect(source).toContain("SERVICE_CARDS");
    expect(source).toContain("SERVICE_CARD_ACCESSIBILITY_LABEL");
    expect(source).not.toContain('require("@/assets/images/ui05-service-cards-baseline.png")');
    expect(source).toContain("家庭顾问、班主任陪跑、AI提醒和专家答疑");
    for (const copy of ["家庭顾问", "班主任陪跑", "AI提醒", "专家答疑"]) expect(source).toContain(copy);
  });

  it("keeps the original weekly completion card and the three content segments", () => {
    expect(source).toContain("本周完成度");
    expect(source).toContain("本周任务　{progress.completed}/{progress.total}");
    expect(source).toContain("完成3次亲子沟通练习");
    expect(source).toContain("成长打卡");
    expect(source).toContain("家长交流");
    expect(source).toContain("本周直播");
  });

  it("uses the floating check-in button as the only confirmed primary exit", () => {
    expect(source).toContain('accessibilityLabel="打卡"');
    expect(source).toContain("＋");
    expect(source).toContain("const checkinScale");
    expect(source).toContain("Animated.sequence");
    expect(source).toContain("toValue: 0.965");
    expect(source).toContain('router.push("/ui/UI-09" as Href)');
    expect(source).not.toContain('router.push("/ui/UI-06" as Href)');
    expect(source).not.toContain('router.push("/ui/UI-08" as Href)');
  });

  it("reuses the existing service journey read projection without adding payment or outbound actions", () => {
    expect(source).toContain("familyApi.getServiceJourney");
    expect(source).toContain("familyApi.getJourneyPlan");
    expect(source).toContain("familyApi.reviewJourneyPhase");
    expect(source).not.toContain("支付");
    expect(source).not.toContain("购买");
    expect(source).not.toContain("分享");
  });

  it("keeps companion progress as family-private process evidence, not peer comparison or outcome proof", () => {
    expect(source).toContain("本周家庭过程记录");
    expect(source).toContain("remote?.process_summary?.completed_actions ?? 0");
    expect(source).toContain("index < progress.completed");
    expect(source).toContain("我记录下这次互动中的一个积极信号");
    expect(source).toContain("自己的观察和感受记录下来");
    expect(source).toContain("家庭私有记录");
    expect(source).toContain("用于复盘");
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
