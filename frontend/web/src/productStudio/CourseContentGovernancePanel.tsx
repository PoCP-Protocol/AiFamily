import { useMemo, useState } from "react";
import { ProductStudioApiError } from "./api";
import {
  HttpCourseContentReadApiClient,
  type CourseContentReadApiClient,
  type PublishedCourseContent,
} from "./courseContentApi";

export function CourseContentGovernancePanel({
  client = new HttpCourseContentReadApiClient(),
  contractPreview = false,
}: {
  client?: CourseContentReadApiClient;
  contractPreview?: boolean;
}) {
  const [courses, setCourses] = useState<PublishedCourseContent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<ProductStudioApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const selected = courses.find((course) => course.id === selectedId) ?? courses[0] ?? null;
  const totals = useMemo(() => ({
    lessons: courses.reduce((sum, course) => sum + course.lessons.length, 0),
    assets: courses.reduce((sum, course) => sum + course.lessons.reduce((count, lesson) => count + lesson.media_asset_ids.length, 0), 0),
  }), [courses]);

  const load = async () => {
    setBusy(true);
    setError(null);
    try {
      const loaded = await client.listPublished();
      setCourses(loaded);
      setSelectedId(loaded[0]?.id ?? null);
    } catch (cause) {
      setCourses([]);
      setSelectedId(null);
      setError(cause instanceof ProductStudioApiError
        ? cause
        : new ProductStudioApiError("INVALID_RESPONSE", "课程目录返回异常。"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-busy={busy} aria-label="Published CourseContent governance" className="panel course-governance-panel">
      <p className="section-kicker">Published read model · Governance health · No ranking</p>
      <h2>已发布课程治理观察台</h2>
      <p className="muted">严格读取已发布 CourseContent，观察课程、课时、课件引用和内容 claim 血缘；计数仅描述目录规模，不代表质量或推荐排序。</p>
      {contractPreview ? <div className="callout" role="note"><strong>开发合同预览</strong><p>生产身份、统一课程仓库与持久 Human Gate 完成前，不读取种子数据，也不宣称24门课程已上线。</p></div> : null}
      <button className="secondary-button" disabled={contractPreview || busy} onClick={() => void load()} type="button">{busy ? "读取中…" : "读取已发布课程"}</button>
      {error ? <div className="callout" role="alert"><strong>{error.code}</strong><p>{error.message}</p></div> : null}

      {courses.length ? (
        <div className="course-governance-layout">
          <aside aria-label="已发布课程目录">
            <div className="course-directory-counts"><span>{courses.length} 门课程</span><span>{totals.lessons} 个课时</span><span>{totals.assets} 个课件引用</span></div>
            <ol>
              {courses.map((course) => <li key={course.id}><button aria-current={selected?.id === course.id ? "true" : undefined} onClick={() => setSelectedId(course.id)} type="button"><strong>{course.title}</strong><span>v{course.version} · {course.lessons.length} 课时</span></button></li>)}
            </ol>
          </aside>
          {selected ? (
            <article className="course-governance-detail">
              <div className="section-heading-row"><div><span className="draft-badge">PUBLISHED · v{selected.version}</span><h3>{selected.title}</h3></div><code>{selected.id}</code></div>
              <p>{selected.problem_statement}</p>
              <dl className="compact-definition-list">
                <div><dt>学习目标</dt><dd>{selected.learning_goal}</dd></div>
                <div><dt>人工审核</dt><dd>{selected.reviewed_by} · {selected.review_reason}</dd></div>
                <div><dt>内容 claim 引用</dt><dd>{selected.content_accuracy_claim_refs.join("、")}（仅引用，未证明 receipt admission）</dd></div>
              </dl>
              <section aria-label="课程治理缺口" className="course-governance-gaps">
                <h4>当前契约缺口</h4>
                <ul>
                  <li><strong>课程体系：MISSING_FROM_CONTRACT</strong><span>六大体系分类没有进入 CourseContent/API。</span></li>
                  <li><strong>产品包血缘：{selected.product_component_id ? "COMPONENT_REF_ONLY" : "NOT_LINKED"}</strong><span>没有 ProductPackage/ProductDefinition 冻结版本与内容哈希。</span></li>
                  <li><strong>课件资产：REFERENCE_ONLY</strong><span>资产没有版本、哈希、生成 provenance、版权、安全及 QA 状态。</span></li>
                  <li><strong>证据准入：NOT_EVALUATED</strong><span>claim refs 不等同于 EvidenceVerificationReceipt 准入。</span></li>
                </ul>
              </section>
              <ol className="published-lesson-list">
                {selected.lessons.map((lesson) => (
                  <li key={lesson.lesson_id}>
                    <span>{lesson.sequence}</span>
                    <div><h4>{lesson.title}</h4><p><strong>知识：</strong>{lesson.knowledge_point}</p><p><strong>行动：</strong>{lesson.action_task}</p><small>课件：{lesson.media_asset_ids.join("、") || "无引用"} · 工具：{lesson.tool_refs.join("、") || "无引用"}</small></div>
                  </li>
                ))}
              </ol>
            </article>
          ) : null}
        </div>
      ) : <p className="empty-state">尚未读取可信的已发布课程目录。</p>}
    </section>
  );
}
