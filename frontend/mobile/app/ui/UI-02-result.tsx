import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { getGrowthFocus } from "@/lib/family/core-growth";
import { useFamilyMobile } from "@/lib/family/family-state";
import { buildUi02AssessmentResultSummary } from "@/lib/family/ui02-assessment-design";

export default function FamilyAssessmentResultScreen() {
  const colors = useColors();
  const { selectedGrowthFocus, assessmentAnswers, assessmentSyncState } = useFamilyMobile();
  const focus = getGrowthFocus(selectedGrowthFocus);
  const observations = focus?.subtitle ? focus.subtitle.split("、").filter(Boolean) : [];
  const resultSummary = buildUi02AssessmentResultSummary(selectedGrowthFocus, assessmentAnswers);
  const uncertainCount = resultSummary
    ? resultSummary.totalCount - resultSummary.answeredCount
    : 0;
  const coveragePercent = resultSummary && resultSummary.totalCount > 0
    ? Math.round((resultSummary.answeredCount / resultSummary.totalCount) * 100)
    : 0;

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: true, title: "测评完成", headerBackTitle: "返回" }} />
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.hero, { backgroundColor: "#EAF6FF" }]}>
          <View style={styles.heroIcon}>
            <IconSymbol name="checkmark.circle.fill" size={26} color="#1B7CF2" />
          </View>
          <View style={styles.heroCopy}>
            <Text style={[styles.cardLabel, { color: colors.muted }]}>家庭自查结果</Text>
            <Text style={[styles.heroTitle, { color: colors.text }]}>免费家庭测评已完成</Text>
            <Text style={[styles.heroText, { color: colors.muted }]}>帮你把最近的情况整理清楚，随时可以回来查看或调整。</Text>
          </View>
        </View>

        <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.sectionHeader}>
            <Text style={[styles.cardLabel, { color: colors.muted }]}>你这次最想先支持的方向</Text>
            <View style={styles.supportBadge}>
              <Text style={styles.supportBadgeText}>支持方向</Text>
            </View>
          </View>
          <Text style={[styles.focusTitle, { color: colors.text }]}>{focus?.title ?? "家庭支持方向"}</Text>
          <Text style={[styles.cardText, { color: colors.muted }]}>{focus?.subtitle ?? "你可以随时回到测评，补充或调整这次的选择。"}</Text>
        </View>

        {observations.length > 0 ? (
          <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <Text style={[styles.cardLabel, { color: colors.muted }]}>这次你关注到的情况</Text>
            {observations.map((item) => (
              <View key={item} style={styles.observationRow}>
                <View style={[styles.dot, { backgroundColor: "#1B7CF2" }]} />
                <Text style={[styles.cardText, { color: colors.text }]}>{item}</Text>
              </View>
            ))}
            <Text style={[styles.boundaryText, { color: colors.muted }]}>这些都是你选择的家庭视角情况，不是对孩子的评分、排名或诊断。</Text>
          </View>
        ) : null}

        {resultSummary ? (
          <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View style={styles.sectionHeader}>
              <Text style={[styles.cardLabel, { color: colors.muted }]}>这次看见了什么</Text>
              <Text style={[styles.progressCount, { color: colors.text }]}>{resultSummary.answeredCount} / {resultSummary.totalCount}</Text>
            </View>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${(resultSummary.answeredCount / resultSummary.totalCount) * 100}%` }]} />
            </View>
            <Text style={[styles.cardTitle, { color: colors.text }]}>观察项已完成</Text>
            <Text style={[styles.cardText, { color: colors.muted }]}>{resultSummary.operationalDefinition}</Text>
            {resultSummary.observationSignals.slice(0, 3).map((item) => (
              <View key={item} style={styles.signalRow}>
                <View style={[styles.dot, { backgroundColor: "#16866D" }]} />
                <Text style={[styles.cardText, { color: colors.text }]}>{item}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {resultSummary ? (
          <View style={[styles.coverageCard, { backgroundColor: "#F5F9FF", borderColor: "#D9E8FA" }]}>
            <View style={styles.sectionHeader}>
              <Text style={[styles.cardLabel, { color: colors.muted }]}>证据覆盖度</Text>
              <Text style={[styles.progressCount, { color: "#164B8A" }]}>{coveragePercent}%</Text>
            </View>
            <Text style={[styles.coverageTitle, { color: colors.text }]}>已记录 {resultSummary.answeredCount} / {resultSummary.totalCount} 项观察</Text>
            <Text style={[styles.cardText, { color: colors.muted }]}>这里只整理本次家庭自查的原始表达，不代表完整评估结论。</Text>
            {uncertainCount > 0 ? <Text style={styles.uncertaintyText}>还有 {uncertainCount} 项未回答或暂不确定，AI 解读时会明确标注信息不足。</Text> : null}
          </View>
        ) : null}

        {resultSummary ? (
          <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <Text style={[styles.cardLabel, { color: colors.muted }]}>为什么这样建议</Text>
            <Text style={[styles.cardText, { color: colors.text }]}>可先从：{resultSummary.supportDirections.slice(0, 3).join("、")}</Text>
            <View style={styles.pillRow}>
              {resultSummary.supportDirections.slice(0, 3).map((item) => (
                <View key={item} style={styles.supportPill}>
                  <Text style={styles.supportPillText}>{item}</Text>
                </View>
              ))}
            </View>
            <View style={styles.evidenceGrid}>
              <View style={styles.evidenceBlock}>
                <Text style={[styles.evidenceLabel, { color: colors.text }]}>背后的依据</Text>
                <Text style={[styles.cardText, { color: colors.muted }]}>{resultSummary.familyTheorySupport.slice(0, 2).join("；")}</Text>
              </View>
              <View style={styles.evidenceBlock}>
                <Text style={[styles.evidenceLabel, { color: colors.text }]}>这次看到的情况</Text>
                <Text style={[styles.cardText, { color: colors.muted }]}>{resultSummary.dataSupport.slice(0, 2).join("；")}</Text>
              </View>
              <View style={styles.evidenceBlock}>
                <Text style={[styles.evidenceLabel, { color: colors.text }]}>可以怎么做</Text>
                <Text style={[styles.cardText, { color: colors.muted }]}>{resultSummary.practiceSupport.slice(0, 3).join("；")}</Text>
              </View>
              <View style={styles.evidenceBlock}>
                <Text style={[styles.evidenceLabel, { color: colors.text }]}>接下来可以继续</Text>
                <Text style={[styles.cardText, { color: colors.muted }]}>{resultSummary.platformIntegration.applicationSurfaces.slice(1, 4).join("、")}</Text>
              </View>
            </View>
            <Text style={[styles.boundaryText, { color: colors.muted }]}>{resultSummary.boundary} 本结果只表示家庭视角下的支持需要。</Text>
          </View>
        ) : null}

        <View style={[styles.statusCard, { backgroundColor: assessmentSyncState === "synced" ? "#EAF8F3" : "#F1F5F9" }]}>
          <IconSymbol name={assessmentSyncState === "synced" ? "checkmark.circle.fill" : "clock.fill"} size={22} color={assessmentSyncState === "synced" ? "#16866D" : "#64748B"} />
          <Text style={[styles.statusText, { color: colors.text }]}>{assessmentSyncState === "synced" ? "已保存到家庭测评记录" : "已保存在本机，连接家庭后可同步"}</Text>
        </View>

        <Pressable onPress={() => router.push("/ui/UI-03" as Href)} style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.tint }, pressed && styles.pressed]}>
          <IconSymbol name="star.fill" size={18} color="#FFFFFF" />
          <Text style={styles.primaryButtonText}>进入 AI 成长综合解读</Text>
        </Pressable>
        <Text style={[styles.nextStepHint, { color: colors.muted }]}>下一步，AI 会基于本次家庭自查整理支持假设；你可以先阅读，再决定是否继续。</Text>
        <Pressable onPress={() => router.replace("/ui/UI-02" as Href)} style={({ pressed }) => [styles.linkButton, pressed && styles.pressed]}>
          <Text style={[styles.linkButtonText, { color: colors.muted }]}>返回调整免费测评</Text>
        </Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { flexGrow: 1, padding: 18, gap: 14 },
  hero: { borderRadius: 20, paddingHorizontal: 16, paddingVertical: 16, gap: 10, flexDirection: "row", alignItems: "flex-start" },
  heroCopy: { flex: 1, gap: 4 },
  heroIcon: { width: 40, height: 40, borderRadius: 13, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  heroTitle: { fontSize: 18, lineHeight: 25, fontWeight: "900" },
  heroText: { fontSize: 13, lineHeight: 20 },
  card: { borderWidth: 1, borderRadius: 18, padding: 16, gap: 7 },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  cardLabel: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  cardTitle: { fontSize: 17, lineHeight: 24, fontWeight: "900" },
  focusTitle: { fontSize: 22, lineHeight: 29, fontWeight: "900" },
  cardText: { fontSize: 13, lineHeight: 21 },
  coverageCard: { borderWidth: 1, borderRadius: 18, padding: 16, gap: 6 },
  coverageTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" },
  uncertaintyText: { color: "#8A5A00", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  supportBadge: { borderRadius: 999, backgroundColor: "#EEF6FF", paddingHorizontal: 10, paddingVertical: 5 },
  supportBadgeText: { color: "#1B65C9", fontSize: 11, lineHeight: 15, fontWeight: "900" },
  progressCount: { fontSize: 18, lineHeight: 24, fontWeight: "900" },
  progressTrack: { height: 7, borderRadius: 999, backgroundColor: "#E2E8F0", overflow: "hidden", marginTop: 2 },
  progressFill: { height: 7, borderRadius: 999, backgroundColor: "#16866D" },
  boundaryText: { fontSize: 12, lineHeight: 19, marginTop: 4 },
  observationRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 2 },
  signalRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, borderRadius: 12, backgroundColor: "#F7FBF8", paddingHorizontal: 10, paddingVertical: 8, marginTop: 2 },
  dot: { width: 6, height: 6, borderRadius: 3, marginTop: 8 },
  pillRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 2 },
  supportPill: { borderRadius: 999, backgroundColor: "#EAF8F3", paddingHorizontal: 11, paddingVertical: 6 },
  supportPillText: { color: "#126E59", fontSize: 12, lineHeight: 16, fontWeight: "800" },
  evidenceGrid: { gap: 8, marginTop: 2 },
  evidenceBlock: { borderRadius: 13, backgroundColor: "#F8FAFC", padding: 11, gap: 3 },
  evidenceLabel: { fontSize: 12, lineHeight: 17, fontWeight: "900" },
  statusCard: { borderRadius: 16, padding: 14, flexDirection: "row", alignItems: "center", gap: 9 },
  statusText: { flex: 1, fontSize: 13, lineHeight: 19, fontWeight: "700" },
  primaryButton: { minHeight: 52, borderRadius: 18, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" },
  linkButton: { minHeight: 40, alignItems: "center", justifyContent: "center", paddingHorizontal: 12 },
  linkButtonText: { fontSize: 12, lineHeight: 18, textAlign: "center", textDecorationLine: "underline" },
  nextStepHint: { fontSize: 12, lineHeight: 18, textAlign: "center", marginTop: -6 },
  pressed: { opacity: 0.85 },
});