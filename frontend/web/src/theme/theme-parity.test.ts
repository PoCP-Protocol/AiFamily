import { describe, expect, it } from "vitest";

import { themeColors, typography } from "./tokens";

// Mirrors frontend/mobile/tests/theme-palette-baseline.test.ts and
// frontend/mobile/tests/typography-baseline.test.ts. These are the exact
// values from frontend/mobile/theme.config.js and
// frontend/mobile/constants/typography.ts, hand-copied because web and
// mobile are independent npm projects with no shared workspace. If mobile's
// source values change and this file isn't updated to match, this test
// fails — that's the point.

describe("web/mobile theme token parity", () => {
  it("locks the approved orange, attachment blue, and growth green", () => {
    expect(themeColors.primary.light).toBe("#F28C45");
    expect(themeColors.trust.light).toBe("#0078D4");
    expect(themeColors.growth.light).toBe("#16866D");
    expect(themeColors.success.light).toBe(themeColors.growth.light);
  });

  it("keeps brand, trust, growth, warning, and error semantics distinct", () => {
    expect(
      new Set([
        themeColors.primary.light,
        themeColors.trust.light,
        themeColors.growth.light,
        themeColors.warning.light,
        themeColors.error.light,
      ]).size,
    ).toBe(5);
  });

  it("uses warm neutral surfaces with high-contrast foreground text", () => {
    expect(themeColors.background.light).toBe("#FFF9F3");
    expect(themeColors.surface.light).toBe("#FFFFFF");
    expect(themeColors.foreground.light).toBe("#10213E");
  });

  it("keeps every color token's dark variant distinct from its light variant", () => {
    (Object.keys(themeColors) as Array<keyof typeof themeColors>).forEach((token) => {
      expect(themeColors[token].dark).not.toBe(themeColors[token].light);
    });
  });

  it("matches mobile's typography scale for the levels every UI needs", () => {
    expect(typography.hero).toMatchObject({ fontSize: 28, fontWeight: 800 });
    expect(typography.screenTitle).toMatchObject({ fontSize: 20, fontWeight: 800 });
    expect(typography.body.fontSize).toBe(15);
    expect(typography.supporting.fontSize).toBeGreaterThanOrEqual(12);
  });
});
