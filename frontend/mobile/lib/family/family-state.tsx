import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useState, type PropsWithChildren } from "react";

import { familyMobileReducer, initialFamilyMobileState, type FamilyMobileState, type FamilyFlowSource, type FamilyRemoteSyncState } from "./family-state-core";
import type { UiActionPolicy } from "./ui-action-policies";
import type { AssessmentAnswer, GrowthFocusId } from "./core-growth";
import type { ChildChoice, PrivateGrowthStoryDraft } from "./child-growth";
import type { ConsultationChannel } from "./service-support";
import type { CommunityAiTagDraft, CommunityPostKind } from "./community-content";

const STORAGE_KEY = "family-ai-mobile-state-v1";

interface FamilyMobileContextValue extends FamilyMobileState {
  reloadLocalState(): Promise<void>;
  startAction(): void;
  completeAction(reflection: string): void;
  skipAction(): void;
  setFlowStatus(status: { flowId?: string | null; lastAction?: string | null; remoteSyncState?: FamilyRemoteSyncState; source?: FamilyFlowSource; retryable?: boolean }): void;
  startCamp(): void;
  activateCampDay(day: number): void;
  recordUiAction(policy: UiActionPolicy, label: string): void;
  selectGrowthFocus(focus: GrowthFocusId): void;
  answerAssessment(questionId: string, answer: AssessmentAnswer): void;
  setAssessmentSyncState(state: FamilyMobileState["assessmentSyncState"]): void;
  setActiveOnboardingId(onboardingId: string | null): void;
  recordChildChoice(promptId: string, choice: ChildChoice): void;
  savePrivateGrowthStory(draft: PrivateGrowthStoryDraft): void;
  saveCommerceIntentDraft(productRef: string, productVersion: number, productTitle: string): void;
  syncCommerceIntentReceipt(intentId: string, entitlementId: string): void;
  saveInvitationDraft(productRef: string, productTitle: string): void;
  saveStudyGroupDraft(productRef: string, productTitle: string, familyCount: 2 | 3 | 4): void;
  cancelStudyGroupDraft(): void;
  saveConsultationNeedDraft(offeringRef: string, offeringVersion: number, offeringTitle: string, providerName: string, channel: ConsultationChannel, slotRef: string | null, timePreference: string, ageBand: string, needFocus: string): void;
  syncConsultationNeedReceipt(bookingRequestId: string, serviceRecordId: string): void;
  saveActivityInterestDraft(activityRef: string, activityTitle: string): void;
  saveCommunityPostDraft(kind: CommunityPostKind, title: string, body: string, topic: string, aiTagDraft?: CommunityAiTagDraft): void;
  toggleCommunityBookmark(exchangeRef: string): void;
  toggleCommunityFollow(exchangeRef: string): void;
  saveCommunityResponseDraft(exchangeRef: string, responseText: string): void;
}

const FamilyMobileContext = createContext<FamilyMobileContextValue | null>(null);

