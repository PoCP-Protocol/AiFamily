import { FamilyApiError } from "./family-api-client";

/** Client-side shape of the existing Journey plan projection.
 * This is a transport contract only; Journey remains the canonical owner.
 */
export interface JourneyPlanDto {
  plan_id?: string;
  status?: string;
  current_phase?: string;
  phases?: { phase: string; status: string }[];
}

export interface JourneyPlanProjectionDto {
  plan?: JourneyPlanDto | null;
}

export type JourneyPlanLoadState =
  | "idle"
  | "loading"
  | "ready"
  | "empty"
  | "blocked"
  | "error";

export type JourneyPlanErrorKind =
  | "ASSESSMENT_REQUIRED"
  | "CONSENT_OR_ACCESS_BLOCKED"
  | "CONFLICT"
  | "NOT_CONFIGURED"
  | "RETRYABLE";

export function classifyJourneyPlanError(error: unknown): JourneyPlanErrorKind {
  if (!(error instanceof FamilyApiError)) return "RETRYABLE";
  const code = error.code.toLowerCase();
  if (error.status === 401 || error.status === 403 || code.includes("consent") || code.includes("forbidden")) {
    return "CONSENT_OR_ACCESS_BLOCKED";
  }
  if (error.status === 409 || code.includes("conflict") || code.includes("already")) {
    return "CONFLICT";
  }
  if (error.code === "FAMILY_API_NOT_CONFIGURED") return "NOT_CONFIGURED";
  return "RETRYABLE";
}

export function journeyPlanErrorCopy(kind: JourneyPlanErrorKind): string {
  switch (kind) {
    case "ASSESSMENT_REQUIRED":
      return "请先完成家庭测评并确认这份理解，再进入家庭计划。";
    case "CONSENT_OR_ACCESS_BLOCKED":
      return "当前家庭授权已失效或暂不可用；请回到家庭入口重新确认。";
    case "CONFLICT":
      return "这份家庭计划刚刚发生了变化；重新读取后再继续。";
    case "NOT_CONFIGURED":
      return "家庭计划服务尚未连接；当前没有创建任何计划。";
    case "RETRYABLE":
      return "家庭计划暂时无法同步；请稍后重试。";
  }
}
