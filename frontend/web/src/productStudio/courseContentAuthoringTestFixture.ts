import type { CourseContentDraftResponse } from "./courseContentAuthoringApi";
import { compileCourseContentDraft, createCourseContentTemplate } from "./courseContentTemplate";

export function completeCourseInput() {
  const state = createCourseContentTemplate();
  Object.assign(state, {
    title: "24节家庭协作课",
    problem_statement: "家庭需要共同学习节奏",
    assessment_criteria: "形成共同约定",
    learning_goal: "建立可持续协作",
    review_cadence: "每6节人工复盘",
    outcome_metrics: "共同约定被确认",
    content_accuracy_claim_refs: "claim:family-rhythm",
    ai_coach_prompt_ref: "prompt:course-coach@v1",
  });
  state.lessons = state.lessons.map((lesson) => ({
    ...lesson,
    title: `第${lesson.sequence}节`,
    knowledge_point: `知识点${lesson.sequence}`,
    action_task: `家庭行动${lesson.sequence}`,
  }));
  return compileCourseContentDraft(state);
}

export function courseDraftResponse(): CourseContentDraftResponse {
  return {
    ...completeCourseInput(),
    id: "course:draft-1",
    version: 1,
    status: "DRAFT",
    tenant_scope: "tenant:demo",
    created_by: "author:1",
    created_at: "2026-09-03T07:00:00+08:00",
    updated_at: "2026-09-03T07:00:00+08:00",
    reviewed_by: null,
    reviewed_at: null,
    review_reason: null,
    published_at: null,
  };
}
