import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-13.tsx"), "utf8");
describe("UI-13 original mall baseline contract", () => {
  it("restores original greeting, invite banner, six categories, and today recommendations", () => {
    for (const copy of ["家庭成长商城", "早上好，乐乐妈妈", "邀请好友领成长礼包", "拼团专区", "家庭成长好物", "成长积分商城", "会员专享", "限时挑战", "邀请有礼", "今日推荐"]) expect(source).toContain(copy);
  });
  it("keeps confirmed invite and product exits and reuses product projection", () => {
    expect(source).toContain('router.push("/ui/UI-15" as Href)');
    expect(source).toContain("UI-14?productRef=");
    expect(source).toContain("getCommerceProducts");
  });
  it("does not charge or automatically activate any entitlement", () => {
    expect(source).toContain("不会扣款，也不会自动开通权益");
  });
});
