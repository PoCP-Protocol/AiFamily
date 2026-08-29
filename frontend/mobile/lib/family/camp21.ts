export interface Camp21Day {
  day: number;
  stage: "观察与连接" | "沟通与习惯" | "反思与延续";
  title: string;
  intent: string;
  action: string;
  suggestedWords: string;
  observationPrompt: string;
  estimatedMinutes: number;
}

export const CAMP_21_DAYS: Camp21Day[] = [
  { day: 1, stage: "观察与连接", title: "先听完一句话", intent: "练习在回应之前，先完整听见孩子。", action: "找一个普通对话，只听完孩子的一句话，不打断也不急着给建议。", suggestedWords: "我先听你说完，你慢慢说。", observationPrompt: "孩子说完后，语气或身体状态有什么变化？", estimatedMinutes: 10 },
  { day: 2, stage: "观察与连接", title: "描述，不评价", intent: "把看到的事实和自己的判断分开。", action: "选择一个日常场景，只说出你看到的行为，不加“懒”“不听话”等评价。", suggestedWords: "我看到书还放在桌上，我们一起看看接下来怎么安排。", observationPrompt: "当你减少评价时，对话是否更容易继续？", estimatedMinutes: 8 },
  { day: 3, stage: "观察与连接", title: "找到情绪背后的需要", intent: "先理解当下，再讨论办法。", action: "冲突出现时，先猜一个可能的感受，并邀请孩子修正。", suggestedWords: "你现在是不是有点失望？如果我猜错了，你可以告诉我。", observationPrompt: "孩子是否愿意补充自己的感受？", estimatedMinutes: 10 },
  { day: 4, stage: "观察与连接", title: "留出十分钟专属时间", intent: "用稳定陪伴建立连接。", action: "让孩子选择一个十分钟活动，你不看手机、不教学，只参与。", suggestedWords: "这十分钟你来选，我们一起做。", observationPrompt: "孩子选择了什么？你最意外的细节是什么？", estimatedMinutes: 10 },
  { day: 5, stage: "观察与连接", title: "看见一次努力", intent: "关注过程而不是只看结果。", action: "找到孩子今天一次具体努力，描述你看到的过程。", suggestedWords: "我看到你刚才重新试了一次，这很不容易。", observationPrompt: "具体描述和泛泛表扬带来的回应有什么不同？", estimatedMinutes: 6 },
  { day: 6, stage: "观察与连接", title: "暂停一次自动反应", intent: "给家长和孩子都留出调节空间。", action: "在想立刻批评时，先做三次缓慢呼吸，再决定是否回应。", suggestedWords: "我需要一分钟整理一下，我们等会儿再说。", observationPrompt: "暂停后，你真正想表达的重点是什么？", estimatedMinutes: 5 },
  { day: 7, stage: "观察与连接", title: "第一次家庭小回顾", intent: "总结做过的行动，不评价谁好谁坏。", action: "回看前六天，选一个最想保留的小动作。", suggestedWords: "这周哪一次相处让我们都轻松一点？", observationPrompt: "家庭愿意保留的动作是什么？", estimatedMinutes: 15 },
  { day: 8, stage: "沟通与习惯", title: "把命令改成有限选择", intent: "在边界内给孩子参与感。", action: "选择一个需要完成的小事，提供两个都可接受的选择。", suggestedWords: "你想先收书包，还是先整理桌面？", observationPrompt: "有限选择是否减少了拉扯？", estimatedMinutes: 8 },
  { day: 9, stage: "沟通与习惯", title: "说清边界与原因", intent: "坚定表达，不使用威胁。", action: "针对一个家庭规则，用一句边界和一句原因表达。", suggestedWords: "九点后手机要放在客厅，因为睡眠是我们共同保护的事。", observationPrompt: "孩子最关心规则的哪一部分？", estimatedMinutes: 10 },
  { day: 10, stage: "沟通与习惯", title: "一起把目标变小", intent: "把模糊要求变成可以开始的动作。", action: "和孩子把一个任务缩小为十分钟能完成的第一步。", suggestedWords: "我们不一次做完，先找出第一小步。", observationPrompt: "任务变小后，开始是否更容易？", estimatedMinutes: 10 },
  { day: 11, stage: "沟通与习惯", title: "用提问代替提醒", intent: "帮助孩子参与计划。", action: "今天只用一个开放问题帮助孩子回想自己的安排。", suggestedWords: "你准备从哪一步开始？需要我帮什么？", observationPrompt: "孩子能否说出自己的下一步？", estimatedMinutes: 8 },
  { day: 12, stage: "沟通与习惯", title: "设计一个环境提示", intent: "少靠意志，多靠环境。", action: "为一个家庭习惯增加可见提示，例如固定收纳点或纸质步骤卡。", suggestedWords: "我们把提醒放在哪里最顺手？", observationPrompt: "环境变化是否减少了口头催促？", estimatedMinutes: 12 },
  { day: 13, stage: "沟通与习惯", title: "失败后重新开始", intent: "练习恢复，而不是追求连续完美。", action: "回看一次没有做到的计划，只讨论下一次如何更容易开始。", suggestedWords: "没做到也可以重新来，下一次我们想改哪一点？", observationPrompt: "当失败不被批评时，孩子是否更愿意讨论？", estimatedMinutes: 10 },
  { day: 14, stage: "沟通与习惯", title: "第二次家庭小回顾", intent: "识别适合自己家庭的沟通与习惯工具。", action: "从第 8–13 天选择一个继续使用、一个暂时放下的工具。", suggestedWords: "哪个方法最像我们家？哪个暂时不适合？", observationPrompt: "家庭做出的选择和理由是什么？", estimatedMinutes: 15 },
  { day: 15, stage: "反思与延续", title: "区分事实和我的想法", intent: "减少把担心当成孩子事实。", action: "写下一件发生的事，再分别写出事实和你的解释。", suggestedWords: "这是我现在的理解，不一定就是你的感受。", observationPrompt: "事实和解释分开后，你的情绪有什么变化？", estimatedMinutes: 10 },
  { day: 16, stage: "反思与延续", title: "看见自己的触发点", intent: "理解家长反应背后的担心。", action: "回想一次强烈反应，写下当时你最担心发生什么。", suggestedWords: "我刚才有点着急，是因为我担心……", observationPrompt: "说出担心后，表达是否更清楚？", estimatedMinutes: 10 },
  { day: 17, stage: "反思与延续", title: "修复一次小冲突", intent: "让道歉和修复成为家庭能力。", action: "选择一个小冲突，先为自己的表达方式负责，再邀请孩子补充。", suggestedWords: "刚才我的语气太重了，对不起。你的感受是什么？", observationPrompt: "修复后，双方是否更愿意继续对话？", estimatedMinutes: 10 },
  { day: 18, stage: "反思与延续", title: "共同定义一个好时刻", intent: "让家庭自己决定什么值得延续。", action: "请每个人说一个最近觉得舒服的家庭时刻。", suggestedWords: "最近哪一刻让你觉得我们很像一个团队？", observationPrompt: "不同成员看重的时刻有什么不同？", estimatedMinutes: 12 },
  { day: 19, stage: "反思与延续", title: "选择一个长期微习惯", intent: "把课程收获变成低负担日常。", action: "从 18 天练习中选择一个每周至少做一次的动作。", suggestedWords: "我们只保留一个最容易坚持的动作，好吗？", observationPrompt: "这个动作需要什么环境支持？", estimatedMinutes: 10 },
  { day: 20, stage: "反思与延续", title: "约定一次家庭小会", intent: "建立稳定、可恢复的家庭复盘节奏。", action: "确定下周一次 15 分钟家庭小会的时间和议题。", suggestedWords: "下周我们用十五分钟聊聊最近最需要配合的一件事。", observationPrompt: "什么时间和形式最不容易成为负担？", estimatedMinutes: 8 },
  { day: 21, stage: "反思与延续", title: "完成过程回顾", intent: "看见做过的行动，并选择下一阶段。", action: "回看完成和跳过的日子，写下一个发现、一个保留动作和一个仍需支持的问题。", suggestedWords: "这 21 天不是考试，我们只看看什么对我们家真正有用。", observationPrompt: "下一阶段更适合继续练习、进入 90 天计划，还是先暂停？", estimatedMinutes: 15 },
];

export function getCamp21Day(day: number) {
  return CAMP_21_DAYS[Math.min(21, Math.max(1, day)) - 1];
}
