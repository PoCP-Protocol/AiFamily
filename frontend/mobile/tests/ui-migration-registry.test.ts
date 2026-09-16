import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { FAMILY_SCREENS } from "../lib/family/ui-registry";
import {
  UI_MIGRATION_REGISTRY,
  assertCompleteUiMigrationRegistry,
  migrationForUi,
} from "../lib/family/ui-migration-registry";

const familyScreenListSource = readFileSync(
  resolve(process.cwd(), "components/family/family-screen-list.tsx"),
  "utf8",
);
const growthTabSource = readFileSync(
  resolve(process.cwd(), "app/(tabs)/growth.tsx"),
  "utf8",
);

describe("UI-01 through UI-34 migration registry", () => {
  it("covers every preserved Mobile baseline exactly once", () => {
    expect(() => assertCompleteUiMigrationRegistry()).not.toThrow();
    expect(UI_MIGRATION_REGISTRY).toHaveLength(34);
    expect(FAMILY_SCREENS).toHaveLength(34);
  });

  it("marks only the callable assessment chain as a Python vertical slice", () => {
    expect(
      UI_MIGRATION_REGISTRY.filter(
        (entry) => entry.status === "PYTHON_VERTICAL_SLICE",
      ).map((entry) => entry.id),
    ).toEqual(["UI-02", "UI-03"]);
  });

  it("gives every screen an implementation batch and backend owner list", () => {
    for (const screen of FAMILY_SCREENS) {
      const migration = migrationForUi(screen.id);
      expect(migration?.batch).toBeTruthy();
      expect(migration?.backendCapabilities.length).toBeGreaterThan(0);
    }
  });

  it("presents UI-03 as a family-confirmed direction rather than a diagnosis", () => {
    const ui03 = FAMILY_SCREENS.find((screen) => screen.id === "UI-03");
    const entryCopy = JSON.stringify(ui03);

    expect(ui03).toMatchObject({
      title: "待确认的成长方向",
      primaryAction: "查看并共同确认",
    });
    expect(entryCopy).toContain("家庭共同选择");
    expect(entryCopy).toContain("可以不同意");
    expect(entryCopy).not.toMatch(
      /AI成长诊断|核心问题|综合评估|生成个性化方案/,
    );
    expect(familyScreenListSource).toContain("item.entryNote");
    expect(growthTabSource).toContain("家庭共同选择");
    expect(growthTabSource).not.toMatch(/AI成长诊断|核心问题/);
  });
});
