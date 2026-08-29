import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const ui21 = readFileSync(resolve(__dirname, "../app/ui/UI-21.tsx"), "utf8");
const ui23 = readFileSync(resolve(__dirname, "../app/ui/UI-23.tsx"), "utf8");
describe("UI-21 与 UI-23 受控提交反馈", () => {
  it("在提交中显示加载反馈，成功后展示明确边界的弹窗", () => {
    for (const source of [ui21, ui23]) { expect(source).toContain("ActivityIndicator"); expect(source).toContain("Modal"); expect(source).toContain("正在保存"); expect(source).toContain("我知道了"); }
    expect(ui21).toContain("咨询需求已保存"); expect(ui21).toContain("没有联系专家、确认时段或发送通知");
    expect(ui23).toContain("活动意向已保存"); expect(ui23).toContain("没有报名、占用名额或发送通知");
  });
});
