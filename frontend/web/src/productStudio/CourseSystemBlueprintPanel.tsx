import { useEffect, useState } from "react";
import { HttpCourseSystemApiClient, type CourseSystemApiClient } from "./courseSystemApi";
import { COURSE_SYSTEM_STAGES } from "./courseSystemBlueprint";

/** Course system is the product-level map; CourseContent and BOM remain versioned implementations. */
export function CourseSystemBlueprintPanel({ client = new HttpCourseSystemApiClient() }: { client?: CourseSystemApiClient }) {
  const [stages, setStages] = useState<typeof COURSE_SYSTEM_STAGES[number][]>([]);
  const [state, setState] = useState("尚未读取课程体系主数据；下方蓝图仅为设计模板，不代表已发布课程。");
  useEffect(() => { let active = true; void client.get("course-system:family-growth").then((system) => { if (active) { setStages(system.stages); setState("已读取课程体系主数据版本：" + system.version); } }).catch(() => { if (active) setState("课程体系主数据暂不可用；蓝图仍为设计模板，不代表已发布课程。"); }); return () => { active = false; }; }, [client]);
  return (
    <section aria-label="课程体系蓝图" className="panel course-system-blueprint">
      <p className="section-kicker">IPD · Service Product Architecture · Course System</p>
      <h2>24 节课程如何成为服务产品</h2>
      <p className="muted">
        课程不是孤立内容，而是从市场洞察衍生出的可交付服务产品。体系层定义成长路径，课程层编排 24 节课，课件层通过 BOM 固化 PPT、工作纸、图片、视频与 Skill 的版本血缘。
      </p>
      <div className="callout" role="status"><strong>主数据状态</strong><p>{state}</p></div>
      <div className="course-system-flow" role="list" aria-label="六阶段课程体系">
        {(stages.length ? stages : COURSE_SYSTEM_STAGES).map((stage) => (
          <article key={stage.id} role="listitem" className="course-system-stage">
            <span className="draft-badge">{stage.id} · {String(stage.lesson_start).padStart(2, "0")}–{String(stage.lesson_end).padStart(2, "0")}</span>
            <h3>{stage.title}</h3>
            <p>{stage.output}</p>
          </article>
        ))}
      </div>
      <div className="callout" role="note">
        <strong>一条可追溯的产品链</strong>
        <p>Market Evidence → ProductPackage → Course System → CourseContent DRAFT → Courseware BOM → Human Gate → Released Service。</p>
        <p>AI 负责拆解需求、生成内容候选和多模态课件草稿；事实、证据准入、发布与对家庭的高影响动作仍由人工闸门确认。</p>
      </div>
    </section>
  );
}
