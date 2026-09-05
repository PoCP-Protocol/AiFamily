import { describe, expect, it } from "vitest";

import {
  ACTIVITY_UI_FUNCTIONAL_HIERARCHY,
  COMMERCE_UI_FUNCTIONAL_HIERARCHY,
  getActivityUiFunctionalHierarchy,
  getCommerceUiFunctionalHierarchy,
} from "../lib/family/ui-functional-hierarchy";

describe("commerce UI four-level functional hierarchy", () => {
  it("covers UI-13 through UI-18 exactly", () => {
    expect(Object.keys(COMMERCE_UI_FUNCTIONAL_HIERARCHY)).toEqual(["UI-13", "UI-14", "UI-15", "UI-16", "UI-17", "UI-18"]);
  });

  it("keeps frozen detail actions separate from real payment", () => {
    expect(getCommerceUiFunctionalHierarchy("UI-14")).toMatchObject({
      l2: ["5.1 商品目录", "5.2 下单意图"],
      capabilityState: "FROZEN",
      actionPolicy: "CONTROLLED_INTENT",
    });
  });

  it("keeps points mutation blocked and membership projection read-only", () => {
    expect(getCommerceUiFunctionalHierarchy("UI-17")).toMatchObject({ layoutMode: "BOUNDARY", actionPolicy: "NO_VALUE_MUTATION" });
    expect(getCommerceUiFunctionalHierarchy("UI-18")).toMatchObject({ layoutMode: "READ_ONLY", actionPolicy: "READ_ONLY" });
  });

  it("keeps adjacent activity screens in GROWTH instead of treating them as live SERVICE booking", () => {
    expect(Object.keys(ACTIVITY_UI_FUNCTIONAL_HIERARCHY)).toEqual(["UI-22", "UI-23"]);
    expect(getActivityUiFunctionalHierarchy("UI-22")).toMatchObject({ l1: "3 GROWTH 成长成果", actionPolicy: "NAVIGATE_ONLY" });
    expect(getActivityUiFunctionalHierarchy("UI-23")).toMatchObject({ capabilityState: "SYNTHETIC_ONLY", actionPolicy: "SAVE_PRIVATE_DRAFT" });
  });
});
