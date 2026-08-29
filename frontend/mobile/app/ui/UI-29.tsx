import type { Href } from "expo-router";
import { router, Stack } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiCoreGrowthProjection, FamilyApiPlatformSurfacesProjection } from "@/lib/family/family-api-projections";
import { selectPersonalGrowthJourney } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

const BADGES = [
  { label: "愿意倾听", detail: "为一次对话留出时间", icon: "heart.fill" as const, color: "#16866D" },
  { label: "坚持行动", detail: "把小事放进日常", icon: "star.fill" as const, color: "#F28C45" },
  { label: "共同回看", detail: "记录自己的过程", icon: "person.2.fill" as const, color: "#7C5CE5" },
] as const;

export default function GrowthOutcomesScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const [core, setCore] = useState<FamilyApiCoreGrowthProjection | null>(null);
  const [platform, setPlatform] = useState<FamilyApiPlatformSurfacesProjection | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    setLoading(true);
    Promise.all([
      familyApi.getDevCoreGrowth<FamilyApiCoreGrowthProjection>(session.token, session.selectedFamily.family_id),
      familyApi.getDevPlatformSurfaces<FamilyApiPlatformSurfacesProjection>(session.token, session.selectedFamily.family_id),
    ]).then(([coreResult, platformResult]) => {
      if (!active) return;
      setCore(coreResult);
      setPlatform(platformResult);
    }).catch((error) => { console.error("UI-29 remote projection failed", error); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const journey = selectPersonalGrowthJourney(platform);
  const completed = state.campCompletedDays.length + (state.lastReceipt ? 1 : 0);
  const evidence = useMemo(() => [
    ...(journey?.entries ?? []).map((item) => ({ id: item.event_id, title: item.label, detail: item.detail, kind: "过程记录" })),
    ...(state.lastReceipt ? [{ id: state.lastReceipt.actionId, title: "完成了一次家庭行动", detail: "这是一次行动与反思，不用急着证明效果。", kind: "家庭确认" }] : []),
  ].slice(0, 4), [journey?.entries, state.lastReceipt]);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={evidence}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={27} color="#22272D" /></Pressable><Text style={styles.topTitle}>成长成果</Text><View style={styles.topSpacer} /></View>
            <View style={styles.hero}>
              <Text style={styles.heroEyebrow}>本周成长慢谈</Text>
              <View style={styles.heroBody}>
                <View><Text style={styles.heroMetric}>{completed}</Text><Text style={styles.heroLabel}>已留下的行动片段</Text></View>
                <View style={styles.ring}><Text style={styles.ringValue}>{state.campCompletedDays.length}</Text><Text style={styles.ringLabel}>成长营小结</Text></View>
                <View><Text style={styles.heroMetric}>{evidence.length}</Text><Text style={styles.heroLabel}>可回看的记录</Text></View>
              </View>
              <View style={styles.heroFoot}><Text style={styles.heroFootText}>过程记录不代表效果结论；只帮助我们看见已经走过的路。</Text></View>
            </View>
            {loading ? <ActivityIndicator color={colors.tint} /> : null}
            <View style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <View style={styles.panelTitleRow}><Text style={[styles.panelTitle, { color: colors.text }]}>我们正在练习的事</Text><Text style={styles.panelAction}>家庭过程</Text></View>
              <View style={styles.badgesRow}>{BADGES.map((item) => <View key={item.label} style={styles.badge}><View style={[styles.badgeIcon, { backgroundColor: `${item.color}18` }]}><IconSymbol name={item.icon} size={24} color={item.color} /></View><Text style={[styles.badgeLabel, { color: colors.text }]}>{item.label}</Text><Text style={[styles.badgeDetail, { color: colors.muted }]}>{item.detail}</Text></View>)}</View>
            </View>
            <View style={styles.sectionTitleRow}><Text style={[styles.sectionTitle, { color: colors.text }]}>过程里的片段</Text><Text style={[styles.sectionHint, { color: colors.muted }]}>{core?.model_gateway.status === "NOOP_NOT_INVOKED" ? "不由模型下结论" : "家庭回看"}</Text></View>
          </View>
        }
        renderItem={({ item }) => <View style={[styles.evidenceCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.evidenceDot} /><View style={styles.evidenceCopy}><Text style={[styles.evidenceKind, { color: colors.tint }]}>{item.kind}</Text><Text style={[styles.evidenceTitle, { color: colors.text }]}>{item.title}</Text><Text style={[styles.evidenceDetail, { color: colors.muted }]}>{item.detail}</Text></View></View>}
        ListEmptyComponent={<View style={[styles.empty, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.emptyTitle, { color: colors.text }]}>从一次小行动开始</Text><Text style={[styles.emptyCopy, { color: colors.muted }]}>完成今天的行动或成长营小结后，这里会留下一段只属于家庭自己的过程记录。</Text></View>}
        ListFooterComponent={<Pressable onPress={() => router.push("/ui/UI-33" as Href)} style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}><Text style={styles.primaryText}>查看家庭档案</Text><IconSymbol name="chevron.right" size={19} color="#FFFFFF" /></Pressable>}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingBottom: 38, gap: 12 }, header: { gap: 12 }, topBar: { minHeight: 40, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, topSpacer: { width: 38 }, hero: { borderRadius: 24, backgroundColor: "#E8F2FF", padding: 18, gap: 14 }, heroEyebrow: { color: "#5B7091", fontSize: 14, lineHeight: 20, fontWeight: "800" }, heroBody: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, heroMetric: { color: "#09295A", fontSize: 29, lineHeight: 35, textAlign: "center", fontWeight: "900" }, heroLabel: { width: 86, color: "#536A8B", fontSize: 10, lineHeight: 15, textAlign: "center" }, ring: { width: 88, height: 88, borderRadius: 44, borderWidth: 7, borderColor: "#B9DCFF", alignItems: "center", justifyContent: "center" }, ringValue: { color: "#09295A", fontSize: 22, lineHeight: 27, fontWeight: "900" }, ringLabel: { color: "#536A8B", fontSize: 9, lineHeight: 13 }, heroFoot: { borderRadius: 12, backgroundColor: "#FFFFFF80", padding: 10 }, heroFootText: { color: "#5B7091", fontSize: 11, lineHeight: 16 }, panel: { borderWidth: 1, borderRadius: 20, padding: 15, gap: 14 }, panelTitleRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, panelTitle: { fontSize: 17, lineHeight: 23, fontWeight: "900" }, panelAction: { color: "#2563EB", fontSize: 12, fontWeight: "700" }, badgesRow: { flexDirection: "row", gap: 8 }, badge: { flex: 1, alignItems: "center", gap: 5 }, badgeIcon: { width: 46, height: 46, borderRadius: 18, alignItems: "center", justifyContent: "center" }, badgeLabel: { fontSize: 12, lineHeight: 17, fontWeight: "800", textAlign: "center" }, badgeDetail: { fontSize: 9, lineHeight: 13, textAlign: "center" }, sectionTitleRow: { flexDirection: "row", justifyContent: "space-between", paddingTop: 4 }, sectionTitle: { fontSize: 17, lineHeight: 23, fontWeight: "900" }, sectionHint: { fontSize: 11, lineHeight: 16 }, evidenceCard: { minHeight: 84, borderWidth: 1, borderRadius: 18, padding: 13, flexDirection: "row", gap: 10, marginTop: 10 }, evidenceDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: "#2563EB", marginTop: 5 }, evidenceCopy: { flex: 1, gap: 3 }, evidenceKind: { fontSize: 10, lineHeight: 14, fontWeight: "800" }, evidenceTitle: { fontSize: 14, lineHeight: 20, fontWeight: "900" }, evidenceDetail: { fontSize: 12, lineHeight: 18 }, empty: { borderWidth: 1, borderRadius: 18, padding: 16, gap: 6, marginTop: 10 }, emptyTitle: { fontSize: 15, lineHeight: 21, fontWeight: "900" }, emptyCopy: { fontSize: 12, lineHeight: 18 }, primaryButton: { marginTop: 18, minHeight: 52, borderRadius: 16, backgroundColor: "#2563EB", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5 }, primaryText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" }, pressed: { opacity: 0.84, transform: [{ scale: 0.985 }] },
});
