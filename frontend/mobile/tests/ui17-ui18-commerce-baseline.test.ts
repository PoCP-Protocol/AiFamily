import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const ui17 = readFileSync(resolve(__dirname, "../app/ui/UI-17.tsx"), "utf8");
const ui18 = readFileSync(resolve(__dirname, "../app/ui/UI-18.tsx"), "utf8");
describe("UI-17 至 UI-18 commerce boundary contract", () => {
  it("keeps a read-only points projection, action records and rule-preview structure", () => {
    for (const copy of ["成长积分", "成长积分投影", "查看积分规则", "可记录的成长行动", "只用于过程回看，不承诺发放积分", "权益规则预览", "查看说明"]) expect(ui17).toContain(copy);
    expect(ui17).toContain("不会自动发放或扣减权益");
    expect(ui17).not.toMatch(/去签到|立即兑换|\+\d+|\d+ 积分/);
  });
  it("keeps the family profile, four projections, read-only membership status, menu and annual member banner", () => {
    for (const copy of ["家庭成长伙伴", "邀请草稿", "积分投影", "可用权益", "会员状态", "只读权益投影", "方案记录", "年度会员服务", "会员中心"]) expect(ui18).toContain(copy);
    expect(ui18).toContain("不会直接开通、续费、扣款或发送通知");
    expect(ui18).not.toMatch(/LV\d|我的等级|距下一|levelTrack|levelFill/);
  });
});
