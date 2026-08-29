import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
const read = (path: string) => readFileSync(resolve(__dirname, `../${path}`), "utf8");
describe("成果资产导出预览与受控分享契约", () => {
  it("在 UI-29 至 UI-34 路由统一展示家庭私有行动入口", () => {
    const overlay = read("components/family/asset-actions-overlay.tsx");
    for (const id of ["UI-29", "UI-30", "UI-31", "UI-32", "UI-33", "UI-34"]) expect(overlay).toContain(id);
    expect(read("app/_layout.tsx")).toContain("AssetActionsOverlay");
  });
  it("仅提供预览和回执，不创建文件、下载或外部分享", () => {
    const actions = read("components/family/private-asset-actions.tsx");
    expect(actions).toContain("导出预览"); expect(actions).toContain("分享回执");
    expect(actions).toContain("不会创建文件、下载或导出数据"); expect(actions).toContain("不会打开外部应用或发送任何内容");
    expect(actions).not.toMatch(/Share\.share|Linking\.openURL|FileSystem|downloadAsync/);
  });
  it("为资产页面提供可审计的 no-op 行动政策", () => {
    const policies = read("lib/family/ui-action-policies.ts");
    for (const id of ["UI-29", "UI-31", "UI-32", "UI-34"]) expect(policies).toContain(`"${id}"`);
    expect(policies).toContain("asset_export");
  });
});
