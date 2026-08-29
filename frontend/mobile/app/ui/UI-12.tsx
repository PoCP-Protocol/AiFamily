import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { buildFamilyRhythmEvents, buildPrivateGrowthStory } from "@/lib/family/child-growth";
import { familyApi } from "@/lib/family/family-api-client";
import { selectPrivateGrowthStory, type FamilyApiPlatformSurfacesProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { haptic } from "@/lib/haptics";

export default function PrivateGrowthStoryScreen() {
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const [remoteProjection, setRemoteProjection] = useState<FamilyApiPlatformSurfacesProjection | null>(null);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getDevPlatformSurfaces<FamilyApiPlatformSurfacesProjection>(session.token, session.selectedFamily.family_id).then((result) => { if (active) setRemoteProjection(result); }).catch((error) => { console.error("UI-12 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const localEvents = useMemo(() => buildFamilyRhythmEvents({ selectedGrowthFocus: state.selectedGrowthFocus, lastReceipt: state.lastReceipt, campCompletedDays: state.campCompletedDays, uiActionReceipts: state.uiActionReceipts, childChoiceDraft: state.childChoiceDraft }).slice(-4), [state.campCompletedDays, state.childChoiceDraft, state.lastReceipt, state.selectedGrowthFocus, state.uiActionReceipts]);
  const remoteStory = selectPrivateGrowthStory(remoteProjection);
  const moments = remoteStory?.moments.length ? remoteStory.moments.slice(0, 2) : localEvents.slice(0, 2).map((event) => event.detail);
  const preview = useMemo(() => remoteStory ? { id: "private-growth-story-current", title: remoteStory.title, summary: remoteStory.summary, sourceEventIds: moments.map((_, index) => `remote-${index}`), familyNote: state.privateGrowthStory?.familyNote ?? "", visibility: "FAMILY_PRIVATE" as const, state: "PRIVATE_DRAFT" as const, perspectiveKind: "family_narrative_not_fact_or_outcome" as const, externalEffect: false as const, updatedAt: new Date().toISOString() } : buildPrivateGrowthStory(localEvents, state.privateGrowthStory?.familyNote ?? ""), [localEvents, moments, remoteStory, state.privateGrowthStory?.familyNote]);
  const leftMoment = moments[0] ?? "我们先从一次愿意慢下来听的家庭行动开始。";
  const rightMoment = moments[1] ?? "我们想继续保留这次尝试，并在下次对话时再练习。";
  const processCount = Math.max(1, preview.sourceEventIds.length);

  const saveDraft = () => { state.savePrivateGrowthStory(preview); haptic.success(); };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} refreshControl={<FamilyRefreshControl />}>
        <View style={styles.topBar}><Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}><IconSymbol name="chevron.left" size={27} color="#22272D" /></Pressable><Text style={styles.topTitle}>家庭成长故事卡</Text><IconSymbol name="lock.fill" size={21} color="#347FDF" /></View>
        <View style={styles.poster}>
          <View style={styles.posterHeader}><Text style={styles.star}>★</Text><Text style={styles.posterHeaderText}>我们一起记录家庭的尝试</Text><Text style={styles.heart}>♥</Text></View>
          <View style={styles.storyBody}>
            <View style={styles.profile}><View style={styles.profileAvatar}><IconSymbol name="person.crop.circle.fill" size={40} color="#3E84D7" /></View><View><Text style={styles.profileTitle}>家庭私有记录</Text><Text style={styles.profileMeta}>来源：家庭过程与家长视角</Text></View></View>
            <View style={styles.divider} />
            <Text style={styles.storyTitle}>{preview.title || "我们一起走过的片段"}</Text>
            <View style={styles.viewpoints}><View style={styles.viewpoint}><Text style={styles.viewpointLabel}>当时的感受</Text><Text style={styles.viewpointText} numberOfLines={3}>{leftMoment}</Text></View><Text style={styles.arrow}>→</Text><View style={styles.viewpoint}><Text style={[styles.viewpointLabel, styles.nowLabel]}>现在想继续</Text><Text style={styles.viewpointText} numberOfLines={3}>{rightMoment}</Text></View></View>
            <View style={styles.processSummary}><View style={styles.processMetric}><Text style={styles.metricLabel}>过程片段</Text><Text style={styles.metricValue}>{processCount}<Text style={styles.metricUnit}> 个</Text></Text></View><View style={styles.metricDivider} /><View style={styles.processMetric}><Text style={styles.metricLabel}>家庭状态</Text><Text style={styles.safeValue}>待家庭回看</Text></View></View>
            <View style={styles.marks}><Mark icon="★" title="愿意倾听" subtitle="保留一次尝试" /><Mark icon="✦" title="一起练习" subtitle="继续慢慢来" /></View>
          </View>
          <View style={styles.privatePanel}><View style={styles.privateIcon}><IconSymbol name="lock.fill" size={44} color="#2D78D8" /></View><View style={styles.privateCopy}><Text style={styles.privateTitle}>仅保存在这个家庭</Text><Text style={styles.privateText}>家庭故事是私有草稿，可继续编辑。</Text><Pressable disabled={localEvents.length === 0 && !remoteStory} onPress={saveDraft} style={({ pressed }) => [styles.saveButton, (localEvents.length === 0 && !remoteStory) && styles.saveDisabled, pressed && styles.pressed]}><Text style={styles.saveText}>保存家庭故事</Text></Pressable></View></View>
        </View>
        {state.privateGrowthStory ? <View style={styles.savedReceipt}><IconSymbol name="checkmark.circle.fill" size={20} color="#16866D" /><Text style={styles.savedText}>家庭私有故事草稿已保存，未公开发布。</Text></View> : null}
        <View style={styles.bottomActions}><ActionPill icon="lock.fill" label="仅家庭可见" /><ActionPill icon="square.and.pencil" label="可继续编辑" /><Pressable onPress={() => router.push("/ui/UI-11" as Href)} style={({ pressed }) => [styles.actionPill, pressed && styles.pressed]}><IconSymbol name="chevron.left" size={19} color="#347FDF" /><Text style={styles.actionLabel}>回到节奏</Text></Pressable></View>
        <Text style={styles.boundary}>这张卡记录家庭过程与视角，不是儿童变化、成长值或效果证明。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function Mark({ icon, title, subtitle }: { icon: string; title: string; subtitle: string }) { return <View style={styles.mark}><Text style={styles.markIcon}>{icon}</Text><Text style={styles.markTitle}>{title}</Text><Text style={styles.markSubtitle}>{subtitle}</Text></View>; }
function ActionPill({ icon, label }: { icon: "lock.fill" | "square.and.pencil"; label: string }) { return <View style={styles.actionPill}><IconSymbol name={icon} size={21} color="#347FDF" /><Text style={styles.actionLabel}>{label}</Text></View>; }

const styles = StyleSheet.create({
  content: { paddingHorizontal: 17, paddingBottom: 27, backgroundColor: "#FFFFFF" }, topBar: { minHeight: 63, flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, backButton: { width: 42, height: 42, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  poster: { borderRadius: 17, padding: 6, backgroundColor: "#267EF0", overflow: "hidden" }, posterHeader: { minHeight: 45, flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 7 }, star: { color: "#FFE15D", fontSize: 23 }, posterHeaderText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" }, heart: { color: "#B7E1FF", fontSize: 19 }, storyBody: { paddingHorizontal: 14, paddingTop: 13, paddingBottom: 12, borderRadius: 13, backgroundColor: "#FFFFFF" }, profile: { flexDirection: "row", alignItems: "center", gap: 9 }, profileAvatar: { width: 43, height: 43, borderRadius: 22, backgroundColor: "#E9F3FF", alignItems: "center", justifyContent: "center" }, profileTitle: { color: "#3E4853", fontSize: 15, lineHeight: 20, fontWeight: "900" }, profileMeta: { color: "#7C8997", fontSize: 10, lineHeight: 15, fontWeight: "700", marginTop: 1 }, divider: { height: 1, backgroundColor: "#E6EBF0", marginVertical: 10 }, storyTitle: { color: "#183E7A", fontSize: 21, lineHeight: 29, fontWeight: "900" }, viewpoints: { marginTop: 12, flexDirection: "row", alignItems: "center", gap: 6 }, viewpoint: { flex: 1, minHeight: 97, borderRadius: 12, padding: 10, backgroundColor: "#EFF6FF" }, viewpointLabel: { color: "#5277A4", fontSize: 12, lineHeight: 16, fontWeight: "900" }, nowLabel: { color: "#2B78D8" }, viewpointText: { color: "#59636E", fontSize: 11, lineHeight: 16, fontWeight: "700", marginTop: 6 }, arrow: { color: "#2B80EB", fontSize: 24, fontWeight: "900" }, processSummary: { minHeight: 76, marginTop: 12, borderWidth: 1, borderColor: "#E6EBF0", borderRadius: 12, flexDirection: "row", alignItems: "center" }, processMetric: { flex: 1, alignItems: "center", gap: 3 }, metricLabel: { color: "#667483", fontSize: 12, lineHeight: 17, fontWeight: "800" }, metricValue: { color: "#2377DF", fontSize: 29, lineHeight: 34, fontWeight: "900" }, metricUnit: { fontSize: 13 }, safeValue: { color: "#2377DF", fontSize: 15, lineHeight: 21, fontWeight: "900" }, metricDivider: { width: 1, height: 43, backgroundColor: "#DFE5EC" }, marks: { minHeight: 100, flexDirection: "row", justifyContent: "space-around", alignItems: "center" }, mark: { alignItems: "center" }, markIcon: { color: "#EAA92B", fontSize: 42, lineHeight: 46, fontWeight: "900" }, markTitle: { color: "#4A5158", fontSize: 13, lineHeight: 18, fontWeight: "900" }, markSubtitle: { color: "#8B949E", fontSize: 10, lineHeight: 14, marginTop: 1 }, privatePanel: { minHeight: 119, marginTop: 6, borderRadius: 13, paddingHorizontal: 17, flexDirection: "row", alignItems: "center", backgroundColor: "#FFFFFF" }, privateIcon: { width: 82, height: 82, borderWidth: 1, borderColor: "#E0E8F2", borderRadius: 12, alignItems: "center", justifyContent: "center" }, privateCopy: { flex: 1, marginLeft: 13 }, privateTitle: { color: "#3D4752", fontSize: 14, lineHeight: 20, fontWeight: "900" }, privateText: { color: "#7A8795", fontSize: 11, lineHeight: 16, marginTop: 3 }, saveButton: { minHeight: 33, marginTop: 7, borderRadius: 17, backgroundColor: "#247AE8", alignItems: "center", justifyContent: "center" }, saveDisabled: { backgroundColor: "#B5C5D9" }, saveText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" }, savedReceipt: { minHeight: 46, marginTop: 10, paddingHorizontal: 12, borderRadius: 12, backgroundColor: "#EDF9F2", flexDirection: "row", alignItems: "center", gap: 7 }, savedText: { color: "#457664", fontSize: 12, lineHeight: 17, fontWeight: "800" }, bottomActions: { marginTop: 13, flexDirection: "row", justifyContent: "space-between" }, actionPill: { width: "31%", minHeight: 64, alignItems: "center", justifyContent: "center", gap: 3 }, actionLabel: { color: "#586674", fontSize: 11, lineHeight: 16, fontWeight: "800", textAlign: "center" }, boundary: { color: "#85919C", fontSize: 10, lineHeight: 15, textAlign: "center", marginTop: 5 }, pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});
