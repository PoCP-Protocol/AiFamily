import type { Href } from "expo-router";
import { router, Stack } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { DataSourceBanner } from "@/components/family/data-source-banner";
import { FamilyFlatList as FlatList } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { createMobileRequestId, familyApi } from "@/lib/family/family-api-client";
import { normalizeAchievementNotifications, type FamilyAchievementNotificationsResponse } from "@/lib/family/feedback-api-contracts";
import type { ServiceCustomerProjection } from "@/lib/family/service-api-contracts";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

export default function ServiceRecordsScreen() {
  const colors = useColors(); const session = useFamilyApiSession(); const state = useFamilyMobile(); const [customer, setCustomer] = useState<ServiceCustomerProjection | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "error">("idle"); const [loadError, setLoadError] = useState<string | null>(null);
  const [achievementNotifications, setAchievementNotifications] = useState<FamilyAchievementNotificationsResponse["unread"]>([]);
  const [notificationState, setNotificationState] = useState<"idle" | "loading" | "ready" | "error">("idle"); const [notificationError, setNotificationError] = useState<string | null>(null);
  const loadRecords = useCallback(async () => { if (session.status !== "connected" || !session.token || !session.selectedFamily) return; setLoadState("loading"); setLoadError(null); try { setCustomer(await familyApi.getServiceCustomerProjection(session.token, session.selectedFamily.family_id)); setLoadState("ready"); } catch { setLoadState("error"); setLoadError("服务记录暂时无法同步；请稍后重试。"); } }, [session.selectedFamily, session.status, session.token]);
  useEffect(() => { void loadRecords(); }, [loadRecords]);
  const loadAchievementNotifications = useCallback(async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setAchievementNotifications([]);
      setNotificationState("idle");
      return;
    }
    const familyId = session.selectedFamily.family_id;
    setNotificationState("loading");
    setNotificationError(null);
    try {
      const raw = await familyApi.getFamilyAchievementNotifications(session.token, familyId);
      const result = normalizeAchievementNotifications(raw);
      if (result.family_id !== familyId) throw new Error("achievement_notification_scope_mismatch");
      setAchievementNotifications(result.unread);
      setNotificationState("ready");
    } catch {
      setNotificationState("error");
      setNotificationError("成就提醒暂时无法同步；请稍后重试。");
    }
  }, [session.selectedFamily, session.status, session.token]);
  useEffect(() => { void loadAchievementNotifications(); }, [loadAchievementNotifications]);
  const openAchievementNotification = async (notification: FamilyAchievementNotificationsResponse["unread"][number]) => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    try {
      await familyApi.markFamilyAchievementNotificationRead(
        session.token,
        session.selectedFamily.family_id,
        notification.notification_id,
        createMobileRequestId("ui34-achievement-read"),
      );
      setAchievementNotifications((current) => current.filter((item) => item.notification_id !== notification.notification_id));
      router.push("/ui/UI-29" as Href);
    } catch {
      setNotificationError("这条成就提醒暂时无法标记已读，请稍后重试。");
      setNotificationState("error");
    }
  };
  const consultations = useMemo(() => [
    ...(customer?.bookings.map((item) => ({ id: item.booking_request_id, title: "家庭咨询意向", detail: `${channelLabel(item.channel)} · ${item.starts_at.slice(0, 10)}`, status: bookingLabel(item.booking_status) })) ?? []),
    ...(state.consultationNeedDraft ? [{ id: state.consultationNeedDraft.id, title: state.consultationNeedDraft.offeringTitle, detail: "家庭私有咨询需求草稿", status: "已保存" }] : []),
  ], [customer?.bookings, state.consultationNeedDraft]);
  const activities = state.activityInterestDraft ? [{ id: state.activityInterestDraft.id, title: state.activityInterestDraft.activityTitle, detail: "家庭私有活动意向", status: "已保存" }] : [];
  const records = [...consultations.map((item) => ({ ...item, group: "咨询" })), ...activities.map((item) => ({ ...item, group: "活动" }))];
  return <ScreenContainer edges={["left", "right", "bottom"]}><Stack.Screen options={{ headerShown: true, title: "服务记录", headerBackTitle: "返回" }} /><FlatList data={records} keyExtractor={(item) => `${item.group}-${item.id}`} contentContainerStyle={styles.content} ListHeaderComponent={<View style={styles.header}><DataSourceBanner />{loadState === "error" ? <Text style={styles.loadError}>{loadError ?? "服务记录暂时无法同步；请稍后重试。"}</Text> : null}{notificationState === "loading" ? <Text style={[styles.notificationMeta, { color: colors.muted }]}>正在同步成就提醒…</Text> : null}{notificationError ? <Pressable accessibilityRole="button" accessibilityLabel="重试同步成就提醒" onPress={() => void loadAchievementNotifications()}><Text style={styles.loadError}>{notificationError} 点击重试</Text></Pressable> : null}{achievementNotifications.length > 0 ? <View style={[styles.notifications, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.notificationHeader}><Text style={[styles.sectionTitle, { color: colors.text }]}>新的成就提醒</Text><Text style={[styles.notificationMeta, { color: colors.muted }]}>{achievementNotifications.length} 条未读</Text></View>{achievementNotifications.map((notification) => <Pressable key={notification.notification_id} accessibilityRole="button" accessibilityLabel={`${notification.title}，${notification.message}`} onPress={() => void openAchievementNotification(notification)} style={({ pressed }) => [styles.notificationRow, pressed && styles.pressed]}><View style={[styles.notificationDot, { backgroundColor: colors.primary }]} /><View style={styles.notificationCopy}><Text style={[styles.notificationTitle, { color: colors.text }]}>{notification.title}</Text><Text style={[styles.notificationMessage, { color: colors.muted }]}>{notification.message}</Text></View><IconSymbol name="chevron.right" size={16} color={colors.muted} /></Pressable>)}</View> : null}<Text style={[styles.sectionTitle, { color: colors.text }]}>我的咨询</Text></View>} renderItem={({ item, index }) => <View>{index === consultations.length && activities.length ? <Text style={[styles.sectionTitle, { color: colors.text, marginTop: 16 }]}>我的活动</Text> : null}<View style={[styles.record, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={[styles.recordIcon, { backgroundColor: item.group === "咨询" ? "#EAF2FF" : "#E8F7F1" }]}><IconSymbol name={item.group === "咨询" ? "headphones.fill" : "calendar.fill"} size={24} color={item.group === "咨询" ? "#2563EB" : "#16866D"} /></View><View style={styles.recordCopy}><Text style={[styles.recordTitle, { color: colors.text }]}>{item.title}</Text><Text style={[styles.recordDetail, { color: colors.muted }]}>{item.detail}</Text></View><Text style={[styles.status, { color: item.status === "已保存" ? "#2563EB" : "#F28C45" }]}>{item.status}</Text></View></View>} ListEmptyComponent={<View style={[styles.empty, { backgroundColor: colors.surface, borderColor: colors.border }]}><IconSymbol name="calendar.fill" size={30} color={colors.muted} /><Text style={[styles.emptyTitle, { color: colors.text }]}>{loadState === "error" ? "暂时无法读取记录" : "还没有需要回看的服务记录"}</Text><Text style={[styles.emptyCopy, { color: colors.muted }]}>{loadState === "error" ? loadError ?? "请稍后重试。" : "保存一次咨询需求或活动意向后，这里会按家庭私有范围回看相应过程。"}</Text></View>} ListFooterComponent={<View style={styles.footer}><View style={[styles.support, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.supportTitle, { color: colors.text }]}>服务支持</Text><View style={styles.supports}><Support icon="headphones.fill" label="服务说明" /><Support icon="message.fill" label="家庭反馈" /><Support icon="book.fill" label="常见问题" /></View></View><Pressable onPress={() => router.push("/ui/UI-31" as Href)} style={({ pressed }) => [styles.outlineButton, { borderColor: colors.tint }, pressed && styles.pressed]}><IconSymbol name="headphones.fill" size={20} color={colors.tint} /> <Text style={[styles.outlineText, { color: colors.tint }]}>返回我的服务</Text></Pressable><Text style={[styles.boundary, { color: colors.muted }]}>服务记录用于回看安排、意向和家庭反馈，不代表服务结果；不会自动联系、拨号、发送消息或创建工单。</Text></View>} /></ScreenContainer>;
}
function Support({ icon, label }: { icon: "headphones.fill" | "message.fill" | "book.fill"; label: string }) { return <View style={styles.supportItem}><View style={styles.supportIcon}><IconSymbol name={icon} size={23} color="#2563EB" /></View><Text style={styles.supportLabel}>{label}</Text></View>; }
function channelLabel(channel: "VIDEO" | "TEXT" | "OFFLINE") { return channel === "VIDEO" ? "视频沟通" : channel === "TEXT" ? "文字沟通" : "线下活动"; }
function bookingLabel(status: string) { return status === "CONFIRMED" ? "待确认" : status === "CANCELLED" ? "已取消" : "已保存"; }
const styles = StyleSheet.create({ content: { padding: 16, paddingBottom: 38, gap: 10 }, header: { gap: 8 }, loadError: { color: "#A53B3B", fontSize: 12, lineHeight: 17 }, notificationMeta: { fontSize: 12, lineHeight: 17, fontWeight: "700" }, notifications: { borderWidth: 1, borderRadius: 18, padding: 13, gap: 8 }, notificationHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, notificationRow: { minHeight: 58, flexDirection: "row", alignItems: "center", gap: 9, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#EDF1F5", paddingTop: 8 }, notificationDot: { width: 9, height: 9, borderRadius: 5 }, notificationCopy: { flex: 1, gap: 2 }, notificationTitle: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, notificationMessage: { fontSize: 11, lineHeight: 16 }, sectionTitle: { fontSize: 18, lineHeight: 24, fontWeight: "900" }, record: { minHeight: 76, borderWidth: 1, borderRadius: 18, padding: 12, flexDirection: "row", alignItems: "center", gap: 10, marginTop: 9 }, recordIcon: { width: 46, height: 46, borderRadius: 16, alignItems: "center", justifyContent: "center" }, recordCopy: { flex: 1, gap: 4 }, recordTitle: { fontSize: 14, lineHeight: 19, fontWeight: "900" }, recordDetail: { fontSize: 11, lineHeight: 16 }, status: { fontSize: 11, fontWeight: "900" }, empty: { marginTop: 10, borderWidth: 1, borderRadius: 18, padding: 18, gap: 8, alignItems: "center" }, emptyTitle: { fontSize: 15, lineHeight: 21, fontWeight: "900" }, emptyCopy: { fontSize: 12, lineHeight: 18, textAlign: "center" }, footer: { paddingTop: 18, gap: 12 }, support: { borderWidth: 1, borderRadius: 20, padding: 15, gap: 12 }, supportTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" }, supports: { flexDirection: "row", justifyContent: "space-around" }, supportItem: { alignItems: "center", gap: 5 }, supportIcon: { width: 42, height: 42, borderRadius: 15, backgroundColor: "#EAF2FF", alignItems: "center", justifyContent: "center" }, supportLabel: { color: "#5B7091", fontSize: 10, lineHeight: 14 }, outlineButton: { minHeight: 52, borderWidth: 1.5, borderRadius: 16, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 }, outlineText: { fontSize: 15, fontWeight: "900" }, boundary: { fontSize: 11, lineHeight: 17, textAlign: "center" }, pressed: { opacity: 0.82, transform: [{ scale: 0.985 }] }, });
