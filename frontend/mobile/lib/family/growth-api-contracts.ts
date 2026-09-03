/**
 * Mobile contracts for the Python growth/journey vertical slice.
 *
 * The Journey query/create/confirm/phase-review routes now exist in FastAPI.
 * Production persistence and identity/consent wiring remain fail-closed, so
 * route presence is not evidence that the capability is production-ready.
 */

export interface JourneyPlanProjection {
  plan: {
    plan_id: string;
    status: "DRAFT" | "ACTIVE" | "PAUSED" | "COMPLETED";
    current_phase: string;
    phases: { phase: string; status: "PENDING" | "ACTIVE" | "REVIEW_DUE" | "COMPLETED" | "BLOCKED" }[];
  } | null;
}

export interface PlanPreviewProjection {
  state?: "FAMILY_REVIEW" | "REVIEW_REQUIRED";
  structure: {
    horizon_days?: number;
    stages: { stage_id: string; small_action: string }[];
  };
  model_gateway_status?: "NOOP_NOT_INVOKED";
}

export interface GrowthPriorityProjection {
  draft?: {
    draft_id: string;
    decision: GrowthPriorityDecision;
    candidate: { profile_id: string; dimension_id: string; eligibility: "ELIGIBLE" } | null;
  };
  active_priority: { priority_id: string; dimension_id?: string; status?: "ACTIVE" } | null;
}

export interface ServiceJourneyProjection {
  projection_version: "UI05_SERVICE_JOURNEY_V1";
  tenant_id?: string;
  family_id: string;
  onboarding_id: string;
  locale?: string;
  content_locale?: string;
  consent_version?: string;
  region_id?: string;
  visibility: "FAMILY_PRIVATE";
  state: "READY" | "REVIEW_REQUIRED";
  process_summary: {
    label: string;
    completed_actions: number;
    /** Optional until the backend exposes a server-owned denominator. */
    total_actions?: number | null;
    boundary: "PROCESS_PROJECTION_NOT_SCORE_OR_OUTCOME";
  };
  /**
   * Optional server-owned task projection. The current Python route only
   * returns process_summary, so the UI must render an empty state until this
   * field is added to the API contract; it must never synthesize completion.
   */
  weekly_tasks?: {
    task_id: string;
    title: string;
    status: "PENDING" | "IN_PROGRESS" | "COMPLETED" | "PAUSED" | "CANCELLED";
    visibility: "FAMILY_PRIVATE";
  }[];
  source_plan_id: string | null;
  current_phase: string | null;
  boundary: "SERVICE_JOURNEY_IS_PRIVATE_PROCESS_SUPPORT_NOT_GROWTH_OUTCOME";
}

export interface Ui09TodayAction {
  task_id: string;
  journey_plan_id?: string | null;
  journey_phase?: string | null;
  day_index?: number;
  assignment_text: string;
  task_state: "NOT_STARTED" | "IN_PROGRESS" | "PAUSED" | "CHECKED_IN" | "PARTIAL" | "NOT_COMPLETED" | "CANCELLED";
  execution_status: "NOT_STARTED" | "IN_PROGRESS" | "PAUSED" | "COMPLETED" | "PARTIAL" | "NOT_COMPLETED" | "CANCELLED";
  checkin_allowed: boolean;
  allowed_actions: ("START" | "PAUSE" | "RESUME" | "CANCEL")[];
  task_version: number;
}

export interface Ui09TodayProjection {
  tenant_id?: string;
  entry_state: "READY" | "EMPTY";
  locale?: string;
  content_locale?: string;
  consent_version?: string;
  region_id?: string;
  today_task: Ui09TodayAction | null;
  today_tasks: Ui09TodayAction[];
}

export interface Ui09TaskReceipt {
  action: Ui09TodayAction;
  result_state: "SUCCESS" | "REPLAYED";
}

export type GrowthPriorityDecision = "P03" | "R03" | "R04" | "R05" | "NO_PRIORITY_YET";

export type JourneyPhaseDecision = "CONTINUE" | "ADJUST" | "PAUSE" | "HUMAN_REVIEW_REQUIRED";
