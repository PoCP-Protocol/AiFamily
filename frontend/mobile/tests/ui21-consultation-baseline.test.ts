import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-21.tsx"), "utf8");
describe("UI-21 原图在线咨询契约", () => {
  it("保留顶部、四步进度、咨询方式、时段、家庭观察和确认预约", () => {
    for (const copy of ["在线咨询 / 预约", "选择方式", "选择时间", "填写信息", "确认需求", "选择咨询方式", "选择时间", "家庭需求", "确认预约"]) expect(source).toContain(copy);
  });
  it("仅保存受控咨询需求并回读 UI-24", () => {
    expect(source).toContain("saveConsultationNeedDraft");
    expect(source).toContain("submitServiceBooking");
    expect(source).toContain('router.push("/ui/UI-24" as Href)');
    expect(source).toContain("没有向外部联系人发消息");
  });
});
