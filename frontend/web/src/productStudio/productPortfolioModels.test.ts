import { describe, expect, it } from "vitest";
import { ProductStudioApiError } from "./api";
import { sampleCatalogSnapshot } from "./productPortfolioFixtures";
import { validateCatalogSnapshot } from "./productPortfolioModels";

describe("versioned product catalog contract", () => {
  it("accepts receipt-backed server selection states without deriving eligibility", () => {
    const snapshot = validateCatalogSnapshot(sampleCatalogSnapshot);
    expect(snapshot.items[0].server_selection_state).toBe("REUSABLE");
    expect(snapshot.items[2].server_selection_state).toBe("NOT_APPLICABLE");
  });

  it("turns malformed unknown input into a governed response error", () => {
    expect(() => validateCatalogSnapshot({ schema_version: "1.0", items: [null] })).toThrow(ProductStudioApiError);
  });

  it("fails closed when a component dependency is absent", () => {
    const invalid = {
      ...sampleCatalogSnapshot,
      items: sampleCatalogSnapshot.items.filter((item) => item.item_kind !== "SKILL"),
    };
    expect(() => validateCatalogSnapshot(invalid)).toThrow(ProductStudioApiError);
  });

  it("fails closed when allowed and forbidden tools overlap", () => {
    const first = sampleCatalogSnapshot.items[0];
    const invalid = {
      ...sampleCatalogSnapshot,
      items: [{ ...first, forbidden_tools: [...first.forbidden_tools, first.allowed_tools[0]] }, ...sampleCatalogSnapshot.items.slice(1)],
    };
    expect(() => validateCatalogSnapshot(invalid)).toThrow(/允许与禁止工具/);
  });

  it("requires a reason code for every non-applicable server projection", () => {
    const invalid = {
      ...sampleCatalogSnapshot,
      items: sampleCatalogSnapshot.items.map((item, index) => index === 2 ? { ...item, reason_codes: [] } : item),
    };
    expect(() => validateCatalogSnapshot(invalid)).toThrow(/reason code/);
  });

  it("rejects a reusable item backed by a blocked receipt", () => {
    const first = sampleCatalogSnapshot.items[0];
    const invalid = {
      ...sampleCatalogSnapshot,
      items: [{ ...first, admission_receipts: [{ ...first.admission_receipts[0], outcome: "BLOCKED" }] }, ...sampleCatalogSnapshot.items.slice(1)],
    };
    expect(() => validateCatalogSnapshot(invalid)).toThrow(/admission receipt/);
  });

  it("rejects a reusable component whose required skill is not reusable", () => {
    const invalid = {
      ...sampleCatalogSnapshot,
      items: sampleCatalogSnapshot.items.map((item) => item.item_kind === "SKILL"
        ? { ...item, server_selection_state: "REVIEW_REQUIRED", reason_codes: ["HUMAN_REVIEW_REQUIRED"] }
        : item),
    };
    expect(() => validateCatalogSnapshot(invalid)).toThrow(/不可复用的 Skill/);
  });
});
