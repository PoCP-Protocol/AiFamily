import type { GrowthFocusId } from "./core-growth";

export type JourneyPhaseId = "SEE" | "PARENT_FIRST" | "CO_CREATE" | "STABILIZE";

export interface MobileJourneyPhase {
  id: JourneyPhaseId;
  label: string;
  days: string;
  intent: string;
  smallAction: string;
}

export const MOBILE_JOURNEY_PHASES: readonly MobileJourneyPhase[] = [
  { id: "SEE", label: "看见与理解", days: "Day 1–14", intent: "先记录家庭场景，区分事实、感受和解释。", smallAction: "每天观察一个互动信号，不急着纠正。" },
  { id: "PARENT_FIRST", label: "家长先行动", days: "Day 15–35", intent: "从家长可以改变的表达和环境开始。", smallAction: "每周练习一个低剂量家长行动。" },
  { id: "CO_CREATE", label: "亲子共同练习", days: "Day 36–69", intent: "让孩子参与规则、目标和复盘。", smallAction: "用一次家庭小会共创一个可执行约定。" },
  { id: "STABILIZE", label: "稳定与复盘", days: "Day 70–90", intent: "保留适合家庭的做法，并允许暂停与恢复。", smallAction: "完成阶段回顾，家庭决定继续、调整或暂停。" },
] as const;

const FOCUS_ACTIONS: Record<GrowthFocusId, string> = {
  PARENT_CHILD_COMMUNICATION: "先听完孩子的一句话，再回应。",
  LEARNING_HABITS: "把一个学习任务缩小成十分钟能开始的第一步。",
  EMOTION_REGULATION: "先说出一个可能的感受，再邀请孩子修正。",
  SELF_REGULATION: "提供两个都可接受的选择，让孩子决定先做哪一步。",
  DEVICE_USE_CONTEXT: "共同确认一条所有家庭成员都执行的手机规则。",
};

export function getJourneyWeeklyAction(focus: GrowthFocusId | null) {
  return focus ? FOCUS_ACTIONS[focus] : "从一次完整倾听开始，观察家庭互动中的一个信号。";
}
