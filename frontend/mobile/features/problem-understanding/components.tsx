import type { ReactNode } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";

import { PROBLEM_UNDERSTANDING_COPY } from "./controller";
import type {
  ProblemUnderstandingPhase,
  UnderstandingMapViewModel,
} from "./model";

interface ConcernComposerProps {
  value: string;
  phase: ProblemUnderstandingPhase;
  onChangeText: TextInputProps["onChangeText"];
  onSubmit: () => void;
}

export function ConcernComposer({
  value,
  phase,
  onChangeText,
  onSubmit,
}: ConcernComposerProps) {
  const busy = phase === "UNDERSTANDING";
  const disabled = busy || value.trim().length === 0;

  return (
    <View style={styles.surface}>
      <Text accessibilityRole="header" style={styles.title}>
        {PROBLEM_UNDERSTANDING_COPY.heading}
      </Text>
      <Text style={styles.supporting}>{PROBLEM_UNDERSTANDING_COPY.prompt}</Text>
      <TextInput
        accessibilityLabel="最近发生的事"
        multiline
        onChangeText={onChangeText}
        placeholder="比如：最近一说到写作业，我们就很容易吵起来……"
        placeholderTextColor="#8E8378"
        style={styles.input}
        value={value}
      />
      <Text style={styles.privacyNote}>
        点“继续”后，我们才会整理这段话。确认前可以退出保存，也可以清空已保存内容。
      </Text>
      <ActionButton
        disabled={disabled}
        label={busy ? "正在整理" : "继续"}
        onPress={onSubmit}
      />
    </View>
  );
}

interface UnderstandingMapProps {
  model: UnderstandingMapViewModel;
}

export function UnderstandingMap({ model }: UnderstandingMapProps) {
  return (
    <View style={styles.stack}>
      <View style={styles.mapHeading}>
        <Text accessibilityRole="header" style={styles.title}>
          看看我有没有听对
        </Text>
        <Text style={styles.supporting}>
          先核对重点，不准确的地方随时可以改。
        </Text>
      </View>
      <View style={styles.mapGrid}>
        <MapSection title="你说的">
          {model.originalWords.map((words, index) => (
            <Text key={`${index}-${words}`} style={styles.body}>
              “{words}”
            </Text>
          ))}
        </MapSection>
        <MapSection title="我们的理解" tone="highlight">
          <Text style={styles.body}>{model.currentUnderstanding}</Text>
        </MapSection>
        <MapSection title="你希望先发生的变化">
          <Text style={styles.emphasis}>{model.desiredChange}</Text>
        </MapSection>
        <MapSection
          title={PROBLEM_UNDERSTANDING_COPY.unknownHeading}
          tone="quiet"
        >
          {model.clarificationSkipped ? (
            <Text style={styles.skippedNote}>
              已选择先跳过，之后还可以回来补充。
            </Text>
          ) : null}
          {model.unknowns.length === 0 ? (
            <Text style={styles.body}>暂时没有需要补充确认的地方。</Text>
          ) : (
            model.unknowns.map((item) => (
              <Bullet key={item.key}>{item.label}</Bullet>
            ))
          )}
        </MapSection>
        {model.alternativeExplanations.length > 0 ? (
          <MapSection title="也可能是另一种情况">
            {model.alternativeExplanations.map((item) => (
              <Bullet key={item}>{item}</Bullet>
            ))}
          </MapSection>
        ) : null}
        <MapSection title="可以从这里开始">
          {model.familyStrengths.map((item) => (
            <Bullet key={item}>{item}</Bullet>
          ))}
        </MapSection>
      </View>
    </View>
  );
}

interface CorrectionConfirmationProps {
  correction: string;
  phase: ProblemUnderstandingPhase;
  canCorrect: boolean;
  canConfirm: boolean;
  onChangeCorrection: TextInputProps["onChangeText"];
  onBeginCorrection: () => void;
  onSubmitCorrection: () => void;
  onConfirm: () => void;
  onSkipClarification: () => void;
  onSaveAndExit: () => void;
}

export function CorrectionConfirmation({
  correction,
  phase,
  canCorrect,
  canConfirm,
  onChangeCorrection,
  onBeginCorrection,
  onSubmitCorrection,
  onConfirm,
  onSkipClarification,
  onSaveAndExit,
}: CorrectionConfirmationProps) {
  if (phase === "CORRECTING") {
    return (
      <View style={styles.surface}>
        <Text accessibilityRole="header" style={styles.sectionTitle}>
          {PROBLEM_UNDERSTANDING_COPY.correctionHeading}
        </Text>
        <TextInput
          accessibilityLabel="补充或修正"
          multiline
          onChangeText={onChangeCorrection}
          placeholder="把不准确的地方告诉我，我会保留前面的内容，重新整理。"
          placeholderTextColor="#8E8378"
          style={styles.input}
          value={correction}
        />
        <ActionButton
          disabled={correction.trim().length === 0}
          label="根据补充重新整理"
          onPress={onSubmitCorrection}
        />
      </View>
    );
  }

  return (
    <View style={[styles.surface, styles.actions]}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>
        这份理解准确吗？
      </Text>
      <Text style={styles.actionHint}>
        {canConfirm
          ? "只有你确认后，才会进入下一步。"
          : "你可以继续补充，也可以先保存这份理解，稍后再回来。"}
      </Text>
      {canConfirm ? (
        <ActionButton
          label={PROBLEM_UNDERSTANDING_COPY.confirmAction}
          onPress={onConfirm}
        />
      ) : (
        <ActionButton
          label="先保存，稍后继续"
          onPress={onSaveAndExit}
          secondary
        />
      )}
      <View style={styles.actionRow}>
        <View style={styles.actionCell}>
          <ActionButton
            disabled={!canCorrect}
            label="有点不对"
            onPress={onBeginCorrection}
            secondary
          />
        </View>
        <View style={styles.actionCell}>
          <ActionButton
            disabled={!canCorrect}
            label="我想补充"
            onPress={onBeginCorrection}
            secondary
          />
        </View>
      </View>
      <View style={styles.divider} />
      <ActionButton label="先跳过澄清" onPress={onSkipClarification} quiet />
      <ActionButton label="退出并保存" onPress={onSaveAndExit} quiet />
    </View>
  );
}

