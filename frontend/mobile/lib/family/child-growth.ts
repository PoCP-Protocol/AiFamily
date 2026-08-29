import type { GrowthFocusId } from "./core-growth";
import type { UiActionReceipt, ActionReceipt } from "./family-state-core";

export type ChildChoice = "TRY_THIS" | "CHOOSE_ANOTHER" | "PAUSE_TODAY";
export type FamilyVisibility = "FAMILY_PRIVATE";

export interface ChildPracticePrompt {
  id: string;
  title: string;
  invitation: string;
  purpose: string;
  estimatedMinutes: number;
  choices: readonly { id: ChildChoice; label: string }[];
}

export interface ChildChoiceDraft {
  id: string;
  promptId: string;
  choice: ChildChoice;
  perspectiveKind: "child_choice_perspective_not_fact";
  visibility: FamilyVisibility;
  recordedAt: string;
  externalEffect: false;
}

export interface FamilyRhythmEvent {
  id: string;
  title: string;
  detail: string;
  sourceUi: `UI-${string}`;
  occurredAt: string;
  kind: "focus_selected" | "plan_viewed" | "family_action" | "camp_action" | "family_review" | "child_choice_recorded";
  evidenceBoundary: "process_event_not_outcome";
}

export interface PrivateGrowthStoryDraft {
  id: string;
  title: string;
  summary: string;
  sourceEventIds: string[];
  familyNote: string;
  visibility: FamilyVisibility;
  state: "PRIVATE_DRAFT";
  perspectiveKind: "family_narrative_not_fact_or_outcome";
  externalEffect: false;
  updatedAt: string;
}

export const CHILD_PRACTICE_PROMPTS: readonly ChildPracticePrompt[] = [
  {
    id: "choose-family-moment",
    title: "选一个想一起做的小片刻",
    invitation: "今天你可以选：一起散步十分钟、听一首歌，或者什么都不做，先休息。",
    purpose: "让孩子在低负担的家庭活动中保有选择。",
    estimatedMinutes: 10,
    choices: [
      { id: "TRY_THIS", label: "我想试试" },
      { id: "CHOOSE_ANOTHER", label: "换一个" },
      { id: "PAUSE_TODAY", label: "今天先暂停" },
    ],
  },
  {
    id: "finish-my-sentence",
    title: "把这句话补完整",
    invitation: "“我希望你先听我说完，因为……”——只说你愿意说的部分。",
    purpose: "帮助孩子表达当下需要，而不是回答系统问题。",
    estimatedMinutes: 5,
    choices: [
      { id: "TRY_THIS", label: "我想试试" },
      { id: "CHOOSE_ANOTHER", label: "换一个" },
      { id: "PAUSE_TODAY", label: "今天先暂停" },
    ],
  },
  {
    id: "design-one-reminder",
    title: "设计一个不催促的小提醒",
    invitation: "和家长一起选一个提醒方式：纸条、闹钟，或者一个约定的手势。",
    purpose: "用环境支持替代反复催促。",
    estimatedMinutes: 8,
    choices: [
      { id: "TRY_THIS", label: "我想试试" },
      { id: "CHOOSE_ANOTHER", label: "换一个" },
      { id: "PAUSE_TODAY", label: "今天先暂停" },
    ],
  },
] as const;

export function getChildPrompt(index: number) {
  const safeIndex = Math.abs(index) % CHILD_PRACTICE_PROMPTS.length;
  return CHILD_PRACTICE_PROMPTS[safeIndex];
}

export interface RhythmSourceState {
  selectedGrowthFocus: GrowthFocusId | null;
  lastReceipt: ActionReceipt | null;
  campCompletedDays: number[];
  uiActionReceipts: UiActionReceipt[];
  childChoiceDraft: ChildChoiceDraft | null;
}

export function buildFamilyRhythmEvents(state: RhythmSourceState): FamilyRhythmEvent[] {
  const events: FamilyRhythmEvent[] = [];
  if (state.selectedGrowthFocus) {
    events.push({
      id: `focus-${state.selectedGrowthFocus}`,
      title: "选择了一个家庭关注方向",
      detail: "家庭决定先从一个真实场景开始。",
      sourceUi: "UI-02",
      occurredAt: "",
      kind: "focus_selected",
      evidenceBoundary: "process_event_not_outcome",
    });
  }
  state.uiActionReceipts.forEach((receipt) => {
    const supported = receipt.screenId === "UI-04" || receipt.screenId === "UI-06" || receipt.screenId === "UI-08";
    if (!supported) return;
    events.push({
      id: `${receipt.screenId}-${receipt.kind}`,
      title: receipt.label,
      detail: receipt.message,
      sourceUi: receipt.screenId,
      occurredAt: receipt.recordedAt,
      kind: receipt.screenId === "UI-04" ? "plan_viewed" : receipt.screenId === "UI-08" ? "family_review" : "family_action",
      evidenceBoundary: "process_event_not_outcome",
    });
  });
  if (state.lastReceipt) {
    events.push({
      id: `action-${state.lastReceipt.actionId}`,
      title: "记录了一次家庭行动",
      detail: "家庭完成并记录了一个低负担行动。",
      sourceUi: "UI-09",
      occurredAt: state.lastReceipt.checkedInAt,
      kind: "family_action",
      evidenceBoundary: "process_event_not_outcome",
    });
  }
  state.campCompletedDays.slice(-4).forEach((day) => {
    events.push({
      id: `camp-day-${day}`,
      title: `完成成长营 Day ${day} 的家庭行动`,
      detail: "这是一条参与记录，不代表成长结果。",
      sourceUi: "UI-09",
      occurredAt: "",
      kind: "camp_action",
      evidenceBoundary: "process_event_not_outcome",
    });
  });
  if (state.childChoiceDraft) {
    events.push({
      id: state.childChoiceDraft.id,
      title: state.childChoiceDraft.choice === "PAUSE_TODAY" ? "家庭尊重了孩子今天暂停的选择" : "孩子参与选择了一次轻松练习",
      detail: "这是一次家庭记录的选择，不用于评价孩子。",
      sourceUi: "UI-10",
      occurredAt: state.childChoiceDraft.recordedAt,
      kind: "child_choice_recorded",
      evidenceBoundary: "process_event_not_outcome",
    });
  }
  return events.slice(-8);
}

export function buildPrivateGrowthStory(events: FamilyRhythmEvent[], familyNote = ""): PrivateGrowthStoryDraft {
  const safeEvents = events.slice(-4);
  const summary = safeEvents.length
    ? `我们一起回看了 ${safeEvents.length} 个已经发生的家庭片段。它们记录尝试，不证明孩子或家庭已经产生确定变化。`
    : "故事还没有开始。可以先从一次家庭愿意记录的小行动出发。";
  return {
    id: "private-growth-story-current",
    title: "我们一起尝试过的几件小事",
    summary,
    sourceEventIds: safeEvents.map((event) => event.id),
    familyNote: familyNote.trim(),
    visibility: "FAMILY_PRIVATE",
    state: "PRIVATE_DRAFT",
    perspectiveKind: "family_narrative_not_fact_or_outcome",
    externalEffect: false,
    updatedAt: new Date().toISOString(),
  };
}
