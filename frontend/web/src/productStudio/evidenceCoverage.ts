import type { OpportunityLineage } from "./decisionApi";

export type ReferenceCoverageStatus =
  | "NOT_RETURNED"
  | "PRESENT_WITHOUT_REFS"
  | "PRESENT_WITH_REFS";

export type EvidenceCoverageNode = {
  node: "MarketSignal" | "CustomerInsight" | "Opportunity";
  status: ReferenceCoverageStatus;
  reason_code: string | null;
};

export type EvidenceCoverage = {
  source: "WEB_DERIVED_FROM_CHAIN";
  structure: OpportunityLineage["completeness"];
  verification: "UNKNOWN_NOT_IN_CONTRACT";
  nodes: EvidenceCoverageNode[];
};

function nodeCoverage(
  node: EvidenceCoverageNode["node"],
  codePrefix: string,
  record: { evidence_refs: string[] } | null,
): EvidenceCoverageNode {
  if (!record) return { node, status: "NOT_RETURNED", reason_code: `${codePrefix}_NOT_RETURNED` };
  if (record.evidence_refs.length === 0) {
    return { node, status: "PRESENT_WITHOUT_REFS", reason_code: `${codePrefix}_EVIDENCE_REFS_EMPTY` };
  }
  return { node, status: "PRESENT_WITH_REFS", reason_code: null };
}

export function deriveEvidenceCoverage(lineage: OpportunityLineage): EvidenceCoverage {
  return {
    source: "WEB_DERIVED_FROM_CHAIN",
    structure: lineage.completeness,
    verification: "UNKNOWN_NOT_IN_CONTRACT",
    nodes: [
      nodeCoverage("MarketSignal", "WEB_REFERENCE_COVERAGE_MARKET_SIGNAL", lineage.market_signal),
      nodeCoverage("CustomerInsight", "WEB_REFERENCE_COVERAGE_CUSTOMER_INSIGHT", lineage.customer_insight),
      nodeCoverage("Opportunity", "WEB_REFERENCE_COVERAGE_OPPORTUNITY", lineage.opportunity),
    ],
  };
}
