import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ConcernComposer,
  CorrectionConfirmation,
  DEV_SYNTHETIC_PROBLEM_UNDERSTANDING,
  RecoveryNotice,
  UnderstandingMap,
  applyConfirmationReceipt,
  beginConfirmation,
  beginCorrection,
  buildUnderstandingMap,
  createProblemUnderstandingState,
  createSyntheticConcern,
  createSyntheticReceipt,
  createSyntheticUnderstanding,
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
  updateConcernDraft,
  updateCorrectionDraft,
} from "@/features/problem-understanding";
import { useColors } from "@/hooks/use-colors";

const SYNTHETIC_ENABLED =
  __DEV__ &&
  DEV_SYNTHETIC_PROBLEM_UNDERSTANDING.environment === "DEV_ONLY" &&
  DEV_SYNTHETIC_PROBLEM_UNDERSTANDING.fixtureOnly;

const STORAGE_KEY = "aifamily:problem-understanding:dev-only:v1";

export default function ProblemUnderstandingRoute() {
  const colors = useColors();
  const [state, setState] = useState(createProblemUnderstandingState);
  const [hydrated, setHydrated] = useState(false);
  const map = useMemo(() => buildUnderstandingMap(state), [state]);

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

  const handleConcernSubmit = () => {
    if (!SYNTHETIC_ENABLED) {
      setState(markUnderstandingUnavailable(state));
      return;
    }
    const submitted = submitConcern(
      state,
      createSyntheticConcern(state.concernDraft),
    );
    setState(receiveUnderstanding(submitted, createSyntheticUnderstanding()));
  };

  const handleCorrectionSubmit = () => {
    if (!SYNTHETIC_ENABLED) {
      setState(markUnderstandingUnavailable(state));
      return;
    }
    const correction = state.correctionDraft.trim();
    const submitted = submitCorrection(state, {
      inputRef: `dev-correction-${Date.now()}`,
      kind: "CORRECTION",
      text: correction,
      createdAt: new Date().toISOString(),
    });
    setState(
      receiveUnderstanding(submitted, createSyntheticUnderstanding(correction)),
    );
  };

  const handleConfirm = async () => {
    const confirming = beginConfirmation(state);
    if (!SYNTHETIC_ENABLED || !confirming.pendingConfirmation) {
      setState(markUnderstandingUnavailable(confirming));
      return;
    }
    const confirmed = applyConfirmationReceipt(
      confirming,
      createSyntheticReceipt(confirming.pendingConfirmation),
    );
    await AsyncStorage.setItem(
      STORAGE_KEY,
      serializeProblemUnderstandingState(confirmed),
    );
    setState(confirmed);
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
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.previewPill}>
          <Text style={styles.previewText}>体验预览</Text>
        </View>

        {state.inputs.length === 0 ? (
          <ConcernComposer
            onChangeText={(value) => setState(updateConcernDraft(state, value))}
            onSubmit={handleConcernSubmit}
            phase={state.phase}
            value={state.concernDraft}
          />
        ) : null}

        {map ? <UnderstandingMap model={map} /> : null}

        {map && state.phase !== "CONFIRMED" ? (
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
        ) : null}

        {(state.phase === "AI_UNAVAILABLE" || state.phase === "ERROR") &&
        state.recoveryMessage ? (
          <RecoveryNotice
            message={state.recoveryMessage}
            onRetry={() => {
              const retrying = retryUnderstanding(state);
              setState(
                SYNTHETIC_ENABLED
                  ? receiveUnderstanding(
                      retrying,
                      createSyntheticUnderstanding(),
                    )
                  : markUnderstandingUnavailable(retrying),
              );
            }}
          />
        ) : null}

        {state.phase === "CONFIRMED" ? (
          <View style={styles.confirmedCard}>
            <Text accessibilityRole="header" style={styles.confirmedTitle}>
              我们已经把这件事说清楚了
            </Text>
            <Text style={styles.confirmedBody}>
              这会作为你们现在想先关注的方向。以后补充的观察和变化，也可以继续回到这里。
            </Text>
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
  confirmedTitle: {
    color: "#30462A",
    fontSize: 22,
    fontWeight: "800",
    lineHeight: 30,
  },
  content: {
    alignSelf: "center",
    gap: 16,
    maxWidth: 680,
    paddingBottom: 48,
    paddingHorizontal: 18,
    paddingTop: 18,
    width: "100%",
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
});
