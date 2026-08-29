export type KnowledgeKind = "fact" | "perspective" | "recommendation" | "action";

export type ModelGatewayStatus = "not_invoked" | "rule_based" | "draft_only";

export interface FamilyKnowledgeItem {
  id: string;
  kind: KnowledgeKind;
  label: string;
  content: string;
  sourceType: "family_input" | "course_method" | "system_rule" | "service_record";
  evidenceBoundary: string;
  modelGatewayStatus: ModelGatewayStatus;
  updatedAt: string;
}

export interface TodayAction {
  id: string;
  title: string;
  reason: string;
  estimatedMinutes: number;
  suggestedWords: string;
  observationPrompt: string;
  status: "not_started" | "in_progress" | "checked_in" | "skipped";
  recommendationSource: "rule_based_dev" | "reviewed_course";
}
