import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { FAMILY_SCREENS, getScreensForTab } from "../lib/family/ui-registry";

describe("App and Web feature parity", () => {
  it("uses the same Expo Router screen registry for all 34 product pages", () => {
    const tabs = ["today", "growth", "discover", "services", "mine"] as const;
    const webReachableScreens = tabs.flatMap((tab) => getScreensForTab(tab));

    expect(FAMILY_SCREENS).toHaveLength(34);
    expect(webReachableScreens.map((screen) => screen.id).sort()).toEqual(FAMILY_SCREENS.map((screen) => screen.id).sort());
  });

  it("keeps desktop navigation on the same five cross-platform routes", () => {
    const source = readFileSync(resolve(__dirname, "../components/family/responsive-platform-shell.tsx"), "utf8");

    expect(source).toContain('label: "今天", route: "/"');
    expect(source).toContain('label: "成长", route: "/growth"');
    expect(source).toContain('label: "发现", route: "/discover"');
    expect(source).toContain('label: "服务", route: "/services"');
    expect(source).toContain('label: "我的", route: "/mine"');
    expect(source).toContain("{children}");
  });
});
