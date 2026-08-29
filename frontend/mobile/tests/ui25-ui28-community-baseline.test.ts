import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const source = (id: string) => readFileSync(resolve(__dirname, `../app/ui/${id}.tsx`), "utf8");
describe("UI-25 至 UI-28 原图社区循环契约", () => {
  it("恢复家长社区搜索、频道、分享横幅和入口", () => {
    const ui25 = source("UI-25");
    for (const copy of ["家长社区", "搜索话题、内容或用户", "今天也来分享孩子成长的小变化", "去分享", "写小记"]) expect(ui25).toContain(copy);
    expect(ui25).toContain('router.push("/ui/UI-26" as Href)');
    expect(ui25).toContain("UI-27?exchangeRef=");
  });
  it("保留发布动态的私有草稿、可编辑标签与隐私边界", () => {
    const ui26 = source("UI-26");
    for (const copy of ["发布动态", "选择小记类型", "小记内容", "可见范围", "仅家庭可见", "保存私有小记"]) expect(ui26).toContain(copy);
    expect(ui26).toContain("saveCommunityPostDraft");
    expect(ui26).toContain("不会公开发布");
    expect(ui26).toContain('flexWrap: "wrap"');
    expect(ui26).toContain('width: "48%"');
  });
  it("保留动态详情与我的社区的私有互动和回读", () => {
    const ui27 = source("UI-27"); const ui28 = source("UI-28");
    for (const copy of ["动态详情", "我的回应草稿", "保存私有回应", "返回社区"]) expect(ui27).toContain(copy);
    for (const copy of ["我的", "我们的家庭内容空间", "私有小记", "我的收藏", "写一篇家庭小记"]) expect(ui28).toContain(copy);
    expect(ui27).toContain('router.push("/ui/UI-25" as Href)');
    expect(ui28).toContain('router.push("/ui/UI-26" as Href)');
  });
  it("不重新引入公开发布、系统分享或公共互动计数", () => {
    const batch = ["UI-25", "UI-26", "UI-27", "UI-28"].map(source).join("\n");
    expect(batch).not.toMatch(/Share\.share|Linking\.openURL|公开发布成功/);
    expect(batch).toContain("不会增加公共计数");
  });
  it("为社区长列表保留统一下拉刷新和受控增量浏览", () => {
    const ui25 = source("UI-25"); const ui27 = source("UI-27");
    expect(ui25).toContain("FamilyRefreshControl"); expect(ui25).toContain("onEndReached={loadMore}"); expect(ui25).toContain("继续浏览更多经验");
    expect(ui27).toContain("FamilyRefreshControl"); expect(ui27).toContain("loadMoreRelated"); expect(ui27).toContain("继续浏览其他经验");
  });
});
