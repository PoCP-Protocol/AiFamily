import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = (id: string) => readFileSync(resolve(__dirname, `../app/ui/${id}.tsx`), "utf8");
describe("UI-29 至 UI-34 成果资产原图与边界契约", () => {
  it("保留成长成果的蓝色过程回顾、过程片段与家庭档案出口", () => {
    const ui29 = source("UI-29");
    for (const copy of ["成长成果", "本周成长慢谈", "我们正在练习的事", "过程里的片段", "查看家庭档案"]) expect(ui29).toContain(copy);
    expect(ui29).toContain('router.push("/ui/UI-33" as Href)');
    expect(ui29).toContain("过程记录不代表效果结论");
  });
  it("保留年度会员、我的服务、订单资产的投影与受控入口", () => {
    const ui30 = source("UI-30"); const ui31 = source("UI-31"); const ui32 = source("UI-32");
    for (const copy of ["我的年度会员服务", "快捷入口", "当前陪伴", "查看订单与资产"]) expect(ui30).toContain(copy);
    expect(ui31).toContain("成长顾问"); expect(ui31).toContain("继续行动");
    expect(ui32).toContain("家庭资产"); expect(ui32).toContain("不会支付、核销、下载、导出或发送内容");
  });
  it("保留家庭档案和服务记录的私有范围及回读出口", () => {
    const ui33 = source("UI-33"); const ui34 = source("UI-34");
    expect(ui33).toContain("家庭成长时间线"); expect(ui33).toContain("不显示儿童身份资料、学校信息或诊断结论");
    expect(ui34).toContain("服务记录"); expect(ui34).toContain("不会自动联系、拨号、发送消息或创建工单");
    expect(ui34).toContain('router.push("/ui/UI-31" as Href)');
  });
  it("不恢复成绩、排名、自动支付或外部分享", () => {
    const batch = ["UI-29", "UI-30", "UI-31", "UI-32", "UI-33", "UI-34"].map(source).join("\n");
    expect(batch).not.toMatch(/Share\.share|Linking\.openURL|paymentIntent|家庭排名/);
  });
});
