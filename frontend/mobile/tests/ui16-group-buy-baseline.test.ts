import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-16.tsx"), "utf8");
describe("UI-16 private participation-intent contract", () => {
  it("keeps title, filters, draft status, reference prices and orange save action", () => {
    for (const copy of ["家庭同行计划", "选择适合的方案，先保存参与意向", "全部", "课程服务", "会员卡", "工具包", "家庭同行示例", "当前仅保存私有草稿", "参考方案", "保存同行意向"]) expect(source).toContain(copy);
  });
  it("keeps join as a synthetic private draft without order or payment creation", () => {
    expect(source).toContain("saveStudyGroupDraft");
    expect(source).toContain("SAVE_SYNTHETIC_STUDY_GROUP_DRAFT");
    expect(source).toContain("没有创建拼团订单、发送邀请或扣款");
    expect(source).not.toMatch(/后结束|去拼团|立即参团/);
  });
});
