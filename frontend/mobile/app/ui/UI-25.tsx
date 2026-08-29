import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { DataSourceBanner } from "@/components/family/data-source-banner";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { communityEntriesForDisplay, COMMUNITY_TOPICS } from "@/lib/family/community-content";
import { familyApi } from "@/lib/family/family-api-client";
import { selectLearningExchangeFeed, type FamilyApiPlatformSurfacesProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

const CHANNELS = ["推荐", "成长打卡", "家长交流", "成长案例", "同城圈子"] as const;

export default function ParentCommunityScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { communityInteractionDrafts, toggleCommunityBookmark } = useFamilyMobile();
  const [projection, setProjection] = useState<FamilyApiPlatformSurfacesProjection | null>(null);
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>("推荐");
  const [visibleCount, setVisibleCount] = useState(4);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadCommunityFeed = useCallback(async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    setLoadState("loading"); setLoadError(null);
    try { setProjection(await familyApi.getDevPlatformSurfaces<FamilyApiPlatformSurfacesProjection>(session.token, session.selectedFamily.family_id)); setLoadState("ready"); }
    catch { setLoadState("error"); setLoadError("社区内容暂时无法同步。"); }
  }, [session.selectedFamily, session.status, session.token]);

  useEffect(() => { void loadCommunityFeed(); }, [loadCommunityFeed]);

  const feed = selectLearningExchangeFeed(projection);
  const entries = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return communityEntriesForDisplay(feed?.entries).filter((item) => {
      const matchesQuery = !needle || `${item.title}${item.summary}${item.topic}`.toLowerCase().includes(needle);
      const matchesChannel = channel === "推荐" || channel === "家长交流" || (channel === "成长打卡" && item.topic === "亲子沟通") || (channel === "成长案例" && item.topic === "家庭阅读") || (channel === "同城圈子" && item.topic === "同城活动");
      return matchesQuery && matchesChannel;
    });
  }, [channel, feed?.entries, query]);
  const visibleEntries = entries.slice(0, visibleCount);
  const loadMore = () => {
    if (loadingMore || visibleCount >= entries.length) return;
    setLoadingMore(true);
    setVisibleCount((count) => Math.min(count + 4, entries.length));
    setLoadingMore(false);
  };

  const openDetail = (exchangeRef: string) => router.push(`/ui/UI-27?exchangeRef=${encodeURIComponent(exchangeRef)}` as Href);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={visibleEntries}
        keyExtractor={(item) => item.exchangeRef}
        contentContainerStyle={styles.content}
        ListHeaderComponent={<View style={styles.header}>
          <View style={styles.topBar}><Text style={styles.topTitle}>家长社区</Text><IconSymbol name="magnifyingglass" size={23} color="#22272D" /></View><DataSourceBanner />{loadState === "error" ? <Pressable onPress={() => void loadCommunityFeed()} style={styles.errorNotice}><Text style={styles.errorText}>{loadError} 点击重试</Text></Pressable> : null}
          <View style={[styles.searchBox, { backgroundColor: colors.surface, borderColor: colors.border }]}><IconSymbol name="magnifyingglass" size={20} color={colors.muted} /><TextInput value={query} onChangeText={setQuery} placeholder="搜索话题、内容或用户" placeholderTextColor={colors.muted} style={[styles.searchInput, { color: colors.text }]} returnKeyType="search" /></View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.channelRow}>{CHANNELS.map((item) => <Pressable key={item} onPress={() => setChannel(item)} style={({ pressed }) => [styles.channelButton, pressed && styles.pressed]}><Text style={[styles.channelText, { color: channel === item ? colors.tint : colors.muted }]}>{item}</Text>{channel === item ? <View style={[styles.channelLine, { backgroundColor: colors.tint }]} /> : null}</Pressable>)}</ScrollView>
          <View style={styles.hero}><View style={styles.heroCopy}><Text style={styles.heroTitle}>今天也来分享孩子成长的小变化</Text><Pressable onPress={() => router.push("/ui/UI-26" as Href)} style={({ pressed }) => [styles.heroAction, pressed && styles.pressed]}><Text style={styles.heroActionText}>去分享</Text><IconSymbol name="chevron.right" size={17} color="#FFFFFF" /></Pressable></View><View style={styles.heroIcon}><IconSymbol name="person.2.fill" size={44} color="#2563EB" /></View></View>
          <View style={[styles.topicPanel, { backgroundColor: colors.surface, borderColor: colors.border }]}>{COMMUNITY_TOPICS.map((topic, index) => <Pressable key={topic} onPress={() => setQuery(topic)} style={({ pressed }) => [styles.topicItem, pressed && styles.pressed]}><View style={[styles.topicIcon, { backgroundColor: ["#16866D18", "#2563EB18", "#7C5CE518", "#F28C4518", "#D74C4C18"][index] }]}><IconSymbol name={["message.fill", "book.fill", "heart.fill", "book.fill", "mappin.circle.fill"][index] as never} size={23} color={["#16866D", "#2563EB", "#7C5CE5", "#F28C45", "#D74C4C"][index]} /></View><Text style={[styles.topicLabel, { color: colors.text }]}>{topic}</Text></Pressable>)}</View>
          <View style={styles.sectionLine}><View><Text style={[styles.sectionTitle, { color: colors.text }]}>{feed?.headline ?? "看看其他家庭的日常小经验"}</Text><Text style={[styles.sectionIntro, { color: colors.muted }]}>{feed?.introduction ?? "先读一读，再决定哪些想法适合自己的家庭。"}</Text></View><Pressable onPress={() => router.push("/ui/UI-28" as Href)}><Text style={[styles.mineLink, { color: colors.tint }]}>我的社区</Text></Pressable></View>
        </View>}
        renderItem={({ item, index }) => {
          const bookmarked = communityInteractionDrafts[item.exchangeRef]?.bookmarked ?? false;
          return <Pressable onPress={() => openDetail(item.exchangeRef)} style={({ pressed }) => [styles.postCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
            <View style={styles.authorRow}><View style={[styles.avatar, { backgroundColor: index % 2 === 0 ? "#F28C4520" : "#16866D20" }]}><IconSymbol name="person.crop.circle.fill" size={34} color={index % 2 === 0 ? "#F28C45" : "#16866D"} /></View><View style={styles.authorCopy}><View style={styles.authorNameRow}><Text style={[styles.authorName, { color: colors.text }]}>{item.authorLabel}</Text><Text style={[styles.reviewedTag, { color: colors.success, backgroundColor: "#16866D14" }]}>经审核摘要</Text></View><Text style={[styles.authorMeta, { color: colors.muted }]}>{item.timeLabel} · {item.topic}</Text></View></View>
            <Text style={[styles.postTitle, { color: colors.text }]}>{item.title}</Text><Text style={[styles.postSummary, { color: colors.muted }]}>{item.summary}</Text>
            <View style={[styles.mediaStrip, { backgroundColor: index % 2 === 0 ? "#E9F2FF" : "#EEF8F4" }]}><IconSymbol name={index % 2 === 0 ? "message.fill" : "book.fill"} size={34} color={index % 2 === 0 ? "#2563EB" : "#16866D"} /><Text style={[styles.mediaText, { color: colors.text }]}>来自家庭日常的经验片段</Text></View>
            <View style={[styles.actionRow, { borderTopColor: colors.border }]}><View style={styles.readAction}><IconSymbol name="message.fill" size={18} color={colors.muted} /><Text style={[styles.actionText, { color: colors.muted }]}>阅读详情</Text></View><Pressable onPress={(event) => { event.stopPropagation(); toggleCommunityBookmark(item.exchangeRef); }} style={({ pressed }) => [styles.bookmarkAction, pressed && styles.pressed]}><IconSymbol name="bookmark.fill" size={19} color={bookmarked ? colors.tint : colors.muted} /><Text style={[styles.actionText, { color: bookmarked ? colors.tint : colors.muted }]}>{bookmarked ? "已收藏" : "收藏"}</Text></Pressable></View>
          </Pressable>;
        }}
        ListEmptyComponent={<View style={styles.empty}><Text style={[styles.emptyTitle, { color: colors.text }]}>暂时没有匹配的内容</Text><Text style={[styles.emptyText, { color: colors.muted }]}>换一个频道或关键词再看看。</Text></View>}
        onEndReached={loadMore}
        onEndReachedThreshold={0.45}
        ListFooterComponent={<View style={styles.footer}><View style={[styles.boundary, { borderColor: colors.border }]}><IconSymbol name="shield.fill" size={20} color={colors.success} /><Text style={[styles.boundaryText, { color: colors.muted }]}>这里展示的是家长经验与个人视角，不是对孩子或家庭的诊断，也不证明教育效果。</Text></View>{loadingMore ? <View style={styles.moreLoading}><Text style={[styles.moreText, { color: colors.muted }]}>正在加载更多经验</Text></View> : visibleCount < entries.length ? <Pressable onPress={loadMore} style={({ pressed }) => [styles.moreButton, { borderColor: colors.tint }, pressed && styles.pressed]}><Text style={[styles.moreText, { color: colors.tint }]}>继续浏览更多经验</Text></Pressable> : null}</View>}
      />
      <Pressable onPress={() => router.push("/ui/UI-26" as Href)} style={({ pressed }) => [styles.fab, pressed && styles.pressed]}><IconSymbol name="square.and.pencil" size={23} color="#FFFFFF" /><Text style={styles.fabText}>写小记</Text></Pressable>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  errorNotice: { borderRadius: 12, padding: 9, backgroundColor: "#FFF4F0" }, errorText: { color: "#9D4E38", fontSize: 11, lineHeight: 16, textAlign: "center", fontWeight: "800" },
  content: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 100, gap: 11 }, header: { gap: 13, marginBottom: 2 }, topBar: { minHeight: 40, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topTitle: { color: "#22272D", fontSize: 22, lineHeight: 30, fontWeight: "900" },
  searchBox: { minHeight: 48, borderWidth: 1, borderRadius: 17, paddingHorizontal: 14, flexDirection: "row", alignItems: "center", gap: 8 }, searchInput: { flex: 1, fontSize: 13, lineHeight: 19, paddingVertical: 9 },
  channelRow: { gap: 23, paddingHorizontal: 2 }, channelButton: { minHeight: 36, justifyContent: "center", alignItems: "center" }, channelText: { fontSize: 14, lineHeight: 20, fontWeight: "800" }, channelLine: { width: 27, height: 3, borderRadius: 2, marginTop: 5 },
  hero: { minHeight: 154, borderRadius: 25, backgroundColor: "#E8F2FF", padding: 20, flexDirection: "row", alignItems: "center", overflow: "hidden" }, heroCopy: { flex: 1, gap: 8 }, heroEyebrow: { color: "#5B7091", fontSize: 12, lineHeight: 17, fontWeight: "800" }, heroTitle: { color: "#09295A", fontSize: 21, lineHeight: 29, fontWeight: "900" }, heroAction: { alignSelf: "flex-start", minHeight: 34, borderRadius: 17, backgroundColor: "#2563EB", paddingHorizontal: 13, flexDirection: "row", alignItems: "center", gap: 3 }, heroActionText: { color: "#FFFFFF", fontSize: 11, lineHeight: 15, fontWeight: "900" }, heroIcon: { width: 82, height: 82, borderRadius: 28, backgroundColor: "#FFFFFF80", alignItems: "center", justifyContent: "center" },
  topicPanel: { minHeight: 102, borderWidth: 1, borderRadius: 21, paddingVertical: 13, paddingHorizontal: 8, flexDirection: "row", justifyContent: "space-between" }, topicItem: { width: 61, alignItems: "center", gap: 7 }, topicIcon: { width: 43, height: 43, borderRadius: 14, alignItems: "center", justifyContent: "center" }, topicLabel: { fontSize: 9, lineHeight: 13, textAlign: "center", fontWeight: "800" },
  sectionLine: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }, sectionTitle: { fontSize: 17, lineHeight: 24, fontWeight: "900" }, sectionIntro: { maxWidth: 275, fontSize: 11, lineHeight: 17, marginTop: 2 }, mineLink: { fontSize: 11, lineHeight: 17, fontWeight: "900", paddingTop: 3 },
  postCard: { borderWidth: 1, borderRadius: 21, padding: 14, gap: 10, marginBottom: 9 }, authorRow: { flexDirection: "row", alignItems: "center", gap: 10 }, avatar: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" }, authorCopy: { flex: 1, gap: 2 }, authorNameRow: { flexDirection: "row", alignItems: "center", gap: 6 }, authorName: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, reviewedTag: { borderRadius: 7, paddingHorizontal: 6, paddingVertical: 2, fontSize: 8, lineHeight: 11, fontWeight: "900" }, authorMeta: { fontSize: 9, lineHeight: 13 }, postTitle: { fontSize: 17, lineHeight: 24, fontWeight: "900" }, postSummary: { fontSize: 12, lineHeight: 19 }, mediaStrip: { minHeight: 82, borderRadius: 17, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 10 }, mediaText: { flex: 1, fontSize: 12, lineHeight: 18, fontWeight: "800" }, actionRow: { borderTopWidth: 1, paddingTop: 10, flexDirection: "row", justifyContent: "space-between" }, readAction: { flexDirection: "row", alignItems: "center", gap: 5 }, bookmarkAction: { minHeight: 28, flexDirection: "row", alignItems: "center", gap: 5 }, actionText: { fontSize: 10, lineHeight: 14, fontWeight: "800" },
  empty: { minHeight: 160, alignItems: "center", justifyContent: "center", gap: 5 }, emptyTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" }, emptyText: { fontSize: 12, lineHeight: 18 }, footer: { gap: 10 }, boundary: { minHeight: 70, borderTopWidth: 1, paddingTop: 15, flexDirection: "row", alignItems: "flex-start", gap: 8 }, boundaryText: { flex: 1, fontSize: 11, lineHeight: 17 }, moreLoading: { minHeight: 40, alignItems: "center", justifyContent: "center" }, moreButton: { minHeight: 42, borderWidth: 1, borderRadius: 17, alignItems: "center", justifyContent: "center" }, moreText: { fontSize: 11, lineHeight: 16, fontWeight: "900" },
  fab: { position: "absolute", right: 18, bottom: 23, minHeight: 48, borderRadius: 24, backgroundColor: "#F28C45", paddingHorizontal: 18, flexDirection: "row", alignItems: "center", gap: 7 }, fabText: { color: "#FFFFFF", fontSize: 13, lineHeight: 18, fontWeight: "900" }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
