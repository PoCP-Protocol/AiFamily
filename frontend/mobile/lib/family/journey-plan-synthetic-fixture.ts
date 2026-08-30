import type { JourneyPlanProjectionDto } from "./journey-plan-contract";

/** Explicit dev-only fixture. It must never be enabled for a connected/production build. */
export const SYNTHETIC_JOURNEY_ENABLED = process.env.EXPO_PUBLIC_FAMILY_JOURNEY_SYNTHETIC === "true";

export const SYNTHETIC_JOURNEY_PROJECTION: JourneyPlanProjectionDto = {
  plan: {
    plan_id: "synthetic-journey-plan-21d",
    status: "ACTIVE",
    current_phase: "SEE",
    phases: [
      { phase: "SEE", status: "REVIEW_DUE" },
      { phase: "PARENT_FIRST", status: "PENDING" },
      { phase: "CO_CREATE", status: "PENDING" },
    ],
  },
};

export const SYNTHETIC_JOURNEY_PREVIEW = {
  structure: {
    stages: [
      { stage_id: "SEE", small_action: "从互相催促，转为先说出当下发生了什么。" },
      { stage_id: "PARENT_FIRST", small_action: "从单方面要求，转为一起选择下一步。" },
      { stage_id: "CO_CREATE", small_action: "从争执循环，转为说清发生了什么并重新约定。" },
    ],
  },
} as const;
