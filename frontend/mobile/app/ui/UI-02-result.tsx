import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { useColors } from "@/hooks/use-colors";
import { getGrowthFocus } from "@/lib/family/core-growth";
import { useFamilyMobile } from "@/lib/family/family-state";
import { buildUi02AssessmentResultSummary } from "@/lib/family/ui02-assessment-design";

export default function FamilyAssessmentResultScreen() {
  const colors = useColors();
  const {
    selectedGrowthFocus,
    assessmentNeedText,
    assessmentAnswers,
    assessmentSyncState,
    restartAssessment,
  } = useFamilyMobile();
  const focus = getGrowthFocus(selectedGrowthFocus);
  const summary = buildUi02AssessmentResultSummary(
    selectedGrowthFocus,
    assessmentAnswers,
  );
  const firstStep =
    summary?.practiceSupport[0] ??
    "今天先留出十分钟，和孩子一起说清楚这件小事。";
  const uncertain =
    summary && summary.answeredCount < summary.totalCount
      ? "有些问题你选择先跳过；之后可以回来补充，不需要现在得出结论。"
      : "这次只整理了你主动提供的少量信息，不能代表家庭的全部情况。";

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
          <Text style={styles.heroBadge}>本次家庭自查已完成</Text>
          <Text style={[styles.heroTitle, { color: colors.text }]}>
            先把这件小事看清楚
          </Text>
          <Text style={[styles.heroText, { color: colors.muted }]}>
            内容仅限你的家庭，可随时回来修改或退出。
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
            {assessmentNeedText.trim() ||
              focus?.title ||
              "你想找到一个更少冲突的开始"}
          </Text>
          <Text style={[styles.cardText, { color: colors.muted }]}>
            {focus?.subtitle || "先从家庭自己的表达开始，再决定要不要继续。"}
          </Text>
        </View>
        <View
          testID="assessment-result-directions"
          style={styles.directionCard}
        >
          <Text style={styles.sectionLabel}>可能的方向</Text>
          <Text style={styles.directionText}>
            {summary?.supportDirections.slice(0, 2).join("；") ||
              "先从一次短对话和一个小约定开始。"}
          </Text>
          <Text style={styles.directionHint}>
            这是支持参考，不是对孩子的评分或诊断。
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
        <View
          style={[
            styles.statusCard,
            {
              backgroundColor:
                assessmentSyncState === "synced" ? "#EAF8F3" : "#F1F5F9",
            },
          ]}
        >
          <Text style={styles.statusIcon}>
            {assessmentSyncState === "synced" ? "✓" : "•"}
          </Text>
          <Text style={[styles.statusText, { color: colors.text }]}>
            {assessmentSyncState === "synced"
              ? "已保存到家庭测评记录"
              : "已保存在本机，之后可继续"}
          </Text>
        </View>
        {assessmentSyncState === "synced" ? (
          <Pressable
            testID="assessment-explanation"
            onPress={() => router.push("/ui/UI-03" as Href)}
            style={({ pressed }) => [
              styles.primaryButton,
              { backgroundColor: colors.tint },
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.primaryButtonText}>查看可解释结果</Text>
          </Pressable>
        ) : (
          <View testID="assessment-local-boundary" style={styles.localBoundary}>
            <Text style={[styles.localBoundaryText, { color: colors.muted }]}>
              这次整理已显示在上面；连上家庭服务后，才会开放服务端回看。
            </Text>
          </View>
        )}
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
