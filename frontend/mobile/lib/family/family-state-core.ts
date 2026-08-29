import { getCamp21Day } from "./camp21";
import type { TodayAction } from "./domain";
import type { ControlledActionKind } from "./ui-action-policies";
import type { FamilyLoop } from "./ui-registry";
import type { AssessmentAnswer, GrowthFocusId } from "./core-growth";
import type { ChildChoice, ChildChoiceDraft, PrivateGrowthStoryDraft } from "./child-growth";
import type { CommerceIntentDraft, FamilyInvitationDraft, FamilyStudyGroupDraft } from "./commerce-entitlements";
import type { ActivityInterestDraft, ConsultationChannel, ConsultationNeedDraft } from "./service-support";
import type { CommunityAiTagDraft, CommunityInteractionDraft, CommunityPostDraft, CommunityPostKind } from "./community-content";

export interface ActionReceipt {
  actionId: string;
  checkedInAt: string;
  reflection: string;
  reflectionKind: "perspective";
  externalEffect: false;
}

export interface UiActionReceipt {
  screenId: `UI-${string}`;
  loop: FamilyLoop;
  kind: ControlledActionKind;
  label: string;
  message: string;
  recordedAt: string;
  externalEffect: false;
}

export type FamilyFlowSource = "LOCAL_DRAFT" | "REMOTE_PROJECTION" | "REMOTE_RECEIPT" | "FALLBACK";
export type FamilyRemoteSyncState = "NOT_STARTED" | "SYNCING" | "SYNCED" | "ERROR";

export interface FamilyMobileState {
  hydrated: boolean;
  todayAction: TodayAction;
  activeCampDay: number | null;
  campStarted: boolean;
  campCurrentDay: number;
  campCompletedDays: number[];
  lastReceipt: ActionReceipt | null;
  /** Cross-screen observability; this is transport/process state, not an outcome. */
  flowId: string | null;
  lastAction: string | null;
  remoteSyncState: FamilyRemoteSyncState;
  source: FamilyFlowSource;
  updatedAt: string;
  retryable: boolean;
  uiActionReceipts: UiActionReceipt[];
  selectedGrowthFocus: GrowthFocusId | null;
  assessmentAnswers: Record<string, AssessmentAnswer>;
  assessmentSyncState: "local" | "syncing" | "synced" | "error";
  activeOnboardingId: string | null;
  childChoiceDraft: ChildChoiceDraft | null;
  privateGrowthStory: PrivateGrowthStoryDraft | null;
  commerceIntentDraft: CommerceIntentDraft | null;
  invitationDraft: FamilyInvitationDraft | null;
  studyGroupDraft: FamilyStudyGroupDraft | null;
  consultationNeedDraft: ConsultationNeedDraft | null;
  activityInterestDraft: ActivityInterestDraft | null;
  communityPostDraft: CommunityPostDraft | null;
  communityInteractionDrafts: Record<string, CommunityInteractionDraft>;
}

export type FamilyMobileAction =
  | { type: "hydrate"; payload: Partial<FamilyMobileState> }
  | { type: "start_action" }
  | { type: "activate_camp_day"; day: number }
  | { type: "start_camp" }
  | { type: "complete_action"; reflection: string }
  | { type: "set_flow_status"; flowId?: string | null; lastAction?: string | null; remoteSyncState?: FamilyRemoteSyncState; source?: FamilyFlowSource; retryable?: boolean }
  | { type: "skip_action" }
  | { type: "record_ui_action"; payload: Omit<UiActionReceipt, "recordedAt" | "externalEffect"> }
  | { type: "select_growth_focus"; focus: GrowthFocusId }
  | { type: "answer_assessment"; questionId: string; answer: AssessmentAnswer }
  | { type: "set_assessment_sync"; state: FamilyMobileState["assessmentSyncState"] }
  | { type: "set_active_onboarding"; onboardingId: string | null }
  | { type: "record_child_choice"; promptId: string; choice: ChildChoice }
  | { type: "save_private_growth_story"; draft: PrivateGrowthStoryDraft }
  | { type: "save_commerce_intent_draft"; productRef: string; productVersion: number; productTitle: string }
  | { type: "sync_commerce_intent_receipt"; intentId: string; entitlementId: string }
  | { type: "save_invitation_draft"; productRef: string; productTitle: string }
  | { type: "save_study_group_draft"; productRef: string; productTitle: string; familyCount: 2 | 3 | 4 }
  | { type: "cancel_study_group_draft" }
  | { type: "save_consultation_need_draft"; offeringRef: string; offeringVersion: number; offeringTitle: string; providerName: string; channel: ConsultationChannel; slotRef: string | null; timePreference: string; ageBand: string; needFocus: string }
  | { type: "sync_consultation_need_receipt"; bookingRequestId: string; serviceRecordId: string }
  | { type: "save_activity_interest_draft"; activityRef: string; activityTitle: string }
  | { type: "save_community_post_draft"; kind: CommunityPostKind; title: string; body: string; topic: string; aiTagDraft?: CommunityAiTagDraft }
  | { type: "toggle_community_bookmark"; exchangeRef: string }
  | { type: "toggle_community_follow"; exchangeRef: string }
  | { type: "save_community_response_draft"; exchangeRef: string; responseText: string };

