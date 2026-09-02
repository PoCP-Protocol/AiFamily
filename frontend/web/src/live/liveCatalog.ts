export type LiveViewState =
  | "loading"
  | "empty"
  | "success"
  | "denied"
  | "withdrawn"
  | "expired"
  | "unauthorized"
  | "forbidden"
  | "not-found"
  | "conflict"
  | "error"
  | "backend-missing"
  | "provider-missing";

export type LiveEnvironment = {
  DEV?: boolean;
  VITE_MEDIA_PLAYBACK_DTO?: string;
  VITE_LIVE_INTERACTION_BASE_URL?: string;
  VITE_LIVE_INTERACTION_WS_URL?: string;
  VITE_LIVE_REPLAY_BASE_URL?: string;
  VITE_LIVE_REPLAY_KNOWLEDGE_BASE_URL?: string;
  VITE_LIVE_COMMERCE_BASE_URL?: string;
  VITE_LIVE_OBSERVABILITY_BASE_URL?: string;
  VITE_LIVE_CONTROL_BASE_URL?: string;
  VITE_LIVE_AI_BASE_URL?: string;
  VITE_LIVE_INCIDENT_BASE_URL?: string;
};

export const resolveLiveInteractionBaseUrl = (environment: LiveEnvironment): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_INTERACTION_BASE_URL) return undefined;
  try {
    const url = new URL(environment.VITE_LIVE_INTERACTION_BASE_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export const resolveLiveInteractionWsUrl = (environment: LiveEnvironment): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_INTERACTION_WS_URL) return undefined;
  try {
    const url = new URL(environment.VITE_LIVE_INTERACTION_WS_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    if (!["ws:", "wss:"].includes(url.protocol)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export const resolveLiveReplayBaseUrl = (environment: LiveEnvironment): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_REPLAY_BASE_URL) return undefined;
  try {
    const url = new URL(environment.VITE_LIVE_REPLAY_BASE_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export const resolveLiveReplayKnowledgeBaseUrl = (
  environment: LiveEnvironment,
): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_REPLAY_KNOWLEDGE_BASE_URL) {
    return undefined;
  }
  try {
    const url = new URL(environment.VITE_LIVE_REPLAY_KNOWLEDGE_BASE_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export const resolveLiveCommerceBaseUrl = (environment: LiveEnvironment): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_COMMERCE_BASE_URL) return undefined;
  try {
    const url = new URL(environment.VITE_LIVE_COMMERCE_BASE_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export const resolveLiveObservabilityBaseUrl = (environment: LiveEnvironment): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_OBSERVABILITY_BASE_URL) return undefined;
  try {
    const url = new URL(environment.VITE_LIVE_OBSERVABILITY_BASE_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export const resolveLiveControlBaseUrl = (environment: LiveEnvironment): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_CONTROL_BASE_URL) return undefined;
  try {
    const url = new URL(environment.VITE_LIVE_CONTROL_BASE_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export const resolveLiveAIBaseUrl = (environment: LiveEnvironment): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_AI_BASE_URL) return undefined;
  try {
    const url = new URL(environment.VITE_LIVE_AI_BASE_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export const resolveLiveIncidentBaseUrl = (environment: LiveEnvironment): string | undefined => {
  if (environment.DEV !== true || !environment.VITE_LIVE_INCIDENT_BASE_URL) return undefined;
  try {
    const url = new URL(environment.VITE_LIVE_INCIDENT_BASE_URL);
    if (!["localhost", "127.0.0.1"].includes(url.hostname)) return undefined;
    return url.toString().replace(/\/$/, "");
  } catch {
    return undefined;
  }
};

export type LiveSectionKey = "live-now" | "upcoming" | "ended";

export type MediaPlaybackState = "LIVE" | "DISCONNECTED" | "RESTARTED" | "ENDED" | "STOPPED" | "REVOKED" | "FAILED";

export type MediaPlaybackDto = {
  source: "synthetic";
  fixture_only: true;
  state: MediaPlaybackState;
  media_session_ref: string;
  playback_url: string;
  control_url?: string;
  sha256?: string;
};

export type LiveRecord = {
  session_ref: string;
  title: string;
  speaker: string;
  problem_tags: string[];
  expert_summary: string;
  applicable_scope: string;
  starts_at: string;
  ends_at: string;
  review_ref: string;
  version: string;
  status: "SCHEDULED" | "LIVE" | "WITHDRAWN" | "EXPIRED";
  approval_status: "APPROVED" | "DENIED";
  expiry_state: "UNEXPIRED" | "EXPIRED";
  audience_scope: "FAMILY";
  family_visibility: "family-private" | "public";
  capabilities: {
    favorite: "LOCKED";
    replay: "LOCKED";
  };
  playback_state: "WAITING_AUTHORIZATION" | MediaPlaybackState;
  playback?: MediaPlaybackDto;
  section: LiveSectionKey;
  as_of: string;
  source: "SANDBOX_SYNTHETIC" | "BACKEND";
  fixture_only: boolean;
};

export type LiveSections = Record<LiveSectionKey, LiveRecord[]>;

export type LiveViewModel = {
  state: LiveViewState;
  record: LiveRecord | null;
  sections?: LiveSections;
};

export const XIAO_JU_DENG_FIXTURE: LiveRecord = {
  session_ref: "live.synthetic.upcoming.1",
  title: "小橘灯：家庭沟通中的温柔练习",
  speaker: "小橘灯老师",
  problem_tags: ["家庭沟通", "照护者"],
  expert_summary: "围绕家庭沟通中的具体场景，练习可核对、可暂停的表达方式。",
  applicable_scope: "家长与照护者",
  starts_at: "2026-09-05 19:30",
  ends_at: "2026-09-05 20:30",
  review_ref: "review:H-LIVE-01",
  version: "H-LIVE-01.v1",
  status: "SCHEDULED",
  approval_status: "APPROVED",
  expiry_state: "UNEXPIRED",
  audience_scope: "FAMILY",
  family_visibility: "family-private",
  capabilities: {
    favorite: "LOCKED",
    replay: "LOCKED",
  },
  playback_state: "WAITING_AUTHORIZATION",
  section: "upcoming",
  as_of: "2026-08-30T18:00:00+08:00",
  source: "SANDBOX_SYNTHETIC",
  fixture_only: true,
};

export const XIAO_JU_DENG_ENDED_FIXTURE: LiveRecord = {
  session_ref: "live.synthetic.ended.1",
  title: "小橘灯：冲突后的家庭复盘",
  speaker: "小橘灯老师",
  problem_tags: ["冲突复盘", "家庭沟通"],
  expert_summary: "Sandbox 合成内容：仅用于展示已结束场次与回看门控状态。",
  applicable_scope: "家长与照护者",
  starts_at: "2026-08-22 19:30",
  ends_at: "2026-08-22 20:30",
  review_ref: "review:H-LIVE-01",
  version: "H-LIVE-01.v1",
  status: "EXPIRED",
  approval_status: "APPROVED",
  expiry_state: "EXPIRED",
  audience_scope: "FAMILY",
  family_visibility: "family-private",
  capabilities: {
    favorite: "LOCKED",
    replay: "LOCKED",
  },
  playback_state: "WAITING_AUTHORIZATION",
  section: "ended",
  as_of: "2026-08-30T18:00:00+08:00",
  source: "SANDBOX_SYNTHETIC",
  fixture_only: true,
};

export const LIVE_SANDBOX_SECTIONS: LiveSections = {
  "live-now": [],
  upcoming: [XIAO_JU_DENG_FIXTURE],
  ended: [XIAO_JU_DENG_ENDED_FIXTURE],
};

const MEDIA_STATES: MediaPlaybackState[] = ["LIVE", "DISCONNECTED", "RESTARTED", "ENDED", "STOPPED", "REVOKED", "FAILED"];

const parseMediaPlaybackDto = (environment: LiveEnvironment): MediaPlaybackDto | null => {
  if (environment.DEV !== true || !environment.VITE_MEDIA_PLAYBACK_DTO) return null;
  try {
    const value = JSON.parse(environment.VITE_MEDIA_PLAYBACK_DTO) as Partial<MediaPlaybackDto>;
    if (
      value.source !== "synthetic" ||
      value.fixture_only !== true ||
      typeof value.media_session_ref !== "string" ||
      typeof value.playback_url !== "string" ||
      !MEDIA_STATES.includes(value.state as MediaPlaybackState)
    ) {
      return null;
    }
    const playbackUrl = new URL(value.playback_url);
    if (!["localhost", "127.0.0.1"].includes(playbackUrl.hostname)) return null;
    if (value.control_url) {
      const controlUrl = new URL(value.control_url);
      if (!["localhost", "127.0.0.1"].includes(controlUrl.hostname)) return null;
    }
    return {
      source: "synthetic",
      fixture_only: true,
      state: value.state as MediaPlaybackState,
      media_session_ref: value.media_session_ref,
      playback_url: value.playback_url,
      ...(typeof value.control_url === "string" ? { control_url: value.control_url } : {}),
      ...(typeof value.sha256 === "string" ? { sha256: value.sha256 } : {}),
    };
  } catch {
    return null;
  }
};

const CONTROL_HEADERS = {
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.adult",
  "X-Actor-Role": "ADULT_VIEWER",
};

export async function loadLiveControlView(
  environment: LiveEnvironment,
  signal?: AbortSignal,
): Promise<LiveViewModel> {
  const baseUrl = resolveLiveControlBaseUrl(environment);
  if (!baseUrl) return { state: "backend-missing", record: null };
  const response = await fetch(
    `${baseUrl}/sandbox/live-control/families/family.synthetic.alpha/sessions`,
    { cache: "no-store", headers: CONTROL_HEADERS, signal },
  );
  if (!response.ok) return { state: responseState(response.status), record: null };
  const payload = await response.json() as unknown;
  if (!Array.isArray(payload)) return { state: "error", record: null };
  const playback = parseMediaPlaybackDto(environment);
  const records = payload.map((item) => parseControlRecord(item, playback));
  if (records.some((record) => record === null)) return { state: "error", record: null };
  const safeRecords = records as LiveRecord[];
  const sections: LiveSections = { "live-now": [], upcoming: [], ended: [] };
  for (const record of safeRecords) sections[record.section].push(record);
  const record = sections["live-now"][0] ?? sections.upcoming[0] ?? null;
  return record ? { state: "success", record, sections } : { state: "empty", record: null, sections };
}

function parseControlRecord(value: unknown, playback: MediaPlaybackDto | null): LiveRecord | null {
  if (!isObject(value) || containsForbiddenLiveField(value)) return null;
  if (
    typeof value.session_ref !== "string" ||
    typeof value.title !== "string" ||
    typeof value.speaker !== "string" ||
    !Array.isArray(value.problem_tags) ||
    value.problem_tags.some((tag) => typeof tag !== "string") ||
    typeof value.expert_summary !== "string" ||
    typeof value.applicable_scope !== "string" ||
    typeof value.starts_at !== "string" ||
    typeof value.ends_at !== "string" ||
    typeof value.review_ref !== "string" ||
    typeof value.version !== "string" ||
    typeof value.as_of !== "string" ||
    value.source !== "SANDBOX_SYNTHETIC" ||
    value.fixture_only !== true ||
    value.external_effect !== false ||
    value.audit_mode !== "SANDBOX_RECEIPT_ONLY" ||
    value.approval_status !== "APPROVED" ||
    value.expiry_state !== "UNEXPIRED" ||
    value.audience_scope !== "FAMILY" ||
    value.family_visibility !== "family-private" ||
    !["SCHEDULED", "LIVE"].includes(String(value.status)) ||
    !["live-now", "upcoming"].includes(String(value.section))
  ) return null;
  const attachedPlayback = playback?.media_session_ref === value.session_ref ? playback : undefined;
  return {
    session_ref: value.session_ref,
    title: value.title,
    speaker: value.speaker,
    problem_tags: value.problem_tags as string[],
    expert_summary: value.expert_summary,
    applicable_scope: value.applicable_scope,
    starts_at: value.starts_at,
    ends_at: value.ends_at,
    review_ref: value.review_ref,
    version: value.version,
    status: value.status as "SCHEDULED" | "LIVE",
    approval_status: "APPROVED",
    expiry_state: "UNEXPIRED",
    audience_scope: "FAMILY",
    family_visibility: "family-private",
    capabilities: { favorite: "LOCKED", replay: "LOCKED" },
    playback_state: attachedPlayback?.state ?? "WAITING_AUTHORIZATION",
    ...(attachedPlayback ? { playback: attachedPlayback } : {}),
    section: value.section as "live-now" | "upcoming",
    as_of: value.as_of,
    source: "SANDBOX_SYNTHETIC",
    fixture_only: true,
  };
}

function containsForbiddenLiveField(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsForbiddenLiveField);
  if (!isObject(value)) return false;
  return Object.entries(value).some(
    ([key, nested]) =>
      /room|token|child|score|ranking|purchase_cta/i.test(key) ||
      containsForbiddenLiveField(nested),
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function responseState(status: number): LiveViewState {
  return {
    401: "unauthorized",
    403: "forbidden",
    404: "not-found",
    409: "conflict",
    503: "provider-missing",
  }[status] as LiveViewState | undefined ?? "error";
}

export const resolveLiveView = (environment: LiveEnvironment): LiveViewModel => {
  if (environment.DEV !== true) return { state: "backend-missing", record: null };
  const playback = parseMediaPlaybackDto(environment);
  if (!playback) return { state: "success", record: XIAO_JU_DENG_FIXTURE, sections: LIVE_SANDBOX_SECTIONS };
  const liveRecord: LiveRecord = {
    ...XIAO_JU_DENG_FIXTURE,
    session_ref: playback.media_session_ref,
    status: playback.state === "ENDED" ? "EXPIRED" : "LIVE",
    expiry_state: playback.state === "ENDED" ? "EXPIRED" : "UNEXPIRED",
    playback_state: playback.state,
    playback,
    section: "live-now",
  };
  return {
    state: "success",
    record: liveRecord,
    sections: { "live-now": [liveRecord], upcoming: [], ended: LIVE_SANDBOX_SECTIONS.ended },
  };
};

export const LIVE_STATE_COPY: Record<LiveViewState, { label: string; message: string }> = {
  loading: { label: "正在读取", message: "正在读取可展示的专家直播信息。" },
  empty: { label: "暂无直播", message: "当前没有可展示的专家直播。" },
  success: { label: "可展示", message: "这是只读的家庭可见直播信息。" },
  denied: { label: "Denied", message: "当前直播信息不可展示。" },
  withdrawn: { label: "已撤下", message: "该直播已撤下，页面不会展示后续动作。" },
  expired: { label: "已结束", message: "该直播已结束，仅保留审核所需的只读信息。" },
  unauthorized: { label: "401 · 需要登录", message: "请登录后再查看家庭可见直播信息。" },
  forbidden: { label: "403 · 无权查看", message: "当前家庭无权查看这条直播信息。" },
  "not-found": { label: "404 · 未找到", message: "未找到可展示的直播信息。" },
  conflict: { label: "409 · 版本冲突", message: "直播信息版本发生变化，请稍后重新读取。" },
  error: { label: "读取失败", message: "直播信息暂时不可用。" },
  "backend-missing": { label: "后端未接入", message: "直播后端尚未接入，生产环境保持 fail-closed。" },
  "provider-missing": { label: "Provider missing", message: "直播提供方不可用，页面保持 fail-closed。" },
};
