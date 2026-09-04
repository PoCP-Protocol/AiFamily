import { router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import {
  createMobileRequestId,
  familyApi,
  FamilyApiError,
  type AiCoachMessageResponse,
  type CaptureNeedSignalResponse,
} from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";

/**
 * First real MVP closed loop: a parent describes a situation, it goes
 * through the real `/needs/signals` -> `/needs/{need_id}/ai-coach/messages`
 * chain (not mock, not the never-built /orchestration/* paths the disabled
 * UI-01 growth-help panel calls), and the Socratic AI Coach reply renders
 * on screen. One round only by design — see the MVP plan's scope cut for
 * why multi-turn follow-up is deliberately not here yet.
 */
export default function AiCoachMvpScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();

  const [inputText, setInputText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [needId, setNeedId] = useState<string | null>(null);
  const [coachReply, setCoachReply] = useState<AiCoachMessageResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canSubmit = session.status === "connected" && !!session.token && !!session.selectedFamily && inputText.trim().length > 0 && !submitting;

  const submit = async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    const text = inputText.trim();
    if (!text) return;

    setSubmitting(true);
    setErrorMessage(null);
    setCoachReply(null);
    try {
      const signalResult = await familyApi.captureNeedSignal<CaptureNeedSignalResponse>(
        session.token,
        session.selectedFamily.family_id,
        {
          raw_text: text,
          statement: text,
          desired_outcome: text,
          source: "FAMILY_EXPRESSED",
          purpose: "FAMILY_NEED",
          consent_version: "v1",
          data_class: "PUBLIC",
        },
        createMobileRequestId("ai-coach-mvp-signal"),
      );
      const capturedNeedId = signalResult.need.need_id;
      setNeedId(capturedNeedId);

      const reply = await familyApi.sendAiCoachMessage<AiCoachMessageResponse>(
        session.token,
        session.selectedFamily.family_id,
        capturedNeedId,
        { parent_message: text },
        createMobileRequestId("ai-coach-mvp-message"),
      );
      setCoachReply(reply);
    } catch (error) {
      setErrorMessage(
        error instanceof FamilyApiError
          ? `暂时没有收到回复（${error.code}）。请检查网络后重试。`
          : "暂时没有收到回复，请检查网络后重试。",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScreenContainer containerClassName="bg-surface">
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()}>
            <IconSymbol name="chevron.right" size={22} color={colors.text} />
          </Pressable>
          <Text style={[styles.title, { color: colors.text }]}>AI 教练（MVP）</Text>
        </View>

        <Text style={[styles.hint, { color: colors.muted }]}>
          说说现在最想解决的事情，AI 教练会反馈理解并提一个引导性问题——不是答案，也不是对孩子的结论。
        </Text>

        <TextInput
          multiline
          value={inputText}
          onChangeText={setInputText}
          editable={!submitting}
          placeholder="例如：孩子写作业总是拖到很晚……"
          placeholderTextColor={colors.muted}
          style={[styles.input, { color: colors.text, borderColor: colors.border, backgroundColor: colors.surface }]}
        />

        <Pressable
          disabled={!canSubmit}
          accessibilityRole="button"
          accessibilityLabel="提交给AI教练"
          onPress={() => void submit()}
          style={({ pressed }) => [
            styles.submitButton,
            { backgroundColor: canSubmit ? colors.tint : colors.border },
            pressed && styles.pressed,
          ]}
        >
          {submitting ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.submitText}>提交</Text>}
        </Pressable>

        {errorMessage ? (
          <Text accessibilityRole="alert" style={[styles.errorText, { color: colors.error, borderColor: `${colors.error}40`, backgroundColor: `${colors.error}08` }]}>
            {errorMessage}
          </Text>
        ) : null}

        {coachReply ? (
          <View style={[styles.replyCard, { borderColor: `${colors.tint}40`, backgroundColor: `${colors.tint}08` }]}>
            <Text style={[styles.replyBoundary, { color: colors.muted }]}>{coachReply.boundary}</Text>
            <Text style={[styles.replyText, { color: colors.text }]}>{coachReply.reflection}</Text>
            <Text style={[styles.replyQuestion, { color: colors.tint }]}>{coachReply.guiding_question}</Text>
            {needId ? <Text style={[styles.replyMeta, { color: colors.muted }]}>need_id: {needId}</Text> : null}
          </View>
        ) : null}
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, gap: 14 },
  topBar: { flexDirection: "row", alignItems: "center", gap: 10 },
  title: { fontSize: 18, fontWeight: "900" },
  hint: { fontSize: 13, lineHeight: 20, fontWeight: "600" },
  input: { minHeight: 96, borderWidth: 1, borderRadius: 12, padding: 12, fontSize: 14, lineHeight: 20, textAlignVertical: "top" },
  submitButton: { borderRadius: 12, paddingVertical: 12, alignItems: "center", justifyContent: "center" },
  submitText: { color: "#FFFFFF", fontSize: 15, fontWeight: "900" },
  pressed: { opacity: 0.85 },
  errorText: { borderWidth: 1, borderRadius: 12, padding: 12, fontSize: 13, lineHeight: 20, fontWeight: "600" },
  replyCard: { borderWidth: 1, borderRadius: 12, padding: 14, gap: 8 },
  replyBoundary: { fontSize: 11, lineHeight: 16, fontWeight: "700" },
  replyText: { fontSize: 14, lineHeight: 21, fontWeight: "600" },
  replyQuestion: { fontSize: 15, lineHeight: 22, fontWeight: "900" },
  replyMeta: { fontSize: 11, lineHeight: 16, fontWeight: "500" },
});
