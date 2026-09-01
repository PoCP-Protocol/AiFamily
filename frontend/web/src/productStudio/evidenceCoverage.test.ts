import { describe, expect, it } from "vitest";
import type { OpportunityLineage } from "./decisionApi";
import { deriveEvidenceCoverage } from "./evidenceCoverage";

const lineage = {
  market_signal: { evidence_refs: ["evidence:signal"] },
  customer_insight: { evidence_refs: [] },
  opportunity: null,
  completeness: "INCOMPLETE_UPSTREAM",
} as unknown as OpportunityLineage;

describe("deriveEvidenceCoverage", () => {
  it("reports discrete reference coverage without inferring verification", () => {
    expect(deriveEvidenceCoverage(lineage)).toEqual({
      source: "WEB_DERIVED_FROM_CHAIN",
      structure: "INCOMPLETE_UPSTREAM",
      verification: "UNKNOWN_NOT_IN_CONTRACT",
      nodes: [
        { node: "MarketSignal", status: "PRESENT_WITH_REFS", reason_code: null },
        { node: "CustomerInsight", status: "PRESENT_WITHOUT_REFS", reason_code: "WEB_REFERENCE_COVERAGE_CUSTOMER_INSIGHT_EVIDENCE_REFS_EMPTY" },
        { node: "Opportunity", status: "NOT_RETURNED", reason_code: "WEB_REFERENCE_COVERAGE_OPPORTUNITY_NOT_RETURNED" },
      ],
    });
  });

  it("keeps verification unknown even when every node has references", () => {
    const complete = {
      ...lineage,
      market_signal: { evidence_refs: ["evidence:signal"] },
      customer_insight: { evidence_refs: ["evidence:insight"] },
      opportunity: { evidence_refs: ["evidence:opportunity"] },
      completeness: "STRUCTURALLY_COMPLETE_TO_OPPORTUNITY",
    } as unknown as OpportunityLineage;
    const result = deriveEvidenceCoverage(complete);
    expect(result.nodes.every(({ status }) => status === "PRESENT_WITH_REFS")).toBe(true);
    expect(result.verification).toBe("UNKNOWN_NOT_IN_CONTRACT");
    expect(JSON.stringify(result)).not.toMatch(/ADMITTED|VERIFIED|READY|SCORE|RANK/);
  });
});
