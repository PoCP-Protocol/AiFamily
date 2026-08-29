import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const ui17 = readFileSync(resolve(__dirname, "../app/ui/UI-17.tsx"), "utf8");
const ui18 = readFileSync(resolve(__dirname, "../app/ui/UI-18.tsx"), "utf8");
describe("UI-17 至 UI-18 original commerce baseline contract", () => {
  it("restores points card, sign-in, task center and redemption structure", () => {
    for (const copy of ["积分商城", "我的成长积分", "去签到 +10", "任务中心", "做任务，赚积分", "积分兑换", "立即兑换"]) expect(ui17).toContain(copy);
    expect(ui17).toContain("不会自动发放或扣减权益");
  });
  it("restores growth partner profile, four stats, level, menu and annual member banner", () => {
    for (const copy of ["成长合伙人", "已邀请家庭", "成长积分", "可用权益", "我的等级", "我的订单", "年度会员服务", "会员中心"]) expect(ui18).toContain(copy);
    expect(ui18).toContain("不会直接开通、续费、扣款或发送通知");
  });
});
