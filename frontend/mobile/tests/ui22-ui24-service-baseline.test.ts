import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = (id: string) => readFileSync(resolve(__dirname, `../app/ui/${id}.tsx`), "utf8");
describe("UI-22 至 UI-24 跨域活动与服务循环契约", () => {
  it("保留活动资料目录的层级和详情出口", () => {
    const ui22 = source("UI-22");
    for (const copy of ["家庭成长活动", "按家庭当前关注，了解可选活动主题", "活动资料", "搜索活动主题或家庭关注", "查看介绍"]) expect(ui22).toContain(copy);
    expect(ui22).toContain("UI-23?activityRef=");
    expect(ui22).toContain("不会报名或占用名额");
    expect(ui22).not.toContain("北京市⌄");
  });
  it("保留活动介绍和私有活动意向", () => {
    const ui23 = source("UI-23");
    for (const copy of ["活动介绍", "家庭活动资料", "活动亮点", "活动流程", "查看活动记录", "保存活动意向"]) expect(ui23).toContain(copy);
    expect(ui23).toContain("saveActivityInterestDraft");
    expect(ui23).toContain("不表示报名、出席或名额确认");
    expect(ui23).not.toContain("立即报名");
  });
  it("恢复我的咨询与活动摘要、记录和会员横幅", () => {
    const ui24 = source("UI-24");
    for (const copy of ["我的", "我的咨询", "我的活动", "成长会员年卡", "查看完整服务记录"]) expect(ui24).toContain(copy);
    expect(ui24).toContain("getServiceCustomerProjection");
    expect(ui24).toContain("不代表服务效果或孩子变化");
  });
});
