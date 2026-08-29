export type ProjectionRequestPhase = "idle" | "loading" | "ready" | "error";
export type ProjectionViewState = "hidden" | "loading" | "refreshing" | "error" | "empty" | "fallback";

export interface ProjectionStateInput {
  phase: ProjectionRequestPhase;
  hasRemoteData: boolean;
  hasLocalData: boolean;
}

export function deriveProjectionViewState(input: ProjectionStateInput): ProjectionViewState {
  if (input.phase === "loading") return input.hasLocalData ? "refreshing" : "loading";
  if (input.phase === "error") return input.hasLocalData ? "fallback" : "error";
  if (input.phase === "ready" && !input.hasRemoteData) return input.hasLocalData ? "fallback" : "empty";
  return "hidden";
}

export function projectionStateLabel(state: ProjectionViewState) {
  if (state === "loading") return "正在读取家庭记录";
  if (state === "refreshing") return "正在更新家庭记录";
  if (state === "error") return "家庭记录暂时没有连上";
  if (state === "empty") return "这里还没有家庭记录";
  if (state === "fallback") return "正在使用本机内容";
  return "";
}

export function projectionCopyForUi(uiId: string | null) {
  const number = Number(uiId?.replace("UI-", ""));
  if (number >= 2 && number <= 12) return {
    loading: "正在读取家庭成长记录",
    emptyTitle: "还没有可回看的成长记录",
    emptyDetail: "可以先完成一次测评、行动或家庭小记；保存后会在这里形成连续回看。",
  };
  if (number >= 13 && number <= 18) return {
    loading: "正在读取方案与家庭权益",
    emptyTitle: "还没有方案或权益记录",
    emptyDetail: "你仍可浏览家庭成长方案；保存意向或获得权益后，这里会更新。",
  };
  if (number >= 19 && number <= 24) return {
    loading: "正在读取专家与服务记录",
    emptyTitle: "还没有咨询或活动记录",
    emptyDetail: "你可以先浏览专家和家庭活动；保存需求后会在家庭空间中回看。",
  };
  if (number >= 25 && number <= 28) return {
    loading: "正在读取家庭内容与小记",
    emptyTitle: "还没有可回看的家庭小记",
    emptyDetail: "可以先写一份家庭私有草稿；保存后可按话题和标签继续整理。",
  };
  if (number >= 29 && number <= 34) return {
    loading: "正在汇总家庭成果与记录",
    emptyTitle: "家庭成果与记录正在积累",
    emptyDetail: "完成成长行动、服务或方案意向后，这里会逐步形成家庭自己的回看。",
  };
  return {
    loading: "正在读取家庭记录",
    emptyTitle: "这里还没有同步记录",
    emptyDetail: "完成相关行动或保存一份草稿后，这里会出现可回看的内容。",
  };
}
