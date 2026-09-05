import { describe, expect, it, vi } from "vitest";

vi.mock("react-native", () => ({
  Platform: {
    select: (families: Record<string, string>) =>
      families.web ?? families.default,
  },
}));

import { FamilyTypography, MIN_TOUCH_TARGET } from "../constants/typography";

describe("Family typography baseline", () => {
  it("keeps readable Chinese text hierarchy", () => {
    expect(FamilyTypography.hero.fontSize).toBe(28);
    expect(FamilyTypography.screenTitle).toMatchObject({
      fontSize: 20,
      lineHeight: 28,
      fontWeight: "800",
    });
    expect(FamilyTypography.body).toMatchObject({
      fontSize: 15,
      lineHeight: 24,
      fontWeight: "400",
    });
    expect(FamilyTypography.supporting.fontSize).toBeGreaterThanOrEqual(12);
  });

  it("uses stable button and metric treatments", () => {
    expect(FamilyTypography.button.fontWeight).toBe("700");
    expect(FamilyTypography.metric.fontVariant).toContain("tabular-nums");
    expect(MIN_TOUCH_TARGET).toBe(44);
  });
});
