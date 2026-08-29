import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import Svg, { Line, Polygon } from "react-native-svg";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { getGrowthFocus } from "@/lib/family/core-growth";
import { familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

interface RemoteReview { recorded_actions?: { receipt_id: string }[]; next_hint?: { text: string } | null; }

export default function GrowthReviewScreen() {
  const session = useFamilyApiSession();
  const { selectedGrowthFocus, lastReceipt, campCompletedDays, activeOnboardingId } = useFamilyMobile();
  const focus = getGrowthFocus(selectedGrowthFocus);
  const [remote, setRemote] = useState<RemoteReview | null>(null);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily || !activeOnboardingId) return;
    let active = true;
    familyApi.getFamilyReviewReadback<RemoteReview>(session.token, session.selectedFamily.family_id, activeOnboardingId)
      .then((result) => { if (active) setRemote(result); })
      .catch((error) => { console.error("UI-08 remote projection failed", error); });
    return () => { active = false; };
  }, [activeOnboardingId, session.selectedFamily, session.status, session.token]);

  const report = useMemo(() => {
    const recorded = (remote?.recorded_actions?.length ?? 0) + (lastReceipt ? 1 : 0) + campCompletedDays.length;
    return {
      recorded,
      advantage: lastReceipt ? "家庭已经记录过一次愿意停下来倾听的行动" : "家庭愿意从一次小行动开始了解彼此",
      attention: focus ? `继续观察“${focus.title}”相关场景，不把一次记录当作结论` : "选择一个最常出现的家庭场景，先从过程开始观察",
      suggestion: remote?.next_hint?.text ?? "本周只练习一个能坚持的小行动，再回看过程",
    };
  }, [campCompletedDays.length, focus, lastReceipt, remote?.next_hint?.text, remote?.recorded_actions?.length]);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} refreshControl={<FamilyRefreshControl />}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}><IconSymbol name="chevron.left" size={27} color="#23272C" /></Pressable>
          <Text style={styles.topTitle}>家庭过程回顾</Text>
          <IconSymbol name="arrow.up.right.square" size={22} color="#23272C" />
        </View>

        <View style={styles.profileBanner}>
          <View style={styles.avatar}><IconSymbol name="person.crop.circle.fill" size={52} color="#FFFFFF" /></View>
          <View style={styles.profileCopy}><Text style={styles.profileTitle}>家庭过程回顾</Text><Text style={styles.profileMeta}>记录时间：2026-08-22</Text><Text style={styles.profileMeta}>报告编号：家庭私有记录</Text></View>
          <Text style={styles.sparkle}>✦</Text>
        </View>

        <Text style={styles.sectionTitle}>五个观察方向</Text>
        <View style={styles.radarPanel}>
          <Text style={[styles.radarLabel, styles.labelTop]}>亲子沟通</Text><Text style={[styles.radarLabel, styles.labelRightTop]}>学习习惯</Text><Text style={[styles.radarLabel, styles.labelRightBottom]}>情绪管理</Text><Text style={[styles.radarLabel, styles.labelLeftBottom]}>自律能力</Text><Text style={[styles.radarLabel, styles.labelLeftTop]}>手机依赖</Text>
          <Svg width={176} height={153} viewBox="0 0 176 153"><Polygon points="88,8 160,59 133,142 43,142 16,59" fill="#D9ECFF" stroke="#8CBFF4" strokeWidth="1.5" /><Polygon points="88,30 139,67 120,124 56,124 37,67" fill="#4B9AF560" stroke="#4B9AF5" strokeWidth="2" /><Line x1="88" y1="8" x2="88" y2="142" stroke="#B9D6F2" /><Line x1="16" y1="59" x2="160" y2="59" stroke="#B9D6F2" /><Line x1="16" y1="59" x2="133" y2="142" stroke="#B9D6F2" /><Line x1="160" y1="59" x2="43" y2="142" stroke="#B9D6F2" /></Svg>
          <View style={styles.radarCenter}><Text style={styles.centerSmall}>已记录</Text><Text style={styles.centerText}>{report.recorded}</Text><Text style={styles.centerSmall}>次行动</Text></View>
        </View>

        <ReportRow tone="green" title="已看见的行动" text={report.advantage} />
        <ReportRow tone="coral" title="继续观察" text={report.attention} />
        <ReportRow tone="gold" title="下一步可试" text={report.suggestion} />

        <Text style={styles.pathTitle}>可选行动路径</Text>
        <View style={styles.pathRow}><PathStep duration="7天" label="先试一次" color="#5B9FF4" /><Text style={styles.arrow}>→</Text><PathStep duration="30天" label="持续记录" color="#568EE9" /><Text style={styles.arrow}>→</Text><PathStep duration="90天" label="回看调整" color="#2B74D8" /></View>

        <Pressable onPress={() => router.push("/ui/UI-04" as Href)} style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}><Text style={styles.primaryText}>查看可选支持方案</Text></Pressable>
        <Text style={styles.boundary}>这是一份家庭过程回顾，不是儿童诊断、家庭总分或效果结论。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function ReportRow({ tone, title, text }: { tone: "green" | "coral" | "gold"; title: string; text: string }) { return <View style={[styles.reportRow, tone === "green" ? styles.green : tone === "coral" ? styles.coral : styles.gold]}><View style={styles.rowMark}><Text style={styles.rowCheck}>✓</Text></View><Text style={styles.rowTitle}>{title}</Text><Text style={styles.rowText}>{text}</Text></View>; }
