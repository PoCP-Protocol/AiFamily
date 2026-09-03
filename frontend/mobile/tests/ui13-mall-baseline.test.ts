import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-13.tsx"), "utf8");
describe("UI-13 catalog functional contract", () => {
  it("keeps the greeting, catalog-first banner, six bounded categories, and recommendations", () => {
    for (const copy of ["家庭成长商城", "早上好，乐乐妈妈", "按家庭需要找支持", "家庭同行计划", "成长支持方案", "成长积分规则", "会员权益", "限时挑战", "邀请说明", "今日推荐"]) expect(source).toContain(copy);
  });
  it("keeps confirmed screen and product exits and reuses product projection", () => {
    expect(source).toContain('target="UI-15"');
    expect(source).toContain("UI-14?productRef=");
    expect(source).toContain("getCommerceProducts");
  });
  it("does not charge or automatically activate any entitlement", () => {
    expect(source).toContain("不会扣款，也不会自动开通权益");
  });
});
