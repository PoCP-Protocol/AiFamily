import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiServiceSupplyProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { serviceOfferingsForDisplay, SUPPORT_THEMES, type SupportOfferingPresentation, type SupportThemeId } from "@/lib/family/service-support";

export default function TeacherZoneScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const [projection, setProjection] = useState<FamilyApiServiceSupplyProjection | null>(null);
  const [query, setQuery] = useState("");
  const [theme, setTheme] = useState<SupportThemeId>("ALL");

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getServiceOfferings<FamilyApiServiceSupplyProjection>(session.token, session.selectedFamily.family_id, {})
      .then((result) => { if (active) setProjection(result); })
      .catch((error) => { console.error("UI-19 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const offerings = useMemo(() => {
    const value = query.trim().toLowerCase();
    return serviceOfferingsForDisplay(projection?.offerings).filter((item) => {
      const matchesTheme = theme === "ALL" || item.theme === theme;
      const matchesQuery = !value || `${item.providerName}${item.title}${item.serviceType}${item.ageBand}`.toLowerCase().includes(value);
      return matchesTheme && matchesQuery;
    });
  }, [projection?.offerings, query, theme]);

  const openOffering = (item: SupportOfferingPresentation) => {
    router.push(`/ui/UI-20?offeringRef=${encodeURIComponent(item.offeringRef)}` as Href);
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={offerings}
        keyExtractor={(item) => item.offeringRef}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>名师专区</Text><Text style={styles.topHeart}>♡</Text></View>
            <View style={[styles.searchBox, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <IconSymbol name="magnifyingglass" size={20} color={colors.muted} />
              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder="搜名师 / 领域 / 问题关键词"
                placeholderTextColor={colors.muted}
                style={[styles.searchInput, { color: colors.text }]}
                returnKeyType="search"
              />
            </View>

            <View style={styles.hero}>
              <View style={styles.heroCopy}>
                  <Text style={styles.heroTitle}>名师在线，帮您解决家庭教育难题</Text>
                <Text style={styles.heroText}>专业 · 温暖 · 有方法</Text>
                <Pressable onPress={() => router.push("/ui/UI-21" as Href)} style={({ pressed }) => [styles.heroAction, pressed && styles.pressed]}>
                  <Text style={styles.heroActionText}>立即咨询</Text>
                </Pressable>
              </View>
              <View style={styles.expertCluster}>
                <View style={[styles.expertBubble, styles.expertBubbleBack]}><Text style={styles.expertInitial}>王</Text></View>
                <View style={[styles.expertBubble, styles.expertBubbleFront]}><Text style={styles.expertInitial}>李</Text></View>
              </View>
            </View>


            {projection?.live_session ? (
              <Pressable onPress={() => router.push("/ui/UI-20" as Href)} style={({ pressed }) => [styles.liveCard, { backgroundColor: "#FFF6F1", borderColor: "#F5C9B1" }, pressed && styles.pressed]}>
                <View style={styles.liveIcon}><IconSymbol name="video.fill" size={23} color="#F28C45" /></View>
                <View style={styles.liveCopy}>
                  <Text style={styles.liveLabel}>{projection.live_session.status === "LIVE" ? "正在进行" : projection.live_session.status === "ENDED" ? "本场已结束" : "近期直播"}</Text>
                  <Text style={[styles.liveTitle, { color: colors.text }]}>{projection.live_session.title}</Text>
                  <Text style={[styles.liveText, { color: colors.muted }]}>{projection.live_session.host_display_name} · {projection.live_session.topic}</Text>
                </View>
                <IconSymbol name="chevron.right" size={20} color="#F28C45" />
              </Pressable>
            ) : null}

            <View style={styles.sectionHeading}>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>热门领域</Text>
              <Text style={[styles.sectionMeta, { color: colors.muted }]}>全部 ›</Text>
            </View>
            <View style={styles.themeGrid}>
              {SUPPORT_THEMES.filter((item) => item.id !== "ALL").map((item) => (
                <Pressable key={item.id} onPress={() => setTheme(theme === item.id ? "ALL" : item.id)} style={({ pressed }) => [styles.themeTile, { backgroundColor: colors.surface, borderColor: theme === item.id ? item.color : colors.border }, pressed && styles.pressed]}>
                  <View style={[styles.themeIcon, { backgroundColor: `${item.color}18` }]}>
                    <IconSymbol name={item.id === "STUDY" ? "book.fill" : item.id === "FAMILY" ? "person.2.fill" : item.id === "FOCUS" ? "clock.fill" : "message.fill"} size={21} color={item.color} />
                  </View>
                  <Text style={[styles.themeLabel, { color: colors.text }]}>{item.label}</Text>
                </Pressable>
              ))}
            </View>
            <View style={styles.sectionHeading}>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>推荐名师</Text>
              <Text style={[styles.sectionMeta, { color: colors.muted }]}>更多 ›</Text>
            </View>
          </View>
        }
        ListEmptyComponent={<View style={styles.empty}><Text style={[styles.emptyTitle, { color: colors.text }]}>暂时没有匹配的支持主题</Text><Text style={[styles.emptyText, { color: colors.muted }]}>换一个关键词或领域再看看。</Text></View>}
        renderItem={({ item }) => (
          <View style={[styles.teacherCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View style={[styles.avatar, { backgroundColor: `${item.accent}20` }]}><Text style={[styles.avatarText, { color: item.accent }]}>{item.providerName.slice(0, 1)}</Text></View>
            <View style={styles.teacherCopy}>
              <View style={styles.teacherTopline}>
                <View style={styles.teacherNameRow}><Text style={[styles.teacherName, { color: colors.text }]}>{item.providerName}</Text><View style={[styles.admittedBadge, { backgroundColor: "#FFF2D8" }]}><Text style={styles.admittedText}>服务资料</Text></View></View>
                <Text style={[styles.availableText, { color: item.availability === "AVAILABLE" ? colors.success : colors.muted }]}>{item.availability === "AVAILABLE" ? "可了解" : "暂无时段"}</Text>
              </View>
              <Text style={[styles.teacherRole, { color: colors.muted }]}>{item.title} · {item.ageBand}</Text>
              <View style={styles.tags}>{item.expertise.slice(0, 3).map((tag) => <Text key={tag} style={[styles.tag, { color: item.accent, borderColor: `${item.accent}50` }]}>{tag}</Text>)}</View>
              <View style={styles.teacherActions}>
                <Pressable onPress={() => openOffering(item)} style={({ pressed }) => [styles.secondaryAction, { borderColor: colors.border }, pressed && styles.pressed]}><Text style={[styles.secondaryText, { color: colors.text }]}>查看详情</Text></Pressable>
                <Pressable onPress={() => router.push(`/ui/UI-21?offeringRef=${encodeURIComponent(item.offeringRef)}` as Href)} style={({ pressed }) => [styles.primaryAction, { backgroundColor: colors.tint }, pressed && styles.pressed]}><Text style={styles.primaryText}>立即咨询</Text></Pressable>
              </View>
            </View>
          </View>
        )}
        ListFooterComponent={<View style={[styles.boundary, { borderColor: colors.border }]}><IconSymbol name="lock.fill" size={19} color={colors.success} /><Text style={[styles.boundaryText, { color: colors.muted }]}>专家资料用于帮助家庭了解支持方向，不代表系统替你选择；咨询前仍由家庭决定。</Text></View>}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 36, gap: 12 },
  header: { gap: 14, marginBottom: 4 },
  topBar: { minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" },
  topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  topHeart: { color: "#22272D", fontSize: 25, lineHeight: 28 },
  searchBox: { minHeight: 48, borderRadius: 16, borderWidth: 1, paddingHorizontal: 13, flexDirection: "row", alignItems: "center", gap: 8 },
  searchInput: { flex: 1, fontSize: 14, lineHeight: 20, paddingVertical: 10 },
  hero: { minHeight: 176, borderRadius: 25, backgroundColor: "#E8F2FF", padding: 20, flexDirection: "row", alignItems: "center", overflow: "hidden" },
  heroCopy: { flex: 1, gap: 8 },
  heroTitle: { color: "#09295A", fontSize: 23, lineHeight: 31, fontWeight: "900" },
  heroText: { color: "#5B7091", fontSize: 13, lineHeight: 18, fontWeight: "700" },
  heroAction: { alignSelf: "flex-start", minHeight: 36, borderRadius: 18, backgroundColor: "#2563EB", justifyContent: "center", paddingHorizontal: 14, marginTop: 2 },
  heroActionText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  expertCluster: { width: 108, height: 120, justifyContent: "center", alignItems: "center" },
  expertBubble: { position: "absolute", width: 72, height: 72, borderRadius: 36, borderWidth: 3, borderColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  expertBubbleBack: { backgroundColor: "#BFD1F8", right: 2, top: 12 },
  expertBubbleFront: { backgroundColor: "#F6D5C4", left: 3, bottom: 10 },
  expertInitial: { color: "#09295A", fontSize: 25, fontWeight: "900" },
  liveCard: { minHeight: 88, borderWidth: 1, borderRadius: 19, padding: 13, flexDirection: "row", alignItems: "center", gap: 10 },
  liveIcon: { width: 44, height: 44, borderRadius: 15, backgroundColor: "#F28C4518", alignItems: "center", justifyContent: "center" },
  liveCopy: { flex: 1, gap: 2 }, liveLabel: { color: "#F28C45", fontSize: 11, lineHeight: 16, fontWeight: "900" }, liveTitle: { fontSize: 14, lineHeight: 20, fontWeight: "900" }, liveText: { fontSize: 11, lineHeight: 16 },
  sectionHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 2 },
  sectionTitle: { fontSize: 20, lineHeight: 27, fontWeight: "900" }, sectionMeta: { fontSize: 12, lineHeight: 17 },
  themeGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  themeTile: { width: "31%", minHeight: 92, borderWidth: 1, borderRadius: 18, alignItems: "center", justifyContent: "center", gap: 6 },
  themeIcon: { width: 39, height: 39, borderRadius: 14, alignItems: "center", justifyContent: "center" }, themeLabel: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  teacherCard: { minHeight: 174, borderWidth: 1, borderRadius: 21, padding: 13, flexDirection: "row", gap: 11, marginBottom: 10 },
  avatar: { width: 70, height: 78, borderRadius: 20, alignItems: "center", justifyContent: "center" }, avatarText: { fontSize: 29, fontWeight: "900" },
  teacherCopy: { flex: 1, gap: 6 }, teacherTopline: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 6 }, teacherNameRow: { flexDirection: "row", alignItems: "center", gap: 5, flex: 1 },
  teacherName: { fontSize: 17, lineHeight: 23, fontWeight: "900" }, admittedBadge: { borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2 }, admittedText: { color: "#B87500", fontSize: 9, lineHeight: 13, fontWeight: "800" },
  availableText: { fontSize: 11, lineHeight: 16, fontWeight: "800" }, teacherRole: { fontSize: 11, lineHeight: 16 }, tags: { flexDirection: "row", flexWrap: "wrap", gap: 5 },
  tag: { borderWidth: 1, borderRadius: 9, paddingHorizontal: 6, paddingVertical: 3, fontSize: 9, lineHeight: 13, fontWeight: "700" }, teacherActions: { flexDirection: "row", gap: 7, marginTop: 2 },
  secondaryAction: { flex: 1, minHeight: 36, borderWidth: 1, borderRadius: 18, alignItems: "center", justifyContent: "center" }, secondaryText: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  primaryAction: { flex: 1, minHeight: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" }, primaryText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  empty: { minHeight: 150, alignItems: "center", justifyContent: "center", gap: 5 }, emptyTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" }, emptyText: { fontSize: 12, lineHeight: 18 },
  boundary: { minHeight: 70, borderTopWidth: 1, marginTop: 4, paddingTop: 14, flexDirection: "row", alignItems: "flex-start", gap: 9 }, boundaryText: { flex: 1, fontSize: 11, lineHeight: 17 },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
