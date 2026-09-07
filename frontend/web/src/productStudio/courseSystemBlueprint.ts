export const COURSE_SYSTEM_STAGE_COUNT = 6;
export const COURSE_SYSTEM_LESSON_COUNT = 24;

export type CourseSystemStage = {
  id: string;
  title: string;
  lesson_start: number;
  lesson_end: number;
  output: string;
};

export type CoursewareArtifactKind = "DECK" | "WORKSHEET" | "IMAGE" | "VIDEO" | "AUDIO" | "DOCUMENT";

export type CoursewareArtifactRef = {
  artifact_id: string;
  kind: CoursewareArtifactKind;
  version_ref: string;
  provenance_ref: string;
  qa_status: "DRAFT" | "REVIEW_REQUIRED" | "APPROVED";
};

export type CourseSystemBlueprint = {
  system_id: string;
  version: string;
  product_package_version_ref: string;
  stages: CourseSystemStage[];
  bom_lesson_sequences?: number[];
};

export type LessonDeliveryRow = {
  sequence: number;
  stage_id: string;
  stage_title: string;
  product_outcome: string;
  service_action: string;
  courseware_status: "BOM_REQUIRED" | "REVIEW_REQUIRED" | "READY";
};

export type LessonDeliveryReadiness = {
  total_lessons: number;
  bom_ready_lessons: number;
  blocked_lessons: number;
  publish_ready: boolean;
};

export const COURSE_SYSTEM_STAGES: readonly CourseSystemStage[] = [
  { id: "S1", title: "家庭觉察", lesson_start: 1, lesson_end: 4, output: "家庭问题地图" },
  { id: "S2", title: "关系连接", lesson_start: 5, lesson_end: 8, output: "沟通与关系行动卡" },
  { id: "S3", title: "成长目标", lesson_start: 9, lesson_end: 12, output: "家庭成长目标树" },
  { id: "S4", title: "日常行动", lesson_start: 13, lesson_end: 16, output: "21 天行动计划" },
  { id: "S5", title: "能力进阶", lesson_start: 17, lesson_end: 20, output: "90 天成长路径" },
  { id: "S6", title: "复盘共创", lesson_start: 21, lesson_end: 24, output: "复盘报告与下一周期需求" },
];

const SERVICE_ACTIONS = [
  "AI引导家庭完成觉察记录",
  "家长练习并记录关系行动",
  "共创家庭目标并确认计划",
  "执行每日行动，异常时升级支持",
  "阶段复盘并连接真人服务",
  "确认结果并沉淀下一周期需求",
] as const;

export function buildLessonDeliveryMatrix(stages: readonly CourseSystemStage[], bomLessonSequences: readonly number[] = []): LessonDeliveryRow[] {
  const bom = new Set(bomLessonSequences);
  return stages.flatMap((stage, stageIndex) => Array.from({ length: 4 }, (_, offset) => ({
    sequence: stage.lesson_start + offset,
    stage_id: stage.id,
    stage_title: stage.title,
    product_outcome: stage.output,
    service_action: SERVICE_ACTIONS[stageIndex],
    courseware_status: bom.has(stage.lesson_start + offset) ? "REVIEW_REQUIRED" as const : "BOM_REQUIRED" as const,
  })));
}

export function summarizeLessonDelivery(rows: readonly LessonDeliveryRow[]): LessonDeliveryReadiness {
  const bomReady = rows.filter((row) => row.courseware_status === "READY").length;
  return {
    total_lessons: rows.length,
    bom_ready_lessons: bomReady,
    blocked_lessons: rows.length - bomReady,
    publish_ready: rows.length === COURSE_SYSTEM_LESSON_COUNT && bomReady === rows.length,
  };
}

export function validateCourseSystemBlueprint(value: CourseSystemBlueprint): CourseSystemBlueprint {
  if (!value.system_id.trim() || !/^v[1-9]\d*$/.test(value.version.trim())) {
    throw new Error("COURSE_SYSTEM_ID_OR_VERSION_INVALID");
  }
  if (!value.product_package_version_ref.trim()) throw new Error("COURSE_SYSTEM_PRODUCT_PACKAGE_REQUIRED");
  if (value.stages.length !== COURSE_SYSTEM_STAGE_COUNT) throw new Error("COURSE_SYSTEM_REQUIRES_SIX_STAGES");
  let expectedStart = 1;
  for (const stage of value.stages) {
    if (stage.lesson_start !== expectedStart || stage.lesson_end - stage.lesson_start !== 3) {
      throw new Error("COURSE_SYSTEM_STAGE_COVERAGE_INVALID");
    }
    expectedStart = stage.lesson_end + 1;
  }
  if (expectedStart !== COURSE_SYSTEM_LESSON_COUNT + 1) throw new Error("COURSE_SYSTEM_MUST_COVER_24_LESSONS");
  return value;
}
