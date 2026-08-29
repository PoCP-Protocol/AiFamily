import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { buildFamilyRhythmEvents } from "@/lib/family/child-growth";
import { familyApi } from "@/lib/family/family-api-client";
import { selectPersonalGrowthJourney, type FamilyApiPlatformSurfacesProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

interface RhythmDisplayItem { id: string; title: string; detail: string; }

export default function FamilyRhythmScreen() {
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const [remoteProjection, setRemoteProjection] = useState<FamilyApiPlatformSurfacesProjection | null>(null);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getDevPlatformSurfaces<FamilyApiPlatformSurfacesProjection>(session.token, session.selectedFamily.family_id).then((result) => { if (active) setRemoteProjection(result); }).catch((error) => { console.error("UI-11 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const localEvents = useMemo(() => buildFamilyRhythmEvents({ selectedGrowthFocus: state.selectedGrowthFocus, lastReceipt: state.lastReceipt, campCompletedDays: state.campCompletedDays, uiActionReceipts: state.uiActionReceipts, childChoiceDraft: state.childChoiceDraft }), [state.campCompletedDays, state.childChoiceDraft, state.lastReceipt, state.selectedGrowthFocus, state.uiActionReceipts]);
  const remoteJourney = selectPersonalGrowthJourney(remoteProjection);
  const events = useMemo<RhythmDisplayItem[]>(() => remoteJourney?.entries.length ? remoteJourney.entries.slice(-3).map((event) => ({ id: event.event_id, title: event.label, detail: event.detail })) : localEvents.slice(-3).map((event) => ({ id: event.id, title: event.title, detail: event.detail })), [localEvents, remoteJourney?.entries]);
  const count = events.length || state.campCompletedDays.length || 1;

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={events}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        ListHeaderComponent={<View><View style={styles.topBar}><Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}><IconSymbol name="chevron.left" size={27} color="#22272D" /></Pressable><Text style={styles.topTitle}>我们的成长节奏</Text><Text style={styles.more}>•••</Text></View><View style={styles.segment}><Segment label="本周" active /><Segment label="本月" /><Segment label="我的过程" /><Segment label="可暂停" /></View><View style={styles.podium}><Podium position="上周" label="慢慢开始" count="过程 1 次" tone="silver" /><Podium position="我们的家庭" label="正在形成节奏" count={`已记录 ${count} 次`} tone="gold" /><Podium position="下次" label="继续一件小事" count="不比较他人" tone="bronze" /></View><Text style={styles.listTitle}>最近家庭过程</Text></View>}
        renderItem={({ item, index }) => <View style={styles.eventRow}><Text style={styles.eventIndex}>{index + 1}</Text><View style={styles.eventAvatar}><IconSymbol name="heart.fill" size={18} color="#5D9CF1" /></View><View style={styles.eventCopy}><Text style={styles.eventTitle}>{item.title}</Text><Text style={styles.eventDetail} numberOfLines={1}>{item.detail}</Text></View><Text style={styles.eventTag}>过程</Text></View>}
        ListEmptyComponent={<View style={styles.empty}><Text style={styles.emptyTitle}>还没有过程记录</Text><Text style={styles.emptyText}>从一次愿意尝试的今日行动开始，之后这里会回看同一家庭的过程。</Text><Pressable onPress={() => router.push("/ui/UI-09" as Href)} style={styles.emptyButton}><Text style={styles.emptyButtonText}>查看今日行动</Text></Pressable></View>}
        ListFooterComponent={<View style={styles.myCard}><View style={styles.myTop}><View style={styles.myAvatar}><IconSymbol name="person.crop.circle.fill" size={42} color="#347FED" /></View><View><Text style={styles.myTitle}>我们的过程：本周已记录 {count} 次</Text><Text style={styles.mySubtitle}>只和自己的过去比较</Text></View></View><View style={styles.myMetrics}><Text style={styles.metric}>已记录 {count} 次</Text><Text style={styles.metric}>可随时暂停</Text></View><View style={styles.safeBadge}><Text style={styles.safeBadgeText}>正在形成属于我们自己的节奏</Text><Text style={styles.safeBadgeIcon}>✦</Text></View><Pressable onPress={() => router.push("/ui/UI-12" as Href)} style={({ pressed }) => [styles.storyButton, pressed && styles.pressed]}><Text style={styles.storyButtonText}>整理成家庭私有故事</Text><IconSymbol name="chevron.right" size={18} color="#FFFFFF" /></Pressable></View>}
      />
    </ScreenContainer>
  );
}

function Segment({ label, active }: { label: string; active?: boolean }) { return <View style={[styles.segmentItem, active && styles.segmentActive]}><Text style={[styles.segmentText, active && styles.segmentTextActive]}>{label}</Text></View>; }
function Podium({ position, label, count, tone }: { position: string; label: string; count: string; tone: "silver" | "gold" | "bronze" }) { return <View style={[styles.podiumItem, tone === "gold" ? styles.podiumGold : tone === "bronze" ? styles.podiumBronze : styles.podiumSilver]}><Text style={styles.podiumPosition}>{position}</Text><View style={styles.podiumAvatar}><IconSymbol name="person.crop.circle.fill" size={41} color={tone === "gold" ? "#B56C14" : "#59748D"} /></View><Text style={styles.podiumLabel}>{label}</Text><Text style={styles.podiumCount}>{count}</Text></View>; }

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingBottom: 27, backgroundColor: "#FFFFFF" }, topBar: { minHeight: 62, alignItems: "center", flexDirection: "row", justifyContent: "space-between" }, backButton: { width: 42, height: 42, justifyContent: "center", alignItems: "flex-start" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, more: { width: 42, textAlign: "right", color: "#2B3036", fontSize: 19, lineHeight: 22, fontWeight: "900", letterSpacing: 1 },
  segment: { minHeight: 42, borderWidth: 1, borderColor: "#C9DAF3", borderRadius: 22, padding: 3, flexDirection: "row" }, segmentItem: { flex: 1, alignItems: "center", justifyContent: "center", borderRadius: 18 }, segmentActive: { backgroundColor: "#F0F7FF", borderWidth: 1, borderColor: "#61A6F7" }, segmentText: { color: "#6E7782", fontSize: 12, lineHeight: 17, fontWeight: "800" }, segmentTextActive: { color: "#287FEA" },
  podium: { height: 218, marginTop: 12, flexDirection: "row", alignItems: "flex-end", justifyContent: "center", gap: 5 }, podiumItem: { width: "30.5%", alignItems: "center", justifyContent: "flex-start", paddingTop: 10, borderTopLeftRadius: 15, borderTopRightRadius: 15 }, podiumSilver: { height: 145, backgroundColor: "#E9F3FF" }, podiumGold: { height: 184, backgroundColor: "#FFF0BF" }, podiumBronze: { height: 135, backgroundColor: "#FFE4CD" }, podiumPosition: { color: "#637689", fontSize: 11, lineHeight: 15, fontWeight: "900" }, podiumAvatar: { width: 51, height: 51, borderRadius: 26, marginTop: 6, backgroundColor: "#FFFFFFA5", alignItems: "center", justifyContent: "center" }, podiumLabel: { color: "#414953", fontSize: 12, lineHeight: 17, fontWeight: "900", marginTop: 5, textAlign: "center" }, podiumCount: { color: "#657482", fontSize: 10, lineHeight: 14, fontWeight: "800", marginTop: 2 }, listTitle: { color: "#343A41", fontSize: 16, lineHeight: 22, fontWeight: "900", marginTop: 13, marginBottom: 2 },
  eventRow: { minHeight: 64, borderBottomWidth: 1, borderBottomColor: "#EDF0F3", flexDirection: "row", alignItems: "center" }, eventIndex: { width: 26, color: "#3F474F", fontSize: 17, lineHeight: 23, fontWeight: "900" }, eventAvatar: { width: 31, height: 31, borderRadius: 16, backgroundColor: "#EAF3FF", alignItems: "center", justifyContent: "center" }, eventCopy: { flex: 1, marginLeft: 9, gap: 1 }, eventTitle: { color: "#454C54", fontSize: 13, lineHeight: 18, fontWeight: "800" }, eventDetail: { color: "#89929C", fontSize: 10, lineHeight: 14 }, eventTag: { color: "#4A88DF", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  empty: { marginTop: 10, borderRadius: 15, padding: 16, backgroundColor: "#F6F9FC", gap: 6 }, emptyTitle: { color: "#3D454D", fontSize: 16, lineHeight: 22, fontWeight: "900" }, emptyText: { color: "#798592", fontSize: 12, lineHeight: 18 }, emptyButton: { alignSelf: "flex-start", minHeight: 36, paddingHorizontal: 13, borderRadius: 18, marginTop: 3, justifyContent: "center", backgroundColor: "#247CED" }, emptyButtonText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  myCard: { marginTop: 15, borderWidth: 2, borderColor: "#74B4FF", borderRadius: 18, padding: 15, backgroundColor: "#F3F9FF" }, myTop: { flexDirection: "row", alignItems: "center", gap: 10 }, myAvatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" }, myTitle: { color: "#367DD8", fontSize: 14, lineHeight: 20, fontWeight: "900" }, mySubtitle: { color: "#637B95", fontSize: 11, lineHeight: 16, fontWeight: "800", marginTop: 2 }, myMetrics: { flexDirection: "row", justifyContent: "space-between", marginTop: 11 }, metric: { color: "#53687C", fontSize: 12, lineHeight: 17, fontWeight: "800" }, safeBadge: { minHeight: 43, marginTop: 12, borderRadius: 8, paddingHorizontal: 11, flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: "#FFF2CE" }, safeBadgeText: { color: "#D48827", fontSize: 14, lineHeight: 20, fontWeight: "900" }, safeBadgeIcon: { color: "#E2A934", fontSize: 25 }, storyButton: { minHeight: 43, marginTop: 10, borderRadius: 22, backgroundColor: "#287CED", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5 }, storyButtonText: { color: "#FFFFFF", fontSize: 13, lineHeight: 18, fontWeight: "900" }, pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});
