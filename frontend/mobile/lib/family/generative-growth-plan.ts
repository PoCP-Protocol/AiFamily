export type GrowthPlanResultStatus = "PLAN_DRAFT" | "NEEDS_MORE_INFORMATION";

export interface GrowthPlanPractice {
  practice_id: string;
  description: string;
  actor: "ADULT" | "FAMILY" | "CHILD_OPTIONAL";
  cadence: string;
  effort: string;
  stop_condition: string;
  repair_option: string;
}

export interface GrowthPlanStage {
  stage_id: string;
  title: string;
  purpose: string;
  practices: GrowthPlanPractice[];
  child_participation_mode: "ADULT_ONLY" | "OPTIONAL" | "ASSENT_REQUIRED";
  signals: { signal_type: "OUTCOME" | "PROTECTION" | "ADAPT" | "STOP"; description: string }[];
  reflection_question: string;
  evidence_refs: string[];
  knowledge_refs: string[];
}

export interface GrowthPlanChoice {
  choice_id: string;
  question: string;
  options: string[];
  target_stage_ids: string[];
}

export interface GenerativeGrowthPlanDraft {
  result_status: "PLAN_DRAFT";
  draft_ref: string;
  draft_version: number;
  title: string;
  family_goal: { statement: string; observable_signs: string[]; evidence_refs: string[] };
  why_this_plan: string;
  duration: { days: number; rationale: string };
  stages: GrowthPlanStage[];
  adjustable_choices: GrowthPlanChoice[];
  unknowns_to_watch: string[];
  review_rhythm: { frequency: string; questions: string[] };
  limitations: string[];
  generated_at?: string;
}

export interface AdoptedGenerativeGrowthPlan {
  plan_id: string;
  tenant_id: string;
  family_id: string;
  subject_refs: string[];
  draft_ref: string;
  draft_version: number;
  model_run_ref: string;
  provenance_ref: string;
  content_sha256: string;
  title: string;
  family_goal: GenerativeGrowthPlanDraft["family_goal"];
  why_this_plan: string;
  duration: GenerativeGrowthPlanDraft["duration"];
  stages: GrowthPlanStage[];
  adjustable_choices: GrowthPlanChoice[];
  selected_choices: Record<string, string>;
  unknowns_to_watch: string[];
  review_rhythm: GenerativeGrowthPlanDraft["review_rhythm"];
  limitations: string[];
  status: "ACTIVE";
  adopted_by: string;
  adopted_at: string;
  boundary: string;
}

export interface GrowthPlanInformationNeeded {
  result_status: "NEEDS_MORE_INFORMATION";
  information_needed: string[];
  known_context_summary: string;
  limitations: string[];
}

export type GenerativeGrowthPlan =
  | GenerativeGrowthPlanDraft
  | GrowthPlanInformationNeeded
  | AdoptedGenerativeGrowthPlan;

export interface GenerativeGrowthPlanResponse {
  family_id?: string;
  plan: GenerativeGrowthPlan | null;
  created?: boolean;
  idempotency_replayed?: boolean;
  named_action?: string;
}

export function isAdoptedGrowthPlan(
  plan: GenerativeGrowthPlan | null,
): plan is AdoptedGenerativeGrowthPlan {
  return plan !== null && "status" in plan && plan.status === "ACTIVE";
}

export function isGrowthPlanDraft(
  plan: GenerativeGrowthPlan | null,
): plan is GenerativeGrowthPlanDraft {
  return plan !== null && "result_status" in plan && plan.result_status === "PLAN_DRAFT";
}

export function isGrowthPlanInformationNeeded(
  plan: GenerativeGrowthPlan | null,
): plan is GrowthPlanInformationNeeded {
  return (
    plan !== null &&
    "result_status" in plan &&
    plan.result_status === "NEEDS_MORE_INFORMATION"
  );
}
