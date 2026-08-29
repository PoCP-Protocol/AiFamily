import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { communityEntriesForDisplay, postKindLabel } from "@/lib/family/community-content";
import { familyApi } from "@/lib/family/family-api-client";
import { selectLearningExchangeFeed, type FamilyApiPlatformSurfacesProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

const TABS = ["私有小记", "待发布草稿", "我的收藏"] as const;

export default function MyCommunityScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { communityPostDraft, communityInteractionDrafts, campCompletedDays, campCurrentDay } = useFamilyMobile();
  const [projection, setProjection] = useState<FamilyApiPlatformSurfacesProjection | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("私有小记");

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getDevPlatformSurfaces<FamilyApiPlatformSurfacesProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => { if (active) setProjection(result); })
      .catch((error) => { console.error("UI-28 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const feed = selectLearningExchangeFeed(projection);
  const bookmarkedEntries = useMemo(() => communityEntriesForDisplay(feed?.entries).filter((item) => communityInteractionDrafts[item.exchangeRef]?.bookmarked), [communityInteractionDrafts, feed?.entries]);
  const followingCount = Object.values(communityInteractionDrafts).filter((item) => item.following).length;
  const responseCount = Object.values(communityInteractionDrafts).filter((item) => item.responseText).length;
  const progress = Math.round((campCompletedDays.length / 21) * 100);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} refreshControl={<FamilyRefreshControl />}>
        <View style={styles.topBar}><View style={styles.topSpacer} /><Text style={styles.topTitle}>我的</Text><Text style={styles.topMore}>•••</Text></View>
        <View style={styles.profileCard}><View style={styles.avatar}><IconSymbol name="person.crop.circle.fill" size={49} color="#2563EB" /></View><View style={styles.profileCopy}><Text style={styles.profileTitle}>我们的家庭内容空间</Text><Text style={styles.profileText}>私有小记、收藏与回应都在这里回看</Text><View style={styles.profileMeta}><Text style={styles.profileMetaText}>仅家庭可见</Text><Text style={styles.profileMetaText}>无公开发布</Text></View></View><IconSymbol name="lock.fill" size={23} color="#09295A" /></View>

        <View style={[styles.summaryPanel, { backgroundColor: colors.surface, borderColor: colors.border }]}><SummaryItem icon="square.and.pencil" label="我的小记" value={communityPostDraft ? "1" : "0"} color="#2563EB" /><SummaryItem icon="bookmark.fill" label="我的收藏" value={String(bookmarkedEntries.length)} color="#F28C45" /><SummaryItem icon="person.2.fill" label="关注草稿" value={String(followingCount)} color="#7C5CE5" /><SummaryItem icon="message.fill" label="回应草稿" value={String(responseCount)} color="#16866D" /></View>

        <View style={[styles.tabBar, { borderBottomColor: colors.border }]}>{TABS.map((item) => <Pressable key={item} onPress={() => setTab(item)} style={({ pressed }) => [styles.tabItem, pressed && styles.pressed]}><Text style={[styles.tabText, { color: tab === item ? colors.tint : colors.muted }]}>{item}</Text>{tab === item ? <View style={[styles.tabLine, { backgroundColor: colors.tint }]} /> : null}</Pressable>)}</View>

        {tab === "我的收藏" ? <View style={styles.listSection}>{bookmarkedEntries.length ? bookmarkedEntries.map((item) => <Pressable key={item.exchangeRef} onPress={() => router.push(`/ui/UI-27?exchangeRef=${encodeURIComponent(item.exchangeRef)}` as Href)} style={({ pressed }) => [styles.contentCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}><View style={[styles.cardIcon, { backgroundColor: "#F28C4518" }]}><IconSymbol name="bookmark.fill" size={24} color="#F28C45" /></View><View style={styles.cardCopy}><Text style={[styles.cardTag, { color: colors.success }]}>#{item.topic}</Text><Text style={[styles.cardTitle, { color: colors.text }]}>{item.title}</Text><Text style={[styles.cardText, { color: colors.muted }]} numberOfLines={2}>{item.summary}</Text></View><IconSymbol name="chevron.right" size={20} color={colors.muted} /></Pressable>) : <EmptyState title="还没有收藏" text="在家长社区看到想慢慢读的内容，可以先收藏到这里。" target="UI-25" />}</View> : <View style={styles.listSection}>{communityPostDraft ? <Pressable onPress={() => router.push("/ui/UI-26" as Href)} style={({ pressed }) => [styles.contentCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}><View style={[styles.cardIcon, { backgroundColor: "#2563EB18" }]}><IconSymbol name="square.and.pencil" size={25} color="#2563EB" /></View><View style={styles.cardCopy}><View style={styles.cardTopline}><Text style={[styles.cardTag, { color: colors.tint }]}>#{communityPostDraft.topic}</Text><Text style={styles.privateTag}>私有草稿</Text></View><Text style={[styles.cardTitle, { color: colors.text }]}>{communityPostDraft.title}</Text><Text style={[styles.cardText, { color: colors.muted }]} numberOfLines={2}>{communityPostDraft.body}</Text>{communityPostDraft.aiTagDraft?.tags.length ? <View style={styles.tagRow}>{communityPostDraft.aiTagDraft.tags.map((tag) => <Text key={tag} style={styles.tagText}>#{tag}</Text>)}</View> : null}<Text style={[styles.cardMeta, { color: colors.muted }]}>{postKindLabel(communityPostDraft.kind)} · 仅家庭可见</Text></View><IconSymbol name="chevron.right" size={20} color={colors.muted} /></Pressable> : <EmptyState title="还没有家庭小记" text="可以从今天的一件小事开始，先保存成家庭私有草稿。" target="UI-26" />}</View>}

        <View style={[styles.campCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.campHeader}><View style={[styles.campIcon, { backgroundColor: "#16866D16" }]}><IconSymbol name="calendar.fill" size={26} color={colors.success} /></View><View style={styles.campCopy}><Text style={[styles.campTitle, { color: colors.text }]}>21 天智慧父母成长营</Text><Text style={[styles.campText, { color: colors.muted }]}>已记录 {campCompletedDays.length}/21 天 · 当前第 {campCurrentDay} 天</Text></View><Pressable onPress={() => router.push("/ui/UI-09" as Href)}><Text style={[styles.campLink, { color: colors.tint }]}>继续</Text></Pressable></View><View style={[styles.progressTrack, { backgroundColor: colors.border }]}><View style={[styles.progressFill, { width: `${progress}%` }]} /></View><Text style={[styles.campBoundary, { color: colors.muted }]}>成长营进度来自家庭行动记录，不是社区等级或家庭评分。</Text></View>

        <View style={[styles.boundary, { borderColor: colors.border }]}><IconSymbol name="shield.fill" size={20} color={colors.success} /><Text style={[styles.boundaryText, { color: colors.muted }]}>当前只管理家庭私有小记和互动草稿；没有粉丝数、公开动态、社区积分或对外可见状态。</Text></View>
        <Pressable onPress={() => router.push("/ui/UI-26" as Href)} style={({ pressed }) => [styles.writeButton, pressed && styles.pressed]}><IconSymbol name="square.and.pencil" size={21} color="#FFFFFF" /><Text style={styles.writeText}>写一篇家庭小记</Text></Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

function SummaryItem({ icon, label, value, color }: { icon: "square.and.pencil" | "bookmark.fill" | "person.2.fill" | "message.fill"; label: string; value: string; color: string }) {
  return <View style={styles.summaryItem}><View style={[styles.summaryIcon, { backgroundColor: `${color}16` }]}><IconSymbol name={icon} size={23} color={color} /></View><Text style={[styles.summaryValue, { color }]}>{value}</Text><Text style={styles.summaryLabel}>{label}</Text></View>;
}

function EmptyState({ title, text, target }: { title: string; text: string; target: "UI-25" | "UI-26" }) {
  const colors = useColors();
  return <View style={[styles.empty, { backgroundColor: colors.surface, borderColor: colors.border }]}><IconSymbol name="lock.fill" size={29} color={colors.muted} /><Text style={[styles.emptyTitle, { color: colors.text }]}>{title}</Text><Text style={[styles.emptyText, { color: colors.muted }]}>{text}</Text><Pressable onPress={() => router.push(`/ui/${target}` as Href)} style={({ pressed }) => [styles.emptyButton, { borderColor: colors.tint }, pressed && styles.pressed]}><Text style={[styles.emptyButtonText, { color: colors.tint }]}>{target === "UI-26" ? "写小记" : "去社区看看"}</Text></Pressable></View>;
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 14, paddingBottom: 42, gap: 14 }, topBar: { minHeight: 40, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topSpacer: { width: 42 }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, topMore: { color: "#22272D", fontSize: 18, lineHeight: 20, fontWeight: "900" }, profileCard: { minHeight: 126, borderRadius: 24, backgroundColor: "#E8F2FF", padding: 18, flexDirection: "row", alignItems: "center", gap: 12 }, avatar: { width: 62, height: 62, borderRadius: 31, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" }, profileCopy: { flex: 1, gap: 4 }, profileTitle: { color: "#09295A", fontSize: 18, lineHeight: 25, fontWeight: "900" }, profileText: { color: "#5B7091", fontSize: 10, lineHeight: 16 }, profileMeta: { flexDirection: "row", gap: 7, marginTop: 3 }, profileMetaText: { color: "#536A8B", fontSize: 9, lineHeight: 13, fontWeight: "800" },
  summaryPanel: { minHeight: 108, borderWidth: 1, borderRadius: 21, padding: 12, flexDirection: "row", justifyContent: "space-between" }, summaryItem: { width: 74, alignItems: "center", gap: 3 }, summaryIcon: { width: 39, height: 39, borderRadius: 13, alignItems: "center", justifyContent: "center" }, summaryValue: { fontSize: 15, lineHeight: 20, fontWeight: "900" }, summaryLabel: { color: "#64748B", fontSize: 9, lineHeight: 13, fontWeight: "800" },
  tabBar: { minHeight: 45, borderBottomWidth: 1, flexDirection: "row" }, tabItem: { flex: 1, alignItems: "center", justifyContent: "center" }, tabText: { fontSize: 12, lineHeight: 18, fontWeight: "900" }, tabLine: { width: 35, height: 3, borderRadius: 2, marginTop: 7 }, listSection: { gap: 10 }, contentCard: { minHeight: 132, borderWidth: 1, borderRadius: 20, padding: 13, flexDirection: "row", alignItems: "center", gap: 10 }, cardIcon: { width: 50, height: 50, borderRadius: 17, alignItems: "center", justifyContent: "center" }, cardCopy: { flex: 1, gap: 3 }, cardTopline: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, cardTag: { fontSize: 9, lineHeight: 13, fontWeight: "900" }, privateTag: { color: "#16866D", backgroundColor: "#16866D13", borderRadius: 7, paddingHorizontal: 6, paddingVertical: 2, fontSize: 8, lineHeight: 11, fontWeight: "900" }, cardTitle: { fontSize: 14, lineHeight: 20, fontWeight: "900" }, cardText: { fontSize: 10, lineHeight: 16 }, cardMeta: { fontSize: 9, lineHeight: 13 }, tagRow: { flexDirection: "row", flexWrap: "wrap", gap: 4 }, tagText: { color: "#2563EB", backgroundColor: "#EAF2FF", borderRadius: 7, paddingHorizontal: 5, paddingVertical: 2, fontSize: 8, lineHeight: 11, fontWeight: "800" },
  empty: { minHeight: 176, borderWidth: 1, borderRadius: 20, padding: 18, alignItems: "center", justifyContent: "center", gap: 6 }, emptyTitle: { fontSize: 14, lineHeight: 20, fontWeight: "900" }, emptyText: { maxWidth: 280, fontSize: 10, lineHeight: 16, textAlign: "center" }, emptyButton: { minHeight: 36, borderWidth: 1.5, borderRadius: 18, paddingHorizontal: 16, alignItems: "center", justifyContent: "center", marginTop: 5 }, emptyButtonText: { fontSize: 10, lineHeight: 15, fontWeight: "900" },
  campCard: { minHeight: 139, borderWidth: 1, borderRadius: 21, padding: 14, gap: 10 }, campHeader: { flexDirection: "row", alignItems: "center", gap: 10 }, campIcon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center" }, campCopy: { flex: 1, gap: 3 }, campTitle: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, campText: { fontSize: 10, lineHeight: 15 }, campLink: { fontSize: 10, lineHeight: 15, fontWeight: "900" }, progressTrack: { height: 7, borderRadius: 4, overflow: "hidden" }, progressFill: { height: 7, borderRadius: 4, backgroundColor: "#16866D" }, campBoundary: { fontSize: 9, lineHeight: 14 }, boundary: { minHeight: 68, borderTopWidth: 1, paddingTop: 14, flexDirection: "row", alignItems: "flex-start", gap: 8 }, boundaryText: { flex: 1, fontSize: 11, lineHeight: 17 }, writeButton: { minHeight: 52, borderRadius: 19, backgroundColor: "#F28C45", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 }, writeText: { color: "#FFFFFF", fontSize: 14, lineHeight: 20, fontWeight: "900" }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
