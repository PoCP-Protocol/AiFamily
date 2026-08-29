import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiCommerceCustomerProjection, FamilyApiMembershipPlansProjection, FamilyApiMembershipProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

const MENU_ITEMS = [
  { id: "orders", label: "我的订单", icon: "cart.fill" as const, target: "UI-32" },
  { id: "invites", label: "邀请记录", icon: "person.2.fill" as const, target: "UI-15" },
  { id: "rewards", label: "奖励明细", icon: "gift.fill" as const, target: "UI-17" },
  { id: "poster", label: "专属海报", icon: "safari.fill" as const, target: "UI-12" },
  { id: "benefits", label: "会员权益", icon: "crown.fill" as const, target: "UI-30" },
  { id: "support", label: "客服支持", icon: "headphones.fill" as const, target: "UI-19" },
] as const;

export default function MembershipCenterScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
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
    ]).then(([planResult, membershipResult, commerceResult]) => {
      if (!active) return;
      setPlans(planResult);
      setMembership(membershipResult);
      setCommerce(commerceResult);
    }).catch((error) => { console.error("UI-18 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const activeSubscription = membership?.subscriptions.find((item) => item.status === "ACTIVE");
  const availableBenefits = membership?.benefits.filter((item) => item.status === "AVAILABLE") ?? [];
  const activeEntitlements = commerce?.entitlements.filter((item) => item.status === "AVAILABLE") ?? [];
  const annualPlan = plans?.plans[0];
  const points = membership?.dev_points?.balance ?? 1280;

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={MENU_ITEMS}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><View style={styles.topSpacer} /><Text style={styles.topTitle}>我的</Text><Text style={styles.more}>•••</Text></View>
            <View style={styles.profileCard}>
              <View style={styles.profileTop}>
                <View style={styles.profileAvatar}>
                  <IconSymbol name="person.crop.circle.fill" size={52} color="#09295A" />
                </View>
                <View style={styles.profileCopy}>
                  <View style={styles.nameRow}>
                    <Text style={styles.profileName}>乐乐妈妈</Text>
                    <Text style={styles.partnerBadge}>成长合伙人</Text>
                  </View>
                  <Text style={styles.profileMotto}>一起成长，一起影响更多家庭</Text>
                </View>
              </View>
              <View style={styles.statsRow}>
                <Stat label="已邀请家庭" value={state.invitationDraft ? "1" : "0"} />
                <Stat label="同行计划" value={state.studyGroupDraft?.state === "PRIVATE_DRAFT" ? "1" : "0"} />
                <Stat label="成长积分" value={String(points)} />
                <Stat label="可用权益" value={String(availableBenefits.length + activeEntitlements.length)} />
              </View>
            </View>
            <View style={[styles.levelCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <View style={styles.levelCopy}>
                <Text style={[styles.levelLabel, { color: colors.muted }]}>我的等级　<Text style={{ color: colors.text, fontWeight: "900" }}>LV3 成长达人</Text></Text>
                <View style={styles.levelTrack}><View style={styles.levelFill} /></View>
                <Text style={[styles.levelHint, { color: colors.muted }]}>距下一步成长记录还有 720 积分</Text>
              </View>
              <IconSymbol name="crown.fill" size={44} color="#E4A928" />
            </View>
          </View>
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/ui/${item.target}` as Href)} style={({ pressed }) => [styles.menuRow, { borderBottomColor: colors.border }, pressed && styles.pressed]}>
            <View style={[styles.menuIcon, { backgroundColor: colors.surface }]}>
              <IconSymbol name={item.icon} size={21} color={colors.muted} />
            </View>
            <Text style={[styles.menuLabel, { color: colors.text }]}>{item.label}</Text>
            <IconSymbol name="chevron.right" size={20} color={colors.muted} />
          </Pressable>
        )}
        ListFooterComponent={
          <View style={styles.footer}>
            <Pressable onPress={() => router.push("/ui/UI-30" as Href)} style={({ pressed }) => [styles.memberBanner, pressed && styles.pressed]}>
              <View style={styles.memberCopy}>
                <Text style={styles.memberTitle}>{annualPlan?.title ?? "年度会员服务"}</Text>
                <Text style={styles.memberStatus}>{activeSubscription ? "会员权益生效中" : "可先了解年度陪伴节奏"}</Text>
                <Text style={styles.memberDate}>{activeSubscription?.effective_to ? `有效期至 ${activeSubscription.effective_to.slice(0, 10)}` : "不自动续费，不产生扣款"}</Text>
                <View style={styles.memberAction}>
                  <Text style={styles.memberActionText}>会员中心</Text>
                  <IconSymbol name="chevron.right" size={17} color="#09295A" />
                </View>
              </View>
              <View style={styles.memberCrown}>
                <IconSymbol name="crown.fill" size={48} color="#E8B74E" />
              </View>
            </Pressable>
            {annualPlan?.benefits.length ? (
              <View style={[styles.benefitPanel, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                <Text style={[styles.benefitTitle, { color: colors.text }]}>家庭可了解的会员支持</Text>
                {annualPlan.benefits.map((benefit) => (
                  <View key={benefit.benefit_ref} style={styles.benefitRow}>
                    <IconSymbol name="checkmark.circle.fill" size={17} color={colors.success} />
                    <Text style={[styles.benefitText, { color: colors.muted }]}>{benefit.title} · {benefit.units_per_grant} {benefit.allocation_type === "COUNT" ? "次" : "项"}</Text>
                  </View>
                ))}
              </View>
            ) : null}
            <Text style={[styles.boundary, { color: colors.muted }]}>会员、权益和积分都来自同一家庭空间；此页面不会直接开通、续费、扣款或发送通知。</Text>
          </View>
        }
      />
    </ScreenContainer>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 38 },
  header: { gap: 12, marginBottom: 6 },
  topBar: { minHeight: 46, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  topSpacer: { width: 42 },
  topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  more: { width: 42, textAlign: "right", color: "#22272D", fontSize: 18, lineHeight: 20, fontWeight: "900", letterSpacing: 1 },
  profileCard: { minHeight: 190, borderRadius: 24, backgroundColor: "#E8F2FF", padding: 17, gap: 18 },
  profileTop: { flexDirection: "row", alignItems: "center", gap: 12 },
  profileAvatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  profileCopy: { flex: 1, gap: 5 },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  profileName: { color: "#09295A", fontSize: 20, lineHeight: 26, fontWeight: "900" },
  partnerBadge: { color: "#FFFFFF", backgroundColor: "#3B8BE3", borderRadius: 10, paddingHorizontal: 8, paddingVertical: 3, fontSize: 10, lineHeight: 14, fontWeight: "800" },
  profileMotto: { color: "#5B7091", fontSize: 12, lineHeight: 18 },
  statsRow: { flexDirection: "row", justifyContent: "space-between" },
  stat: { flex: 1, alignItems: "center", gap: 5 },
  statLabel: { color: "#536A8B", fontSize: 10, lineHeight: 14 },
  statValue: { color: "#09295A", fontSize: 20, lineHeight: 26, fontWeight: "900" },
  levelCard: { minHeight: 96, borderWidth: 1, borderRadius: 20, padding: 15, flexDirection: "row", alignItems: "center", gap: 12 },
  levelCopy: { flex: 1, gap: 6 },
  levelLabel: { fontSize: 12, lineHeight: 17 },
  levelTrack: { height: 7, borderRadius: 4, backgroundColor: "#E4E9F1" },
  levelFill: { width: "58%", height: 7, borderRadius: 4, backgroundColor: "#E4A928" },
  levelHint: { fontSize: 10, lineHeight: 15 },
  menuRow: { minHeight: 58, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", gap: 10 },
  menuIcon: { width: 34, height: 34, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  menuLabel: { flex: 1, fontSize: 14, lineHeight: 19, fontWeight: "700" },
  footer: { gap: 12, paddingTop: 16 },
  memberBanner: { minHeight: 174, borderRadius: 24, backgroundColor: "#FFF6DF", padding: 19, flexDirection: "row", alignItems: "center", gap: 12 },
  memberCopy: { flex: 1, gap: 7 },
  memberTitle: { color: "#6C4B00", fontSize: 22, lineHeight: 29, fontWeight: "900" },
  memberStatus: { color: "#B87500", fontSize: 13, lineHeight: 18, fontWeight: "800" },
  memberDate: { color: "#7B6848", fontSize: 11, lineHeight: 16 },
  memberAction: { alignSelf: "flex-start", minHeight: 34, borderRadius: 17, backgroundColor: "#F3D985", paddingHorizontal: 12, flexDirection: "row", alignItems: "center", gap: 2 },
  memberActionText: { color: "#09295A", fontSize: 11, lineHeight: 15, fontWeight: "900" },
  memberCrown: { width: 82, height: 82, borderRadius: 28, backgroundColor: "#FFFFFF80", alignItems: "center", justifyContent: "center" },
  benefitPanel: { borderWidth: 1, borderRadius: 20, padding: 15, gap: 9 },
  benefitTitle: { fontSize: 15, lineHeight: 20, fontWeight: "900" },
  benefitRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  benefitText: { flex: 1, fontSize: 12, lineHeight: 18 },
  boundary: { fontSize: 11, lineHeight: 17, textAlign: "center" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
