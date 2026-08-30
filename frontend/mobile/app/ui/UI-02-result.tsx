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
import {
  AssessmentDimensionList,
  AssessmentDimensionRadar,
} from "@/components/family/assessment-dimension-radar";
import { useColors } from "@/hooks/use-colors";
import {
  buildAssessmentDimensionProfiles,
  getAssessmentKnowledgeBrief,
} from "@/lib/family/assessment-dimension-profile";
import { buildUi02AssessmentResultSummary } from "@/lib/family/ui02-assessment-design";
import { useFamilyMobile } from "@/lib/family/family-state";

export default function FamilyAssessmentResultScreen() {
  const colors = useColors();
  const {
    assessmentNeedText,
    assessmentAnswers,
    selectedGrowthFocus,
    assessmentSyncState,
    restartAssessment,
  } = useFamilyMobile();
  const resultNeed =
    assessmentNeedText.trim() || "你想找到一个更少冲突的开始";
  const firstStep = resultNeed.includes("作业") || resultNeed.includes("学习")
    ? "先看见“开始”这一刻发生了什么：给彼此一点缓冲，再一起找出最难的一段。"
    : resultNeed.includes("手机") || resultNeed.includes("游戏")
      ? "先把使用边界和停下来的时刻说清楚，再听孩子为什么还想继续。"
      : "先留出一段不被打断的时间，把这件事听完整，再一起决定怎么往前走。";
  const resultProfiles = buildAssessmentDimensionProfiles(
    Object.entries(assessmentAnswers).map(([item_ref, response_value]) => ({
      item_ref,
      response_value,
    })),
    selectedGrowthFocus,
  );
  const focusSummary = buildUi02AssessmentResultSummary(
    selectedGrowthFocus,
    assessmentAnswers,
  );
  const knowledgeBrief = getAssessmentKnowledgeBrief(selectedGrowthFocus);
  const [perspectiveFeedback, setPerspectiveFeedback] = useState<
    "LIKE" | "NOT_LIKE" | "ADD_CONTEXT" | null
  >(null);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
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
    "目前只看到了你主动说出的场景；下一次可以继续补充发生的时间、触发点，以及孩子和家长当时的感受。";

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen
        options={{
          headerShown: true,
          title: "家庭成长解读",
          headerBackTitle: "返回",
        }}
      />
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.hero}>
          <Text style={styles.heroBadge}>本次测评 · 家庭视角</Text>
          <Text style={[styles.heroTitle, { color: colors.text }]}>
            先把家庭的真实处境看清楚
          </Text>
          <Text style={[styles.heroText, { color: colors.muted }]}>
            根据你刚才的回答，先整理出一张可以继续补充的家庭地图。它只从你主动提供的内容出发。
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
            {resultNeed}
          </Text>
          <Text style={[styles.cardText, { color: colors.muted }]}>
            不替你给孩子下结论，先把这件反复发生的事放回家庭关系与日常环境里理解。
          </Text>
        </View>
        <View testID="assessment-result-profile" style={styles.profileSection}>
          <View style={styles.sectionHeadingRow}>
            <View style={styles.sectionHeadingCopy}>
              <Text style={styles.sectionLabel}>家庭观察画像</Text>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>五个方向，看看事情卡在哪一层</Text>
            </View>
            <Text style={styles.sectionMeta}>今天的回答</Text>
          </View>
          <AssessmentDimensionRadar profiles={resultProfiles} />
          <AssessmentDimensionList profiles={resultProfiles} activeFocus={selectedGrowthFocus} />
        </View>
        <View
          testID="assessment-result-directions"
          style={styles.directionCard}
        >
          <Text style={styles.sectionLabel}>为什么先从这里开始</Text>
          <Text style={styles.directionText}>
            {focusSummary?.familyTheorySupport[0] ?? "先看家庭互动与环境，再决定是否需要更多支持。"}
          </Text>
          <Text style={styles.directionHint}>
            {focusSummary?.operationalDefinition ?? "回答多少就看见多少，未回答的方向不会被猜测。"}
          </Text>
        </View>
        <View testID="assessment-result-knowledge" style={styles.knowledgeCard}>
          <Text style={styles.sectionLabel}>这份理解背后的知识</Text>
          <Text style={[styles.knowledgeTitle, { color: colors.text }]}>为什么先看「{knowledgeBrief?.title ?? "家庭互动"}」</Text>
          <Text style={styles.knowledgeText}>{knowledgeBrief?.familyLens ?? "先看家庭互动与环境，再决定是否需要更多支持。"}</Text>
          <Text style={styles.knowledgeSource}>参考家庭教育与发展研究；这是一条实践参考，不是对孩子的结论。</Text>
        </View>
        <View
          testID="assessment-result-uncertain"
          style={[
            styles.card,
            { backgroundColor: colors.surface, borderColor: colors.border },
          ]}
        >
          <Text style={styles.sectionLabel}>下一次我们还要看什么</Text>
          <Text style={[styles.cardText, { color: colors.text }]}>
            {uncertain}
          </Text>
          <Text style={[styles.cardText, { color: colors.muted }]}>
            你可以随时回来补充或改写，后续的成长方案会跟着你的理解调整。
          </Text>
        </View>
        <View testID="assessment-result-next-step" style={styles.nextStepCard}>
          <Text style={styles.sectionLabel}>成长方案 · 从今天开始</Text>
          <Text style={styles.nextStepTitle}>{firstStep}</Text>
          <Text style={styles.nextStepText}>
            先不急着改变孩子，先找到最值得改变的环节；这一阶段确认后，后面的 21 天和 90 天方案才会更贴近你们家。
          </Text>
        </View>
        <View testID="assessment-result-feedback" style={styles.feedbackCard}>
          <Text style={styles.sectionLabel}>由你来定，这份理解对不对</Text>
          <Text
            style={[styles.feedbackIntro, { color: colors.text }]}
          >
            你最了解自己的家庭。像、不像、补充，都能帮助我们更贴近你们家；你不需要接受一个不属于自己的解释。
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
                onPress={() => {
                  setPerspectiveFeedback(value);
                  setFeedbackSubmitted(value !== "ADD_CONTEXT");
                }}
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
                onPress={() => {
                  if (supplementText.trim()) setFeedbackSubmitted(true);
                }}
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
              {perspectiveFeedback === "ADD_CONTEXT" && !feedbackSubmitted
                ? "补充一句，让这份理解更贴近你们家。"
                : "反馈已记在本次整理里；登录后可以继续校准家庭方案。"}
            </Text>
          ) : null}
        </View>
        <View testID="assessment-result-action" style={styles.actionCard}>
          <Text style={styles.sectionLabel}>把理解带回生活</Text>
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
              {savedAction === "started" ? "已开启第一阶段" : "开始第一阶段"}
            </Text>
          </Pressable>
          {savedAction === "started" ? (
            <Text style={[styles.actionStatus, { color: colors.muted }]}>
              第一阶段已经为你展开，明天可以回来继续看。
            </Text>
          ) : null}
          <Pressable
            testID="assessment-save-for-later"
            accessibilityRole="button"
            onPress={() => setSavedAction("saved")}
            style={({ pressed }) => [styles.editButton, pressed && styles.pressed]}
          >
            <Text style={[styles.editButtonText, { color: colors.tint }]}>
              先留在这里，明天再看
            </Text>
          </Pressable>
          {savedAction === "saved" ? (
            <Text style={[styles.actionStatus, { color: colors.muted }]}>
              已为你保留当前整理，明天可以继续补充。
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
            这次整理还没有放入家庭空间；登录并完成授权后，可以持续回看和复盘。
          </Text>
        </View>
        <View testID="assessment-local-boundary" style={styles.localBoundary}>
          <Text style={[styles.localBoundaryText, { color: colors.muted }]}>
            当前先展示本次整理。登录并完成授权后，它才会进入家庭空间，成为可以持续修订的成长记录。
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
  profileSection: { gap: 10 },
  sectionHeadingRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10,
  },
  sectionHeadingCopy: { flex: 1, gap: 3 },
  sectionTitle: { fontSize: 18, lineHeight: 25, fontWeight: "900" },
  sectionMeta: { color: "#7B8FA4", fontSize: 11, lineHeight: 17, fontWeight: "800" },
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
  knowledgeCard: {
    borderRadius: 18,
    backgroundColor: "#FFFDF8",
    borderWidth: 1,
    borderColor: "#F0E2C4",
    padding: 16,
    gap: 9,
  },
  knowledgeTitle: { fontSize: 17, lineHeight: 24, fontWeight: "900" },
  knowledgeText: { color: "#624B22", fontSize: 14, lineHeight: 22, fontWeight: "700" },
  knowledgeSource: { color: "#8A7043", fontSize: 12, lineHeight: 18 },
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
