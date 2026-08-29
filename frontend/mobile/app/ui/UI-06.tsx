import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiCommerceCustomerProjection, FamilyApiMembershipPlansProjection, FamilyApiMembershipProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

const MENU_ITEMS = [
  { id: "report", label: "我的报告", icon: "book.fill" as const, target: "UI-08" },
  { id: "plan", label: "我的计划", icon: "calendar.fill" as const, target: "UI-04" },
  { id: "orders", label: "订单", icon: "ticket.fill" as const, target: "UI-32" },
  { id: "invite", label: "邀请有礼", icon: "gift.fill" as const, target: "UI-15" },
  { id: "archive", label: "成长档案", icon: "wallet.fill" as const, target: "UI-33" },
  { id: "support", label: "联系客服", icon: "headphones.fill" as const, target: "UI-19" },
] as const;

export default function MyMembershipScreen() {
  const session = useFamilyApiSession();
  const mobile = useFamilyMobile();
  const [plans, setPlans] = useState<FamilyApiMembershipPlansProjection | null>(null);
  const [membership, setMembership] = useState<FamilyApiMembershipProjection | null>(null);
  const [commerce, setCommerce] = useState<FamilyApiCommerceCustomerProjection | null>(null);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    Promise.all([
      familyApi.getMembershipPlans<FamilyApiMembershipPlansProjection>(session.token, session.selectedFamily.family_id),
      familyApi.getMembershipCustomerProjection<FamilyApiMembershipProjection>(session.token, session.selectedFamily.family_id),
      familyApi.getCommerceCustomerProjection<FamilyApiCommerceCustomerProjection>(session.token, session.selectedFamily.family_id),
    ]).then(([nextPlans, nextMembership, nextCommerce]) => {
      if (!active) return;
      setPlans(nextPlans);
      setMembership(nextMembership);
      setCommerce(nextCommerce);
    }).catch((error) => { console.error("UI-06 remote action failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const summary = useMemo(() => {
    const activeSubscription = membership?.subscriptions.find((item) => item.status === "ACTIVE");
    const benefitCount = membership?.benefits.filter((item) => item.status === "AVAILABLE").length ?? 0;
    const entitlementCount = commerce?.entitlements.filter((item) => item.status === "AVAILABLE").length ?? 0;
    const effectiveTo = activeSubscription?.effective_to?.slice(0, 10);
    return {
      memberLabel: activeSubscription ? "年度会员" : "成长会员",
      companionDays: activeSubscription ? "家庭成长陪伴已同步" : "家庭成长陪伴记录待同步",
      points: membership?.dev_points?.balance ?? 0,
      level: activeSubscription ? "Lv.3" : "Lv.1",
      coins: benefitCount + entitlementCount,
      dateLabel: effectiveTo ? `有效期至 ${effectiveTo}` : "有效期待确认",
      planTitle: plans?.plans[0]?.title ?? "会员服务待确认",
    };
  }, [commerce?.entitlements, membership?.benefits, membership?.dev_points?.balance, membership?.subscriptions, plans?.plans]);

  const invitedCount = mobile.invitationDraft ? 1 : 0;

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={MENU_ITEMS}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View>
            <View style={styles.topBar}>
              <View style={styles.topSpacer} />
              <Text style={styles.topTitle}>我的</Text>
              <View style={styles.topActions}><Text style={styles.more}>•••</Text><Text style={styles.topCircle}>⊙</Text></View>
            </View>

            <View style={styles.memberCard}>
              <View style={styles.memberHead}>
                <View style={styles.avatar}><IconSymbol name="person.crop.circle.fill" size={58} color="#09295A" /></View>
                <View style={styles.memberIdentity}>
                  <View style={styles.nameRow}><Text style={styles.memberName}>乐乐妈妈</Text><Text style={styles.memberBadge}>{summary.memberLabel}</Text></View>
                  <Text style={styles.memberDays}>{summary.companionDays}</Text>
                </View>
              </View>
              <View style={styles.memberStats}>
                <MemberStat label="成长积分" value={String(summary.points)} />
                <MemberStat label="家庭等级" value={summary.level} />
                <MemberStat label="亲子币" value={String(summary.coins)} />
              </View>
            </View>

            <Pressable onPress={() => router.push("/ui/UI-15" as Href)} style={({ pressed }) => [styles.inviteCard, pressed && styles.pressed]}>
              <View style={styles.inviteCopy}>
                <Text style={styles.inviteTitle}>邀请 3 个家庭，解锁会员权益</Text>
                <Text style={styles.inviteProgress}>已邀请 {invitedCount}/3</Text>
                <View style={styles.inviteTrack}><View style={[styles.inviteFill, { width: `${(invitedCount / 3) * 100}%` }]} /></View>
              </View>
              <View style={styles.inviteAction}><Text style={styles.inviteActionText}>去邀请</Text></View>
            </Pressable>
          </View>
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/ui/${item.target}` as Href)} style={({ pressed }) => [styles.menuRow, pressed && styles.rowPressed]}>
            <View style={styles.menuIcon}><IconSymbol name={item.icon} size={22} color={MENU_ICON_COLORS[item.id]} /></View>
            <Text style={styles.menuLabel}>{item.label}</Text>
            <IconSymbol name="chevron.right" size={21} color="#A8B0BA" />
          </Pressable>
        )}
        ListFooterComponent={
          <Pressable onPress={() => router.push("/ui/UI-30" as Href)} style={({ pressed }) => [styles.annualCard, pressed && styles.pressed]}>
            <View style={styles.annualCopy}>
              <Text style={styles.annualTitle}>{summary.planTitle}</Text>
              <Text style={styles.annualDate}>{summary.dateLabel}</Text>
              <View style={styles.benefitButton}><Text style={styles.benefitButtonText}>查看权益</Text></View>
            </View>
            <View style={styles.crownPanel}><IconSymbol name="crown.fill" size={70} color="#F4C75B" /></View>
          </Pressable>
        }
      />
    </ScreenContainer>
  );
}

const MENU_ICON_COLORS: Record<string, string> = {
  report: "#4F9AF5", plan: "#5D9CF1", orders: "#47BA77", invite: "#F26D71", archive: "#8063D2", support: "#68717D",
};

function MemberStat({ label, value }: { label: string; value: string }) {
  return <View style={styles.memberStat}><Text style={styles.memberStatLabel}>{label}</Text><Text style={styles.memberStatValue}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  content: { paddingBottom: 34, backgroundColor: "#FFFFFF" },
  topBar: { minHeight: 67, paddingHorizontal: 20, alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  topSpacer: { width: 58 },
  topTitle: { color: "#20242A", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  topActions: { width: 58, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  more: { color: "#20242A", fontSize: 17, lineHeight: 20, fontWeight: "900", letterSpacing: 1 },
  topCircle: { color: "#20242A", fontSize: 25, lineHeight: 25 },
  memberCard: { marginHorizontal: 17, minHeight: 211, borderRadius: 17, padding: 20, backgroundColor: "#092F76" },
  memberHead: { flexDirection: "row", alignItems: "center" },
  avatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", overflow: "hidden" },
  memberIdentity: { flex: 1, marginLeft: 12, gap: 4 },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  memberName: { color: "#09295A", fontSize: 21, lineHeight: 28, fontWeight: "900" },
  memberBadge: { color: "#8C5410", backgroundColor: "#F5D78D", borderRadius: 5, paddingHorizontal: 7, paddingVertical: 2, fontSize: 11, lineHeight: 16, fontWeight: "900" },
  memberDays: { color: "#5B7091", fontSize: 13, lineHeight: 19, fontWeight: "700" },
  memberStats: { marginTop: 35, flexDirection: "row", justifyContent: "space-between" },
  memberStat: { minWidth: 76, alignItems: "center", gap: 3 },
  memberStatLabel: { color: "#536A8B", fontSize: 12, lineHeight: 17 },
  memberStatValue: { color: "#09295A", fontSize: 23, lineHeight: 29, fontWeight: "900" },
  inviteCard: { minHeight: 100, marginHorizontal: 17, marginTop: 16, borderRadius: 12, paddingHorizontal: 17, paddingVertical: 15, backgroundColor: "#FFF1D5", flexDirection: "row", alignItems: "center", gap: 10 },
  inviteCopy: { flex: 1, gap: 5 },
  inviteTitle: { color: "#4B3A24", fontSize: 16, lineHeight: 22, fontWeight: "900" },
  inviteProgress: { color: "#937A55", fontSize: 11, lineHeight: 16, fontWeight: "700" },
  inviteTrack: { height: 5, maxWidth: 125, borderRadius: 4, backgroundColor: "#F5D49C", overflow: "hidden" },
  inviteFill: { height: 5, borderRadius: 4, backgroundColor: "#C98A2D" },
  inviteAction: { minWidth: 66, minHeight: 43, borderRadius: 10, backgroundColor: "#F4A91F", alignItems: "center", justifyContent: "center" },
  inviteActionText: { color: "#FFFFFF", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  menuRow: { minHeight: 57, marginHorizontal: 17, paddingHorizontal: 11, flexDirection: "row", alignItems: "center", borderBottomWidth: 1, borderBottomColor: "#F0F2F4" },
  menuIcon: { width: 31, alignItems: "center" },
  menuLabel: { flex: 1, marginLeft: 9, color: "#3B4149", fontSize: 15, lineHeight: 21, fontWeight: "700" },
  annualCard: { minHeight: 171, marginHorizontal: 17, marginTop: 21, borderRadius: 16, overflow: "hidden", paddingLeft: 27, paddingRight: 16, paddingVertical: 23, backgroundColor: "#FFF6DF", flexDirection: "row", alignItems: "center" },
  annualCopy: { flex: 1, gap: 8 },
  annualTitle: { color: "#6C4B00", fontSize: 23, lineHeight: 31, fontWeight: "900" },
  annualDate: { color: "#7B6848", fontSize: 13, lineHeight: 19, fontWeight: "700" },
  benefitButton: { alignSelf: "flex-start", minWidth: 86, minHeight: 35, marginTop: 4, borderRadius: 18, backgroundColor: "#F6DB8B", alignItems: "center", justifyContent: "center" },
  benefitButtonText: { color: "#2D2730", fontSize: 13, lineHeight: 18, fontWeight: "900" },
  crownPanel: { width: 105, alignItems: "center", justifyContent: "center" },
  pressed: { opacity: 0.88, transform: [{ scale: 0.985 }] },
  rowPressed: { opacity: 0.66 },
});
