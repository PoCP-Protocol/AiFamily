import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiPlatformSurfacesProjection } from "@/lib/family/family-api-projections";
import { selectGrowthActivityCatalog } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { growthActivitiesForDisplay } from "@/lib/family/service-support";
import { haptic } from "@/lib/haptics";

export default function ActivityDetailScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const { activityRef } = useLocalSearchParams<{ activityRef?: string }>();
  const [projection, setProjection] = useState<FamilyApiPlatformSurfacesProjection | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "submitting" | "saved">("idle");

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getDevPlatformSurfaces<FamilyApiPlatformSurfacesProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => { if (active) setProjection(result); })
      .catch((error) => { console.error("UI-23 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const activities = useMemo(() => growthActivitiesForDisplay(selectGrowthActivityCatalog(projection)?.activities), [projection]);
  const activity = activities.find((item) => item.activityRef === activityRef) ?? activities[0];
  const saved = saveState === "saved" || state.activityInterestDraft?.activityRef === activity.activityRef;

  const saveInterest = async () => {
    setSaveState("submitting");
    const flowId = `activity-interest:${activity.activityRef}`;
    state.setFlowStatus({ flowId, lastAction: "SAVE_ACTIVITY_INTEREST_DRAFT", remoteSyncState: "NOT_STARTED", source: "LOCAL_DRAFT", retryable: false });
    state.saveActivityInterestDraft(activity.activityRef, activity.title);
    if (session.status === "connected" && session.token && session.selectedFamily) {
      state.setFlowStatus({ flowId, lastAction: "SAVE_ACTIVITY_INTEREST_DRAFT", remoteSyncState: "SYNCING", source: "LOCAL_DRAFT", retryable: false });
      await familyApi.recordDevFlowEvent(session.token, session.selectedFamily.family_id, { ui_id: "UI-23", command: "SAVE_ACTIVITY_INTEREST_DRAFT", selection: activity.activityRef }, `family-mobile-ui23:${session.selectedFamily.family_id}:${activity.activityRef}`);
      state.setFlowStatus({ flowId, lastAction: "SAVE_ACTIVITY_INTEREST_DRAFT", remoteSyncState: "SYNCED", source: "REMOTE_RECEIPT", retryable: false });
    }
    setSaveState("saved");
    haptic.success();
  };

  const agenda = activity.agenda.map((label, index) => ({ id: `${activity.activityRef}-agenda-${index}`, label, time: index === 0 ? "开始" : `第 ${index + 1} 段` }));

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={agenda}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>活动详情</Text><Text style={styles.topMore}>↗</Text></View>
            <View style={[styles.hero, { backgroundColor: `${activity.accent}20` }]}><IconSymbol name="person.2.fill" size={68} color={activity.accent} /></View>
            <View style={styles.titleBlock}><Text style={[styles.activityTag, { color: activity.accent, backgroundColor: `${activity.accent}16` }]}>{activity.theme}</Text><Text style={[styles.title, { color: colors.text }]}>{activity.title}</Text><Text style={[styles.subtitle, { color: colors.muted }]}>{activity.summary}</Text></View>
            <View style={[styles.metaPanel, { backgroundColor: colors.surface, borderColor: colors.border }]}><MetaCell icon="clock.fill" label={activity.scheduleLabel} /><MetaCell icon="mappin.circle.fill" label={activity.locationLabel} /><MetaCell icon="person.2.fill" label={activity.ageHint.replace("适龄参考：", "")} /></View>
            <View style={[styles.section, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.sectionTitle, { color: colors.text }]}>活动亮点</Text>{activity.highlights.map((item) => <View key={item} style={styles.highlightLine}><IconSymbol name="checkmark.circle.fill" size={18} color={colors.tint} /><Text style={[styles.highlightText, { color: colors.muted }]}>{item}</Text></View>)}</View>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>活动流程</Text>
          </View>
        }
        renderItem={({ item, index }) => <View style={styles.agendaRow}><View style={styles.agendaRail}><View style={[styles.agendaDot, { backgroundColor: colors.tint }]} />{index < agenda.length - 1 ? <View style={[styles.agendaLine, { backgroundColor: "#CADBFA" }]} /> : null}</View><View style={styles.agendaCopy}><Text style={[styles.agendaTime, { color: colors.tint }]}>{item.time}</Text><Text style={[styles.agendaLabel, { color: colors.text }]}>{item.label}</Text></View></View>}
        ListFooterComponent={
          <View style={styles.footer}>
            <View style={[styles.section, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.sectionTitle, { color: colors.text }]}>适合家庭</Text><Text style={[styles.sectionText, { color: colors.muted }]}>{activity.ageHint}。希望先了解主题、方法和家庭练习方式的家长，可以把活动意向先记下来。</Text><Text style={[styles.boundary, { color: colors.muted }]}>活动介绍不承诺家庭变化；保存意向不表示报名、出席或名额确认。</Text></View>
            {saved ? <View style={[styles.receipt, { backgroundColor: "#16866D12", borderColor: colors.success }]}><IconSymbol name="checkmark.circle.fill" size={24} color={colors.success} /><View style={styles.receiptCopy}><Text style={[styles.receiptTitle, { color: colors.success }]}>活动想法已记下</Text><Text style={[styles.receiptText, { color: colors.muted }]}>当前没有报名、通知或写入系统日历；是否继续参加由家庭之后决定。</Text></View></View> : null}
            <View style={styles.actionRow}><Pressable onPress={() => router.push("/ui/UI-24" as Href)} style={({ pressed }) => [styles.consultAction, { borderColor: colors.tint }, pressed && styles.pressed]}><Text style={[styles.consultText, { color: colors.tint }]}>我的活动</Text></Pressable><Pressable disabled={saveState === "submitting"} onPress={saveInterest} style={({ pressed }) => [styles.primaryAction, pressed && styles.pressed, saveState === "submitting" && styles.disabled]}>{saveState === "submitting" ? <View style={styles.loadingContent}><ActivityIndicator size="small" color="#FFFFFF" /><Text style={styles.primaryText}>正在保存</Text></View> : <Text style={styles.primaryText}>{saved ? "已记下报名意向" : "立即报名"}</Text>}</Pressable></View>
            <Modal transparent visible={saveState === "saved"} animationType="fade" onRequestClose={() => setSaveState("idle")}><View style={styles.modalScrim}><View style={styles.successModal}><IconSymbol name="checkmark.circle.fill" size={44} color={colors.success} /><Text style={styles.successTitle}>活动意向已保存</Text><Text style={styles.successText}>已记在家庭私有空间；当前没有报名、占用名额或发送通知。</Text><Pressable onPress={() => setSaveState("idle")} style={styles.successAction}><Text style={styles.successActionText}>我知道了</Text></Pressable></View></View></Modal>
          </View>
        }
      />
    </ScreenContainer>
  );
}