const initialAction: TodayAction = {
  id: "family-listen-one-sentence",
  title: "先听完孩子的一句话，再回应",
  reason: "今天不急着讲道理，只练习一次完整倾听。",
  estimatedMinutes: 10,
  suggestedWords: "我先听你说完，你慢慢说。",
  observationPrompt: "孩子说完后，语气或身体状态有什么变化？",
  status: "not_started",
  recommendationSource: "rule_based_dev",
};

export const initialFamilyMobileState: FamilyMobileState = {
  hydrated: false,
  todayAction: initialAction,
  activeCampDay: null,
  campStarted: false,
  campCurrentDay: 1,
  campCompletedDays: [],
  lastReceipt: null,
  flowId: null,
  lastAction: null,
  remoteSyncState: "NOT_STARTED",
  source: "LOCAL_DRAFT",
  updatedAt: new Date(0).toISOString(),
  retryable: false,
  uiActionReceipts: [],
  selectedGrowthFocus: null,
  assessmentAnswers: {},
  assessmentSyncState: "local",
  activeOnboardingId: null,
  childChoiceDraft: null,
  privateGrowthStory: null,
  commerceIntentDraft: null,
  invitationDraft: null,
  studyGroupDraft: null,
  consultationNeedDraft: null,
  activityInterestDraft: null,
  communityPostDraft: null,
  communityInteractionDrafts: {},
};

