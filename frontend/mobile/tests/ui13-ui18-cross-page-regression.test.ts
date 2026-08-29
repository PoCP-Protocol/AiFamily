import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = (id: string) => readFileSync(resolve(__dirname, `../app/ui/${id}.tsx`), "utf8");
describe("UI-13 至 UI-18 原图对齐后的跨页面回归", () => {
  it("保留商城到邀请、商品、拼团、积分和会员的已确认入口", () => {
    const ui13 = source("UI-13");
    expect(ui13).toContain('router.push("/ui/UI-15" as Href)');
    expect(ui13).toContain("UI-14?productRef=");
    for (const target of ["UI-16", "UI-17", "UI-18"]) expect(ui13).toContain(`target="${target}"`);
  });
  it("保留商品、邀请和拼团的回读路线", () => {
    expect(source("UI-14")).toContain('router.push("/ui/UI-15" as Href)');
    expect(source("UI-14")).toContain('router.push(`/ui/UI-16?productRef=');
    expect(source("UI-15")).toContain('router.push(`/ui/UI-14?productRef=');
    expect(source("UI-16")).toContain('router.push("/ui/UI-13" as Href)');
  });
  it("保留积分任务和成长合伙人菜单的既有出口", () => {
    const ui17 = source("UI-17");
    for (const target of ["UI-08", "UI-15", "UI-09", "UI-12", "UI-19"]) expect(ui17).toContain(`target: "${target}"`);
    const ui18 = source("UI-18");
    for (const target of ["UI-32", "UI-15", "UI-17", "UI-12", "UI-30", "UI-19"]) expect(ui18).toContain(`target: "${target}"`);
  });
  it("不重新引入支付、真实外发或自动权益", () => {
    const batch = ["UI-13", "UI-14", "UI-15", "UI-16", "UI-17", "UI-18"].map(source).join("\n");
    expect(batch).not.toMatch(/paymentIntent|支付宝|微信支付|Share\.share|Linking\.openURL/);
    expect(batch).toContain("不会扣款");
    expect(batch).toContain("没有打开外部应用");
    expect(batch).toContain("没有创建拼团订单、发送邀请或扣款");
  });
});
