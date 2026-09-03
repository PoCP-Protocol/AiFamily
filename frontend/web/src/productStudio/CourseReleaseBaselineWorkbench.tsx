import { useMemo, useState } from "react";
import {
  compileCourseReleaseBaseline,
  createCourseReleaseBaselineForm,
  isReleaseLessonComplete,
  type CourseReleaseLessonBinding,
} from "./courseReleaseBaseline";

const splitRefs = (value: string) => value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);

export function CourseReleaseBaselineWorkbench() {
  const [form, setForm] = useState(createCourseReleaseBaselineForm);
  const [activeLesson, setActiveLesson] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  const [compiled, setCompiled] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const completeLessons = useMemo(() => form.lessons.filter(isReleaseLessonComplete).length, [form.lessons]);
  const lesson = form.lessons[activeLesson];

  const updateField = (field: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setCompiled(null);
    setError(null);
  };
  const updateLesson = (patch: Partial<CourseReleaseLessonBinding>) => {
    setForm((current) => ({
      ...current,
      lessons: current.lessons.map((item, index) => index === activeLesson ? { ...item, ...patch } : item),
    }));
    setCompiled(null);
    setError(null);
  };
  const compile = () => {
    try {
      setCompiled(JSON.stringify(compileCourseReleaseBaseline(form), null, 2));
      setError(null);
    } catch (cause) {
      const code = cause instanceof Error ? cause.message : "RELEASE_BASELINE_INVALID";
      const lessonNumber = code.match(/RELEASE_LESSON_(\d+)/)?.[1];
      setError(lessonNumber
        ? `第 ${lessonNumber} 节尚未绑定版本化 Lesson、ContentSpec、AssetBundle 和 Skill。`
        : `发布基线未通过：${code}`);
      setCompiled(null);
    }
  };

  return (
    <section aria-label="Course release baseline compiler" className="panel course-release-workbench">
      <p className="section-kicker">PLM · Immutable BOM · Release candidate · Human decision</p>
      <h2>课程发布基线与课件 BOM</h2>
      <p className="muted">冻结课程体系、产品包、产品定义、24课时、内容规格、课件资产包、Skill、Prompt、安全策略与证据回执的精确版本。编译成功仍只是 DRAFT。</p>
      <div className="callout" role="note"><strong>合同预览，尚无生产发布路由</strong><p>浏览器不能创建 RELEASED 状态、回滚目标或人工决定；正式发布必须由服务端 Human Gate 生成。</p></div>

      <div className="course-release-lineage-grid">
        <label>课程体系版本引用<input value={form.course_system_version_ref} onChange={(event) => updateField("course_system_version_ref", event.target.value)} placeholder="course-system:learning-growth@v1" /></label>
        <label>ProductPackage 版本引用<input value={form.product_package_version_ref} onChange={(event) => updateField("product_package_version_ref", event.target.value)} placeholder="product-package:family-rhythm@v2" /></label>
        <label className="course-wide-field">ProductPackage 内容哈希（SHA-256）<input value={form.product_package_content_hash} onChange={(event) => updateField("product_package_content_hash", event.target.value)} /></label>
        <label>ProductDefinition 版本引用<input value={form.product_definition_version_ref} onChange={(event) => updateField("product_definition_version_ref", event.target.value)} /></label>
        <label>CourseContent 版本引用<input value={form.course_content_version_ref} onChange={(event) => updateField("course_content_version_ref", event.target.value)} /></label>
        <label>安全策略版本引用<input value={form.safety_policy_version_ref} onChange={(event) => updateField("safety_policy_version_ref", event.target.value)} /></label>
        <label>Prompt Bundle 版本引用<input value={form.prompt_bundle_version_ref} onChange={(event) => updateField("prompt_bundle_version_ref", event.target.value)} /></label>
        <label>Locale<input value={form.locale} onChange={(event) => updateField("locale", event.target.value)} /></label>
        <label>交付渠道<input value={form.delivery_channel} onChange={(event) => updateField("delivery_channel", event.target.value)} /></label>
        <label className="course-wide-field">证据回执引用（每行一个）<textarea rows={3} value={form.evidence_receipt_refs} onChange={(event) => updateField("evidence_receipt_refs", event.target.value)} /></label>
        <label className="course-wide-field">发布说明<textarea rows={3} value={form.release_notes} onChange={(event) => updateField("release_notes", event.target.value)} /></label>
      </div>

      <div className="course-release-bom-layout">
        <aside aria-label="24课时发布 BOM 导航">
          <div><strong>不可变课时 BOM</strong><span>{completeLessons}/24 已绑定</span></div>
          <ol>{form.lessons.map((item, index) => <li key={item.sequence}><button aria-current={index === activeLesson ? "step" : undefined} className={isReleaseLessonComplete(item) ? "is-complete" : ""} onClick={() => setActiveLesson(index)} type="button"><span>{item.sequence}</span></button></li>)}</ol>
        </aside>
        <section aria-labelledby="release-lesson-title" className="course-release-lesson-editor">
          <div className="section-heading-row"><div><p className="section-kicker">BOM position {lesson.sequence} / 24</p><h3 id="release-lesson-title">第 {lesson.sequence} 节版本绑定</h3></div><span>{isReleaseLessonComplete(lesson) ? "BOUND" : "INCOMPLETE"}</span></div>
          <label>Lesson 版本引用<input value={lesson.lesson_version_ref} onChange={(event) => updateLesson({ lesson_version_ref: event.target.value })} /></label>
          <label>ContentSpec 版本引用<input value={lesson.content_spec_version_ref} onChange={(event) => updateLesson({ content_spec_version_ref: event.target.value })} /></label>
          <label>AssetBundle 版本引用<input value={lesson.asset_bundle_version_ref} onChange={(event) => updateLesson({ asset_bundle_version_ref: event.target.value })} /></label>
          <label>Skill 版本引用（每行一个）<textarea rows={3} value={lesson.skill_version_refs.join("\n")} onChange={(event) => updateLesson({ skill_version_refs: splitRefs(event.target.value) })} /></label>
          <p className="muted">AssetBundle 应冻结 PPT/讲义/工作纸/图片/音视频等具体 AssetVersion；本合同不把资产 ID 当作已审核文件。</p>
        </section>
      </div>

      <div className="course-compile-actions">
        <label className="consent-row"><input checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />我确认该结果只是发布基线 DRAFT，仍需证据准入、资产 QA 和人工发布决定。</label>
        <button className="secondary-button" disabled={!confirmed} onClick={compile} type="button">编译发布基线 DRAFT</button>
        <button className="primary-button" disabled type="button">提交人工发布门禁</button>
      </div>
      {error ? <div className="callout" role="alert"><strong>发布基线未通过</strong><p>{error}</p></div> : null}
      {compiled ? <details className="course-contract-preview"><summary>查看不可变发布基线合同</summary><pre>{compiled}</pre></details> : null}
    </section>
  );
}