export function FamilyMobileProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(familyMobileReducer, initialFamilyMobileState);
  const [hasHydrated, setHasHydrated] = useState(false);

  useEffect(() => {
    let active = true;
    let settled = false;
    const finishHydration = (payload: Record<string, never> | FamilyMobileState) => {
      if (!active || settled) return;
      settled = true;
      dispatch({ type: "hydrate", payload });
      setHasHydrated(true);
    };
    const fallbackTimer = setTimeout(() => {
      finishHydration({});
    }, 1200);
    AsyncStorage.getItem(STORAGE_KEY)
      .then((value) => {
        finishHydration(value ? JSON.parse(value) : {});
      })
      .catch(() => {
        finishHydration({});
      });
    return () => { active = false; clearTimeout(fallbackTimer); };
  }, []);

  useEffect(() => {
    if (!hasHydrated) return;
    const persistedState = { ...state, hydrated: undefined };
    void AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(persistedState));
  }, [hasHydrated, state]);

  const reloadLocalState = useCallback(async () => {
    const stored = await AsyncStorage.getItem(STORAGE_KEY).catch(() => null);
    dispatch({ type: "hydrate", payload: stored ? JSON.parse(stored) : {} });
  }, []);

  const value = useMemo<FamilyMobileContextValue>(() => ({
    ...state,
    reloadLocalState,
    startAction: () => dispatch({ type: "start_action" }),
    completeAction: (reflection) => dispatch({ type: "complete_action", reflection }),
    skipAction: () => dispatch({ type: "skip_action" }),
    setFlowStatus: (status) => dispatch({ type: "set_flow_status", ...status }),
    startCamp: () => dispatch({ type: "start_camp" }),
    activateCampDay: (day) => dispatch({ type: "activate_camp_day", day }),
    recordUiAction: (policy, label) => dispatch({
      type: "record_ui_action",
      payload: {
        screenId: policy.screenId,
        loop: policy.loop,
        kind: policy.kind,
        label,
        message: policy.receiptMessage,
      },
    }),
    selectGrowthFocus: (focus) => dispatch({ type: "select_growth_focus", focus }),
    answerAssessment: (questionId, answer) => dispatch({ type: "answer_assessment", questionId, answer }),
    setAssessmentSyncState: (nextState) => dispatch({ type: "set_assessment_sync", state: nextState }),
    setActiveOnboardingId: (onboardingId) => dispatch({ type: "set_active_onboarding", onboardingId }),
    recordChildChoice: (promptId, choice) => dispatch({ type: "record_child_choice", promptId, choice }),
    savePrivateGrowthStory: (draft) => dispatch({ type: "save_private_growth_story", draft }),
    saveCommerceIntentDraft: (productRef, productVersion, productTitle) => dispatch({ type: "save_commerce_intent_draft", productRef, productVersion, productTitle }),
    syncCommerceIntentReceipt: (intentId, entitlementId) => dispatch({ type: "sync_commerce_intent_receipt", intentId, entitlementId }),
    saveInvitationDraft: (productRef, productTitle) => dispatch({ type: "save_invitation_draft", productRef, productTitle }),
    saveStudyGroupDraft: (productRef, productTitle, familyCount) => dispatch({ type: "save_study_group_draft", productRef, productTitle, familyCount }),
    cancelStudyGroupDraft: () => dispatch({ type: "cancel_study_group_draft" }),
    saveConsultationNeedDraft: (offeringRef, offeringVersion, offeringTitle, providerName, channel, slotRef, timePreference, ageBand, needFocus) => dispatch({ type: "save_consultation_need_draft", offeringRef, offeringVersion, offeringTitle, providerName, channel, slotRef, timePreference, ageBand, needFocus }),
    syncConsultationNeedReceipt: (bookingRequestId, serviceRecordId) => dispatch({ type: "sync_consultation_need_receipt", bookingRequestId, serviceRecordId }),
    saveActivityInterestDraft: (activityRef, activityTitle) => dispatch({ type: "save_activity_interest_draft", activityRef, activityTitle }),
    saveCommunityPostDraft: (kind, title, body, topic, aiTagDraft) => dispatch({ type: "save_community_post_draft", kind, title, body, topic, aiTagDraft }),
    toggleCommunityBookmark: (exchangeRef) => dispatch({ type: "toggle_community_bookmark", exchangeRef }),
    toggleCommunityFollow: (exchangeRef) => dispatch({ type: "toggle_community_follow", exchangeRef }),
    saveCommunityResponseDraft: (exchangeRef, responseText) => dispatch({ type: "save_community_response_draft", exchangeRef, responseText }),
  }), [reloadLocalState, state]);

  return <FamilyMobileContext.Provider value={value}>{children}</FamilyMobileContext.Provider>;
}

export function useFamilyMobile() {
  const value = useContext(FamilyMobileContext);
  if (!value) throw new Error("useFamilyMobile must be used within FamilyMobileProvider");
  return value;
}
