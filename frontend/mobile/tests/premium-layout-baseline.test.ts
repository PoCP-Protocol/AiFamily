import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

function source(id: string) {
  return readFileSync(resolve(__dirname, `../app/ui/${id}.tsx`), "utf8");
}

describe("premium layout baseline", () => {
  it("keeps the mobile mall readable with a two-column product grid", () => {
    const mall = source("UI-13");
    expect(mall).toContain('key="mall-products-2-columns"');
    expect(mall).toContain("numColumns={2}");
    expect(mall).toContain("backgroundColor: colors.background");
  });

  it("keeps points rewards in a spacious two-column grid", () => {
    const points = source("UI-17");
    expect(points).toMatch(/rewardRow:\s*\{[^}]*flexWrap:\s*"wrap"/s);
    expect(points).toMatch(/rewardCard:\s*\{[^}]*width:\s*"48%"/s);
    expect(points).toMatch(/taskRow:\s*\{[^}]*borderRadius:\s*16/s);
  });

  it("keeps commerce surfaces theme-aware instead of mixing light pages and dark cards", () => {
    for (const id of ["UI-13", "UI-15", "UI-16", "UI-17", "UI-18"]) {
      expect(source(id)).toContain("backgroundColor: colors.background");
    }
  });
});
