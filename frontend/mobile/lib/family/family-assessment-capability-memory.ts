import type { GrowthFocusId } from "./core-growth";

export type FamilyAssessmentMemoryKind = "DIMENSION" | "ITEM" | "EVIDENCE_ANCHOR" | "PRACTICE_PATTERN" | "OUTCOME_FEEDBACK";
export type Ui02AssessmentAnswer = "OFTEN" | "SOMETIMES" | "RARELY" | "NOT_SURE";

export type FamilyAssessmentMemoryQuestion = {
  itemRef: string;
  text: string;
  intent: string;
  evidenceAnchor: string;
};

export type FamilyAssessmentBlueprintStep = {
  stepRef: string;
  title: string;
  purpose: string;
  outputUpperBound: "CONSENT" | "NEED" | "INTENT" | "PREFERENCE" | "DECISION";
  prompt: string;
};

export type FamilyAssessmentDimensionMemory = {
  focusId: GrowthFocusId;
  title: string;
  operationalDefinition: string;
  theorySupport: readonly string[];
  familyTheorySupport: readonly string[];
  dataSupport: readonly string[];
  practiceSupport: readonly string[];
  observableSignals: readonly string[];
  boundary: string;
  nextSupportDirections: readonly string[];
  questions: readonly FamilyAssessmentMemoryQuestion[];
};

export type FamilyAssessmentCapabilityMemory = {
  capabilityRef: string;
  version: string;
  capabilityClass: "REAL_DOMAIN_CAPABILITY" | "REAL_MODEL_INTELLIGENCE";
  memoryKinds: readonly FamilyAssessmentMemoryKind[];
  assessmentToolRef: string;
  assessmentToolVersion: number;
  aiUseCase: "ASSESSMENT_INTERPRETATION";
  boundary: {
    truthClass: "FAMILY_PERSPECTIVE";
    notScore: true;
    notDiagnosis: true;
    noRanking: true;
    trainingUse: false;
    familyDataMemory: "NAMED_ACTION_AND_CONSENT_ONLY";
  };
  answerOptions: readonly { id: Ui02AssessmentAnswer; label: string }[];
  researchBasis: readonly string[];
  blueprint: {
    methodName: "Family Support Assessment";
    productLabel: "免费家庭测评";
    layer: "L0_FAMILY_NEED_AND_SERVICE_PREFERENCE";
    positioning: string;
    stepModel: readonly FamilyAssessmentBlueprintStep[];
  };
  platformIntegration: {
    businessScenario: "S2_FAMILY_SELF_CHECK_AND_SUPPORT_NEED";
    dataObjects: readonly string[];
    applicationSurfaces: readonly string[];
    aiBoundary: string;
    improvementLoop: string;
  };
  dimensions: readonly FamilyAssessmentDimensionMemory[];
  improvementSignals: readonly string[];
};

