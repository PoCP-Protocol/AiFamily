export type ProductStage = "DEMAND" | "MARKET_EVIDENCE" | "PRODUCT_PACKAGE" | "GATE" | "PLM" | "STOPPED";

export type GateDecision = "GO" | "NO_GO" | "CONDITIONAL";
export type LifecycleRecommendation = "SCALE" | "REVISE" | "KILL";
export type EvidenceStatus = "VERIFIED" | "UNKNOWN" | "STALE" | "CONTRADICTED";

export type EvidenceRef = {
  ref: string;
  label: string;
  kind: "demand" | "market" | "competitor" | "experiment" | "pilot";
  status: EvidenceStatus;
};

export type DraftArtifact = {
  id: string;
  title: string;
  summary: string;
  evidenceRefs: EvidenceRef[];
  status: "DRAFT";
  provenanceRef?: string;
};

export type ProductZone = "HOMOGENEOUS" | "ADVANTAGE" | "EXCLUSIVE_CANDIDATE";

export type ProductStudioState = {
  currentStage: ProductStage;
  demand: DraftArtifact;
  market: DraftArtifact & { competitorEvidence: EvidenceRef[] };
  productPackage: DraftArtifact & { zone: ProductZone; durationDays: 21 | 90 };
  gate: {
    decision: GateDecision | null;
    evidenceRefs: EvidenceRef[];
    decidedBy?: string;
  };
  plm: {
    recommendation: LifecycleRecommendation | null;
    evidenceRefs: EvidenceRef[];
  };
};

export type ProductStudioAction =
  | { type: "ADVANCE_STAGE" }
  | { type: "SET_GATE_DECISION"; decision: GateDecision; decidedBy?: string }
  | { type: "SET_LIFECYCLE_RECOMMENDATION"; recommendation: LifecycleRecommendation };
