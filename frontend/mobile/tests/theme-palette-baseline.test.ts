import { describe, expect, it } from "vitest";

import themeConfig from "../theme.config";

describe("Warm Education palette baseline", () => {
  it("locks the approved orange, attachment blue, and growth green", () => {
    expect(themeConfig.themeColors.primary.light).toBe("#F28C45");
    expect(themeConfig.themeColors.trust.light).toBe("#0078D4");
    expect(themeConfig.themeColors.growth.light).toBe("#16866D");
    expect(themeConfig.themeColors.success.light).toBe(themeConfig.themeColors.growth.light);
  });

  it("keeps brand, trust, growth, warning, and error semantics distinct", () => {
    const colors = themeConfig.themeColors;
    expect(new Set([
      colors.primary.light,
      colors.trust.light,
      colors.growth.light,
      colors.warning.light,
      colors.error.light,
    ]).size).toBe(5);
  });

  it("uses warm neutral surfaces with high-contrast foreground text", () => {
    expect(themeConfig.themeColors.background.light).toBe("#FFF9F3");
    expect(themeConfig.themeColors.surface.light).toBe("#FFFFFF");
    expect(themeConfig.themeColors.foreground.light).toBe("#10213E");
  });
});
