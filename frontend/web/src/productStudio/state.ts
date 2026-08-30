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
];

export function canAdvance(state: ProductStudioState): boolean {
  switch (state.currentStage) {
    case "DEMAND":
      return state.demand.evidenceRefs.length > 0;
    case "MARKET_EVIDENCE":
      return state.market.evidenceRefs.length > 0 && state.market.competitorEvidence.length > 0;
    case "PRODUCT_PACKAGE":
      return state.productPackage.evidenceRefs.length > 0;
    case "GATE":
      return state.gate.decision !== null && state.gate.evidenceRefs.length > 0;
    case "PLM":
      return false;
  }
}

export function productStudioReducer(
  state: ProductStudioState,
  action: ProductStudioAction,
): ProductStudioState {
  switch (action.type) {
    case "SET_GATE_DECISION":
      return {
        ...state,
        gate: {
          ...state.gate,
          decision: action.decision,
          ...(action.decidedBy ? { decidedBy: action.decidedBy } : {}),
        },
      };
    case "SET_LIFECYCLE_RECOMMENDATION":
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

