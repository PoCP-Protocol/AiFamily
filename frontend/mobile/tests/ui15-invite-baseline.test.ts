import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-15.tsx"), "utf8");
describe("UI-15 private invitation-draft contract", () => {
  it("keeps the invitation explanation, draft status, rule previews, templates and lower banner", () => {
    for (const copy of ["邀请说明", "创建一份家庭邀请说明", "邀请说明草稿", "可了解的权益说明", "规则待确认", "保存邀请草稿", "选择草稿模板", "好友说明", "动态文案", "海报文案", "一起成长，一起变好"]) expect(source).toContain(copy);
  });
  it("keeps invitation as a local controlled draft and returns to product detail", () => {
    expect(source).toContain("saveInvitationDraft");
    expect(source).toContain("recordDevFlowEvent");
    expect(source).toMatch(/router\.push\(\s*`\/ui\/UI-14\?productRef=/);
    expect(source).toContain("没有打开外部应用");
  });
  it("does not directly use a real sharing API or outbound URL", () => expect(source).not.toMatch(/Share\.share|Linking\.openURL|WebBrowser/));
  it("does not present synthetic progress or guaranteed rewards", () => {
    expect(source).not.toMatch(/1\/3|价值 ¥|立即邀请|邀请得奖励/);
  });
});
