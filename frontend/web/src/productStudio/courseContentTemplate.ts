export const COURSE_LESSON_COUNT = 24;

export type CourseLessonDraft = {
  lesson_id: string;
  sequence: number;
  title: string;
  knowledge_point: string;
  action_task: string;
  media_asset_ids: string[];
  tool_refs: string[];
  stage_id: string;
  bom_line_ref: string;
};

export type CourseContentDraftInput = {
  title: string;
  problem_statement: string;
  assessment_criteria: string[];
  learning_goal: string;
  lessons: CourseLessonDraft[];
  review_cadence: string;
  outcome_metrics: string[];
  content_accuracy_claim_refs: string[];
  product_component_id: null;
  course_system_version_ref: string;
  ai_coach_prompt_ref: string | null;
};

export type CourseContentTemplateState = Omit<
  CourseContentDraftInput,
  "assessment_criteria" | "outcome_metrics" | "content_accuracy_claim_refs"
> & {
  assessment_criteria: string;
  outcome_metrics: string;
  content_accuracy_claim_refs: string;
};

const uniqueLines = (value: string) => [
  ...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)),
];

const CURRICULUM_BASELINE: ReadonlyArray<readonly [string, string, string]> = [
  ["看见家庭现状", "把具体事件与评价分开记录", "完成一次家庭困扰事实记录"],
  ["说清主要矛盾", "区分表面冲突与真实需要", "共同写下一条主要矛盾陈述"],
  ["建立安全对话", "用观察、感受、需要、请求组织表达", "完成一次十分钟安全对话"],
  ["绘制家庭问题地图", "把问题、影响与可控范围连接起来", "确认一张家庭问题地图"],
  ["听见彼此需要", "识别立场背后的需要", "完成一次需要澄清练习"],
  ["表达而不指责", "用具体行为描述替代人格评价", "把一段指责改写成请求"],
  ["建立共同约定", "约定应可观察、可执行、可复盘", "共同制定一条家庭约定"],
  ["修复一次连接", "关系修复需要承认影响并提出行动", "完成一次修复对话并记录回应"],
  ["定义成长方向", "目标应描述希望增加的家庭能力", "写出一个家庭成长方向"],
  ["拆解目标树", "把方向拆成阶段结果与日常行为", "完成一棵目标树的一级拆解"],
  ["选择可行指标", "指标记录行动和结果证据而非家庭排名", "确定两项可观察指标"],
  ["确认成长计划", "计划需要家庭成员理解并愿意参与", "召开一次计划确认会"],
  ["设计日常行动", "小步行动比宏大承诺更容易坚持", "安排一次十五分钟家庭行动"],
  ["建立行动提示", "提示应服务于行动而不是制造压力", "设置一个家庭可接受的提示"],
  ["处理行动阻碍", "先识别阻碍再调整行动剂量", "记录一次阻碍并提出替代方案"],
  ["完成二十一天复盘", "复盘关注证据、感受与下一步选择", "完成21天行动复盘"],
  ["识别重复模式", "重复发生的互动模式可成为改进线索", "记录一个重复模式及触发条件"],
  ["练习家庭协商", "协商需要明确选择、边界和责任", "完成一次有限选项协商"],
  ["连接外部支持", "需要时使用专家、管家或社区支持", "识别一个合适的支持入口"],
  ["形成九十天路径", "长期路径由阶段结果和复盘节点组成", "确认90天路径的首个阶段"],
  ["汇总成长证据", "证据应来自真实行动记录与家庭反馈", "整理一份阶段证据清单"],
  ["进行家庭复盘", "复盘同时看见进展、困难与关系感受", "召开一次家庭阶段复盘"],
  ["提出下一周期假设", "下一周期应基于证据提出可验证假设", "写下一条下一周期改进假设"],
  ["共创下一周期", "家庭共同选择下一步而非被动接受方案", "确认下一周期行动与支持方式"],
];

