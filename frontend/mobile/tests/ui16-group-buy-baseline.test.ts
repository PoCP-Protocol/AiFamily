import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-16.tsx"), "utf8");
describe("UI-16 original group-buy baseline contract", () => {
  it("restores title, subtitle, tabs, group leader/countdown, prices and orange join action", () => {
    for (const copy of ["拼团专区", "多家庭一起学，更划算", "全部", "课程服务", "会员卡", "工具包", "团长：乐乐妈妈", "后结束", "拼团价", "去拼团"]) expect(source).toContain(copy);
  });
  it("keeps join as a synthetic private draft without order or payment creation", () => {
    expect(source).toContain("saveStudyGroupDraft");
    expect(source).toContain("SAVE_SYNTHETIC_STUDY_GROUP_DRAFT");
    expect(source).toContain("没有创建拼团订单、发送邀请或扣款");
  });
});
