import { useMemo, useState } from "react";
import {
  compileCourseContentDraft,
  createCourseContentTemplate,
  isLessonComplete,
  type CourseLessonDraft,
} from "./courseContentTemplate";

const splitRefs = (value: string) => value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);

export function CourseContentWorkbench({ contractPreview = false }: { contractPreview?: boolean }) {
  const [course, setCourse] = useState(createCourseContentTemplate);
  const [activeLesson, setActiveLesson] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const completedLessons = useMemo(() => course.lessons.filter(isLessonComplete).length, [course.lessons]);
  const lesson = course.lessons[activeLesson];

  const updateLesson = (patch: Partial<CourseLessonDraft>) => {
    setCourse((current) => ({
      ...current,
      lessons: current.lessons.map((item, index) => index === activeLesson ? { ...item, ...patch } : item),
    }));
    setPreview(null);
    setError(null);
  };

  const updateCourse = (field: keyof typeof course, value: string) => {
    setCourse((current) => ({ ...current, [field]: value }));
    setPreview(null);
    setError(null);
  };

  const compilePreview = () => {
    try {
      setPreview(JSON.stringify(compileCourseContentDraft(course), null, 2));
      setError(null);
    } catch (cause) {
      const code = cause instanceof Error ? cause.message : "COURSE_CONTRACT_INVALID";
      setError(code.startsWith("COURSE_LESSON_")
        ? `请先补全第 ${code.match(/\d+/)?.[0] ?? "对应"} 节的标题、知识点与行动任务。`
        : "请完整填写课程总纲、24 节内容、复盘节奏、结果指标与内容准确性引用。");
      setPreview(null);
    }
  };

  return (
    <section aria-label="24 lesson CourseContent workbench" className="panel course-content-workbench">
      <p className="section-kicker">ProductPackage → CourseContent DRAFT → Courseware BOM → Human Gate</p>
      <h2>24 课时课程与课件编排</h2>
      <p className="muted">
        把课程总纲、每节知识点、家庭行动任务、工具与课件资产引用编译为一个 CourseContent DRAFT。24 是当前产品模板，不是全平台硬编码规则。
      </p>
      <div className="callout" role="note">
        <strong>{contractPreview ? "合同预览，尚未开放生产保存" : "仅创建 DRAFT"}</strong>
        <p>内容准确性引用不等于证据已准入；课程体系、产品包冻结版本和课件资产版本仍需后端补齐，AI 不能直接发布。</p>
      </div>

      <div className="course-overview-grid">
        <label>课程名称<input value={course.title} onChange={(event) => updateCourse("title", event.target.value)} /></label>
        <label>学习目标<input value={course.learning_goal} onChange={(event) => updateCourse("learning_goal", event.target.value)} /></label>
        <label className="course-wide-field">要解决的家庭问题<textarea rows={2} value={course.problem_statement} onChange={(event) => updateCourse("problem_statement", event.target.value)} /></label>
        <label>评估标准（每行一个）<textarea rows={3} value={course.assessment_criteria} onChange={(event) => updateCourse("assessment_criteria", event.target.value)} /></label>
        <label>结果指标（每行一个）<textarea rows={3} value={course.outcome_metrics} onChange={(event) => updateCourse("outcome_metrics", event.target.value)} /></label>
        <label>人工复盘节奏<input value={course.review_cadence} onChange={(event) => updateCourse("review_cadence", event.target.value)} /></label>
        <label>AI 教练 Prompt 引用（可选）<input value={course.ai_coach_prompt_ref ?? ""} onChange={(event) => updateCourse("ai_coach_prompt_ref", event.target.value)} /></label>
        <label className="course-wide-field">内容准确性 claim 引用（每行一个）<textarea rows={2} value={course.content_accuracy_claim_refs} onChange={(event) => updateCourse("content_accuracy_claim_refs", event.target.value)} /></label>
      </div>

      <div className="course-lesson-layout">
        <aside aria-label="24 课时导航" className="course-lesson-rail">
          <div><strong>课时结构</strong><span>{completedLessons}/24 已完整</span></div>
          <ol>
            {course.lessons.map((item, index) => (
              <li key={item.lesson_id}>
                <button
                  aria-current={index === activeLesson ? "step" : undefined}
                  className={isLessonComplete(item) ? "is-complete" : ""}
                  onClick={() => setActiveLesson(index)}
                  type="button"
                >
                  <span>{item.sequence}</span>{item.title || `第 ${item.sequence} 节`}
                </button>
              </li>
            ))}
          </ol>
        </aside>

        <section aria-labelledby="active-course-lesson-title" className="course-lesson-editor">
          <div className="section-heading-row">
            <div><p className="section-kicker">Lesson {lesson.sequence} / 24</p><h3 id="active-course-lesson-title">{lesson.title || `第 ${lesson.sequence} 节待编排`}</h3></div>
            <code>{lesson.lesson_id}</code>
          </div>
          <label>课时标题<input value={lesson.title} onChange={(event) => updateLesson({ title: event.target.value })} /></label>
          <label>核心知识点<textarea rows={4} value={lesson.knowledge_point} onChange={(event) => updateLesson({ knowledge_point: event.target.value })} /></label>
          <label>家庭行动任务<textarea rows={4} value={lesson.action_task} onChange={(event) => updateLesson({ action_task: event.target.value })} /></label>
          <div className="course-asset-grid">
            <label>课件资产 ID<textarea rows={3} value={lesson.media_asset_ids.join("\n")} onChange={(event) => updateLesson({ media_asset_ids: splitRefs(event.target.value) })} placeholder="deck:lesson-01-v1" /></label>
            <label>工具 / Skill 引用<textarea rows={3} value={lesson.tool_refs.join("\n")} onChange={(event) => updateLesson({ tool_refs: splitRefs(event.target.value) })} placeholder="skill:family-dialogue@v1" /></label>
          </div>
          <p className="muted">资产 ID 目前只是引用，不代表 PPT、图片、音视频已生成、已授权或已通过质量审核。</p>
        </section>
      </div>

      <div className="course-compile-actions">
        <label className="consent-row"><input checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />我确认这只是课程设计 DRAFT，仍需证据准入、课件 QA 和人工发布决策。</label>
        <button className="secondary-button" disabled={!confirmed} onClick={compilePreview} type="button">编译 24 课时合同预览</button>
        <button className="primary-button" disabled={contractPreview || !confirmed || !preview} type="button">保存 CourseContent DRAFT</button>
      </div>
      {error ? <div className="callout" role="alert"><strong>课程合同未通过</strong><p>{error}</p></div> : null}
      {preview ? <details className="course-contract-preview"><summary>查看浏览器将提交的白名单合同</summary><pre>{preview}</pre></details> : null}
    </section>
  );
}
