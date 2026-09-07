import { useEffect, useMemo, useState } from "react";
import { HttpCourseSystemApiClient, type CourseSystemApiClient } from "./courseSystemApi";
import { buildLessonDeliveryMatrix, COURSE_SYSTEM_STAGES, summarizeLessonDelivery, summarizeStageDelivery } from "./courseSystemBlueprint";
import { HttpCourseDeliveryProjectionApiClient, type CourseDeliveryProjectionApiClient } from "./courseDeliveryProjectionApi";

/** Course system is the product-level map; CourseContent and BOM remain versioned implementations. */
export function CourseSystemBlueprintPanel({ client, deliveryClient, courseContentId, tenantScope }: { client?: CourseSystemApiClient; deliveryClient?: CourseDeliveryProjectionApiClient; courseContentId?: string; tenantScope?: string }) {
  const resolvedClient = useMemo(() => client ?? new HttpCourseSystemApiClient({ tenantScope }), [client, tenantScope]);
  const resolvedDeliveryClient = useMemo(() => deliveryClient ?? new HttpCourseDeliveryProjectionApiClient({ tenantScope }), [deliveryClient, tenantScope]);
  const [stages, setStages] = useState<typeof COURSE_SYSTEM_STAGES[number][]>([]);
  const [bomLessonSequences, setBomLessonSequences] = useState<number[]>([]);
  const [bomStatuses, setBomStatuses] = useState<Record<number, { qa_status: string; rights_status: string; safety_status: string }>>({});
  const [productPackageRef, setProductPackageRef] = useState<string | null>(null);
  const [courseSystemVersion, setCourseSystemVersion] = useState<string | null>(null);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [selectedReason, setSelectedReason] = useState<string | null>(null);
  const [state, setState] = useState("尚未读取课程体系主数据；下方蓝图仅为设计模板，不代表已发布课程。");
  const [serviceProjection, setServiceProjection] = useState<{ ready_lessons: number; blocked_lessons: number; publishable_to_service: boolean } | null>(null);
  useEffect(() => { let active = true; void resolvedClient.get("course-system:family-growth").then((system) => { if (active) { setStages(system.stages); setProductPackageRef(system.product_package_version_ref); setCourseSystemVersion(system.version); setBomLessonSequences(system.bom_lesson_sequences ?? []); setBomStatuses(system.bom_lesson_statuses ?? {}); setState("已读取课程体系主数据版本：" + system.version); } }).catch(() => { if (active) setState("课程体系主数据暂不可用；蓝图仍为设计模板，不代表已发布课程。"); }); return () => { active = false; }; }, [resolvedClient]);
  useEffect(() => { if (!courseContentId) return; let active = true; void resolvedDeliveryClient.get(courseContentId).then((projection) => { if (active) setServiceProjection(projection); }).catch(() => { if (active) setServiceProjection(null); }); return () => { active = false; }; }, [courseContentId, resolvedDeliveryClient]);
  const delivery = buildLessonDeliveryMatrix(stages.length ? stages : COURSE_SYSTEM_STAGES, bomLessonSequences, bomStatuses);
  const readiness = summarizeLessonDelivery(delivery);
  const stageReadiness = summarizeStageDelivery(delivery);
  const visibleLessons = delivery.filter((lesson) => (!selectedStageId || lesson.stage_id === selectedStageId) && (!selectedReason || lesson.governance_reason === selectedReason));
  return (
    <section aria-label="课程体系蓝图" className="panel course-system-blueprint">
      <p className="section-kicker">IPD · Service Product Architecture · Course System</p>
      <h2>24 节课程如何成为服务产品</h2>
      <p className="muted">
        课程不是孤立内容，而是从市场洞察衍生出的可交付服务产品。体系层定义成长路径，课程层编排 24 节课，课件层通过 BOM 固化 PPT、工作纸、图片、视频与 Skill 的版本血缘。
      </p>
      <div className="callout" role="status"><strong>主数据状态</strong><p>{state}</p></div>
      {courseContentId ? <div className="callout" role="status" aria-label="服务交付投影状态"><strong>服务交付投影</strong><p>{serviceProjection ? `${serviceProjection.ready_lessons}/24 节已具备服务交付条件；${serviceProjection.publishable_to_service ? "允许进入服务发布" : `仍阻断 ${serviceProjection.blocked_lessons} 节`}` : "尚未读取已发布课程交付投影。"}</p></div> : null}
      <div className="callout" role="note" aria-label="产品包版本追溯"><strong>产品包版本追溯</strong><p>{productPackageRef && courseSystemVersion ? <><code>{productPackageRef}</code> → <code>course-system:family-growth@{courseSystemVersion}</code></> : "ProductPackage（待读取）"}</p></div>
      <div className="course-system-flow" role="list" aria-label="六阶段课程体系">
        {(stages.length ? stages : COURSE_SYSTEM_STAGES).map((stage) => (
          <article key={stage.id} role="listitem" className="course-system-stage">
            <span className="draft-badge">{stage.id} · {String(stage.lesson_start).padStart(2, "0")}–{String(stage.lesson_end).padStart(2, "0")}</span>
            <h3>{stage.title}</h3>
            <p>{stage.output}</p>
          </article>
        ))}
      </div>
      <div className="callout" role="region" aria-label="24课时交付矩阵">
        <strong>24课时交付矩阵</strong>
        <p className="muted">每节课必须同时绑定产品结果、家庭服务动作和课件BOM；BOM未完成时不得进入发布基线。</p>
        <p role="status" aria-label="课程发布准备度">
          交付准备度：{readiness.bom_ready_lessons}/{readiness.total_lessons} 节课件已就绪；
          {readiness.publish_ready ? "可进入发布评审" : `仍有 ${readiness.blocked_lessons} 节被 BOM 阻断`}
        </p>
        <div aria-label="全局阻断原因" role="group">
          <span>阻断构成：</span>
          {([['NO_ASSET', '缺资产'], ['QA', 'QA'], ['RIGHTS', '版权'], ['SAFETY', '安全']] as const).map(([reason, label]) => <button key={reason} type="button" aria-pressed={selectedReason === reason} onClick={() => setSelectedReason(selectedReason === reason ? null : reason)}>{label} {readiness.blocked_by_reason[reason]}</button>)}
        </div>
        <ul aria-label="阶段交付准备度">
          {stageReadiness.map((stage) => <li key={stage.stage_id}><button type="button" aria-pressed={selectedStageId === stage.stage_id} onClick={() => setSelectedStageId(selectedStageId === stage.stage_id ? null : stage.stage_id)}><strong>{stage.stage_id} · {stage.stage_title}</strong><span>{stage.ready_lessons}/{stage.total_lessons} 就绪 · {stage.next_action}</span></button></li>)}
        </ul>
        {selectedStageId || selectedReason ? <p role="status">当前筛选：{selectedStageId ? stageReadiness.find((stage) => stage.stage_id === selectedStageId)?.stage_title : "全部阶段"}{selectedReason ? ` · ${selectedReason}` : ""} · <button type="button" onClick={() => { setSelectedStageId(null); setSelectedReason(null); }}>清除全部筛选</button></p> : null}
        <div aria-label="治理原因筛选" role="group">
          {(["NO_ASSET", "QA", "RIGHTS", "SAFETY"] as const).map((reason) => <button key={reason} type="button" aria-pressed={selectedReason === reason} onClick={() => setSelectedReason(selectedReason === reason ? null : reason)}>{reason}</button>)}
          {selectedReason ? <button type="button" onClick={() => setSelectedReason(null)}>清除原因筛选</button> : null}
        </div>
        <ol aria-label="24课时交付清单">
          {visibleLessons.map((lesson) => (
            <li key={lesson.sequence}>
              <strong>第{lesson.sequence}课 · {lesson.stage_title}</strong>
              <span>{lesson.product_outcome} · {lesson.service_action} · {lesson.courseware_status} · {lesson.governance_reason === "READY" ? "治理通过" : `阻断：${lesson.governance_reason}`}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="callout" role="note">
        <strong>一条可追溯的产品链</strong>
        <p>Market Evidence → ProductPackage → Course System → CourseContent DRAFT → Courseware BOM → Human Gate → Released Service。</p>
        <p>AI 负责拆解需求、生成内容候选和多模态课件草稿；事实、证据准入、发布与对家庭的高影响动作仍由人工闸门确认。</p>
      </div>
    </section>
  );
}
