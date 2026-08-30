export type LiveViewState =
  | "loading"
  | "empty"
  | "success"
  | "denied"
  | "withdrawn"
  | "expired"
  | "unauthorized"
  | "forbidden"
  | "conflict"
  | "error"
  | "backend-missing";

export type LiveEnvironment = {
  DEV?: boolean;
};

export type LiveRecord = {
  title: string;
  speaker: string;
  applicable_scope: string;
  starts_at: string;
  ends_at: string;
  review_ref: string;
  version: string;
  status: "SCHEDULED" | "LIVE" | "WITHDRAWN" | "EXPIRED";
  family_visibility: "family-private" | "public";
  as_of: string;
  source: "DEV_FIXTURE" | "BACKEND";
  fixture: boolean;
};

export type LiveViewModel = {
  state: LiveViewState;
  record: LiveRecord | null;
};

export const XIAO_JU_DENG_FIXTURE: LiveRecord = {
  title: "小橘灯：家庭沟通中的温柔练习",
  speaker: "小橘灯老师",
  applicable_scope: "家长与照护者",
  starts_at: "2026-09-05 19:30",
  ends_at: "2026-09-05 20:30",
  review_ref: "review:H-LIVE-01",
  version: "H-LIVE-01.v1",
  status: "SCHEDULED",
  family_visibility: "family-private",
  as_of: "2026-08-30T18:00:00+08:00",
  source: "DEV_FIXTURE",
  fixture: true,
};

export const resolveLiveView = (environment: LiveEnvironment): LiveViewModel =>
  environment.DEV === true
    ? { state: "success", record: XIAO_JU_DENG_FIXTURE }
    : { state: "backend-missing", record: null };

export const LIVE_STATE_COPY: Record<LiveViewState, { label: string; message: string }> = {
  loading: { label: "正在读取", message: "正在读取可展示的专家直播信息。" },
  empty: { label: "暂无直播", message: "当前没有可展示的专家直播。" },
  success: { label: "可展示", message: "这是只读的家庭可见直播信息。" },
  denied: { label: "Denied", message: "当前直播信息不可展示。" },
  withdrawn: { label: "已撤下", message: "该直播已撤下，页面不会展示后续动作。" },
  expired: { label: "已结束", message: "该直播已结束，仅保留审核所需的只读信息。" },
  unauthorized: { label: "401 · 需要登录", message: "请登录后再查看家庭可见直播信息。" },
  forbidden: { label: "403 · 无权查看", message: "当前家庭无权查看这条直播信息。" },
  conflict: { label: "409 · 版本冲突", message: "直播信息版本发生变化，请稍后重新读取。" },
  error: { label: "读取失败", message: "直播信息暂时不可用。" },
  "backend-missing": { label: "后端未接入", message: "直播后端尚未接入，生产环境保持 fail-closed。" },
};
