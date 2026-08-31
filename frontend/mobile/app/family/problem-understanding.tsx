import { useMemo, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
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
  submitConcern,
  submitCorrection,
  updateConcernDraft,
  updateCorrectionDraft,
} from "@/features/problem-understanding";
import { useColors } from "@/hooks/use-colors";

const SYNTHETIC_ENABLED =
  __DEV__ &&
  DEV_SYNTHETIC_PROBLEM_UNDERSTANDING.environment === "DEV" &&
  DEV_SYNTHETIC_PROBLEM_UNDERSTANDING.dataSource === "SYNTHETIC";

export default function ProblemUnderstandingRoute() {
  const colors = useColors();
  const [state, setState] = useState(createProblemUnderstandingState);
  const map = useMemo(() => buildUnderstandingMap(state), [state]);

  const handleConcernSubmit = () => {
    if (!SYNTHETIC_ENABLED) {
      setState(markUnderstandingUnavailable(state));
      return;
    }
    const submitted = submitConcern(state, createSyntheticConcern(state.concernDraft));
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
    setState(receiveUnderstanding(submitted, createSyntheticUnderstanding(correction)));
  };

  const handleConfirm = () => {
    const confirming = beginConfirmation(state);
    if (!SYNTHETIC_ENABLED || !confirming.pendingConfirmation) {
      setState(markUnderstandingUnavailable(confirming));
      return;
    }
    setState(
      applyConfirmationReceipt(
        confirming,
        createSyntheticReceipt(confirming.pendingConfirmation),
      ),
    );
  };

  return (
    <SafeAreaView style={[styles.safeArea, { backgroundColor: colors.background }]}>
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
            onSubmitCorrection={handleCorrectionSubmit}
            phase={state.phase}
          />
        ) : null}

        {state.phase === "AI_UNAVAILABLE" && state.recoveryMessage ? (
          <RecoveryNotice
            message={state.recoveryMessage}
            onRetry={() => {
              const retrying = retryUnderstanding(state);
              setState(
                SYNTHETIC_ENABLED
                  ? receiveUnderstanding(retrying, createSyntheticUnderstanding())
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
});
