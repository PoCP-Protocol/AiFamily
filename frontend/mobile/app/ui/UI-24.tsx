import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { DataSourceBanner } from "@/components/family/data-source-banner";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiServiceCustomerProjection, FamilyApiServiceSupplyProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { channelLabel, serviceOfferingsForDisplay } from "@/lib/family/service-support";

export default function MyConsultationsAndActivitiesScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const [supply, setSupply] = useState<FamilyApiServiceSupplyProjection | null>(null);
  const [projection, setProjection] = useState<FamilyApiServiceCustomerProjection | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    setLoadState("loading");
    setLoadError(null);
    try {
      const [supplyResult, customerResult] = await Promise.all([
        familyApi.getServiceOfferings<FamilyApiServiceSupplyProjection>(session.token, session.selectedFamily.family_id, {}),
        familyApi.getServiceCustomerProjection<FamilyApiServiceCustomerProjection>(session.token, session.selectedFamily.family_id),
      ]);
      setSupply(supplyResult);
      setProjection(customerResult);
      setLoadState("ready");
    } catch {
      setLoadState("error");
      setLoadError("咨询与活动记录暂时无法同步；请稍后重试。");
    }
  }, [session.selectedFamily, session.status, session.token]);

  useEffect(() => { void loadData(); }, [loadData]);

  const offerings = useMemo(() => serviceOfferingsForDisplay(supply?.offerings), [supply?.offerings]);
  const remoteBookings = projection?.bookings ?? [];
  const localDraft = state.consultationNeedDraft;
  const activityDraft = state.activityInterestDraft;
  const consultationCount = remoteBookings.length || (localDraft ? 1 : 0);
  const activityCount = activityDraft ? 1 : 0;
  const recordCount = projection?.service_records.length ?? (localDraft?.serviceRecordId ? 1 : 0);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} refreshControl={<FamilyRefreshControl />}>
        <View style={styles.topBar}><View style={styles.topSpacer} /><Text style={styles.topTitle}>我的</Text><Text style={styles.topMore}>•••</Text></View><DataSourceBanner />
        {loadState === "error" ? <View style={[styles.loadError, { borderColor: colors.border, backgroundColor: colors.surface }]}><Text style={[styles.loadErrorText, { color: colors.text }]}>{loadError}</Text><Pressable onPress={() => void loadData}><Text style={[styles.sectionAction, { color: colors.tint }]}>重试</Text></Pressable></View> : null}
        <View style={styles.profileRow}><View style={styles.avatar}><Text style={styles.avatarText}>家</Text></View><View style={styles.profileCopy}><Text style={[styles.profileName, { color: colors.text }]}>我们的家庭</Text><Text style={[styles.profileLevel, { color: colors.muted }]}>家庭支持记录 · 私有可见</Text></View><View style={styles.memberBadge}><IconSymbol name="star.fill" size={15} color="#B87500" /><Text style={styles.memberText}>成长中心</Text></View></View>
        <View style={[styles.stats, { backgroundColor: colors.surface, borderColor: colors.border }]}><Stat value={consultationCount} label="我的咨询" /><Stat value={activityCount} label="我的活动" /><Stat value={recordCount} label="过程记录" /><Stat value={state.uiActionReceipts.length} label="家庭小记" /></View>

        <View style={styles.sectionHeading}><Text style={[styles.sectionTitle, { color: colors.text }]}>我的咨询</Text><Pressable onPress={() => router.push("/ui/UI-19" as Href)}><Text style={[styles.sectionAction, { color: colors.tint }]}>继续了解</Text></Pressable></View>
        {remoteBookings.length ? remoteBookings.map((item) => {
          const offering = offerings.find((candidate) => candidate.offeringRef === item.service_offering_ref);
          return <View key={item.booking_request_id} style={[styles.recordCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={[styles.recordAvatar, { backgroundColor: "#2563EB18" }]}><IconSymbol name="person.crop.circle.fill" size={29} color={colors.tint} /></View><View style={styles.recordCopy}><Text style={[styles.recordTitle, { color: colors.text }]}>{offering?.providerName || "家庭成长顾问"} · {offering?.title || "家庭支持"}</Text><Text style={[styles.recordMeta, { color: colors.muted }]}>{formatDate(item.starts_at)} · {channelLabel(item.channel)}</Text></View><StatusBadge status={item.status} /></View>;
        }) : localDraft ? <View style={[styles.recordCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={[styles.recordAvatar, { backgroundColor: "#2563EB18" }]}><IconSymbol name="person.crop.circle.fill" size={29} color={colors.tint} /></View><View style={styles.recordCopy}><Text style={[styles.recordTitle, { color: colors.text }]}>{localDraft.providerName} · {localDraft.offeringTitle}</Text><Text style={[styles.recordMeta, { color: colors.muted }]}>{localDraft.timePreference} · {channelLabel(localDraft.channel)}</Text></View><StatusBadge status={localDraft.state === "SYNCED_RECEIPT" ? "REQUESTED" : "DRAFT"} /></View> : <EmptyPanel title="还没有咨询记录" text="可以先从名师专区了解支持主题，不需要现在作决定。" target="UI-19" />}

        <View style={styles.sectionHeading}><Text style={[styles.sectionTitle, { color: colors.text }]}>我的活动</Text><Pressable onPress={() => router.push("/ui/UI-22" as Href)}><Text style={[styles.sectionAction, { color: colors.tint }]}>发现活动</Text></Pressable></View>
        {activityDraft ? <View style={[styles.recordCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={[styles.recordAvatar, { backgroundColor: "#F28C4518" }]}><IconSymbol name="calendar.fill" size={27} color="#F28C45" /></View><View style={styles.recordCopy}><Text style={[styles.recordTitle, { color: colors.text }]}>{activityDraft.activityTitle}</Text><Text style={[styles.recordMeta, { color: colors.muted }]}>活动想法已保存在家庭空间，时间与方式待确认</Text></View><StatusBadge status="DRAFT" /></View> : <EmptyPanel title="还没有活动想法" text="可以先看看适合当前家庭阶段的活动主题。" target="UI-22" />}

        <Pressable onPress={() => router.push("/ui/UI-18" as Href)} style={({ pressed }) => [styles.memberBanner, pressed && styles.pressed]}><View style={styles.memberCopy}><Text style={styles.memberLabel}>成长会员年卡</Text><Text style={styles.memberTitle}>专家支持、活动和家庭成长服务统一回看</Text><View style={styles.memberBenefits}><Text style={styles.memberBenefit}>专家服务</Text><Text style={styles.memberBenefit}>成长活动</Text><Text style={styles.memberBenefit}>家庭记录</Text></View></View><View style={styles.memberAction}><Text style={styles.memberActionText}>查看权益</Text></View></Pressable>

        <View style={[styles.boundary, { borderColor: colors.border }]}><IconSymbol name="lock.fill" size={20} color={colors.success} /><Text style={[styles.boundaryText, { color: colors.muted }]}>这里回看的咨询、活动和服务记录只说明家庭曾经记下过一个过程，不代表服务效果或孩子变化。</Text></View>
        <Pressable onPress={() => router.push("/ui/UI-34" as Href)} style={({ pressed }) => [styles.recordsButton, { borderColor: colors.tint }, pressed && styles.pressed]}><Text style={[styles.recordsButtonText, { color: colors.tint }]}>查看完整服务记录</Text><IconSymbol name="chevron.right" size={19} color={colors.tint} /></Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

function Stat({ value, label }: { value: number; label: string }) { const colors = useColors(); return <View style={styles.stat}><Text style={[styles.statValue, { color: colors.text }]}>{value}</Text><Text style={[styles.statLabel, { color: colors.muted }]}>{label}</Text></View>; }
function StatusBadge({ status }: { status: string }) { const label = status === "CONFIRMED" ? "已确认" : status === "CANCELLED" ? "已暂停" : status === "REQUESTED" ? "需求已记下" : status === "COMPLETED" ? "已完成" : "家庭草稿"; const color = status === "CANCELLED" ? "#8794A5" : status === "CONFIRMED" || status === "COMPLETED" ? "#16866D" : "#F28C45"; return <View style={[styles.statusBadge, { backgroundColor: `${color}15` }]}><Text style={[styles.statusText, { color }]}>{label}</Text></View>; }
function EmptyPanel({ title, text, target }: { title: string; text: string; target: string }) { const colors = useColors(); return <Pressable onPress={() => router.push(`/ui/${target}` as Href)} style={({ pressed }) => [styles.emptyPanel, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}><View style={styles.emptyCopy}><Text style={[styles.recordTitle, { color: colors.text }]}>{title}</Text><Text style={[styles.recordMeta, { color: colors.muted }]}>{text}</Text></View><IconSymbol name="chevron.right" size={20} color={colors.tint} /></Pressable>; }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.valueOf()) ? "时间待确认" : date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" }); }

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 14, paddingBottom: 38, gap: 14 }, topBar: { minHeight: 40, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topSpacer: { width: 42 }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, topMore: { color: "#22272D", fontSize: 18, lineHeight: 20, fontWeight: "900" }, profileRow: { flexDirection: "row", alignItems: "center", gap: 11 }, avatar: { width: 62, height: 62, borderRadius: 31, backgroundColor: "#DCE8FF", alignItems: "center", justifyContent: "center" }, avatarText: { color: "#09295A", fontSize: 24, fontWeight: "900" }, profileCopy: { flex: 1, gap: 2 }, profileName: { fontSize: 20, lineHeight: 27, fontWeight: "900" }, profileLevel: { fontSize: 11, lineHeight: 16 }, memberBadge: { minHeight: 32, borderRadius: 16, backgroundColor: "#FFF2D8", paddingHorizontal: 10, flexDirection: "row", alignItems: "center", gap: 3 }, memberText: { color: "#B87500", fontSize: 10, lineHeight: 14, fontWeight: "900" },
  stats: { minHeight: 84, borderWidth: 1, borderRadius: 19, flexDirection: "row", alignItems: "center" }, stat: { flex: 1, alignItems: "center", gap: 3 }, statValue: { fontSize: 21, lineHeight: 27, fontWeight: "900" }, statLabel: { fontSize: 9, lineHeight: 13, textAlign: "center" }, sectionHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 2 }, sectionTitle: { fontSize: 19, lineHeight: 26, fontWeight: "900" }, sectionAction: { fontSize: 11, lineHeight: 16, fontWeight: "800" },
  recordCard: { minHeight: 90, borderWidth: 1, borderRadius: 19, padding: 12, flexDirection: "row", alignItems: "center", gap: 9 }, recordAvatar: { width: 50, height: 50, borderRadius: 16, alignItems: "center", justifyContent: "center" }, recordCopy: { flex: 1, gap: 4 }, recordTitle: { fontSize: 13, lineHeight: 19, fontWeight: "900" }, recordMeta: { fontSize: 10, lineHeight: 15 }, loadError: { minHeight: 52, borderWidth: 1, borderRadius: 15, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", gap: 10 }, loadErrorText: { flex: 1, fontSize: 12, lineHeight: 17 }, statusBadge: { borderRadius: 9, paddingHorizontal: 7, paddingVertical: 4 }, statusText: { fontSize: 9, lineHeight: 13, fontWeight: "900" },
  emptyPanel: { minHeight: 82, borderWidth: 1, borderRadius: 19, padding: 13, flexDirection: "row", alignItems: "center", gap: 8 }, emptyCopy: { flex: 1, gap: 4 }, memberBanner: { minHeight: 148, borderRadius: 23, backgroundColor: "#FFF6DF", padding: 17, flexDirection: "row", alignItems: "center", gap: 12 }, memberCopy: { flex: 1, gap: 7 }, memberLabel: { color: "#B87500", fontSize: 13, lineHeight: 18, fontWeight: "900" }, memberTitle: { color: "#6C4B00", fontSize: 17, lineHeight: 23, fontWeight: "900" }, memberBenefits: { flexDirection: "row", flexWrap: "wrap", gap: 5 }, memberBenefit: { color: "#7B6848", backgroundColor: "#FFFFFF80", borderRadius: 9, paddingHorizontal: 7, paddingVertical: 4, fontSize: 9, lineHeight: 13, fontWeight: "700" }, memberAction: { minHeight: 38, borderRadius: 19, backgroundColor: "#F5D99B", paddingHorizontal: 12, alignItems: "center", justifyContent: "center" }, memberActionText: { color: "#714800", fontSize: 10, lineHeight: 14, fontWeight: "900" },
  boundary: { minHeight: 72, borderTopWidth: 1, paddingTop: 14, flexDirection: "row", alignItems: "flex-start", gap: 8 }, boundaryText: { flex: 1, fontSize: 11, lineHeight: 17 }, recordsButton: { minHeight: 50, borderWidth: 1, borderRadius: 18, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 3 }, recordsButtonText: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
