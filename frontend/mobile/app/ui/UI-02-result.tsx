import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useState } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { useColors } from "@/hooks/use-colors";
import { useFamilyMobile } from "@/lib/family/family-state";

export default function FamilyAssessmentResultScreen() {
  const colors = useColors();
  const {
    assessmentNeedText,
    assessmentSyncState,
    restartAssessment,
  } = useFamilyMobile();
  const previewNeed =
    assessmentNeedText.trim() || "你想找到一个更少冲突的开始";
  const firstStep = previewNeed.includes("作业") || previewNeed.includes("学习")
    ? "今晚先只处理“开始”这一刻：给彼此十分钟缓冲，再问最难的是哪一小段。"
    : previewNeed.includes("手机") || previewNeed.includes("游戏")
      ? "今晚先约定一个可以停下来的时刻，停下后先听孩子说完这一局为什么还想继续。"
      : "今晚先留出十分钟，只听孩子把这件小事说完，再一起选一个最小的下一步。";
  const [perspectiveFeedback, setPerspectiveFeedback] = useState<
    "LIKE" | "NOT_LIKE" | "ADD_CONTEXT" | null
  >(null);
  const [supplementText, setSupplementText] = useState("");
  const [savedAction, setSavedAction] = useState<"idle" | "started" | "saved">(
    "idle",
  );

  useEffect(() => {
    if (assessmentSyncState === "synced") {
      router.replace("/ui/UI-03" as Href);
    }
  }, [assessmentSyncState]);
  const uncertain =
    "这是当前页面暂存的预览，还没有同步到家庭支持卡，也不能代表家庭的全部情况。";

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen
        options={{
          headerShown: true,
          title: "家庭支持整理",
          headerBackTitle: "返回",
        }}
      />
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.hero}>
          <Text style={styles.heroBadge}>当前页面暂存 · 预览</Text>
          <Text style={[styles.heroTitle, { color: colors.text }]}>
            今晚，先让这件事轻一点
          </Text>
          <Text style={[styles.heroText, { color: colors.muted }]}>
            先带走一张支持卡和一个可以马上试的小动作；连接家庭服务后，才会保存为正式结果。
          </Text>
        </View>
        <View
          testID="assessment-result-heard"
          style={[
            styles.card,
            { backgroundColor: colors.surface, borderColor: colors.border },
          ]}
        >
          <Text style={styles.sectionLabel}>我们听到的家庭关注</Text>
          <Text style={[styles.cardTitle, { color: colors.text }]}>
            {previewNeed}
          </Text>
          <Text style={[styles.cardText, { color: colors.muted }]}>
            不替你给孩子下结论，先把这件反复发生的小事说清楚。
          </Text>
        </View>
        <View
          testID="assessment-result-directions"
          style={styles.directionCard}
        >
          <Text style={styles.sectionLabel}>可能的方向</Text>
          <Text style={styles.directionText}>
            先处理一个具体时刻，不要求今晚解决全部问题。
          </Text>
          <Text style={styles.directionHint}>
            这是支持参考，是否贴近你们家由你决定。
          </Text>
        </View>
        <View
          testID="assessment-result-uncertain"
          style={[
            styles.card,
            { backgroundColor: colors.surface, borderColor: colors.border },
          ]}
        >
          <Text style={styles.sectionLabel}>还不确定的地方</Text>
          <Text style={[styles.cardText, { color: colors.text }]}>
            {uncertain}
          </Text>
          <Text style={[styles.cardText, { color: colors.muted }]}>
            如果这句话不准确，可以返回修改；不会自动触发任何行动。
          </Text>
        </View>
        <View testID="assessment-result-next-step" style={styles.nextStepCard}>
          <Text style={styles.sectionLabel}>今天可以尝试的一小步</Text>
          <Text style={styles.nextStepTitle}>{firstStep}</Text>
          <Text style={styles.nextStepText}>
            先试一次，再由你决定是否继续。
          </Text>
        </View>
        <View testID="assessment-result-feedback" style={styles.feedbackCard}>
          <Text style={styles.sectionLabel}>这句话像你们家吗？</Text>
          <Text style={[styles.feedbackIntro, { color: colors.text }]}>
            你的反馈只帮助我们改进这次理解，不会改写家庭事实。
          </Text>
          <View style={styles.feedbackRow}>
            {([
              ["LIKE", "像我们家"],
              ["NOT_LIKE", "不太像"],
              ["ADD_CONTEXT", "补充"],
            ] as const).map(([value, label]) => (
              <Pressable
                testID={`assessment-feedback-${value.toLowerCase()}`}
                accessibilityRole="button"
                key={value}
                onPress={() => setPerspectiveFeedback(value)}
                style={({ pressed }) => [
                  styles.feedbackButton,
                  perspectiveFeedback === value && styles.feedbackSelected,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.feedbackButtonText}>{label}</Text>
              </Pressable>
            ))}
          </View>
          {perspectiveFeedback === "ADD_CONTEXT" ? (
            <View style={styles.supplementBox}>
              <TextInput
                testID="assessment-feedback-input"
                accessibilityLabel="补充家庭情况"
                value={supplementText}
                onChangeText={setSupplementText}
                placeholder="补充一句，这样的描述哪里不准确？"
                placeholderTextColor="#94A3B8"
                multiline
                style={[styles.supplementInput, { color: colors.text }]}
              />
              <Pressable
                testID="assessment-feedback-submit"
                accessibilityRole="button"
                onPress={() => setPerspectiveFeedback("ADD_CONTEXT")}
                style={({ pressed }) => [
                  styles.supplementSubmit,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={[styles.supplementSubmitText, { color: colors.tint }]}>提交补充</Text>
              </Pressable>
            </View>
          ) : null}
          {perspectiveFeedback ? (
            <Text style={[styles.feedbackStatus, { color: colors.muted }]}>
              这次反馈只在当前页面暂存，还没有同步。
            </Text>
          ) : null}
        </View>
        <View testID="assessment-result-action" style={styles.actionCard}>
          <Text style={styles.sectionLabel}>接下来只选一件事</Text>
          <Pressable
            testID="assessment-start-small-step"
            accessibilityRole="button"
            onPress={() => setSavedAction("started")}
            style={({ pressed }) => [
              styles.primaryButton,
              { backgroundColor: colors.tint },
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.primaryButtonText}>
              {savedAction === "started" ? "已记下今晚这一步" : "开始尝试这一步"}
            </Text>
          </Pressable>
          {savedAction === "started" ? (
            <Text style={[styles.actionStatus, { color: colors.muted }]}>
              当前页面可以继续查看，这一步还没有同步。
            </Text>
          ) : null}
          <Pressable
            testID="assessment-save-for-later"
            accessibilityRole="button"
            onPress={() => setSavedAction("saved")}
            style={({ pressed }) => [styles.editButton, pressed && styles.pressed]}
          >
            <Text style={[styles.editButtonText, { color: colors.tint }]}>
              先保存，明天再看
            </Text>
          </Pressable>
          {savedAction === "saved" ? (
            <Text style={[styles.actionStatus, { color: colors.muted }]}>
              当前页面已保留，明天重新连接后再查看家庭支持卡。
            </Text>
          ) : null}
        </View>
        <View
          style={[
            styles.statusCard,
            { backgroundColor: "#F1F5F9" },
          ]}
        >
          <Text style={styles.statusIcon}>•</Text>
          <Text style={[styles.statusText, { color: colors.text }]}>
            这次内容只在当前页面暂存，还没有同步。
          </Text>
        </View>
        <View testID="assessment-local-boundary" style={styles.localBoundary}>
          <Text style={[styles.localBoundaryText, { color: colors.muted }]}>
            这次是当前页面的预览；连接家庭并完成授权后，才会开放可回看的家庭支持卡。
          </Text>
        </View>
        <Pressable
          testID="assessment-restart"
          onPress={() => {
            restartAssessment();
            router.replace("/ui/UI-02" as Href);
          }}
          style={({ pressed }) => [
            styles.editButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.editButtonText, { color: colors.tint }]}>
            重新开始测评
          </Text>
        </Pressable>
        <Pressable
          testID="assessment-edit"
          onPress={() => router.replace("/ui/UI-02" as Href)}
          style={({ pressed }) => [
            styles.editButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.editButtonText, { color: colors.tint }]}>
            返回修改
          </Text>
        </Pressable>
        <Pressable
          testID="assessment-exit"
          onPress={() => router.back()}
          style={({ pressed }) => [
            styles.exitButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.exitText, { color: colors.muted }]}>退出</Text>
        </Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { flexGrow: 1, padding: 18, gap: 12 },
  hero: { borderRadius: 20, backgroundColor: "#E8F2FF", padding: 17, gap: 7 },
  heroBadge: {
    color: "#2563EB",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "900",
  },
  heroTitle: { fontSize: 23, lineHeight: 31, fontWeight: "900" },
  heroText: { fontSize: 13, lineHeight: 20 },
  card: { borderRadius: 17, borderWidth: 1, padding: 16, gap: 8 },
  sectionLabel: {
    color: "#5B7091",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "900",
  },
  cardTitle: { fontSize: 18, lineHeight: 25, fontWeight: "900" },
  cardText: { fontSize: 14, lineHeight: 22 },
  directionCard: {
    borderRadius: 17,
    backgroundColor: "#F7FBF8",
    borderWidth: 1,
    borderColor: "#D8EBDD",
    padding: 16,
    gap: 8,
  },
  directionText: {
    color: "#214B3D",
    fontSize: 16,
    lineHeight: 24,
    fontWeight: "800",
  },
  directionHint: { color: "#5B7091", fontSize: 12, lineHeight: 18 },
  nextStepCard: {
    borderRadius: 17,
    backgroundColor: "#FFF8ED",
    borderWidth: 1,
    borderColor: "#F2D8AA",
    padding: 16,
    gap: 8,
  },
  nextStepTitle: {
    color: "#6E4300",
    fontSize: 18,
    lineHeight: 26,
    fontWeight: "900",
  },
  nextStepText: { color: "#8A6729", fontSize: 13, lineHeight: 20 },
  feedbackCard: {
    borderRadius: 17,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D9E2EC",
    padding: 16,
    gap: 9,
  },
  feedbackIntro: { fontSize: 13, lineHeight: 20 },
  feedbackRow: { flexDirection: "row", gap: 8, marginTop: 2 },
  feedbackButton: {
    flex: 1,
    minHeight: 42,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 6,
  },
  feedbackSelected: { backgroundColor: "#EAF2FF", borderColor: "#1B7CF2" },
  feedbackButtonText: { color: "#1B65C9", fontSize: 12, fontWeight: "900" },
  feedbackStatus: { fontSize: 12, lineHeight: 18 },
  supplementBox: { gap: 8 },
  supplementInput: {
    minHeight: 84,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    borderRadius: 13,
    padding: 12,
    fontSize: 13,
    lineHeight: 20,
    textAlignVertical: "top",
  },
  supplementSubmit: {
    minHeight: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  supplementSubmitText: {
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "900",
    textDecorationLine: "underline",
  },
  actionCard: {
    borderRadius: 17,
    backgroundColor: "#F8FBFF",
    borderWidth: 1,
    borderColor: "#D9E8FA",
    padding: 16,
    gap: 9,
  },
  actionStatus: { fontSize: 12, lineHeight: 18 },
  statusCard: {
    borderRadius: 15,
    padding: 13,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
  },
  statusIcon: { color: "#16866D", fontSize: 20, fontWeight: "900" },
  statusText: { flex: 1, fontSize: 13, lineHeight: 19, fontWeight: "700" },
  localBoundary: {
    borderRadius: 15,
    backgroundColor: "#F8FAFC",
    borderWidth: 1,
    borderColor: "#D7E0EA",
    padding: 13,
  },
  localBoundaryText: { fontSize: 13, lineHeight: 19, textAlign: "center" },
  primaryButton: {
    minHeight: 50,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 16,
    lineHeight: 22,
    fontWeight: "900",
  },
  editButton: { minHeight: 42, alignItems: "center", justifyContent: "center" },
  editButtonText: {
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "900",
    textDecorationLine: "underline",
  },
  exitButton: { minHeight: 40, alignItems: "center", justifyContent: "center" },
  exitText: {
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "800",
    textDecorationLine: "underline",
  },
  pressed: { opacity: 0.82 },
});
