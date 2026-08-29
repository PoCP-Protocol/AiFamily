import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = (id: string) => readFileSync(resolve(__dirname, `../app/ui/${id}.tsx`), "utf8");
describe("UI-22 至 UI-24 原图服务循环契约", () => {
  it("恢复沙龙目录的原图层级和详情出口", () => {
    const ui22 = source("UI-22");
    for (const copy of ["线下沙龙", "走进家庭成长沙龙", "北京市⌄", "搜索沙龙主题 / 讲师 / 场地", "查看详情"]) expect(ui22).toContain(copy);
    expect(ui22).toContain("UI-23?activityRef=");
    expect(ui22).toContain("不会报名或占用名额");
  });
  it("恢复活动详情和受控报名意向", () => {
    const ui23 = source("UI-23");
    for (const copy of ["活动详情", "活动亮点", "活动流程", "我的活动", "立即报名"]) expect(ui23).toContain(copy);
    expect(ui23).toContain("saveActivityInterestDraft");
    expect(ui23).toContain("不表示报名、出席或名额确认");
  });
  it("恢复我的咨询与活动摘要、记录和会员横幅", () => {
    const ui24 = source("UI-24");
    for (const copy of ["我的", "我的咨询", "我的活动", "成长会员年卡", "查看完整服务记录"]) expect(ui24).toContain(copy);
    expect(ui24).toContain("getServiceCustomerProjection");
    expect(ui24).toContain("不代表服务效果或孩子变化");
  });
});
