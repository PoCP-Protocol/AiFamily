import type { AssessmentAnswer, GrowthFocusId } from "./core-growth";

export interface LocalGrowthExplanation {
  focus: GrowthFocusId;
  headline: string;
  summary: string;
  hypothesis: string;
  recommendation: string;
  fallback: string;
  observationPrompt: string;
}

const EXPLANATIONS: Record<GrowthFocusId, LocalGrowthExplanation> = {
  PARENT_CHILD_COMMUNICATION: {
    focus: "PARENT_CHILD_COMMUNICATION",
    headline: "先让对话继续，再一起找办法",
    summary: "你选择先关注亲子沟通。当前答案只代表家长最近两周的观察，不等同于孩子的固定特点。",
    hypothesis: "一个可能的方向是：家庭很想尽快解决问题，因此回应常常早于完整倾听。",
    recommendation: "本周先练习一次“听完一句话再回应”，把解决问题放到连接之后。",
    fallback: "如果当下情绪很强，只说“我需要一分钟，等会儿再听你说”。",
    observationPrompt: "孩子说完后，语气、身体状态或愿意继续说的程度有什么变化？",
  },
  LEARNING_HABITS: {
    focus: "LEARNING_HABITS",
    headline: "把催促变成可以开始的第一小步",
    summary: "你选择先关注学习习惯。这里记录的是家庭场景，而不是孩子能力或学习结果。",
    hypothesis: "一个可能的方向是：任务太大或开始条件不清楚，让家长和孩子都依赖反复提醒。",
    recommendation: "本周只选择一个任务，和孩子一起把它缩小成十分钟可以开始的第一步。",
    fallback: "如果孩子暂时不愿开始，先讨论“哪一步最难”，不立即增加要求。",
    observationPrompt: "任务变小后，孩子是否更容易说出下一步或开始行动？",
  },
  EMOTION_REGULATION: {
    focus: "EMOTION_REGULATION",
    headline: "先照顾情绪，再讨论该怎么办",
    summary: "你选择先关注情绪调节。情绪反应是场景中的体验，不构成医学或心理诊断。",
    hypothesis: "一个可能的方向是：双方都很在意问题，但强烈情绪让彼此暂时听不见真正的需要。",
    recommendation: "本周练习一次情绪命名，并允许对方修正你的猜测。",
    fallback: "如果无法继续对话，约定一个明确的重新开始时间。",
    observationPrompt: "当感受被说出来后，对话是否更容易继续？",
  },
  SELF_REGULATION: {
    focus: "SELF_REGULATION",
    headline: "把安排变成孩子可以参与的选择",
    summary: "你选择先关注自我管理。当前内容不评价孩子是否自律，只关注家庭如何共同设计下一步。",
    hypothesis: "一个可能的方向是：家长承担了大部分计划工作，孩子参与目标和复盘的机会较少。",
    recommendation: "本周选择一件小事，提供两个都可接受的选择，让孩子决定先做哪一步。",
    fallback: "如果孩子不选择，家长可以先示范一次，再邀请下次参与。",
    observationPrompt: "当孩子拥有有限选择时，开始行动是否更顺利？",
  },
  DEVICE_USE_CONTEXT: {
    focus: "DEVICE_USE_CONTEXT",
    headline: "从共同规则开始，而不是只盯着屏幕时间",
    summary: "你选择先关注手机与边界。手机冲突常与家庭规则、示范和当下需要有关，不能单独推导孩子问题。",
    hypothesis: "一个可能的方向是：规则还不够清楚或大人与孩子执行不一致，使每次使用都需要重新谈判。",
    recommendation: "本周只共同确认一个可执行规则，并由所有家庭成员一起遵守。",
    fallback: "如果规则讨论升级为争执，先暂停，记录双方最关心的一个点。",
    observationPrompt: "规则更清楚后，临时提醒和争执是否减少？",
  },
};

export function getLocalGrowthExplanation(focus: GrowthFocusId | null) {
  return focus ? EXPLANATIONS[focus] : null;
}

export function summarizeAssessmentPerspective(answers: Record<string, AssessmentAnswer>) {
  const values = Object.values(answers);
  const often = values.filter((answer) => answer === "often").length;
  const sometimes = values.filter((answer) => answer === "sometimes").length;
  const uncertain = values.filter((answer) => answer === "not_sure").length;
  if (uncertain > 0) return `有 ${uncertain} 个场景你选择了“不确定”，保留观察比急着下结论更重要。`;
  if (often > 0) return `有 ${often} 个场景最近经常出现，适合先从一个低负担行动开始。`;
  if (sometimes > 0) return `这些场景偶尔出现，可以用一周时间观察什么情况下更容易发生。`;
  return "这些场景最近较少出现，可以把当前有效做法记录下来。";
}