interface RecoveryNoticeProps {
  message: string;
  onRetry: () => void;
}

export function RecoveryNotice({ message, onRetry }: RecoveryNoticeProps) {
  return (
    <View accessibilityRole="alert" style={[styles.surface, styles.recovery]}>
      <Text style={styles.sectionTitle}>你说过的内容还在</Text>
      <Text style={styles.body}>{message}</Text>
      <ActionButton label="稍后再试一次" onPress={onRetry} secondary />
    </View>
  );
}

function MapSection({
  children,
  title,
  tone = "regular",
}: {
  children: ReactNode;
  title: string;
  tone?: "regular" | "quiet" | "highlight";
}) {
  return (
    <View
      style={[
        styles.section,
        tone === "quiet" && styles.quietSection,
        tone === "highlight" && styles.highlightSection,
      ]}
    >
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Bullet({ children }: { children: ReactNode }) {
  return <Text style={styles.body}>• {children}</Text>;
}

function ActionButton({
  disabled = false,
  label,
  onPress,
  secondary = false,
  quiet = false,
}: {
  disabled?: boolean;
  label: string;
  onPress: () => void;
  secondary?: boolean;
  quiet?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondaryButton,
        quiet && styles.quietButton,
        disabled && styles.disabledButton,
        pressed && !disabled && styles.pressedButton,
      ]}
    >
      <Text
        style={[
          styles.buttonText,
          secondary && styles.secondaryButtonText,
          quiet && styles.quietButtonText,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  actionCell: { flex: 1, minWidth: 130 },
  actionHint: { color: "#6E6258", fontSize: 13, lineHeight: 20 },
  actionRow: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  actions: { gap: 10 },
  body: { color: "#443A32", fontSize: 16, lineHeight: 25 },
  button: {
    alignItems: "center",
    backgroundColor: "#D8663A",
    borderRadius: 16,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  buttonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "700" },
  disabledButton: { opacity: 0.45 },
  divider: { backgroundColor: "#EADDD3", height: 1, marginVertical: 2 },
  emphasis: {
    color: "#8B3E22",
    fontSize: 18,
    fontWeight: "700",
    lineHeight: 27,
  },
  input: {
    backgroundColor: "#FFFDFC",
    borderColor: "#E7D8CC",
    borderRadius: 18,
    borderWidth: 1,
    color: "#302923",
    fontSize: 16,
    lineHeight: 25,
    minHeight: 132,
    padding: 16,
    textAlignVertical: "top",
  },
  highlightSection: { backgroundColor: "#FFF4EC", borderColor: "#EBC3A9" },
  mapGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  mapHeading: { gap: 4 },
  privacyNote: { color: "#6E6258", fontSize: 13, lineHeight: 20 },
  pressedButton: { opacity: 0.78 },
  quietSection: { backgroundColor: "#F3F0EA" },
  quietButton: { backgroundColor: "transparent", paddingVertical: 10 },
  quietButtonText: { color: "#765B4C", fontSize: 14 },
  recovery: { borderColor: "#D9CBBF", borderWidth: 1 },
  secondaryButton: {
    backgroundColor: "#F8EEE7",
    borderColor: "#DFA889",
    borderWidth: 1,
  },
  secondaryButtonText: { color: "#7C3D27" },
  section: {
    backgroundColor: "#FFFFFF",
    borderColor: "#EFE5DE",
    borderRadius: 18,
    borderWidth: 1,
    flexBasis: 280,
    flexGrow: 1,
    gap: 8,
    padding: 18,
  },
  sectionTitle: {
    color: "#302923",
    fontSize: 17,
    fontWeight: "700",
    lineHeight: 24,
  },
  skippedNote: { color: "#6E6258", fontSize: 14, lineHeight: 21 },
  stack: { gap: 12 },
  supporting: { color: "#6E6258", fontSize: 15, lineHeight: 23 },
  surface: {
    backgroundColor: "#FFF8F3",
    borderRadius: 22,
    gap: 14,
    padding: 20,
  },
  title: { color: "#2D261F", fontSize: 25, fontWeight: "800", lineHeight: 34 },
});