export const FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY: FamilyAssessmentCapabilityMemory = {
  capabilityRef: "FAMILY_ASSESSMENT_AI_CAPABILITY",
  version: "v1",
  capabilityClass: "REAL_DOMAIN_CAPABILITY",
  memoryKinds: ["DIMENSION", "ITEM", "EVIDENCE_ANCHOR", "PRACTICE_PATTERN", "OUTCOME_FEEDBACK"],
  assessmentToolRef: "FAMILY_SUPPORT_NEEDS",
  assessmentToolVersion: 2,
  aiUseCase: "ASSESSMENT_INTERPRETATION",
  boundary: {
    truthClass: "FAMILY_PERSPECTIVE",
    notScore: true,
    notDiagnosis: true,
    noRanking: true,
    trainingUse: false,
    familyDataMemory: "NAMED_ACTION_AND_CONSENT_ONLY",
  },
  answerOptions: [
    { id: "OFTEN", label: "经常" },
    { id: "SOMETIMES", label: "有时" },
    { id: "RARELY", label: "很少" },
    { id: "NOT_SURE", label: "不确定" },
  ],
  researchBasis: [
    "Family 分层家庭支持评估框架：首阶段只能做 L0 家庭需要与偏好确认，不做评分、排名、诊断或儿童能力测验。",
    "CASEL SEL：家庭、学校、社区共同支持自我觉察、情绪管理、关系、负责决策与目标达成。",
    "CDC Essentials for Parenting：面向家长的支持应提供可使用的文章、视频和活动，而不是给家庭下结论。",
    "Harvard Executive Function：计划、注意、切换和任务管理能力依赖支持性环境，可通过实践发展。",
    "AAP HealthyChildren 媒介资料：数字媒介需要家长监测和共同解释，重点是家庭规则和支持。",
  ],
  blueprint: {
    methodName: "Family Support Assessment",
    productLabel: "免费家庭测评",
    layer: "L0_FAMILY_NEED_AND_SERVICE_PREFERENCE",
    positioning: "用 2-5 分钟帮助监护人说明此刻希望获得哪类家庭支持，并形成可追溯的 Need/Intent；不测量孩子、不生成结论。",
    stepModel: [
      { stepRef: "CONSENT_AND_BOUNDARY", title: "说明与同意", purpose: "说明非诊断、非评分、可退出和数据最小化。", outputUpperBound: "CONSENT", prompt: "这不是诊断或给孩子打分，只帮助你说明此刻希望获得哪类支持。" },
      { stepRef: "CURRENT_NEED", title: "当下关切", purpose: "让家庭用自己的语言或选择项表达当前最想理清的事。", outputUpperBound: "NEED", prompt: "最近最想一起理清的是哪件事？" },
      { stepRef: "SUPPORT_DIRECTION", title: "支持方向", purpose: "确认家庭希望先看哪类支持方向。", outputUpperBound: "INTENT", prompt: "你更希望先从哪类家庭支持开始？" },
      { stepRef: "SERVICE_PREFERENCE", title: "偏好与边界", purpose: "确认家庭愿意看文字资源、计划草案，或只保留记录。", outputUpperBound: "PREFERENCE", prompt: "你希望先看已准入的文字资源，还是只保留这次记录？" },
      { stepRef: "NEXT_DECISION", title: "结束确认", purpose: "由家庭明确选择继续、返回、暂停或暂不行动。", outputUpperBound: "DECISION", prompt: "你可以选择一个下一步，也可以暂不行动。" },
    ],
  },
  platformIntegration: {
    businessScenario: "S2_FAMILY_SELF_CHECK_AND_SUPPORT_NEED",
    dataObjects: ["AssessmentTool", "AssessmentSession", "AssessmentResponse", "FamilyNeed", "SupportDirection", "ConsentReceipt"],
    applicationSurfaces: ["完成免费家庭测评", "查看家庭成长解读", "生成90天陪伴计划", "用日常行动卡持续记录"],
    aiBoundary: "AI 只能做家庭视角整理、资源匹配和下一步建议草案；不得生成诊断、总分、排名或核心事实写入。",
    improvementLoop: "以完成率、退出题项、不确定选项比例、家庭反馈、人工审核结果和后续行动有用性持续校准题项与支持资源。",
  },
  dimensions: [
    {
      focusId: "LEARNING_HABITS",
      title: "学习习惯",
      operationalDefinition: "家庭情境中孩子启动、维持、完成学习任务时获得结构支持的情况。",
      theorySupport: ["Harvard Executive Function：计划、注意、切换和任务管理能力依赖支持性环境，可通过实践发展。", "CDC Parenting：家庭 routines and rules 可作为家长支持儿童行为与学习节奏的实践入口。"],
      familyTheorySupport: ["孩子开始学习、坚持完成任务，常常需要一个稳定、可预期的家庭节奏。", "比起反复催促，更有效的是把开始、休息、收尾这些步骤说清楚、做固定。"],
      dataSupport: ["只记录这次家长看到的三个情况，不给孩子打分。", "如果很多家长选了“不确定”，我们会优先把题目改得更清楚。", "后续只根据家庭自己确认的行动反馈改进建议。"],
      practiceSupport: ["每天用一个固定动作开始学习，比如喝水、摆好文具、打开作业。", "把作业先拆成最容易开始的一小步。", "结束后用一两句话回看今天哪里顺、哪里卡住。"],
      observableSignals: ["作业启动", "困难坚持", "家庭学习节奏"],
      boundary: "不推断智力、学习障碍或学习成绩原因。",
      nextSupportDirections: ["固定学习开始流程", "把作业拆小步", "换一种提醒方式"],
      questions: [
        { itemRef: "LEARNING_HABITS_Q01", text: "过去两周，孩子开始写作业前常需要反复提醒。", intent: "观察任务启动与外部催促依赖。", evidenceAnchor: "学习习惯与执行功能实践假设；需后续研究证据补强。" },
        { itemRef: "LEARNING_HABITS_Q02", text: "孩子遇到稍难的题目时，容易拖延、分心或直接放弃。", intent: "观察坚持性与困难恢复。", evidenceAnchor: "自我调节学习与任务坚持相关研究概念。" },
        { itemRef: "LEARNING_HABITS_Q03", text: "家里目前缺少稳定的学习开始、休息和收尾节奏。", intent: "观察家庭情境中的学习结构支持。", evidenceAnchor: "家庭学习环境与例行情境实践经验。" },
      ],
    },
    {
      focusId: "EMOTION_REGULATION",
      title: "情绪管理",
      operationalDefinition: "孩子情绪触发、表达、恢复，以及家长共同调节支持的家庭互动情况。",
      theorySupport: ["CASEL SEL：管理情绪是社会情绪学习核心能力之一。", "CDC Parenting：Noticing and Naming Emotions 可作为家长支持儿童情绪表达的实践方向。", "Family 知识库 MD-001：情绪教练式回应可作为低风险家庭沟通方法。"],
      familyTheorySupport: ["孩子情绪上来时，先被理解，通常比马上讲道理更容易恢复。", "大人先稳住节奏，孩子才更容易学会把感受说出来、把事情说清楚。"],
      dataSupport: ["只记录情绪恢复、能不能先停一下、家长怎么回应这三类情况。", "常见的卡点会用来匹配更容易上手的沟通方法。", "如果出现高风险表达，需要人工介入，测评不会自动下判断。"],
      practiceSupport: ["先把孩子的感受说出来，比如“你现在很着急”。", "吵起来时先停一小会儿，再继续说。", "先接住孩子一句话，再讨论事情怎么处理。"],
      observableSignals: ["恢复时间", "冲突暂停", "家长回应策略"],
      boundary: "不判断心理疾病、气质类型或临床风险。",
      nextSupportDirections: ["先把感受说出来", "吵起来先停一下", "事后重新和好"],
      questions: [
        { itemRef: "EMOTION_REGULATION_Q01", text: "过去两周，孩子情绪上来后需要较长时间才能恢复。", intent: "观察情绪恢复时间。", evidenceAnchor: "情绪调节研究中的恢复与调节策略概念。" },
        { itemRef: "EMOTION_REGULATION_Q02", text: "亲子冲突中，大人和孩子都很难先暂停再说。", intent: "观察共同调节和冲突暂停能力。", evidenceAnchor: "亲子互动中的共同调节实践假设。" },
        { itemRef: "EMOTION_REGULATION_Q03", text: "孩子表达焦虑、生气或委屈时，家长不太确定如何回应。", intent: "观察家长回应策略需求。", evidenceAnchor: "家庭情绪支持与回应方式相关研究概念。" },
      ],
    },
    {
      focusId: "PARENT_CHILD_COMMUNICATION",
      title: "亲子沟通",
      operationalDefinition: "孩子是否愿意表达、家长是否能倾听，以及冲突后关系修复的家庭循环。",
      theorySupport: ["CASEL SEL：支持性关系是儿童社会情绪发展和学习环境的重要部分。", "CDC Parenting：Connecting and Communicating 提供家长可用的连接与沟通原则。", "Family 知识库 CN-001/CN-002：被听见感与防御/强制互动循环可作为互动观察构念。"],
      familyTheorySupport: ["孩子愿意说，往往从“我说了会被听见”开始。", "亲子沟通不是一次说服，而是少一点纠正，多一点听见，再一起修复。"],
      dataSupport: ["只记录孩子愿不愿意说、对话会不会变成纠正、冲突后能不能修复这三类情况。", "结果只给出可尝试的支持方向，不给孩子贴标签。", "后续会看家庭自己反馈这些建议是否真的有用。"],
      practiceSupport: ["先重复一遍孩子在意的点，让孩子知道你听见了。", "少一点马上讲道理或纠正，多问一句“你最在意的是什么”。", "冲突后留一个重新说话、重新和好的小步骤。"],
      observableSignals: ["表达意愿", "讲道理/纠正循环", "冲突修复"],
      boundary: "不把一次冲突概括成关系事实或孩子性格标签。",
      nextSupportDirections: ["今晚怎么开口", "先听孩子说完", "吵完怎么和好"],
      questions: [
        { itemRef: "PARENT_CHILD_COMMUNICATION_Q01", text: "孩子遇到不顺心的事，通常不太愿意主动和家长说。", intent: "观察沟通意愿与信任入口。", evidenceAnchor: "亲子沟通开放性与家庭支持研究概念。" },
        { itemRef: "PARENT_CHILD_COMMUNICATION_Q02", text: "家长想帮助孩子时，对话容易变成讲道理、纠正或争执。", intent: "观察沟通循环与冲突升级。", evidenceAnchor: "亲子冲突与沟通方式实践经验。" },
        { itemRef: "PARENT_CHILD_COMMUNICATION_Q03", text: "冲突后，家里较少有重新和好、复盘或修复的过程。", intent: "观察关系修复机制。", evidenceAnchor: "关系修复与家庭互动质量研究概念。" },
      ],
    },
    {
      focusId: "DEVICE_USE_CONTEXT",
      title: "手机依赖",
      operationalDefinition: "数字设备使用对睡眠、作业、家庭节奏与亲子规则协商的影响。",
      theorySupport: ["AAP HealthyChildren Media：儿童需要父母监测并帮助解释媒介影响。", "CDC Parenting：家庭 rules and routines 可用于建立可共同执行的日常边界。"],
      familyTheorySupport: ["手机问题通常不是只靠没收解决，关键是全家把规则提前说清楚。", "规则越临时，越容易拉扯；规则越具体，孩子越知道怎么配合。"],
      dataSupport: ["只记录手机或平板是否影响作业、睡眠、家庭安排和规则执行。", "这些信息只用来帮助家庭把规则说清楚。", "不判断孩子是不是成瘾，也不输出风险等级。"],
      practiceSupport: ["一起说清楚什么时候能用、在哪里用、睡前什么时候放下。", "提前约定规则，少在临场反复讨价还价。", "大人和孩子尽量按同一套规则执行。"],
      observableSignals: ["日常功能干扰", "围绕设备冲突", "规则一致性"],
      boundary: "不使用成瘾诊断，不把设备问题单独归因于孩子。",
      nextSupportDirections: ["一起定手机规则", "睡前放下手机", "减少反复拉扯"],
      questions: [
        { itemRef: "DEVICE_USE_CONTEXT_Q01", text: "手机或平板使用经常影响作业、睡眠或家庭安排。", intent: "观察屏幕使用对日常功能的干扰。", evidenceAnchor: "青少年数字媒介使用与睡眠/学习干扰研究概念。" },
        { itemRef: "DEVICE_USE_CONTEXT_Q02", text: "围绕手机使用，家里经常发生讨价还价或冲突。", intent: "观察规则执行中的亲子冲突。", evidenceAnchor: "家庭媒介规则与冲突管理实践经验。" },
        { itemRef: "DEVICE_USE_CONTEXT_Q03", text: "家里的手机规则不够清楚，或大人和孩子执行标准不一致。", intent: "观察边界清晰度与一致性。", evidenceAnchor: "家庭规则一致性与行为边界研究概念。" },
      ],
    },
    {
      focusId: "SELF_REGULATION",
      title: "自律能力",
      operationalDefinition: "孩子在家庭支持下参与计划、执行、检查和复盘的自我管理过程。",
      theorySupport: ["Harvard Executive Function：自我调节包含计划、注意、任务管理等可发展能力。", "CASEL SEL：负责决策与目标达成需要家庭、学校、社区共同支持。"],
      familyTheorySupport: ["自律不是一句“你要自觉”就能长出来，需要孩子慢慢参与计划、执行和复盘。", "大人逐步放手，孩子才有机会练习自己安排、自己检查、自己调整。"],
      dataSupport: ["只记录孩子是否依赖监督、是否参与计划、是否会一起复盘方法。", "根据家庭选择，给出更容易执行的小步骤。", "不评价孩子自律强弱，也不做家庭排名。"],
      practiceSupport: ["让孩子一起参与定计划，而不是只接收安排。", "提前说好怎么检查完成情况。", "事情没做好时，先看方法哪里卡住，而不是只催着补救。"],
      observableSignals: ["监督依赖", "自主参与", "方法复盘"],
      boundary: "不评价孩子懒惰或意志品质，不生成能力排名。",
      nextSupportDirections: ["一起定计划", "说好怎么检查", "慢慢减少监督"],
      questions: [
        { itemRef: "SELF_REGULATION_Q01", text: "孩子完成日常任务时，比较依赖家长全程监督。", intent: "观察外部监督依赖。", evidenceAnchor: "自我调节与执行功能研究概念。" },
        { itemRef: "SELF_REGULATION_Q02", text: "孩子较少参与制定自己的计划、目标或检查方式。", intent: "观察自主参与程度。", evidenceAnchor: "自主性支持与自我管理实践经验。" },
        { itemRef: "SELF_REGULATION_Q03", text: "事情没做好时，家里通常忙着催促补救，较少一起复盘方法。", intent: "观察反思和策略调整。", evidenceAnchor: "自我调节学习中的监控与反思概念。" },
      ],
    },
  ],
  improvementSignals: ["completion_rate", "dropoff_item_ref", "not_sure_rate", "parent_feedback", "human_review_outcome", "followup_action_usefulness"],
} as const;

export function getFamilyAssessmentDimensionMemory(focusId: GrowthFocusId | null) {
  return FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.find((dimension) => dimension.focusId === focusId) ?? null;
}

export function getFamilyAssessmentMemoryQuestions(focusId: GrowthFocusId | null) {
  return getFamilyAssessmentDimensionMemory(focusId)?.questions ?? [];
}
