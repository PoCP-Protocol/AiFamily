import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiPlatformSurfacesProjection } from "@/lib/family/family-api-projections";
import { selectGrowthActivityCatalog } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { growthActivitiesForDisplay, type GrowthActivityPresentation } from "@/lib/family/service-support";

const THEMES = ["全部", "亲子沟通", "学习习惯", "情绪陪伴", "家庭关系"] as const;

export default function SalonListScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const [projection, setProjection] = useState<FamilyApiPlatformSurfacesProjection | null>(null);
  const [query, setQuery] = useState("");
  const [theme, setTheme] = useState<(typeof THEMES)[number]>("全部");

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getDevPlatformSurfaces<FamilyApiPlatformSurfacesProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => { if (active) setProjection(result); })
      .catch((error) => { console.error("UI-22 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const catalog = selectGrowthActivityCatalog(projection);
  const activities = useMemo(() => {
    const value = query.trim().toLowerCase();
    return growthActivitiesForDisplay(catalog?.activities).filter((item) => {
      const matchesTheme = theme === "全部" || item.theme === theme;
      const matchesQuery = !value || `${item.title}${item.summary}${item.theme}`.toLowerCase().includes(value);
      return matchesTheme && matchesQuery;
    });
  }, [catalog?.activities, query, theme]);

  const openActivity = (item: GrowthActivityPresentation) => router.push(`/ui/UI-23?activityRef=${encodeURIComponent(item.activityRef)}` as Href);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={activities}
        keyExtractor={(item) => item.activityRef}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>线下沙龙</Text><Text style={styles.topMore}>•••</Text></View>
            <View style={styles.hero}>
              <View style={styles.heroCopy}><Text style={styles.heroTitle}>走进家庭成长沙龙，与同阶段家长交流</Text><Text style={styles.heroText}>学习 · 交流 · 成长</Text></View>
              <View style={styles.heroIllustration}><IconSymbol name="person.2.fill" size={45} color="#2563EB" /></View>
            </View>
            <View style={styles.searchRow}>
              <View style={[styles.cityChip, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.cityText, { color: colors.text }]}>北京市⌄</Text></View>
              <View style={[styles.searchBox, { backgroundColor: colors.surface, borderColor: colors.border }]}><IconSymbol name="magnifyingglass" size={19} color={colors.muted} /><TextInput value={query} onChangeText={setQuery} placeholder="搜索沙龙主题 / 讲师 / 场地" placeholderTextColor={colors.muted} style={[styles.searchInput, { color: colors.text }]} returnKeyType="search" /></View>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.themeRow}>{THEMES.map((item) => <Pressable key={item} onPress={() => setTheme(item)} style={({ pressed }) => [styles.themeChip, { backgroundColor: theme === item ? colors.tint : colors.surface, borderColor: theme === item ? colors.tint : colors.border }, pressed && styles.pressed]}><Text style={[styles.themeText, { color: theme === item ? "#FFFFFF" : colors.muted }]}>{item}</Text></Pressable>)}</ScrollView>
          </View>
        }
        renderItem={({ item, index }) => (
          <Pressable onPress={() => openActivity(item)} style={({ pressed }) => [styles.activityCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
            <View style={[styles.activityVisual, { backgroundColor: `${item.accent}18` }]}><IconSymbol name={index % 2 === 0 ? "person.2.fill" : "book.fill"} size={38} color={item.accent} /></View>
            <View style={styles.activityCopy}>
              <View style={styles.activityTopline}><Text style={[styles.activityTag, { color: item.accent, backgroundColor: `${item.accent}15` }]}>{item.theme}</Text><Text style={[styles.sourceText, { color: colors.muted }]}>{item.source === "FAMILY_API" ? "家庭活动目录" : "活动资料"}</Text></View>
              <Text style={[styles.activityTitle, { color: colors.text }]}>{item.title}</Text>
              <View style={styles.metaLine}><IconSymbol name="clock.fill" size={15} color={colors.tint} /><Text style={[styles.metaText, { color: colors.muted }]}>{item.scheduleLabel}</Text></View>
              <View style={styles.metaLine}><IconSymbol name="mappin.circle.fill" size={15} color={colors.tint} /><Text style={[styles.metaText, { color: colors.muted }]}>{item.locationLabel}</Text></View>
              <View style={styles.cardBottom}><Text style={[styles.ageHint, { color: colors.success }]}>{item.ageHint.replace("适龄参考：", "")}</Text><View style={[styles.detailButton, { backgroundColor: colors.tint }]}><Text style={styles.detailButtonText}>查看详情</Text></View></View>
            </View>
          </Pressable>
        )}
        ListEmptyComponent={<View style={styles.empty}><Text style={[styles.emptyTitle, { color: colors.text }]}>暂时没有匹配的活动</Text><Text style={[styles.emptyText, { color: colors.muted }]}>换一个主题或关键词再看看。</Text></View>}
        ListFooterComponent={<View style={[styles.boundary, { borderColor: colors.border }]}><IconSymbol name="lock.fill" size={19} color={colors.success} /><Text style={[styles.boundaryText, { color: colors.muted }]}>查看活动目录不会报名或占用名额；活动时间、方式与地点以之后的家庭确认为准。</Text></View>}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 36, gap: 11 }, header: { gap: 13, marginBottom: 2 }, topBar: { minHeight: 42, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, topMore: { color: "#22272D", fontSize: 18, lineHeight: 20, fontWeight: "900" },
  hero: { minHeight: 158, borderRadius: 25, backgroundColor: "#E8F2FF", padding: 19, flexDirection: "row", alignItems: "center", overflow: "hidden" }, heroCopy: { flex: 1, gap: 8 }, heroTitle: { color: "#09295A", fontSize: 23, lineHeight: 31, fontWeight: "900" }, heroText: { color: "#5B7091", fontSize: 13, lineHeight: 18, fontWeight: "800" }, heroIllustration: { width: 86, height: 86, borderRadius: 28, backgroundColor: "#FFFFFF80", alignItems: "center", justifyContent: "center" },
  searchRow: { flexDirection: "row", gap: 8 }, cityChip: { width: 104, minHeight: 47, borderWidth: 1, borderRadius: 15, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4 }, cityText: { fontSize: 11, lineHeight: 16, fontWeight: "800" }, searchBox: { flex: 1, minHeight: 47, borderWidth: 1, borderRadius: 15, paddingHorizontal: 11, flexDirection: "row", alignItems: "center", gap: 7 }, searchInput: { flex: 1, fontSize: 12, lineHeight: 18, paddingVertical: 9 },
  themeRow: { gap: 8 }, themeChip: { minHeight: 36, borderWidth: 1, borderRadius: 18, alignItems: "center", justifyContent: "center", paddingHorizontal: 14 }, themeText: { fontSize: 11, lineHeight: 16, fontWeight: "800" },
  activityCard: { minHeight: 188, borderWidth: 1, borderRadius: 21, padding: 12, flexDirection: "row", gap: 12, marginBottom: 9 }, activityVisual: { width: 112, borderRadius: 18, alignItems: "center", justifyContent: "center" }, activityCopy: { flex: 1, gap: 6 }, activityTopline: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 5 }, activityTag: { borderRadius: 8, paddingHorizontal: 6, paddingVertical: 3, fontSize: 9, lineHeight: 13, fontWeight: "900" }, sourceText: { fontSize: 8, lineHeight: 12 }, activityTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" }, metaLine: { flexDirection: "row", alignItems: "center", gap: 4 }, metaText: { flex: 1, fontSize: 10, lineHeight: 15 }, cardBottom: { marginTop: "auto", flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 6 }, ageHint: { flex: 1, fontSize: 9, lineHeight: 13, fontWeight: "800" }, detailButton: { minHeight: 32, borderRadius: 16, paddingHorizontal: 10, alignItems: "center", justifyContent: "center" }, detailButtonText: { color: "#FFFFFF", fontSize: 10, lineHeight: 14, fontWeight: "900" },
  empty: { minHeight: 150, alignItems: "center", justifyContent: "center", gap: 5 }, emptyTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" }, emptyText: { fontSize: 12, lineHeight: 18 }, boundary: { minHeight: 68, borderTopWidth: 1, paddingTop: 14, flexDirection: "row", alignItems: "flex-start", gap: 8 }, boundaryText: { flex: 1, fontSize: 11, lineHeight: 17 }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