export function createCourseContentTemplate(options: { withCurriculumBaseline?: boolean } = {}): CourseContentTemplateState {
  const withCurriculumBaseline = options.withCurriculumBaseline ?? false;
  return {
    title: "",
    problem_statement: "",
    assessment_criteria: "",
    learning_goal: "",
    lessons: Array.from({ length: COURSE_LESSON_COUNT }, (_, index) => ({
      lesson_id: `lesson-${String(index + 1).padStart(2, "0")}`,
      sequence: index + 1,
      title: withCurriculumBaseline ? CURRICULUM_BASELINE[index][0] : "",
      knowledge_point: withCurriculumBaseline ? CURRICULUM_BASELINE[index][1] : "",
      action_task: withCurriculumBaseline ? CURRICULUM_BASELINE[index][2] : "",
      // Design-time AssetBundle references. These identify the governed BOM
      // slots; they are not claims that binaries exist or passed QA/rights
      // review. Release remains blocked until the Human Gate resolves them.
      media_asset_ids: withCurriculumBaseline
        ? [
            `courseware:family-growth:lesson-${String(index + 1).padStart(2, "0")}:deck@v1`,
            `courseware:family-growth:lesson-${String(index + 1).padStart(2, "0")}:worksheet@v1`,
            `courseware:family-growth:lesson-${String(index + 1).padStart(2, "0")}:document@v1`,
          ]
        : [],
      tool_refs: [],
      stage_id: `S${Math.floor(index / 4) + 1}`,
      bom_line_ref: `courseware:family-growth:lesson-${String(index + 1).padStart(2, "0")}@v1`,
    })),
    review_cadence: "",
    outcome_metrics: "",
    content_accuracy_claim_refs: "",
    product_component_id: null,
    course_system_version_ref: "course-system:family-growth@v1",
    ai_coach_prompt_ref: null,
  };
}

export function isLessonComplete(lesson: CourseLessonDraft): boolean {
  return Boolean(lesson.title.trim() && lesson.knowledge_point.trim() && lesson.action_task.trim());
}

export function compileCourseContentDraft(state: CourseContentTemplateState): CourseContentDraftInput {
  const scalarFields = [
    state.title,
    state.problem_statement,
    state.learning_goal,
    state.review_cadence,
  ];
  const assessmentCriteria = uniqueLines(state.assessment_criteria);
  const outcomeMetrics = uniqueLines(state.outcome_metrics);
  const claimRefs = uniqueLines(state.content_accuracy_claim_refs);
  if (scalarFields.some((value) => !value.trim())
    || assessmentCriteria.length === 0
    || outcomeMetrics.length === 0
    || claimRefs.length === 0 || !state.course_system_version_ref.trim()) {
    throw new Error("COURSE_OVERVIEW_INCOMPLETE");
  }
  if (state.lessons.length !== COURSE_LESSON_COUNT) throw new Error("COURSE_REQUIRES_24_LESSONS");
  const ids = new Set<string>();
  for (const [index, lesson] of state.lessons.entries()) {
    if (lesson.sequence !== index + 1) throw new Error("COURSE_LESSON_SEQUENCE_INVALID");
    if (!lesson.lesson_id.trim() || ids.has(lesson.lesson_id)) throw new Error("COURSE_LESSON_ID_INVALID");
    if (!isLessonComplete(lesson)) throw new Error(`COURSE_LESSON_${lesson.sequence}_INCOMPLETE`);
    ids.add(lesson.lesson_id);
  }
  return {
    title: state.title.trim(),
    problem_statement: state.problem_statement.trim(),
    assessment_criteria: assessmentCriteria,
    learning_goal: state.learning_goal.trim(),
    lessons: state.lessons.map((lesson) => ({
      ...lesson,
      lesson_id: lesson.lesson_id.trim(),
      title: lesson.title.trim(),
      knowledge_point: lesson.knowledge_point.trim(),
      action_task: lesson.action_task.trim(),
      media_asset_ids: [...new Set(lesson.media_asset_ids.map((item) => item.trim()).filter(Boolean))],
      tool_refs: [...new Set(lesson.tool_refs.map((item) => item.trim()).filter(Boolean))],
      stage_id: lesson.stage_id.trim(),
      bom_line_ref: lesson.bom_line_ref.trim(),
    })),
    review_cadence: state.review_cadence.trim(),
    outcome_metrics: outcomeMetrics,
    content_accuracy_claim_refs: claimRefs,
    product_component_id: null,
    course_system_version_ref: state.course_system_version_ref.trim(),
    ai_coach_prompt_ref: state.ai_coach_prompt_ref?.trim() || null,
  };
}
