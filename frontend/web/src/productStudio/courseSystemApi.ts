import { ProductStudioApiError, type ProductStudioFetch } from "./api";
import type { CourseSystemBlueprint, CourseSystemStage } from "./courseSystemBlueprint";

export interface CourseSystemApiClient { get(systemId: string): Promise<CourseSystemBlueprint>; }

type Options = { baseUrl?: string; fetchImpl?: ProductStudioFetch };
const stages = (value: unknown): CourseSystemStage[] => {
  if (!Array.isArray(value) || value.length !== 6) throw new ProductStudioApiError("INVALID_RESPONSE", "课程体系阶段数据无效。");
  return value.map((item, index) => {
    if (!item || typeof item !== "object") throw new ProductStudioApiError("INVALID_RESPONSE", `第${index + 1}阶段无效。`);
    const row = item as Record<string, unknown>;
    if (typeof row.stage_id !== "string" || typeof row.title !== "string" || typeof row.outcome !== "string"
      || !Number.isInteger(row.lesson_start) || !Number.isInteger(row.lesson_end)) {
      throw new ProductStudioApiError("INVALID_RESPONSE", `第${index + 1}阶段字段无效。`);
    }
    return { id: row.stage_id, title: row.title, lesson_start: Number(row.lesson_start), lesson_end: Number(row.lesson_end), output: row.outcome };
  });
};

export function validateCourseSystem(value: unknown): CourseSystemBlueprint {
  if (!value || typeof value !== "object") throw new ProductStudioApiError("INVALID_RESPONSE", "课程体系响应无效。");
  const row = value as Record<string, unknown>;
  if (typeof row.system_id !== "string" || typeof row.tenant_scope !== "string" || !Number.isInteger(row.version)
    || typeof row.product_package_version_ref !== "string") throw new ProductStudioApiError("INVALID_RESPONSE", "课程体系主数据字段无效。");
  const bomStatuses: Record<number, { qa_status: string; rights_status: string; safety_status: string }> = {};
  const bom = Array.isArray(row.bom) ? row.bom.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const sequence = (item as Record<string, unknown>).lesson_sequence;
    if (!Number.isInteger(sequence)) return [];
    const artifacts = Array.isArray((item as Record<string, unknown>).artifacts) ? (item as Record<string, unknown>).artifacts as unknown[] : [];
    if (!artifacts.length) throw new ProductStudioApiError("INVALID_RESPONSE", "课程体系BOM行必须包含课件资产。");
    const statuses = artifacts.map((asset) => {
      if (!asset || typeof asset !== "object" || Array.isArray(asset)) throw new ProductStudioApiError("INVALID_RESPONSE", "课程体系BOM课件资产结构无效。");
      const artifact = asset as Record<string, unknown>;
      if (typeof artifact.artifact_id !== "string" || !artifact.artifact_id.trim() || typeof artifact.version_ref !== "string" || !artifact.version_ref.trim() || typeof artifact.provenance_ref !== "string" || !artifact.provenance_ref.trim()) throw new ProductStudioApiError("INVALID_RESPONSE", "课程体系BOM课件血缘字段缺失。");
      const qa = String(artifact?.qa_status ?? "DRAFT");
      const rights = String(artifact?.rights_status ?? "UNKNOWN");
      const safety = String(artifact?.safety_status ?? "UNKNOWN");
      if (!["DRAFT", "REVIEW_REQUIRED", "APPROVED"].includes(qa) || !["UNKNOWN", "CLEARED", "RESTRICTED"].includes(rights) || !["UNKNOWN", "REVIEW_REQUIRED", "CLEARED"].includes(safety)) throw new ProductStudioApiError("INVALID_RESPONSE", "课程体系BOM治理状态无效。");
      return { qa_status: qa, rights_status: rights, safety_status: safety };
    });
    bomStatuses[Number(sequence)] = { qa_status: statuses.every((status) => status.qa_status === "APPROVED") ? "APPROVED" : "REVIEW_REQUIRED", rights_status: statuses.every((status) => status.rights_status === "CLEARED") ? "CLEARED" : "UNKNOWN", safety_status: statuses.every((status) => status.safety_status === "CLEARED") ? "CLEARED" : "REVIEW_REQUIRED" };
    return [Number(sequence)];
  }) : [];
  if (new Set(bom).size !== bom.length || bom.some((sequence) => sequence < 1 || sequence > 24)) {
    throw new ProductStudioApiError("INVALID_RESPONSE", "课程体系BOM课次必须在1-24范围内且不可重复。");
  }
  const normalized = { system_id: row.system_id, version: `v${row.version}`, product_package_version_ref: row.product_package_version_ref, stages: stages(row.stages), bom_lesson_sequences: bom, bom_lesson_statuses: bomStatuses };
  return normalized;
}

export class HttpCourseSystemApiClient implements CourseSystemApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: ProductStudioFetch;
  constructor(options: Options = {}) { this.baseUrl = options.baseUrl ?? ""; this.fetchImpl = options.fetchImpl ?? fetch; }
  async get(systemId: string): Promise<CourseSystemBlueprint> {
    const response = await this.fetchImpl(`${this.baseUrl}/product-intelligence/courses/system/${encodeURIComponent(systemId)}`);
    if (!response.ok) throw new ProductStudioApiError(response.status === 404 ? "NOT_FOUND" : "UNAVAILABLE", "课程体系暂不可读取。", response.status);
    return validateCourseSystem(await response.json());
  }
}