function MetaCell({ icon, label }: { icon: "clock.fill" | "mappin.circle.fill" | "person.2.fill"; label: string }) { const colors = useColors(); return <View style={styles.metaCell}><IconSymbol name={icon} size={21} color={colors.tint} /><Text style={[styles.metaLabel, { color: colors.muted }]}>{label}</Text></View>; }

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 10, paddingBottom: 34, gap: 8 }, header: { gap: 13 }, topBar: { minHeight: 42, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, topMore: { color: "#22272D", fontSize: 22, lineHeight: 26 }, hero: { height: 222, borderRadius: 25, alignItems: "center", justifyContent: "center" }, titleBlock: { gap: 6 }, activityTag: { alignSelf: "flex-start", borderRadius: 9, paddingHorizontal: 8, paddingVertical: 4, fontSize: 10, lineHeight: 14, fontWeight: "900" }, title: { fontSize: 26, lineHeight: 34, fontWeight: "900" }, subtitle: { fontSize: 13, lineHeight: 20 },
  metaPanel: { minHeight: 104, borderWidth: 1, borderRadius: 19, flexDirection: "row", alignItems: "center" }, metaCell: { flex: 1, alignItems: "center", justifyContent: "center", gap: 6, paddingHorizontal: 5 }, metaLabel: { fontSize: 9, lineHeight: 14, textAlign: "center" }, section: { borderWidth: 1, borderRadius: 19, padding: 14, gap: 8 }, sectionTitle: { fontSize: 18, lineHeight: 24, fontWeight: "900" }, highlightLine: { flexDirection: "row", alignItems: "flex-start", gap: 7 }, highlightText: { flex: 1, fontSize: 12, lineHeight: 18 },
  agendaRow: { minHeight: 58, flexDirection: "row" }, agendaRail: { width: 28, alignItems: "center" }, agendaDot: { width: 10, height: 10, borderRadius: 5, marginTop: 6 }, agendaLine: { width: 2, flex: 1, marginTop: 3 }, agendaCopy: { flex: 1, paddingBottom: 12, gap: 2 }, agendaTime: { fontSize: 10, lineHeight: 14, fontWeight: "800" }, agendaLabel: { fontSize: 13, lineHeight: 19, fontWeight: "800" },
  footer: { gap: 13, marginTop: 4 }, sectionText: { fontSize: 12, lineHeight: 19 }, boundary: { fontSize: 10, lineHeight: 16 }, receipt: { minHeight: 82, borderWidth: 1, borderRadius: 18, padding: 13, flexDirection: "row", alignItems: "center", gap: 9 }, receiptCopy: { flex: 1, gap: 3 }, receiptTitle: { fontSize: 14, lineHeight: 20, fontWeight: "900" }, receiptText: { fontSize: 11, lineHeight: 17 }, actionRow: { flexDirection: "row", gap: 9 }, consultAction: { width: 110, minHeight: 52, borderWidth: 1, borderRadius: 18, alignItems: "center", justifyContent: "center" }, consultText: { fontSize: 12, lineHeight: 17, fontWeight: "900" }, primaryAction: { flex: 1, minHeight: 52, borderRadius: 18, backgroundColor: "#F28C45", alignItems: "center", justifyContent: "center" }, loadingContent: { flexDirection: "row", alignItems: "center", gap: 7 }, disabled: { opacity: 0.78 }, primaryText: { color: "#FFFFFF", fontSize: 14, lineHeight: 20, fontWeight: "900" }, modalScrim: { flex: 1, backgroundColor: "#09295A66", alignItems: "center", justifyContent: "center", paddingHorizontal: 34 }, successModal: { width: "100%", borderRadius: 24, backgroundColor: "#FFFFFF", padding: 24, alignItems: "center", gap: 12 }, successTitle: { color: "#09295A", fontSize: 20, lineHeight: 28, fontWeight: "900" }, successText: { color: "#5D6D84", fontSize: 13, lineHeight: 20, textAlign: "center" }, successAction: { alignSelf: "stretch", minHeight: 48, borderRadius: 18, backgroundColor: "#F28C45", alignItems: "center", justifyContent: "center", marginTop: 4 }, successActionText: { color: "#FFFFFF", fontSize: 15, lineHeight: 21, fontWeight: "900" }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
