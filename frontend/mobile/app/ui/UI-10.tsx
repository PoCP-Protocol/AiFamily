import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { getChildPrompt } from "@/lib/family/child-growth";
import { familyApi } from "@/lib/family/family-api-client";
import { selectChildActionPrompt, type FamilyApiCoreGrowthProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { haptic } from "@/lib/haptics";

const ACTIVITY_CARDS = [
  { title: "专注力训练", subtitle: "一起专心一会儿", icon: "◎", bg: "#C9F4F8", ink: "#237EAD" },
  { title: "阅读打卡", subtitle: "养成阅读习惯", icon: "▰", bg: "#FFE3A7", ink: "#C17522" },
  { title: "情绪小日记", subtitle: "认识和表达心情", icon: "●", bg: "#DDD0FF", ink: "#7A55BC" },
  { title: "今日目标", subtitle: "朝着今天的目标走", icon: "✓", bg: "#FFE1AD", ink: "#DB7A1E" },
] as const;

export default function ChildAssistantScreen() {
  const session = useFamilyApiSession();
  const { campCompletedDays } = useFamilyMobile();
  const [remoteProjection, setRemoteProjection] = useState<FamilyApiCoreGrowthProjection | null>(null);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getDevCoreGrowth<FamilyApiCoreGrowthProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => { if (active) setRemoteProjection(result); })
      .catch((error) => { console.error("UI-10 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const apiPrompt = selectChildActionPrompt(remoteProjection);
  const localPrompt = useMemo(() => getChildPrompt(campCompletedDays.length), [campCompletedDays.length]);
  const challenge = apiPrompt ? { title: apiPrompt.headline, invitation: apiPrompt.shared_action } : { title: localPrompt.title, invitation: localPrompt.invitation };
  const progress = Math.min(86, 32 + campCompletedDays.length * 8);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.topBar}><Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}><IconSymbol name="chevron.left" size={27} color="#22272D" /></Pressable><Text style={styles.topTitle}>成长小助手</Text><Text style={styles.more}>•••</Text></View>
        <View style={styles.welcome}><View style={styles.cloudOne} /><View style={styles.cloudTwo} /><View style={styles.childFigure}><View style={styles.childHead} /><View style={styles.childArm} /></View><Text style={styles.welcomeTitle}>Hi，乐乐小朋友！</Text><Text style={styles.welcomeSubtitle}>今天又是元气满满的一天！</Text></View>
        <View style={styles.energyCard}><View style={styles.energyHead}><View style={styles.lightning}><Text style={styles.lightningText}>ϟ</Text></View><Text style={styles.energyTitle}>成长能量</Text><Text style={styles.energyValue}>今天慢慢积累</Text></View><View style={styles.energyRow}><View style={styles.energyTrack}><View style={[styles.energyFill, { width: `${progress}%` }]} /></View><Text style={styles.level}>Lv.3</Text></View></View>
        <View style={styles.cardGrid}>{ACTIVITY_CARDS.map((card) => <View key={card.title} style={[styles.activityCard, { backgroundColor: card.bg }]}><Text style={[styles.activityIcon, { color: card.ink }]}>{card.icon}</Text><View><Text style={[styles.activityTitle, { color: card.ink }]}>{card.title}</Text><Text style={styles.activitySubtitle}>{card.subtitle}</Text></View></View>)}</View>
        <View style={styles.challengeCard}><View style={styles.challengeTitleRow}><Text style={styles.trophy}>♜</Text><Text style={styles.challengeLabel}>今日挑战</Text></View><Text style={styles.challengeText} numberOfLines={2}>{challenge.invitation}</Text><View style={styles.challengeMeta}><Text style={styles.processNote}>一次家庭小行动</Text><Text style={styles.starNote}>慢慢积累</Text><View style={styles.arrowCircle}><IconSymbol name="chevron.right" size={20} color="#377EDC" /></View></View></View>
        <View style={styles.collection}><Text style={styles.collectionTitle}>我的小收藏</Text><View style={styles.collectionRow}><Collection icon="★" label={String(Math.max(1, campCompletedDays.length))} color="#FFB52B" /><Collection icon="♜" label="3" color="#9165E6" /><Collection icon="♕" label="1" color="#E1A331" /><Collection icon="▣" label="2" color="#F08E49" /></View></View>
        <Pressable onPress={() => { haptic.light(); router.push("/ui/UI-09" as Href); }} style={({ pressed }) => [styles.startButton, pressed && styles.pressed]}><Text style={styles.startText}>开始挑战</Text></Pressable>
        <Text style={styles.boundary}>挑战是一起尝试，不记录能力、分数或成长结果。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function Collection({ icon, label, color }: { icon: string; label: string; color: string }) { return <View style={styles.collectionItem}><Text style={[styles.collectionIcon, { color }]}>{icon}</Text><Text style={styles.collectionNumber}>{label}</Text></View>; }

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingBottom: 26, backgroundColor: "#FFFFFF" }, topBar: { minHeight: 67, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, backButton: { width: 44, height: 44, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#20242A", fontSize: 20, lineHeight: 27, fontWeight: "900" }, more: { color: "#2B3036", width: 44, textAlign: "right", fontSize: 20, lineHeight: 22, fontWeight: "900", letterSpacing: 1 },
  welcome: { minHeight: 151, borderRadius: 15, paddingHorizontal: 20, paddingTop: 31, overflow: "hidden", backgroundColor: "#C7F2FF" }, cloudOne: { position: "absolute", left: -30, bottom: -26, width: 150, height: 65, borderRadius: 40, backgroundColor: "#FFFFFFB0" }, cloudTwo: { position: "absolute", left: 80, top: -24, width: 132, height: 48, borderRadius: 35, backgroundColor: "#FFFFFF80" }, childFigure: { position: "absolute", right: 40, bottom: 0, width: 77, height: 92, borderTopLeftRadius: 34, borderTopRightRadius: 34, backgroundColor: "#1577C9" }, childHead: { position: "absolute", left: 11, top: -36, width: 57, height: 57, borderRadius: 29, backgroundColor: "#7A422B" }, childArm: { position: "absolute", right: -21, top: 18, width: 37, height: 15, borderRadius: 8, backgroundColor: "#F6B177", transform: [{ rotate: "-42deg" }] }, welcomeTitle: { color: "#1F2E3B", fontSize: 23, lineHeight: 30, fontWeight: "900" }, welcomeSubtitle: { color: "#3F637B", fontSize: 14, lineHeight: 20, fontWeight: "800", marginTop: 5 },
  energyCard: { minHeight: 91, marginTop: -1, borderWidth: 1, borderColor: "#E4EBF1", borderRadius: 17, paddingHorizontal: 16, paddingVertical: 13, backgroundColor: "#FFFFFF" }, energyHead: { flexDirection: "row", alignItems: "center" }, lightning: { width: 25, height: 25, borderRadius: 13, backgroundColor: "#FFF0C6", alignItems: "center", justifyContent: "center" }, lightningText: { color: "#F2A61C", fontSize: 21, lineHeight: 23, fontWeight: "900" }, energyTitle: { color: "#3C4249", marginLeft: 7, fontSize: 15, lineHeight: 21, fontWeight: "900" }, energyValue: { flex: 1, textAlign: "right", color: "#23282F", fontSize: 15, lineHeight: 21, fontWeight: "900" }, energyRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 12 }, energyTrack: { flex: 1, height: 18, padding: 2, borderRadius: 9, backgroundColor: "#E9EDF1", overflow: "hidden" }, energyFill: { height: 14, borderRadius: 7, backgroundColor: "#FFAE1A" }, level: { color: "#E98728", fontSize: 16, lineHeight: 21, fontWeight: "900" },
  cardGrid: { marginTop: 17, flexDirection: "row", flexWrap: "wrap", gap: 14, justifyContent: "space-between" }, activityCard: { width: "47.9%", minHeight: 120, borderRadius: 16, padding: 13, overflow: "hidden", justifyContent: "space-between" }, activityIcon: { alignSelf: "flex-end", fontSize: 44, lineHeight: 45, fontWeight: "900", opacity: 0.8 }, activityTitle: { fontSize: 18, lineHeight: 24, fontWeight: "900" }, activitySubtitle: { color: "#59646F", fontSize: 12, lineHeight: 17, fontWeight: "700", marginTop: 3 },
  challengeCard: { minHeight: 101, marginTop: 17, borderWidth: 1, borderColor: "#E4EBF1", borderRadius: 17, paddingHorizontal: 15, paddingVertical: 12, backgroundColor: "#FFFFFF" }, challengeTitleRow: { flexDirection: "row", alignItems: "center", gap: 7 }, trophy: { color: "#F0A81C", fontSize: 21, lineHeight: 24 }, challengeLabel: { color: "#3F454C", fontSize: 16, lineHeight: 22, fontWeight: "900" }, challengeText: { color: "#404951", fontSize: 15, lineHeight: 21, fontWeight: "800", marginTop: 5 }, challengeMeta: { flexDirection: "row", alignItems: "center", marginTop: 4 }, processNote: { color: "#F29B32", fontSize: 12, lineHeight: 17, fontWeight: "900" }, starNote: { color: "#3FB083", fontSize: 12, lineHeight: 17, fontWeight: "900", marginLeft: 18 }, arrowCircle: { marginLeft: "auto", width: 35, height: 35, borderRadius: 18, backgroundColor: "#E9F2FF", alignItems: "center", justifyContent: "center" },
  collection: { minHeight: 84, marginTop: 13, borderWidth: 1, borderColor: "#E4EBF1", borderRadius: 17, paddingHorizontal: 14, paddingVertical: 10 }, collectionTitle: { color: "#42474D", fontSize: 15, lineHeight: 20, fontWeight: "900" }, collectionRow: { flexDirection: "row", justifyContent: "space-around", marginTop: 4 }, collectionItem: { alignItems: "center", gap: 0 }, collectionIcon: { fontSize: 31, lineHeight: 36, fontWeight: "900" }, collectionNumber: { color: "#4E5760", fontSize: 12, lineHeight: 16, fontWeight: "900" },
  startButton: { minHeight: 56, marginTop: 13, borderRadius: 29, backgroundColor: "#1D78EC", alignItems: "center", justifyContent: "center" }, startText: { color: "#FFFFFF", fontSize: 19, lineHeight: 26, fontWeight: "900" }, boundary: { color: "#84909B", textAlign: "center", fontSize: 10, lineHeight: 15, marginTop: 8 }, pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});