function PathStep({ duration, label, color }: { duration: string; label: string; color: string }) { return <View style={styles.pathStep}><Text style={[styles.pathDuration, { color }]}>{duration}</Text><Text style={styles.pathLabel}>{label}</Text></View>; }

const styles = StyleSheet.create({
  content: { paddingHorizontal: 14, paddingBottom: 28, backgroundColor: "#FFFFFF" }, topBar: { minHeight: 56, alignItems: "center", justifyContent: "space-between", flexDirection: "row" }, backButton: { width: 42, height: 42, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#20242A", fontSize: 17, lineHeight: 24, fontWeight: "900" },
  profileBanner: { minHeight: 74, borderRadius: 10, paddingHorizontal: 13, flexDirection: "row", alignItems: "center", backgroundColor: "#4A9BEF", overflow: "hidden" }, avatar: { width: 53, height: 53, borderRadius: 27, backgroundColor: "#FFFFFF28", alignItems: "center", justifyContent: "center" }, profileCopy: { flex: 1, marginLeft: 11, gap: 2 }, profileTitle: { color: "#FFFFFF", fontSize: 17, lineHeight: 23, fontWeight: "900" }, profileMeta: { color: "#E5F2FF", fontSize: 10, lineHeight: 14, fontWeight: "700" }, sparkle: { color: "#D8F1FF", fontSize: 24 },
  sectionTitle: { color: "#30353B", fontSize: 15, lineHeight: 21, fontWeight: "900", marginTop: 9, marginBottom: 1 }, radarPanel: { height: 182, alignItems: "center", justifyContent: "center", position: "relative" }, radarLabel: { position: "absolute", color: "#50606F", fontSize: 10, lineHeight: 14, fontWeight: "800" }, labelTop: { top: 2 }, labelRightTop: { top: 42, right: 3 }, labelRightBottom: { bottom: 37, right: 4 }, labelLeftBottom: { bottom: 37, left: 4 }, labelLeftTop: { top: 42, left: 3 }, radarCenter: { position: "absolute", width: 72, height: 72, borderRadius: 36, backgroundColor: "#F2F8FF", alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: "#569EF4" }, centerSmall: { color: "#5C7996", fontSize: 10, lineHeight: 13, fontWeight: "800" }, centerText: { color: "#287CEC", fontSize: 23, lineHeight: 25, fontWeight: "900" },
  reportRow: { minHeight: 31, borderRadius: 8, paddingHorizontal: 8, flexDirection: "row", alignItems: "center", gap: 7, marginTop: 5 }, green: { backgroundColor: "#EDF8F1" }, coral: { backgroundColor: "#FFF1EB" }, gold: { backgroundColor: "#FFF7E7" }, rowMark: { width: 17, height: 17, borderRadius: 9, backgroundColor: "#55B779", alignItems: "center", justifyContent: "center" }, rowCheck: { color: "#FFFFFF", fontSize: 11, lineHeight: 12, fontWeight: "900" }, rowTitle: { color: "#4D5C62", minWidth: 42, fontSize: 12, lineHeight: 16, fontWeight: "900" }, rowText: { flex: 1, color: "#4D575F", fontSize: 10, lineHeight: 14, fontWeight: "700" },
  pathTitle: { color: "#33383E", fontSize: 14, lineHeight: 20, fontWeight: "900", marginTop: 10, marginBottom: 4 }, pathRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-around" }, pathStep: { width: 72, minHeight: 47, borderRadius: 9, backgroundColor: "#F3F8FF", alignItems: "center", justifyContent: "center" }, pathDuration: { fontSize: 18, lineHeight: 22, fontWeight: "900" }, pathLabel: { color: "#5F6A77", fontSize: 10, lineHeight: 14, fontWeight: "800" }, arrow: { color: "#9AB0C5", fontSize: 20 }, primaryButton: { minHeight: 49, marginTop: 12, borderRadius: 25, backgroundColor: "#1678F2", alignItems: "center", justifyContent: "center" }, primaryText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" }, boundary: { color: "#87919B", textAlign: "center", fontSize: 10, lineHeight: 15, marginTop: 9 }, pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});
