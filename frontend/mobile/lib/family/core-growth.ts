export type GrowthFocusId =
  | "PARENT_CHILD_COMMUNICATION"
  | "LEARNING_HABITS"
  | "EMOTION_REGULATION"
  | "SELF_REGULATION"
  | "DEVICE_USE_CONTEXT";

export type AssessmentAnswer = "often" | "sometimes" | "rarely" | "not_sure" | "OFTEN" | "SOMETIMES" | "RARELY" | "NOT_SURE";

export interface GrowthFocusDefinition {
  id: GrowthFocusId;
  title: string;
  subtitle: string;
  color: string;
  questions: readonly { id: string; text: string }[];
}

export const GROWTH_FOCUSES: readonly GrowthFocusDefinition[] = [
  {
    id: "PARENT_CHILD_COMMUNICATION",
    title: "亲子沟通",
    subtitle: "想减少争执，更多听见彼此",
    color: "#2563EB",
    questions: [
      { id: "communication-interrupt", text: "对话中，我们会很快打断或纠正对方。" },
      { id: "communication-escalate", text: "一个小问题容易升级成情绪冲突。" },
      { id: "communication-repair", text: "冲突后，我们不知道怎样重新开始。" },
    ],
  },
  {
    id: "LEARNING_HABITS",
    title: "学习习惯",
    subtitle: "希望把催促变成更可持续的节奏",
    color: "#16866D",
    questions: [
      { id: "learning-start", text: "开始学习常常需要家长反复提醒。" },
      { id: "learning-plan", text: "孩子很难把任务拆成可以开始的小步骤。" },
      { id: "learning-recover", text: "一次没完成后，容易放弃后续安排。" },
    ],
  },
  {
    id: "EMOTION_REGULATION",
    title: "情绪调节",
    subtitle: "先照顾情绪，再一起处理问题",
    color: "#F28C45",
    questions: [
      { id: "emotion-name", text: "情绪出现时，我们很难说清发生了什么。" },
      { id: "emotion-pause", text: "家长或孩子都很难在冲突中暂停一下。" },
      { id: "emotion-support", text: "我们不确定怎样回应对方的强烈情绪。" },
    ],
  },
  {
    id: "SELF_REGULATION",
    title: "自我管理",
    subtitle: "帮助孩子参与目标和生活安排",
    color: "#8B5CF6",
    questions: [
      { id: "self-choice", text: "孩子很少参与决定自己的下一步。" },
      { id: "self-routine", text: "生活安排经常依赖家长全程推动。" },
      { id: "self-reflect", text: "完成后，我们很少一起回看什么有帮助。" },
    ],
  },
  {
    id: "DEVICE_USE_CONTEXT",
    title: "手机与边界",
    subtitle: "建立清楚、可共同执行的家庭规则",
    color: "#00A8E8",
    questions: [
      { id: "device-rule", text: "家里还没有清楚一致的手机使用约定。" },
      { id: "device-conflict", text: "手机使用经常成为亲子冲突的起点。" },
      { id: "device-example", text: "大人和孩子执行的规则常常不一致。" },
    ],
  },
] as const;

export const ASSESSMENT_ANSWER_OPTIONS: readonly { id: AssessmentAnswer; label: string }[] = [
  { id: "often", label: "经常" },
  { id: "sometimes", label: "有时" },
  { id: "rarely", label: "很少" },
  { id: "not_sure", label: "不确定" },
] as const;

export function getGrowthFocus(id: GrowthFocusId | null) {
  return GROWTH_FOCUSES.find((item) => item.id === id) ?? null;
}

export function assessmentCompletion(focusId: GrowthFocusId | null, answers: Record<string, AssessmentAnswer>) {
  const focus = getGrowthFocus(focusId);
  if (!focus) return 0;
  return focus.questions.filter((question) => answers[question.id]).length / focus.questions.length;
}
