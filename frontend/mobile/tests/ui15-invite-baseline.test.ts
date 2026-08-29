import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = readFileSync(resolve(__dirname, "../app/ui/UI-15.tsx"), "utf8");
describe("UI-15 original invite baseline contract", () => {
  it("restores invite header, 1/3 progress, rewards, immediate CTA, methods and lower banner", () => {
    for (const copy of ["邀请有礼", "邀请 3 个家庭", "1/3", "邀请奖励进度", "立即邀请", "邀请方式", "微信好友", "朋友圈", "生成海报", "一起成长，一起变好"]) expect(source).toContain(copy);
  });
  it("keeps invitation as a local controlled draft and returns to product detail", () => {
    expect(source).toContain("saveInvitationDraft");
    expect(source).toContain("recordDevFlowEvent");
    expect(source).toContain('router.push(`/ui/UI-14?productRef=');
    expect(source).toContain("没有打开外部应用");
  });
  it("does not directly use a real sharing API or outbound URL", () => expect(source).not.toMatch(/Share\.share|Linking\.openURL|WebBrowser/));
});
