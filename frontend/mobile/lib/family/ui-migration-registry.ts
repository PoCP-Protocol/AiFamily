import { FAMILY_SCREENS } from "./ui-registry";

export type UiMigrationStatus =
  | "PYTHON_VERTICAL_SLICE"
  | "PYTHON_API_PARTIAL"
  | "MOBILE_BASELINE_ONLY";

export type UiMigrationBatch =
  | "FOUNDATION"
  | "ASSESSMENT"
  | "JOURNEY_ACTION"
  | "COMMERCE"
  | "SERVICE"
  | "COMMUNITY"
  | "ASSETS_PROFILE";

export interface UiMigrationDefinition {
  id: `UI-${string}`;
  batch: UiMigrationBatch;
  status: UiMigrationStatus;
  backendCapabilities: string[];
}

/**
 * Executable scope for the UI-01 -> UI-34 migration.
 *
 * A screen being present in the app is not evidence that its Python backend is
 * ready. Statuses deliberately separate the preserved Mobile baseline from a
 * callable vertical slice.
 */
export const UI_MIGRATION_REGISTRY: UiMigrationDefinition[] = [
  { id: "UI-01", batch: "FOUNDATION", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["family_home_projection"] },
  { id: "UI-02", batch: "ASSESSMENT", status: "PYTHON_VERTICAL_SLICE", backendCapabilities: ["identity_context", "consent_gate", "assessment"] },
  { id: "UI-03", batch: "ASSESSMENT", status: "PYTHON_VERTICAL_SLICE", backendCapabilities: ["assessment", "model_gateway", "growth_intent"] },
  { id: "UI-04", batch: "JOURNEY_ACTION", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["journey_plan"] },
  { id: "UI-05", batch: "JOURNEY_ACTION", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["journey", "phase_review"] },
  { id: "UI-06", batch: "COMMERCE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["membership", "entitlement"] },
  { id: "UI-07", batch: "ASSESSMENT", status: "PYTHON_API_PARTIAL", backendCapabilities: ["assessment_catalog", "consent"] },
  { id: "UI-08", batch: "JOURNEY_ACTION", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["outcome_review"] },
  { id: "UI-09", batch: "JOURNEY_ACTION", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["growth_action", "check_in"] },
  { id: "UI-10", batch: "JOURNEY_ACTION", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["child_action_projection"] },
  { id: "UI-11", batch: "JOURNEY_ACTION", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["family_rhythm_projection"] },
  { id: "UI-12", batch: "COMMUNITY", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["private_growth_story"] },
  { id: "UI-13", batch: "COMMERCE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["catalog"] },
  { id: "UI-14", batch: "COMMERCE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["product", "order_intent"] },
  { id: "UI-15", batch: "COMMERCE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["invite_draft"] },
  { id: "UI-16", batch: "COMMERCE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["participation_intent"] },
  { id: "UI-17", batch: "COMMERCE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["points_ledger"] },
  { id: "UI-18", batch: "COMMERCE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["membership", "entitlement"] },
  { id: "UI-19", batch: "SERVICE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["service_provider", "service_offering"] },
  { id: "UI-20", batch: "SERVICE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["service_provider", "availability_slot"] },
  { id: "UI-21", batch: "SERVICE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["booking_request", "consent"] },
  { id: "UI-22", batch: "SERVICE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["service_activity_catalog"] },
  { id: "UI-23", batch: "SERVICE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["service_activity"] },
  { id: "UI-24", batch: "SERVICE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["booking_projection", "service_record"] },
  { id: "UI-25", batch: "COMMUNITY", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["moderated_family_feed"] },
  { id: "UI-26", batch: "COMMUNITY", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["private_post_draft"] },
  { id: "UI-27", batch: "COMMUNITY", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["family_post_detail"] },
  { id: "UI-28", batch: "COMMUNITY", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["family_private_posts"] },
  { id: "UI-29", batch: "ASSETS_PROFILE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["outcome_evidence"] },
  { id: "UI-30", batch: "COMMERCE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["membership", "annual_entitlement"] },
  { id: "UI-31", batch: "SERVICE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["service_customer_projection"] },
  { id: "UI-32", batch: "ASSETS_PROFILE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["order", "family_asset"] },
  { id: "UI-33", batch: "ASSETS_PROFILE", status: "MOBILE_BASELINE_ONLY", backendCapabilities: ["family_core", "consent"] },
  { id: "UI-34", batch: "SERVICE", status: "PYTHON_API_PARTIAL", backendCapabilities: ["service_record"] },
];

export function migrationForUi(id: string) {
  return UI_MIGRATION_REGISTRY.find((entry) => entry.id === id);
}

export function assertCompleteUiMigrationRegistry() {
  const screenIds = FAMILY_SCREENS.map((screen) => screen.id).sort();
  const migrationIds = UI_MIGRATION_REGISTRY.map((entry) => entry.id).sort();
  if (new Set(migrationIds).size !== migrationIds.length) {
    throw new Error("UI migration registry contains duplicate screen ids");
  }
  if (JSON.stringify(screenIds) !== JSON.stringify(migrationIds)) {
    throw new Error("UI migration registry must cover exactly UI-01 through UI-34");
  }
}
