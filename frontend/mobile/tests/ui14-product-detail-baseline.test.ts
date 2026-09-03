import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-14.tsx"), "utf8");
const commerceSource = readFileSync(resolve(__dirname, "../lib/family/commerce-entitlements.ts"), "utf8");
describe("UI-14 controlled product-intent contract", () => {
  it("keeps detail, delivery, private invite draft, and controlled action bar", () => {
    for (const copy of ["商品详情", "你将获得", "训练营 ＋ 打卡社群 ＋ 顾问答疑", "创建一份邀请说明草稿", "去了解", "收藏", "客服", "保存方案意向", "了解同行计划"]) expect(source).toContain(copy);
  });
  it("keeps the 21-day camp product copy aligned with the visual baseline", () => {
    for (const copy of ["¥399", "原价¥699", "拼团价 ¥199 (3人成团)", "会员价 ¥179 (会员再享95折)", "21天系统训练", "打卡社群陪伴", "专家顾问答疑", "视频课程", "每日打卡", "社群交流", "专家答疑"]) expect(commerceSource).toContain(copy);
  });
  it("keeps bookmark and support as controlled local no-ops without external effect", () => {
    expect(source).toContain("仅本机");
    expect(source).toContain("不外发通知");
    expect(source).not.toMatch(/openURL|Linking\.|sendMessage|外发会话/);
  });
  it("keeps saving as a controlled intent and the group-plan action as the UI-16 route", () => {
    expect(source).toContain("submitCommerceIntent");
    expect(source).toMatch(/router\.push\(\s*`\/ui\/UI-16\?productRef=/);
    expect(source).toContain("不会扣款");
  });
  it("does not add a payment SDK or external order placement", () => {
    expect(source).not.toMatch(/paymentIntent|checkout|支付宝|微信支付/);
    expect(source).not.toContain("立即购买");
  });
});
