import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useMemo, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ConcernComposer,
  CorrectionConfirmation,
  type GeneratedUnderstandingResponse,
  RecoveryNotice,
  UnderstandingMap,
  beginConfirmation,
  beginCorrection,
  buildUnderstandingMap,
  createProblemUnderstandingState,
  markUnderstandingUnavailable,
  receiveUnderstanding,
  retryUnderstanding,
  restoreProblemUnderstandingState,
  resumeSavedProblemUnderstanding,
  saveProblemUnderstandingForLater,
  serializeProblemUnderstandingState,
  skipClarification,
  submitConcern,
  submitCorrection,
  toUnderstandingDraft,
  updateConcernDraft,
  updateCorrectionDraft,
} from "@/features/problem-understanding";
import { useColors } from "@/hooks/use-colors";
import {
  createMobileRequestId,
  familyApi,
} from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";

const STORAGE_KEY = "aifamily:problem-understanding:generative:v2";

export default function ProblemUnderstandingRoute() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { width } = useWindowDimensions();
  const [state, setState] = useState(createProblemUnderstandingState);
  const [hydrated, setHydrated] = useState(false);
  const [reviewWidth, setReviewWidth] = useState(0);
  const map = useMemo(() => buildUnderstandingMap(state), [state]);
  const isCompact = width < 480;
  const isDesktop = width >= 960;
  const isWideReview = reviewWidth >= 760;

  useEffect(() => {
    let active = true;
    void AsyncStorage.getItem(STORAGE_KEY)
      .then((saved) => {
        if (active) setState(restoreProblemUnderstandingState(saved));
      })
      .finally(() => {
        if (active) setHydrated(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const requestUnderstanding = async (
    submitted: typeof state,
    inputRef: string,
    text: string,
    revision: number,
    priorDraftArtifactHash: string | null,
  ) => {
    if (
      session.status !== "connected" ||
      !session.token ||
      !session.selectedFamily
    ) {
      setState(markUnderstandingUnavailable(submitted));
      return;
    }
    try {
      const response =
        await familyApi.generateFamilyUnderstanding<GeneratedUnderstandingResponse>(
          session.token,
          session.selectedFamily.family_id,
          {
            run_id: `${inputRef}:v${revision}`,
            tenant_id: session.selectedFamily.tenant_id,
            guardian_input_ref: inputRef,
            guardian_text: text,
            revision,
            prior_draft_artifact_hash: priorDraftArtifactHash,
          },
        );
      setState(
        receiveUnderstanding(
          submitted,
          toUnderstandingDraft(
            response,
            session.selectedFamily.tenant_id,
            session.selectedFamily.family_id,
          ),
        ),
      );
    } catch {
      setState(markUnderstandingUnavailable(submitted));
    }
  };

  const handleConcernSubmit = () => {
    const text = state.concernDraft.trim();
    const inputRef = createMobileRequestId("guardian-concern");
    const submitted = submitConcern(
      state,
      {
        inputRef,
        kind: "CONCERN",
        text,
        createdAt: new Date().toISOString(),
      },
    );
    setState(submitted);
    void requestUnderstanding(submitted, inputRef, text, 1, null);
  };

  const handleCorrectionSubmit = () => {
    const correction = state.correctionDraft.trim();
    const inputRef = createMobileRequestId("guardian-correction");
    const priorDraft = state.drafts.at(-1) ?? null;
    const submitted = submitCorrection(state, {
      inputRef,
      kind: "CORRECTION",
      text: correction,
      createdAt: new Date().toISOString(),
    });
    setState(submitted);
    void requestUnderstanding(
      submitted,
      inputRef,
      [...state.inputs.map((item) => item.text), correction].join("\n\n补充或修正："),
      (priorDraft?.draftVersion ?? 1) + 1,
      priorDraft?.reviewedDraftRef ?? null,
    );
  };

  const handleConfirm = () => {
    const confirming = beginConfirmation(state);
    setState(
      confirming.pendingConfirmation
        ? confirming
        : {
            ...state,
            recoveryMessage: "确认服务正在连接，请先保存这次理解，稍后继续。",
          },
    );
  };

  const handleSaveAndExit = async () => {
    const saved = saveProblemUnderstandingForLater(
      state,
      new Date().toISOString(),
    );
    await AsyncStorage.setItem(
      STORAGE_KEY,
      serializeProblemUnderstandingState(saved),
    );
    setState(saved);
  };

  const handleDelete = async () => {
    await AsyncStorage.removeItem(STORAGE_KEY);
    setState(createProblemUnderstandingState());
  };

  const handleStartNew = async () => {
    await AsyncStorage.removeItem(STORAGE_KEY);
    setState(createProblemUnderstandingState());
  };

  if (!hydrated) {
    return (
      <SafeAreaView
        style={[styles.safeArea, { backgroundColor: colors.background }]}
      >
        <View accessibilityRole="progressbar" style={styles.loadingCard}>
          <Text style={styles.confirmedTitle}>正在找回你上次保存的内容…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (state.phase === "SAVED") {
    return (
      <SafeAreaView
        style={[styles.safeArea, { backgroundColor: colors.background }]}
      >
        <View style={styles.savedScreen}>
          <View style={styles.confirmedCard}>
            <Text accessibilityRole="header" style={styles.confirmedTitle}>
              已为你保存
            </Text>
            <Text style={styles.confirmedBody}>
              下次打开会回到这份理解。你也可以现在继续，或删除已保存内容。
            </Text>
          </View>
          <Pressable
            accessibilityRole="button"
            onPress={() => setState(resumeSavedProblemUnderstanding(state))}
            style={styles.primaryButton}
          >
            <Text style={styles.primaryButtonText}>继续这次对话</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={handleDelete}
            style={styles.secondaryButton}
          >
            <Text style={styles.secondaryButtonText}>删除已保存内容</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={[styles.safeArea, { backgroundColor: colors.background }]}
    >
      <ScrollView
        contentContainerStyle={[
          styles.content,
          isCompact && styles.contentCompact,
          isDesktop && styles.contentWide,
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.hero}>
          <View style={styles.previewPill}>
            <Text style={styles.previewText}>家庭对话体验</Text>
          </View>
          <Text accessibilityRole="header" style={styles.heroTitle}>
            今天，想先把哪件事说清楚？
          </Text>
          <Text style={styles.heroBody}>
            说一件正在困扰你的事。你会先看到我们的理解，修正后再由你确认。
          </Text>
          <View
            accessibilityLabel="说出困扰，确认理解，获得下一步"
            style={styles.steps}
          >
            <Text style={styles.stepActive}>1 说出困扰</Text>
            <Text style={styles.stepArrow}>→</Text>
            <Text style={styles.step}>2 确认理解</Text>
            <Text style={styles.stepArrow}>→</Text>
            <Text style={styles.step}>3 获得下一步</Text>
          </View>
        </View>

        {state.inputs.length === 0 ? (
          <ConcernComposer
            onChangeText={(value) => setState(updateConcernDraft(state, value))}
            onSubmit={handleConcernSubmit}
            phase={state.phase}
            value={state.concernDraft}
          />
        ) : null}

        {map ? (
          <View
            onLayout={(event) => setReviewWidth(event.nativeEvent.layout.width)}
            style={[
              styles.reviewLayout,
              isWideReview && styles.reviewLayoutWide,
            ]}
          >
            <View style={styles.reviewMain}>
              <UnderstandingMap model={map} />
            </View>
            {state.phase !== "CONFIRMED" ? (
              <View
                style={[
                  styles.reviewRail,
                  isWideReview && styles.reviewRailWide,
                ]}
              >
                <CorrectionConfirmation
                  canConfirm={map.canConfirm}
                  canCorrect={map.canCorrect}
                  correction={state.correctionDraft}
                  onBeginCorrection={() => setState(beginCorrection(state))}
                  onChangeCorrection={(value) =>
                    setState(updateCorrectionDraft(state, value))
                  }
                  onConfirm={handleConfirm}
                  onSaveAndExit={handleSaveAndExit}
                  onSkipClarification={() => setState(skipClarification(state))}
                  onSubmitCorrection={handleCorrectionSubmit}
                  phase={state.phase}
                />
              </View>
            ) : null}
          </View>
        ) : null}

        {(state.phase === "AI_UNAVAILABLE" || state.phase === "ERROR") &&
        state.recoveryMessage ? (
          <RecoveryNotice
            message={state.recoveryMessage}
            onRetry={() => {
              const retrying = retryUnderstanding(state);
              const lastInput = retrying.inputs.at(-1);
              const priorDraft = retrying.drafts.at(-1) ?? null;
              setState(retrying);
              if (!lastInput) {
                setState(markUnderstandingUnavailable(retrying));
                return;
              }
              void requestUnderstanding(
                retrying,
                lastInput.inputRef,
                retrying.inputs.map((item) => item.text).join("\n\n补充或修正："),
                priorDraft ? priorDraft.draftVersion + 1 : 1,
                priorDraft?.reviewedDraftRef ?? null,
              );
            }}
          />
        ) : null}

        {state.phase === "CONFIRMED" ? (
          <View style={styles.confirmedLayout}>
            <View style={styles.confirmedCard}>
              <Text accessibilityRole="header" style={styles.confirmedTitle}>
                这次理解已经确认
              </Text>
              <Text style={styles.confirmedBody}>
                你确认的是当前想先关注的方向。以后有新情况，还可以回来补充。
              </Text>
              <Pressable
                accessibilityRole="button"
                onPress={handleStartNew}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryButtonText}>补充新情况</Text>
              </Pressable>
              <Text style={styles.confirmedBody}>
                也可以开始一次新的理解，之前确认的内容仍会保留在家庭记录中。
              </Text>
              <Pressable
                accessibilityRole="button"
                onPress={handleStartNew}
                style={styles.primaryButton}
              >
                <Text style={styles.primaryButtonText}>开始新的理解</Text>
              </Pressable>
            </View>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  confirmedBody: {
    color: "#5F5147",
    fontSize: 16,
    lineHeight: 25,
  },
  confirmedCard: {
    backgroundColor: "#EEF4E9",
    borderColor: "#C8D8BE",
    borderRadius: 22,
    borderWidth: 1,
    gap: 10,
    padding: 20,
  },
  confirmedLayout: { gap: 14, maxWidth: 720 },
  confirmedTitle: {
    color: "#30462A",
    fontSize: 22,
    fontWeight: "800",
    lineHeight: 30,
  },
  content: {
    alignSelf: "center",
    gap: 16,
    maxWidth: 1180,
    paddingBottom: 48,
    paddingHorizontal: 32,
    paddingTop: 28,
    width: "100%",
  },
  contentCompact: { paddingHorizontal: 16, paddingTop: 16 },
  contentWide: { gap: 24, paddingBottom: 72, paddingTop: 44 },
  hero: { gap: 12, maxWidth: 760 },
  heroBody: {
    color: "#64584F",
    fontSize: 16,
    lineHeight: 25,
    maxWidth: 650,
  },
  heroTitle: {
    color: "#2D261F",
    fontSize: 30,
    fontWeight: "800",
    lineHeight: 39,
  },
  loadingCard: { margin: 24, padding: 20 },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#D8663A",
    borderRadius: 16,
    padding: 15,
  },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "700" },
  previewPill: {
    alignSelf: "flex-start",
    backgroundColor: "#F3E8DF",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  previewText: {
    color: "#775747",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.4,
  },
  reviewLayout: { gap: 18 },
  reviewLayoutWide: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 28,
  },
  reviewMain: { flex: 1, minWidth: 0 },
  reviewRail: { width: "100%" },
  reviewRailWide: { flexShrink: 0, width: 340 },
  safeArea: { flex: 1 },
  savedScreen: {
    alignSelf: "center",
    gap: 12,
    maxWidth: 680,
    padding: 20,
    width: "100%",
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: "#F8EEE7",
    borderColor: "#DFA889",
    borderRadius: 16,
    borderWidth: 1,
    padding: 15,
  },
  secondaryButtonText: { color: "#7C3D27", fontSize: 16, fontWeight: "700" },
  step: { color: "#786B61", fontSize: 13, fontWeight: "700" },
  stepActive: { color: "#A74624", fontSize: 13, fontWeight: "800" },
  stepArrow: { color: "#BFA99A", fontSize: 13 },
  steps: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 7,
  },
});
