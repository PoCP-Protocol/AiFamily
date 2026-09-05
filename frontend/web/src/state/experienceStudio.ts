import type { ExperienceApiError, ExperienceDraft, ReplaySnapshot, RunStatus } from "../api/client";

export type StudioState = {
  status: RunStatus;
  draft: ExperienceDraft | null;
  error: ExperienceApiError | null;
  message: string | null;
  replay: ReplaySnapshot | null;
};

export const initialStudioState: StudioState = {
  status: "idle",
  draft: null,
  error: null,
  message: null,
  replay: null,
};

export type StudioAction =
  | { type: "VALIDATING" }
  | { type: "RUNNING" }
  | { type: "RETRYING" }
  | { type: "DRAFT_READY"; draft: ExperienceDraft }
  | { type: "FAILED"; error: ExperienceApiError }
  | { type: "HUMAN_REVIEW"; message: string }
  | { type: "DELETED" }
  | { type: "RESET" }
  | { type: "REPLAY_READY"; replay: ReplaySnapshot }
  | { type: "MESSAGE"; message: string };

export function studioReducer(state: StudioState, action: StudioAction): StudioState {
  switch (action.type) {
    case "VALIDATING":
      return { ...state, status: "validating", error: null, message: null };
    case "RUNNING":
      return { ...state, status: "running", error: null, message: null };
    case "RETRYING":
      return { ...state, status: "retrying", error: null, message: "正在使用同一幂等请求重试。" };
    case "DRAFT_READY":
      return { status: "success", draft: action.draft, error: null, message: null, replay: null };
    case "FAILED":
      return { ...state, status: action.error.status, error: action.error, message: null };
    case "HUMAN_REVIEW":
      return { ...state, status: "human_review", error: null, message: action.message };
    case "DELETED":
      return { status: "deleted", draft: null, error: null, message: "这次体验及其媒体引用已删除。", replay: null };
    case "RESET":
      return initialStudioState;
    case "MESSAGE":
      return { ...state, message: action.message };
    case "REPLAY_READY":
      return { ...state, replay: action.replay, message: "已打开这次体验的事件回放。" };
  }
}
