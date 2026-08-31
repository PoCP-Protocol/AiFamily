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
import type { ProblemUnderstandingPhase, UnderstandingMapViewModel } from "./model";

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
      <ActionButton disabled={disabled} label={busy ? "正在整理" : "继续"} onPress={onSubmit} />
    </View>
  );
}

interface UnderstandingMapProps {
  model: UnderstandingMapViewModel;
}

export function UnderstandingMap({ model }: UnderstandingMapProps) {
  return (
    <View style={styles.stack}>
      <Text accessibilityRole="header" style={styles.title}>我们先把这件事说清楚</Text>
      <MapSection title="你刚才告诉我的">
        {model.originalWords.map((words, index) => (
          <Text key={`${index}-${words}`} style={styles.body}>“{words}”</Text>
        ))}
      </MapSection>
      <MapSection title="我目前的理解">
        <Text style={styles.body}>{model.currentUnderstanding}</Text>
      </MapSection>
      {model.alternativeExplanations.length > 0 ? (
        <MapSection title="也可能是另一种情况">
          {model.alternativeExplanations.map((item) => (
            <Bullet key={item}>{item}</Bullet>
          ))}
        </MapSection>
      ) : null}
      <MapSection title="你们已经在努力的地方">
        {model.familyStrengths.map((item) => <Bullet key={item}>{item}</Bullet>)}
      </MapSection>
      <MapSection title="你希望先发生的变化">
        <Text style={styles.emphasis}>{model.desiredChange}</Text>
      </MapSection>
      <MapSection title={PROBLEM_UNDERSTANDING_COPY.unknownHeading} tone="quiet">
        {model.unknowns.length === 0 ? (
          <Text style={styles.body}>暂时没有需要补充确认的地方。</Text>
        ) : (
          model.unknowns.map((item) => <Bullet key={item.key}>{item.label}</Bullet>)
        )}
      </MapSection>
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
    <View style={styles.actions}>
      <ActionButton disabled={!canCorrect} label="有一点需要调整" onPress={onBeginCorrection} secondary />
      <ActionButton disabled={!canConfirm} label={PROBLEM_UNDERSTANDING_COPY.confirmAction} onPress={onConfirm} />
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
  tone?: "regular" | "quiet";
}) {
  return (
    <View style={[styles.section, tone === "quiet" && styles.quietSection]}>
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
}: {
  disabled?: boolean;
  label: string;
  onPress: () => void;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondaryButton,
        disabled && styles.disabledButton,
        pressed && !disabled && styles.pressedButton,
      ]}
    >
      <Text style={[styles.buttonText, secondary && styles.secondaryButtonText]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  actions: { gap: 10 },
  body: { color: "#443A32", fontSize: 16, lineHeight: 25 },
  button: { alignItems: "center", backgroundColor: "#D8663A", borderRadius: 16, paddingHorizontal: 18, paddingVertical: 14 },
  buttonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "700" },
  disabledButton: { opacity: 0.45 },
  emphasis: { color: "#8B3E22", fontSize: 18, fontWeight: "700", lineHeight: 27 },
  input: { backgroundColor: "#FFFDFC", borderColor: "#E7D8CC", borderRadius: 18, borderWidth: 1, color: "#302923", fontSize: 16, lineHeight: 25, minHeight: 132, padding: 16, textAlignVertical: "top" },
  pressedButton: { opacity: 0.78 },
  quietSection: { backgroundColor: "#F3F0EA" },
  recovery: { borderColor: "#D9CBBF", borderWidth: 1 },
  secondaryButton: { backgroundColor: "#F8EEE7", borderColor: "#DFA889", borderWidth: 1 },
  secondaryButtonText: { color: "#7C3D27" },
  section: { backgroundColor: "#FFFFFF", borderRadius: 18, gap: 8, padding: 18 },
  sectionTitle: { color: "#302923", fontSize: 17, fontWeight: "700", lineHeight: 24 },
  stack: { gap: 12 },
  supporting: { color: "#6E6258", fontSize: 15, lineHeight: 23 },
  surface: { backgroundColor: "#FFF8F3", borderRadius: 22, gap: 14, padding: 20 },
  title: { color: "#2D261F", fontSize: 25, fontWeight: "800", lineHeight: 34 },
});