export function familyMobileReducer(state: FamilyMobileState, action: FamilyMobileAction): FamilyMobileState {
  if (action.type === "hydrate") return { ...state, ...action.payload, hydrated: true, updatedAt: action.payload.updatedAt ?? state.updatedAt };
  if (action.type === "set_flow_status") return {
    ...state,
    ...(action.flowId === undefined ? {} : { flowId: action.flowId }),
    ...(action.lastAction === undefined ? {} : { lastAction: action.lastAction }),
    ...(action.remoteSyncState === undefined ? {} : { remoteSyncState: action.remoteSyncState }),
    ...(action.source === undefined ? {} : { source: action.source }),
    ...(action.retryable === undefined ? {} : { retryable: action.retryable }),
    updatedAt: new Date().toISOString(),
  };
  if (action.type === "start_action") return { ...state, lastAction: "START_TODAY_ACTION", updatedAt: new Date().toISOString(), todayAction: { ...state.todayAction, status: "in_progress" } };
  if (action.type === "start_camp") return { ...state, lastAction: "START_CAMP", updatedAt: new Date().toISOString(), campStarted: true };
  if (action.type === "activate_camp_day") {
    const day = getCamp21Day(action.day);
    return {
      ...state,
      lastAction: `ACTIVATE_CAMP_DAY:${day.day}`,
      flowId: `camp21-day-${day.day}`,
      source: "LOCAL_DRAFT",
      remoteSyncState: "NOT_STARTED",
      retryable: false,
      updatedAt: new Date().toISOString(),
      campStarted: true,
      activeCampDay: day.day,
      campCurrentDay: day.day,
      lastReceipt: null,
      todayAction: {
        id: `camp21-day-${day.day}`,
        title: day.title,
        reason: day.intent,
        estimatedMinutes: day.estimatedMinutes,
        suggestedWords: day.suggestedWords,
        observationPrompt: day.observationPrompt,
        status: "not_started",
        recommendationSource: "reviewed_course",
      },
    };
  }
  if (action.type === "complete_action") {
    const completedDays = state.activeCampDay && !state.campCompletedDays.includes(state.activeCampDay)
      ? [...state.campCompletedDays, state.activeCampDay].sort((a, b) => a - b)
      : state.campCompletedDays;
    const nextCampDay = state.activeCampDay ? Math.min(21, state.activeCampDay + 1) : state.campCurrentDay;
    return {
      ...state,
      lastAction: "COMPLETE_TODAY_ACTION",
      source: "LOCAL_DRAFT",
      remoteSyncState: "NOT_STARTED",
      retryable: false,
      updatedAt: new Date().toISOString(),
      todayAction: { ...state.todayAction, status: "checked_in" },
      campCompletedDays: completedDays,
      campCurrentDay: nextCampDay,
      lastReceipt: {
        actionId: state.todayAction.id,
        checkedInAt: new Date().toISOString(),
        reflection: action.reflection.trim(),
        reflectionKind: "perspective",
        externalEffect: false,
      },
    };
  }
  if (action.type === "skip_action") return { ...state, lastAction: "SKIP_TODAY_ACTION", updatedAt: new Date().toISOString(), todayAction: { ...state.todayAction, status: "skipped" } };
  if (action.type === "record_ui_action") {
    const receipt: UiActionReceipt = {
      ...action.payload,
      recordedAt: new Date().toISOString(),
      externalEffect: false,
    };
    const withoutReplay = state.uiActionReceipts.filter((item) => !(item.screenId === receipt.screenId && item.kind === receipt.kind));
    return { ...state, uiActionReceipts: [...withoutReplay, receipt] };
  }
  if (action.type === "select_growth_focus") {
    return {
      ...state,
      selectedGrowthFocus: action.focus,
      assessmentAnswers: {},
      assessmentSyncState: "local",
    };
  }
  if (action.type === "answer_assessment") {
    return {
      ...state,
      assessmentAnswers: { ...state.assessmentAnswers, [action.questionId]: action.answer },
      assessmentSyncState: "local",
    };
  }
  if (action.type === "set_assessment_sync") return { ...state, assessmentSyncState: action.state };
  if (action.type === "set_active_onboarding") return { ...state, activeOnboardingId: action.onboardingId };
  if (action.type === "record_child_choice") {
    return {
      ...state,
      childChoiceDraft: {
        id: `child-choice-${action.promptId}`,
        promptId: action.promptId,
        choice: action.choice,
        perspectiveKind: "child_choice_perspective_not_fact",
        visibility: "FAMILY_PRIVATE",
        recordedAt: new Date().toISOString(),
        externalEffect: false,
      },
    };
  }
  if (action.type === "save_private_growth_story") return { ...state, privateGrowthStory: action.draft };
  if (action.type === "save_commerce_intent_draft") {
    return {
      ...state,
      commerceIntentDraft: {
        id: `commerce-intent-${action.productRef}`,
        productRef: action.productRef,
        productVersion: action.productVersion,
        productTitle: action.productTitle,
        state: "LOCAL_DRAFT",
        intentId: null,
        entitlementId: null,
        visibility: "FAMILY_PRIVATE",
        externalEffect: false,
        recordedAt: new Date().toISOString(),
      },
    };
  }
  if (action.type === "sync_commerce_intent_receipt" && state.commerceIntentDraft) {
    return {
      ...state,
      commerceIntentDraft: {
        ...state.commerceIntentDraft,
        state: "SYNCED_RECEIPT",
        intentId: action.intentId,
        entitlementId: action.entitlementId,
      },
    };
  }
  if (action.type === "save_invitation_draft") {
    return {
      ...state,
      invitationDraft: {
        id: `invitation-draft-${action.productRef}`,
        productRef: action.productRef,
        productTitle: action.productTitle,
        state: "PRIVATE_DRAFT",
        visibility: "FAMILY_PRIVATE",
        externalEffect: false,
        recordedAt: new Date().toISOString(),
      },
    };
  }
  if (action.type === "save_study_group_draft") {
    return {
      ...state,
      studyGroupDraft: {
        id: `study-group-draft-${action.productRef}`,
        productRef: action.productRef,
        productTitle: action.productTitle,
        familyCount: action.familyCount,
        state: "PRIVATE_DRAFT",
        visibility: "FAMILY_PRIVATE",
        externalEffect: false,
        recordedAt: new Date().toISOString(),
      },
    };
  }
  if (action.type === "cancel_study_group_draft" && state.studyGroupDraft) {
    return { ...state, studyGroupDraft: { ...state.studyGroupDraft, state: "CANCELLED" } };
  }
  if (action.type === "save_consultation_need_draft") {
    return {
      ...state,
      consultationNeedDraft: {
        id: `consultation-need-${action.offeringRef}`,
        offeringRef: action.offeringRef,
        offeringVersion: action.offeringVersion,
        offeringTitle: action.offeringTitle,
        providerName: action.providerName,
        channel: action.channel,
        slotRef: action.slotRef,
        timePreference: action.timePreference,
        ageBand: action.ageBand,
        needFocus: action.needFocus,
        consentAcknowledged: true,
        state: "LOCAL_DRAFT",
        bookingRequestId: null,
        serviceRecordId: null,
        visibility: "FAMILY_PRIVATE",
        externalEffect: false,
        recordedAt: new Date().toISOString(),
      },
    };
  }
  if (action.type === "sync_consultation_need_receipt" && state.consultationNeedDraft) {
    return {
      ...state,
      consultationNeedDraft: {
        ...state.consultationNeedDraft,
        state: "SYNCED_RECEIPT",
        bookingRequestId: action.bookingRequestId,
        serviceRecordId: action.serviceRecordId,
      },
    };
  }
  if (action.type === "save_activity_interest_draft") {
    return {
      ...state,
      activityInterestDraft: {
        id: `activity-interest-${action.activityRef}`,
        activityRef: action.activityRef,
        activityTitle: action.activityTitle,
        state: "PRIVATE_DRAFT",
        visibility: "FAMILY_PRIVATE",
        externalEffect: false,
        recordedAt: new Date().toISOString(),
      },
    };
  }
  if (action.type === "save_community_post_draft") {
    return {
      ...state,
      communityPostDraft: {
        id: state.communityPostDraft?.id ?? `community-post-${Date.now()}`,
        kind: action.kind,
        title: action.title.trim(),
        body: action.body.trim(),
        topic: action.topic,
        state: "PRIVATE_DRAFT",
        visibility: "FAMILY_PRIVATE",
        perspectiveKind: "PARENT_PERSPECTIVE_NOT_FACT",
        privacyReview: "ACKNOWLEDGED",
        ...(action.aiTagDraft ? { aiTagDraft: action.aiTagDraft } : {}),
        recordedAt: new Date().toISOString(),
        externalEffect: false,
      },
    };
  }
  if (action.type === "toggle_community_bookmark" || action.type === "toggle_community_follow" || action.type === "save_community_response_draft") {
    const current = state.communityInteractionDrafts[action.exchangeRef] ?? {
      exchangeRef: action.exchangeRef,
      bookmarked: false,
      following: false,
      responseText: "",
      state: "PRIVATE_DRAFT" as const,
      visibility: "FAMILY_PRIVATE" as const,
      perspectiveKind: "PARENT_PERSPECTIVE_NOT_PUBLIC_COMMENT" as const,
      updatedAt: new Date().toISOString(),
      externalEffect: false as const,
    };
    const next: CommunityInteractionDraft = {
      ...current,
      bookmarked: action.type === "toggle_community_bookmark" ? !current.bookmarked : current.bookmarked,
      following: action.type === "toggle_community_follow" ? !current.following : current.following,
      responseText: action.type === "save_community_response_draft" ? action.responseText.trim() : current.responseText,
      updatedAt: new Date().toISOString(),
    };
    return { ...state, communityInteractionDrafts: { ...state.communityInteractionDrafts, [action.exchangeRef]: next } };
  }
  return state;
}
