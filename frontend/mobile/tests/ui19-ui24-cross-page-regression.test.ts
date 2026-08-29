import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = (id: string) => readFileSync(resolve(__dirname, `../app/ui/${id}.tsx`), "utf8");
describe("UI-19 至 UI-24 专家服务跨页面回归", () => {
  it("保留专家目录到详情和咨询、活动目录到详情的已确认路由", () => {
    expect(source("UI-19")).toContain("UI-20?offeringRef=");
    expect(source("UI-19")).toContain("UI-21?offeringRef=");
    expect(source("UI-20")).toContain("UI-21?offeringRef=");
    expect(source("UI-22")).toContain("UI-23?activityRef=");
  });
  it("保留咨询与活动回读服务记录，并无真实外部效果", () => {
    expect(source("UI-21")).toContain('router.push("/ui/UI-24" as Href)');
    expect(source("UI-23")).toContain('router.push("/ui/UI-24" as Href)');
    const batch = ["UI-19", "UI-20", "UI-21", "UI-22", "UI-23", "UI-24"].map(source).join("\n");
    expect(batch).not.toMatch(/Linking\.openURL|Share\.share|paymentIntent|微信支付|支付宝/);
  });
});
