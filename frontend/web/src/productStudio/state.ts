import type {
  ProductStage,
  ProductStudioAction,
  ProductStudioState,
} from "./types";

export const PRODUCT_STAGE_ORDER: ProductStage[] = [
  "DEMAND",
  "MARKET_EVIDENCE",
  "PRODUCT_PACKAGE",
  "GATE",
  "PLM",
  "STOPPED",
];

function hasVerifiedEvidence(refs: ProductStudioState["demand"]["evidenceRefs"]): boolean {
  return refs.length > 0 && refs.every((evidence) => evidence.status === "VERIFIED");
}

export function canAdvance(state: ProductStudioState): boolean {
  switch (state.currentStage) {
    case "DEMAND":
      return hasVerifiedEvidence(state.demand.evidenceRefs);
    case "MARKET_EVIDENCE":
      return hasVerifiedEvidence(state.market.evidenceRefs) && hasVerifiedEvidence(state.market.competitorEvidence);
    case "PRODUCT_PACKAGE":
      return hasVerifiedEvidence(state.productPackage.evidenceRefs);
    case "GATE":
      return state.gate.decision !== null && state.gate.decision !== "NO_GO" && hasVerifiedEvidence(state.gate.evidenceRefs);
    case "PLM":
    case "STOPPED":
      return false;
  }
}

export function productStudioReducer(
  state: ProductStudioState,
  action: ProductStudioAction,
): ProductStudioState {
  switch (action.type) {
    case "SET_GATE_DECISION":
      if (state.currentStage !== "GATE") return state;
      return {
        ...state,
        currentStage: action.decision === "NO_GO" ? "STOPPED" : state.currentStage,
        gate: {
          ...state.gate,
          decision: action.decision,
          ...(action.decidedBy ? { decidedBy: action.decidedBy } : {}),
        },
      };
    case "SET_LIFECYCLE_RECOMMENDATION":
      if (state.currentStage !== "PLM") return state;
      return {
        ...state,
        plm: { ...state.plm, recommendation: action.recommendation },
      };
    case "ADVANCE_STAGE": {
      if (!canAdvance(state)) return state;
      const index = PRODUCT_STAGE_ORDER.indexOf(state.currentStage);
      return index < PRODUCT_STAGE_ORDER.length - 1
        ? { ...state, currentStage: PRODUCT_STAGE_ORDER[index + 1] }
        : state;
    }
  }
}
