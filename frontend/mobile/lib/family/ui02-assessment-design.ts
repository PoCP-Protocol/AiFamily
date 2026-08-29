import type { GrowthFocusId } from "./core-growth";
import { FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY, getFamilyAssessmentMemoryQuestions } from "./family-assessment-capability-memory";

export type Ui02AssessmentAnswer = "OFTEN" | "SOMETIMES" | "RARELY" | "NOT_SURE";

export type Ui02AssessmentQuestion = {
  itemRef: string;
  text: string;
  intent: string;
  evidenceAnchor: string;
};

export const UI02_ASSESSMENT_VERSION = "FAMILY_SUPPORT_NEEDS/v2";

export const UI02_ASSESSMENT_ANSWER_OPTIONS = FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.answerOptions;

export const UI02_DEEP_ASSESSMENT_QUESTIONS = Object.fromEntries(
  FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.map((dimension) => [dimension.focusId, dimension.questions]),
) as Record<GrowthFocusId, readonly Ui02AssessmentQuestion[]>;

export const UI02_DEEP_ASSESSMENT_ITEM_REFS = Object.values(UI02_DEEP_ASSESSMENT_QUESTIONS).flatMap((questions) => questions.map((question) => question.itemRef));

export function getUi02DeepAssessmentQuestions(focusId: GrowthFocusId | null) {
  return getFamilyAssessmentMemoryQuestions(focusId);
}

export function buildUi02AssessmentResultSummary(focusId: GrowthFocusId | null, answers: Record<string, string | undefined>) {
  const dimension = FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.find((item) => item.focusId === focusId) ?? null;
  if (!dimension) return null;
  const answeredItems = dimension.questions
    .map((question) => ({ question, answer: answers[question.itemRef] }))
    .filter((item) => item.answer);
  const prioritySignals = answeredItems
    .filter((item) => item.answer === "OFTEN" || item.answer === "SOMETIMES")
    .map((item) => item.question.text);
  const observationSignals = prioritySignals.length > 0 ? prioritySignals : dimension.observableSignals;
  return {
    title: dimension.title,
    operationalDefinition: dimension.operationalDefinition,
    answeredCount: answeredItems.length,
    totalCount: dimension.questions.length,
    observationSignals,
    supportDirections: dimension.nextSupportDirections,
    theorySupport: dimension.theorySupport,
    familyTheorySupport: dimension.familyTheorySupport,
    dataSupport: dimension.dataSupport,
    practiceSupport: dimension.practiceSupport,
    boundary: dimension.boundary,
    platformIntegration: FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.platformIntegration,
  };
}
