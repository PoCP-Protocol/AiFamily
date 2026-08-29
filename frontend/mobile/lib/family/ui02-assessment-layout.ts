import type { GrowthFocusId } from "./core-growth";
import { FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY } from "./family-assessment-capability-memory";

/**
 * UI-02 第 2/5 步的原图展示文案与排序。
 * 题目、测评理论与方法来源于家庭教育模型能力记忆，这里只做 App 基线呈现适配。
 */
export const UI02_ORIGINAL_FOCUS_LAYOUT: readonly {
  id: GrowthFocusId;
  title: string;
  subtitle: string;
  method: string;
}[] = FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.map((dimension) => ({
  id: dimension.focusId,
  title: dimension.title,
  subtitle: dimension.observableSignals.join("、"),
  method: dimension.operationalDefinition,
}));

export const UI02_ASSESSMENT_METHOD_SOURCE = {
  capabilityRef: FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.capabilityRef,
  version: FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.version,
  toolRef: FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.assessmentToolRef,
  theory: "家庭教育模型以维度记忆、题目记忆、证据锚点、实践模式和结果反馈构成免费家庭测评能力。",
  boundary: FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.boundary,
} as const;
