import type { GrowthFocusId } from "./core-growth";
import {
  FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY,
  type FamilyAssessmentDimensionMemory,
} from "./family-assessment-capability-memory";

export type AssessmentDimensionObservation = {
  item_ref: string;
  response_value: string | boolean;
};

export type AssessmentDimensionProfile = {
  focusId: GrowthFocusId;
  title: string;
  signals: readonly string[];
  operationalDefinition: string;
  supportDirection: string;
  statusLabel: string;
  statusTone: "quiet" | "watch" | "focus" | "unknown";
  signalValue: number;
  explored: boolean;
  deepAnsweredCount: number;
};

export type AssessmentKnowledgeBrief = {
  title: string;
  familyLens: string;
  evidence: string;
  practiceThemes: readonly string[];
};

const SIGNAL_VALUES: Record<string, number> = {
  OFTEN: 0.88,
  SOMETIMES: 0.64,
  RARELY: 0.34,
};

function profileForDimension(
  dimension: FamilyAssessmentDimensionMemory,
  observationsByRef: Map<string, string | boolean>,
  activeFocus: GrowthFocusId | null,
): AssessmentDimensionProfile {
  const overviewRef = dimension.questions[0]?.itemRef;
  const rawOverviewAnswer = overviewRef
    ? observationsByRef.get(overviewRef)
    : undefined;
  const overviewAnswer =
    typeof rawOverviewAnswer === "string"
      ? rawOverviewAnswer.toUpperCase()
      : rawOverviewAnswer;
  const deepAnsweredCount = dimension.questions
    .slice(1)
    .filter((question) => observationsByRef.has(question.itemRef)).length;
  const explored =
    typeof overviewAnswer === "string" && overviewAnswer !== "NOT_SURE";
  const isUnknown = overviewAnswer === "NOT_SURE" || overviewAnswer === undefined;

  let statusLabel = "待了解";
  let statusTone: AssessmentDimensionProfile["statusTone"] = "unknown";
  let signalValue = 0.16;
  if (overviewAnswer === "OFTEN") {
    statusLabel = "值得先看";
    statusTone = "focus";
    signalValue = SIGNAL_VALUES.OFTEN;
  } else if (overviewAnswer === "SOMETIMES") {
    statusLabel = "正在观察";
    statusTone = "watch";
    signalValue = SIGNAL_VALUES.SOMETIMES;
  } else if (overviewAnswer === "RARELY") {
    statusLabel = "已有基础";
    statusTone = "quiet";
    signalValue = SIGNAL_VALUES.RARELY;
  } else if (isUnknown) {
    statusLabel = overviewAnswer === "NOT_SURE" ? "信息还不够" : "待了解";
  }

  if (activeFocus === dimension.focusId && explored && deepAnsweredCount > 0) {
    statusLabel = `${statusLabel} · 已深入 ${deepAnsweredCount} 题`;
  }

  return {
    focusId: dimension.focusId,
    title: dimension.title,
    signals: dimension.observableSignals,
    operationalDefinition: dimension.operationalDefinition,
    supportDirection: dimension.nextSupportDirections[0] ?? "从家庭日常继续观察",
    statusLabel,
    statusTone,
    signalValue,
    explored,
    deepAnsweredCount,
  };
}

export function buildAssessmentDimensionProfiles(
  observations: readonly AssessmentDimensionObservation[],
  activeFocus: GrowthFocusId | null,
): readonly AssessmentDimensionProfile[] {
  const observationsByRef = new Map(
    observations.map((observation) => [
      observation.item_ref,
      observation.response_value,
    ]),
  );
  return FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.map((dimension) =>
    profileForDimension(dimension, observationsByRef, activeFocus),
  );
}

export function assessmentDimensionCaption(
  profiles: readonly AssessmentDimensionProfile[],
) {
  const exploredCount = profiles.filter((profile) => profile.explored).length;
  if (exploredCount === profiles.length) {
    return "五个方向都已有回答；最关心的方向还展开看得更深。";
  }
  if (exploredCount === 0) {
    return "先从五个方向认识家庭日常，回答多少就看见多少。";
  }
  return `已看见 ${exploredCount} 个方向，其余方向留到以后慢慢了解。`;
}

/**
 * Turn the compiled knowledge snapshot into language that can be shown to a
 * parent. This is a reference layer, not a diagnosis engine: it explains why
 * a direction is worth exploring and keeps the original evidence trail close
 * to the recommendation.
 */
export function getAssessmentKnowledgeBrief(
  focusId: GrowthFocusId | null,
): AssessmentKnowledgeBrief | null {
  const dimension = FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.find(
    (item) => item.focusId === focusId,
  );
  if (!dimension) return null;
  return {
    title: dimension.title,
    familyLens:
      dimension.familyTheorySupport[0] ??
      "先看家庭互动与环境，再决定是否需要更多支持。",
    evidence:
      dimension.theorySupport[0] ??
      "这是一条家庭教育实践参考，不是对孩子的结论。",
    practiceThemes: dimension.nextSupportDirections.slice(0, 3),
  };
}
