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
  inputMode: MultimodalInputMode;
  voiceCaptureState: VoiceCaptureState;
  voiceMessage: string | null;
  imageAttached: boolean;
  attachedMediaMimeType: string | null;
  canUseSandboxImage: boolean;
  canRemoveImage: boolean;
  onChangeText: TextInputProps["onChangeText"];
  onChangeInputMode: (mode: MultimodalInputMode) => void;
  onVoiceCapture: () => void;
  onToggleSandboxImage: () => void;
  onSubmit: () => void;
}

export type MultimodalInputMode =
  | "TEXT"
  | "VOICE"
  | "IMAGE"
  | "ANIMATION"
  | "VIDEO";
export type VoiceCaptureState = "IDLE" | "CAPTURING" | "READY" | "UNAVAILABLE";

const INPUT_MODES: readonly {
  mode: MultimodalInputMode;
  label: string;
  cue: string;
}[] = [
  { mode: "TEXT", label: "写下来", cue: "文字" },
  { mode: "VOICE", label: "说一说", cue: "语音" },
  { mode: "IMAGE", label: "加图片", cue: "图片" },
  { mode: "ANIMATION", label: "看动画", cue: "动图" },
  { mode: "VIDEO", label: "加视频", cue: "视频" },
];

export function ConcernComposer({
  value,
  phase,
  inputMode,
  voiceCaptureState,
  voiceMessage,
  imageAttached,
  attachedMediaMimeType,
  canUseSandboxImage,
  canRemoveImage,
  onChangeText,
  onChangeInputMode,
  onVoiceCapture,
  onToggleSandboxImage,
  onSubmit,
}: ConcernComposerProps) {
  const busy = phase === "UNDERSTANDING";
  const disabled = busy || value.trim().length === 0;
  const mediaInputSelected =
    inputMode === "IMAGE" || inputMode === "ANIMATION" || inputMode === "VIDEO";

  return (
    <View style={styles.surface}>
      <Text accessibilityRole="header" style={styles.title}>
        {PROBLEM_UNDERSTANDING_COPY.heading}
      </Text>
      <Text style={styles.supporting}>{PROBLEM_UNDERSTANDING_COPY.prompt}</Text>
      <View accessibilityRole="radiogroup" style={styles.inputModeRow}>
        {INPUT_MODES.map((item) => {
          const selected = inputMode === item.mode;
          return (
            <Pressable
              accessibilityLabel={`${item.label}，${item.cue}输入`}
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              key={item.mode}
              onPress={() => onChangeInputMode(item.mode)}
              style={({ pressed }) => [
                styles.inputModeButton,
                selected && styles.inputModeButtonSelected,
                pressed && styles.pressedButton,
              ]}
            >
              <Text
                style={[
                  styles.inputModeCue,
                  selected && styles.inputModeCueSelected,
                ]}
              >
                {item.cue}
              </Text>
              <Text
                style={[
                  styles.inputModeLabel,
                  selected && styles.inputModeLabelSelected,
                ]}
              >
                {item.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      {inputMode === "VOICE" ? (
        <View style={styles.voicePanel}>
          <View style={styles.waveform}>
            {[12, 22, 34, 18, 40, 26, 15, 31, 20].map((height, index) => (
              <View
                key={`${height}-${index}`}
                style={[
                  styles.waveBar,
                  { height },
                  voiceCaptureState === "CAPTURING" && styles.waveBarActive,
                ]}
              />
            ))}
          </View>
          <Text style={styles.voiceTitle}>
            {voiceCaptureState === "CAPTURING"
              ? "正在听你说"
              : voiceCaptureState === "READY"
                ? "已转成可编辑文字"
                : "用语音说，比打字更自然"}
          </Text>
          <Text style={styles.voiceBody}>
            {voiceMessage ??
              "录音会先经过授权和转写；你确认文字后，才会交给 AI 整理。"}
          </Text>
          <ActionButton
            disabled={voiceCaptureState === "CAPTURING"}
            label={
              voiceCaptureState === "CAPTURING"
                ? "正在准备转写"
                : voiceCaptureState === "READY"
                  ? "重新说一次"
                  : "开始语音表达"
            }
            onPress={onVoiceCapture}
            secondary
          />
        </View>
      ) : null}
      {mediaInputSelected ? (
        <View style={styles.imagePanel}>
          <View
            style={[
              styles.imagePreview,
              inputMode === "VIDEO" && styles.videoPreview,
              inputMode === "ANIMATION" && styles.animationPreview,
            ]}
          >
            <View style={styles.imageSun} />
            <View style={styles.imageMountainLeft} />
            <View style={styles.imageMountainRight} />
            {inputMode === "VIDEO" ? (
              <View style={styles.playButton}>
                <Text style={styles.playButtonText}>▶</Text>
              </View>
            ) : null}
            {inputMode === "ANIMATION" ? (
              <Text style={styles.animationMark}>GIF</Text>
            ) : null}
          </View>
          <View style={styles.imageCopy}>
            <Text style={styles.voiceTitle}>
              {imageAttached
                ? `${mediaLabel(attachedMediaMimeType)}已加入这次表达`
                : inputMode === "VIDEO"
                  ? "视频可以保留事情发生的过程"
                  : inputMode === "ANIMATION"
                    ? "动图可以呈现反复出现的互动"
                    : "图片可以补充当时的情境"}
            </Text>
            <Text style={styles.voiceBody}>
              {imageAttached
                ? `AI 只能引用已授权的${mediaLabel(attachedMediaMimeType)}标识；结论仍需你核对。`
                : canUseSandboxImage
                  ? `当前可用一个明确标记的沙盒${inputMode === "VIDEO" ? "视频" : inputMode === "ANIMATION" ? "动图" : "图片"}验证完整交互。`
                  : "请从家庭媒体库选择已授权媒体；当前页面不会自行读取相册或视频库。"}
            </Text>
            {canUseSandboxImage || canRemoveImage ? (
              <ActionButton
                label={
                  canRemoveImage
                    ? `移除${mediaLabel(attachedMediaMimeType)}`
                    : `加入沙盒${inputMode === "VIDEO" ? "视频" : inputMode === "ANIMATION" ? "动图" : "图片"}`
                }
                onPress={onToggleSandboxImage}
                secondary
              />
            ) : null}
          </View>
        </View>
      ) : null}
      <Text style={styles.inputLabel}>
        {inputMode === "VOICE"
          ? "检查并修改转写"
          : mediaInputSelected
            ? "再补一句你希望我们注意什么"
            : "最近发生的事"}
      </Text>
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
  onAnswerQuestion: (question: string) => void;
}

export function UnderstandingMap({
  model,
  onAnswerQuestion,
}: UnderstandingMapProps) {
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
        <MapSection title="真正拉扯你们的">
          <Text style={styles.body}>{model.centralTension}</Text>
        </MapSection>
        <MapSection title="你真正想守护的">
          <Text style={styles.body}>{model.careIntent}</Text>
        </MapSection>
        <MapSection title="你希望先发生的变化">
          <Text style={styles.emphasis}>{model.desiredChange}</Text>
          <Text style={styles.supporting}>
            {model.desiredChangeBasis === "EXPLICIT"
              ? "这是根据你明确表达的期待整理的。"
              : "这是 AI 的暂定理解，需要你确认。"}
          </Text>
          {model.observableSigns.map((item) => (
            <Bullet key={item}>{item}</Bullet>
          ))}
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
        {model.hypotheses.length > 0 ? (
          <MapSection title="几种值得一起验证的理解">
            <Text style={styles.supporting}>
              这些不是定论。你可以看看哪一种更贴近，也可以告诉我哪里不对。
            </Text>
            {model.hypotheses.map((item) => (
              <View key={item.key} style={styles.hypothesisCard}>
                <View style={styles.hypothesisMetaRow}>
                  <Text style={styles.hypothesisLabel}>一种可能</Text>
                  <Text style={styles.confidenceLabel}>
                    当前把握：{confidenceLabel(item.confidence)}
                  </Text>
                </View>
                <Text style={styles.emphasis}>{item.statement}</Text>
                <Text style={styles.body}>{item.rationale}</Text>
                <Text style={styles.evidenceHeading}>
                  我这样理解，是因为你提到
                </Text>
                {item.evidenceObservations.map((observation) => (
                  <Bullet key={observation}>{observation}</Bullet>
                ))}
                {item.knowledgeBasisCount > 0 ? (
                  <Text style={styles.knowledgeNote}>
                    同时参考了家庭成长知识库中的相关方法。
                  </Text>
                ) : null}
                <Text style={styles.evidenceHeading}>
                  什么信息会改变这个判断
                </Text>
                <Text style={styles.body}>
                  {item.disconfirmingEvidenceNeeded}
                </Text>
              </View>
            ))}
          </MapSection>
        ) : null}
        {model.followUpQuestions.length > 0 ? (
          <MapSection title="接下来，我想认真问你">
            {model.followUpQuestions.map((item) => (
              <Pressable
                accessibilityLabel={`回答：${item}`}
                accessibilityRole="button"
                key={item}
                onPress={() => onAnswerQuestion(item)}
                style={({ pressed }) => [
                  styles.questionButton,
                  pressed && styles.pressedButton,
                ]}
              >
                <Text style={styles.questionText}>{item}</Text>
                <Text style={styles.questionAction}>回答这个问题 →</Text>
              </Pressable>
            ))}
          </MapSection>
        ) : null}
        <MapSection title="你们已经拥有的力量">
          {model.familyStrengths.map((item) => (
            <Bullet key={item}>{item}</Bullet>
          ))}
        </MapSection>
        <MapSection title="这份理解从哪里来" tone="quiet">
          <Text style={styles.body}>{model.sourceSummary}</Text>
          <Text style={styles.supporting}>
            第 {model.draftVersion} 版 · {formatGeneratedAt(model.generatedAt)}
          </Text>
        </MapSection>
        <MapSection title="这份理解的边界" tone="quiet">
          {model.limitations.map((item) => (
            <Bullet key={item}>{item}</Bullet>
          ))}
        </MapSection>
      </View>
    </View>
  );
}

interface CorrectionConfirmationProps {
  correction: string;
  followUpQuestion: string | null;
  phase: ProblemUnderstandingPhase;
  canCorrect: boolean;
  canConfirm: boolean;
  onChangeCorrection: TextInputProps["onChangeText"];
  onBeginCorrection: () => void;
  onSubmitCorrection: () => void;
  onConfirm: () => void;
  onSkipClarification: () => void;
  onSaveAndExit: () => void;
  onRequestHumanReview: () => void;
  onDelete: () => void;
  busyAction?: "human-review" | "delete" | "decision" | null;
}

export function CorrectionConfirmation({
  correction,
  followUpQuestion,
  phase,
  canCorrect,
  canConfirm,
  onChangeCorrection,
  onBeginCorrection,
  onSubmitCorrection,
  onConfirm,
  onSkipClarification,
  onSaveAndExit,
  onRequestHumanReview,
  onDelete,
  busyAction = null,
}: CorrectionConfirmationProps) {
  if (phase === "CORRECTING") {
    return (
      <View style={styles.surface}>
        <Text accessibilityRole="header" style={styles.sectionTitle}>
          {followUpQuestion
            ? "关于这个问题，你愿意多说一点吗？"
            : PROBLEM_UNDERSTANDING_COPY.correctionHeading}
        </Text>
        {followUpQuestion ? (
          <Text style={styles.followUpQuestion}>“{followUpQuestion}”</Text>
        ) : null}
        <TextInput
          accessibilityLabel="补充或修正"
          multiline
          onChangeText={onChangeCorrection}
          placeholder={
            followUpQuestion
              ? "写下你想到的情形、感受或例子。"
              : "把不准确的地方告诉我，我会保留前面的内容，重新整理。"
          }
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
        这只会记下你的反馈，不会自动改变家庭记录。
      </Text>
      <ActionButton
        disabled={!canConfirm || busyAction !== null}
        label={
          busyAction === "decision"
            ? "正在记下"
            : PROBLEM_UNDERSTANDING_COPY.confirmAction
        }
        onPress={onConfirm}
      />
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
      <ActionButton
        disabled={busyAction !== null}
        label={
          busyAction === "human-review" ? "正在联系人工" : "请人工帮我看看"
        }
        onPress={onRequestHumanReview}
        secondary
      />
      <ActionButton label="退出并保存" onPress={onSaveAndExit} quiet />
      <ActionButton
        disabled={busyAction !== null}
        label={busyAction === "delete" ? "正在删除" : "删除这次内容"}
        onPress={onDelete}
        quiet
      />
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

function formatGeneratedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚更新";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function confidenceLabel(value: "LOW" | "MEDIUM" | "HIGH"): string {
  if (value === "HIGH") return "较高";
  if (value === "MEDIUM") return "中等";
  return "初步";
}

function mediaLabel(mimeType: string | null): string {
  if (mimeType?.startsWith("video/")) return "视频";
  if (mimeType === "image/gif" || mimeType === "image/webp") return "动图";
  return "图片";
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
  inputLabel: { color: "#4A3D34", fontSize: 13, fontWeight: "800" },
  inputModeButton: {
    alignItems: "center",
    backgroundColor: "#FFFDFC",
    borderColor: "#E7D8CC",
    borderRadius: 16,
    borderWidth: 1,
    flex: 1,
    flexBasis: 92,
    gap: 2,
    minHeight: 64,
    justifyContent: "center",
    paddingHorizontal: 8,
    paddingVertical: 9,
  },
  inputModeButtonSelected: {
    backgroundColor: "#FFF0E5",
    borderColor: "#D8663A",
  },
  inputModeCue: { color: "#8A796C", fontSize: 11, fontWeight: "700" },
  inputModeCueSelected: { color: "#A74624" },
  inputModeLabel: { color: "#4A3D34", fontSize: 14, fontWeight: "800" },
  inputModeLabelSelected: { color: "#8B3E22" },
  inputModeRow: { flexDirection: "row", flexWrap: "wrap", gap: 9 },
  animationMark: {
    backgroundColor: "#FFFFFFDD",
    borderRadius: 8,
    bottom: 8,
    color: "#6C4B86",
    fontSize: 11,
    fontWeight: "900",
    paddingHorizontal: 7,
    paddingVertical: 4,
    position: "absolute",
    right: 8,
  },
  animationPreview: { backgroundColor: "#E9DDF4" },
  imageCopy: { flex: 1, gap: 6, minWidth: 180 },
  imageMountainLeft: {
    backgroundColor: "#A9BE9D",
    bottom: -18,
    height: 62,
    left: -8,
    position: "absolute",
    transform: [{ rotate: "38deg" }],
    width: 62,
  },
  imageMountainRight: {
    backgroundColor: "#78936E",
    bottom: -26,
    height: 78,
    position: "absolute",
    right: -4,
    transform: [{ rotate: "45deg" }],
    width: 78,
  },
  imagePanel: {
    alignItems: "center",
    backgroundColor: "#F1F5EC",
    borderColor: "#C8D8BE",
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 14,
    padding: 14,
  },
  imagePreview: {
    backgroundColor: "#DCEAD4",
    borderRadius: 16,
    height: 112,
    overflow: "hidden",
    position: "relative",
    width: 112,
  },
  imageSun: {
    backgroundColor: "#F0B35E",
    borderRadius: 14,
    height: 28,
    position: "absolute",
    right: 16,
    top: 15,
    width: 28,
  },
  playButton: {
    alignItems: "center",
    backgroundColor: "#1F2937CC",
    borderRadius: 22,
    height: 44,
    justifyContent: "center",
    left: 34,
    position: "absolute",
    top: 34,
    width: 44,
  },
  playButtonText: { color: "#FFFFFF", fontSize: 18, marginLeft: 2 },
  highlightSection: { backgroundColor: "#FFF4EC", borderColor: "#EBC3A9" },
  hypothesisCard: {
    backgroundColor: "#FFFDFC",
    borderColor: "#E7D8CC",
    borderRadius: 15,
    borderWidth: 1,
    gap: 8,
    padding: 15,
  },
  hypothesisLabel: { color: "#8B3E22", fontSize: 13, fontWeight: "800" },
  hypothesisMetaRow: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    justifyContent: "space-between",
  },
  confidenceLabel: { color: "#75675D", fontSize: 12, fontWeight: "700" },
  evidenceHeading: { color: "#4F443B", fontSize: 13, fontWeight: "800" },
  followUpQuestion: {
    color: "#6A3B2A",
    fontSize: 16,
    fontWeight: "700",
    lineHeight: 25,
  },
  knowledgeNote: {
    color: "#516148",
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 20,
  },
  mapGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  mapHeading: { gap: 4 },
  privacyNote: { color: "#6E6258", fontSize: 13, lineHeight: 20 },
  pressedButton: { opacity: 0.78 },
  questionAction: { color: "#9B4728", fontSize: 13, fontWeight: "700" },
  questionButton: {
    backgroundColor: "#FFF9F5",
    borderColor: "#E7D8CC",
    borderRadius: 14,
    borderWidth: 1,
    gap: 6,
    padding: 14,
  },
  questionText: { color: "#443A32", fontSize: 16, lineHeight: 24 },
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
  voiceBody: {
    color: "#6E6258",
    fontSize: 13,
    lineHeight: 20,
    textAlign: "center",
  },
  voicePanel: {
    alignItems: "center",
    backgroundColor: "#F7F0FF",
    borderColor: "#DCCBEA",
    borderRadius: 18,
    borderWidth: 1,
    gap: 9,
    padding: 16,
  },
  voiceTitle: {
    color: "#44344F",
    fontSize: 16,
    fontWeight: "800",
    lineHeight: 23,
  },
  videoPreview: { backgroundColor: "#DCE7F4" },
  waveBar: { backgroundColor: "#B8A4C7", borderRadius: 999, width: 5 },
  waveBarActive: { backgroundColor: "#8D55B0" },
  waveform: { alignItems: "center", flexDirection: "row", gap: 5, height: 44 },
});
