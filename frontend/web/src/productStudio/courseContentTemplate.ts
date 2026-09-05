export const COURSE_LESSON_COUNT = 24;

export type CourseLessonDraft = {
  lesson_id: string;
  sequence: number;
  title: string;
  knowledge_point: string;
  action_task: string;
  media_asset_ids: string[];
  tool_refs: string[];
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

export function createCourseContentTemplate(): CourseContentTemplateState {
  return {
    title: "",
    problem_statement: "",
    assessment_criteria: "",
    learning_goal: "",
    lessons: Array.from({ length: COURSE_LESSON_COUNT }, (_, index) => ({
      lesson_id: `lesson-${String(index + 1).padStart(2, "0")}`,
      sequence: index + 1,
      title: "",
      knowledge_point: "",
      action_task: "",
      media_asset_ids: [],
      tool_refs: [],
    })),
    review_cadence: "",
    outcome_metrics: "",
    content_accuracy_claim_refs: "",
    product_component_id: null,
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
    || claimRefs.length === 0) {
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
    })),
    review_cadence: state.review_cadence.trim(),
    outcome_metrics: outcomeMetrics,
    content_accuracy_claim_refs: claimRefs,
    product_component_id: null,
    ai_coach_prompt_ref: state.ai_coach_prompt_ref?.trim() || null,
  };
}
