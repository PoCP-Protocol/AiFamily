import { describe, expect, it } from "vitest";

import { FAMILY_SCREENS } from "../lib/family/ui-registry";
import {
  UI_MIGRATION_REGISTRY,
  assertCompleteUiMigrationRegistry,
  migrationForUi,
} from "../lib/family/ui-migration-registry";

describe("UI-01 through UI-34 migration registry", () => {
  it("covers every preserved Mobile baseline exactly once", () => {
    expect(() => assertCompleteUiMigrationRegistry()).not.toThrow();
    expect(UI_MIGRATION_REGISTRY).toHaveLength(34);
    expect(FAMILY_SCREENS).toHaveLength(34);
  });

  it("marks only the callable assessment chain as a Python vertical slice", () => {
    expect(UI_MIGRATION_REGISTRY.filter((entry) => entry.status === "PYTHON_VERTICAL_SLICE").map((entry) => entry.id)).toEqual([
      "UI-02",
      "UI-03",
    ]);
  });

  it("gives every screen an implementation batch and backend owner list", () => {
    for (const screen of FAMILY_SCREENS) {
      const migration = migrationForUi(screen.id);
      expect(migration?.batch).toBeTruthy();
      expect(migration?.backendCapabilities.length).toBeGreaterThan(0);
    }
  });
});
