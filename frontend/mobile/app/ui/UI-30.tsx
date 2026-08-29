import type { Href } from "expo-router";
import { router, Stack } from "expo-router";
import { useEffect, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type {
  FamilyApiCommerceCustomerProjection,
  FamilyApiMembershipPlansProjection,
  FamilyApiMembershipProjection,
} from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

const QUICK_LINKS = [
  { label: "我的报告", icon: "chart.bar.fill" as const, target: "UI-08" },
  { label: "我的计划", icon: "book.fill" as const, target: "UI-04" },
  { label: "我的咨询", icon: "headphones.fill" as const, target: "UI-24" },
  { label: "我的活动", icon: "calendar.fill" as const, target: "UI-23" },
  { label: "订单中心", icon: "wallet.fill" as const, target: "UI-32" },
  { label: "邀请有礼", icon: "gift.fill" as const, target: "UI-15" },
] as const;

export default function AnnualCompanionScreen() {
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
    ]).then(([nextPlans, nextMembership, nextCommerce]) => {
      if (!active) return;
      setPlans(nextPlans);
      setMembership(nextMembership);
      setCommerce(nextCommerce);
    }).catch((error) => { console.error("UI-30 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const subscription = membership?.subscriptions.find((item) => item.status === "ACTIVE");
  const benefits = membership?.benefits.filter((item) => item.status === "AVAILABLE") ?? [];
  const entitlements = commerce?.entitlements.filter((item) => item.status === "AVAILABLE") ?? [];
  const annualPlan = plans?.plans[0];
  const serviceProgress = state.campStarted ? Math.round((state.campCompletedDays.length / 21) * 100) : 0;

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={QUICK_LINKS}
        numColumns={3}
        keyExtractor={(item) => item.label}
        contentContainerStyle={styles.content}
        columnWrapperStyle={styles.linkRow}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={27} color="#22272D" /></Pressable><Text style={styles.topTitle}>我的年度会员服务</Text><Text style={styles.topMore}>•••</Text></View>
            <View style={styles.profile}>
              <View style={styles.profileTop}>
                <View style={styles.avatar}><IconSymbol name="person.crop.circle.fill" size={54} color="#09295A" /></View>
                <View style={styles.profileCopy}>
                  <View style={styles.nameRow}><Text style={styles.name}>我的家庭</Text><Text style={styles.badge}>年度陪伴</Text></View>
                  <Text style={styles.subtitle}>{subscription ? "陪伴服务进行中" : "可以先了解适合家庭的长期陪伴节奏"}</Text>
                </View>
              </View>
              <View style={styles.stats}>
                <Stat label="成长积分" value={membership?.dev_points ? String(membership.dev_points.balance) : "—"} />
                <Stat label="家庭服务" value={String((state.consultationNeedDraft ? 1 : 0) + (state.activityInterestDraft ? 1 : 0))} />
                <Stat label="可用权益" value={String(benefits.length + entitlements.length)} />
                <Stat label="邀请记录" value={state.invitationDraft ? "1" : "0"} />
              </View>
            </View>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>快捷入口</Text>
          </View>
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/ui/${item.target}` as Href)} style={({ pressed }) => [styles.link, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
            <View style={styles.linkIcon}><IconSymbol name={item.icon} size={25} color="#2563EB" /></View>
            <Text style={[styles.linkText, { color: colors.text }]}>{item.label}</Text>
          </Pressable>
        )}
        ListFooterComponent={
          <View style={styles.footer}>
            <View style={[styles.currentService, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <View style={styles.currentTop}><Text style={[styles.currentTitle, { color: colors.text }]}>当前陪伴</Text><Text style={styles.currentState}>{state.campStarted ? "进行中" : "等待开始"}</Text></View>
              <Text style={[styles.currentName, { color: colors.text }]}>{state.campStarted ? "21 天智慧父母成长营" : "90 天家庭成长计划"}</Text>
              <View style={styles.track}><View style={[styles.fill, { width: `${serviceProgress}%` }]} /></View>
              <Text style={[styles.currentHint, { color: colors.muted }]}>{state.campStarted ? `已完成 ${state.campCompletedDays.length} 个成长营小结，继续按自己的速度走。` : "从一次测评或小行动开始，再慢慢形成自己的节奏。"}</Text>
            </View>
            <Pressable onPress={() => router.push("/ui/UI-32" as Href)} style={({ pressed }) => [styles.banner, pressed && styles.pressed]}>
              <View style={styles.bannerCopy}>
                <Text style={styles.bannerTitle}>{annualPlan?.title ?? "年度会员服务"}</Text>
                <Text style={styles.bannerText}>{subscription ? "家庭权益与服务支持正在生效" : "先查看权益与长期陪伴节奏"}</Text>
                <View style={styles.bannerButton}><Text style={styles.bannerButtonText}>查看订单与资产</Text><IconSymbol name="chevron.right" size={16} color="#09295A" /></View>
              </View>
              <IconSymbol name="crown.fill" size={56} color="#E8B74E" />
            </Pressable>
            <Text style={[styles.boundary, { color: colors.muted }]}>续费、开通和支付都需要家庭另行确认；此处只回看现有权益与意向。</Text>
          </View>
        }
      />
    </ScreenContainer>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <View style={styles.stat}><Text style={styles.statValue}>{value}</Text><Text style={styles.statLabel}>{label}</Text></View>;
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingBottom: 38, gap: 10 }, header: { gap: 12 }, topBar: { minHeight: 40, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 18, lineHeight: 25, fontWeight: "900" }, topMore: { color: "#22272D", fontSize: 18, lineHeight: 20, fontWeight: "900" }, profile: { minHeight: 162, borderRadius: 22, backgroundColor: "#E8F2FF", padding: 16, gap: 14 }, profileTop: { flexDirection: "row", alignItems: "center", gap: 12 }, avatar: { width: 58, height: 58, borderRadius: 29, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" }, profileCopy: { flex: 1, gap: 5 }, nameRow: { flexDirection: "row", alignItems: "center", gap: 8 }, name: { color: "#09295A", fontSize: 21, lineHeight: 28, fontWeight: "900" }, badge: { color: "#8A5A00", backgroundColor: "#F8DE94", borderRadius: 10, paddingHorizontal: 8, paddingVertical: 3, fontSize: 11, fontWeight: "800" }, subtitle: { color: "#5B7091", fontSize: 12, lineHeight: 18 }, stats: { flexDirection: "row", justifyContent: "space-between", backgroundColor: "#FFFFFF", borderRadius: 18, paddingVertical: 12 }, stat: { flex: 1, alignItems: "center", gap: 3 }, statValue: { color: "#09295A", fontSize: 20, lineHeight: 26, fontWeight: "900" }, statLabel: { color: "#5B7091", fontSize: 10, lineHeight: 14, textAlign: "center" }, sectionTitle: { fontSize: 17, lineHeight: 23, fontWeight: "900", paddingTop: 3 }, linkRow: { gap: 10, marginBottom: 10 }, link: { flex: 1, minHeight: 92, borderWidth: 1, borderRadius: 18, alignItems: "center", justifyContent: "center", gap: 7, paddingHorizontal: 5 }, linkIcon: { width: 38, height: 38, borderRadius: 14, backgroundColor: "#EAF2FF", alignItems: "center", justifyContent: "center" }, linkText: { fontSize: 11, lineHeight: 16, fontWeight: "800", textAlign: "center" }, footer: { gap: 12, paddingTop: 5 }, currentService: { borderWidth: 1, borderRadius: 20, padding: 15, gap: 8 }, currentTop: { flexDirection: "row", justifyContent: "space-between" }, currentTitle: { fontSize: 14, lineHeight: 19, fontWeight: "900" }, currentState: { color: "#2563EB", backgroundColor: "#EAF2FF", borderRadius: 9, paddingHorizontal: 8, paddingVertical: 2, fontSize: 10, fontWeight: "800" }, currentName: { fontSize: 17, lineHeight: 23, fontWeight: "900" }, track: { height: 8, borderRadius: 5, backgroundColor: "#E2E8F0" }, fill: { height: 8, borderRadius: 5, backgroundColor: "#2563EB" }, currentHint: { fontSize: 11, lineHeight: 17 }, banner: { minHeight: 154, borderRadius: 22, backgroundColor: "#FFF6DF", padding: 18, flexDirection: "row", alignItems: "center", gap: 12 }, bannerCopy: { flex: 1, gap: 7 }, bannerTitle: { color: "#6C4B00", fontSize: 21, lineHeight: 28, fontWeight: "900" }, bannerText: { color: "#7B6848", fontSize: 12, lineHeight: 18 }, bannerButton: { alignSelf: "flex-start", minHeight: 30, borderRadius: 15, backgroundColor: "#F3D985", paddingHorizontal: 10, flexDirection: "row", alignItems: "center" }, bannerButtonText: { color: "#09295A", fontSize: 10, lineHeight: 14, fontWeight: "900" }, boundary: { fontSize: 11, lineHeight: 17, textAlign: "center" }, pressed: { opacity: 0.82, transform: [{ scale: 0.985 }] },
});
