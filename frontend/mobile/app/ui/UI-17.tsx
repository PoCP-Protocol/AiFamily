import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiMembershipProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { getUiActionPolicy } from "@/lib/family/ui-action-policies";
import { haptic } from "@/lib/haptics";

const TASKS = [
  {
    id: "review-report",
    label: "查看家庭成长报告",
    status: "过程记录",
    target: "UI-08",
  },
  {
    id: "invite-draft",
    label: "创建家庭邀请草稿",
    status: "私有草稿",
    target: "UI-15",
  },
  {
    id: "daily-action",
    label: "完成一次家庭行动",
    status: "过程记录",
    target: "UI-09",
  },
  {
    id: "private-story",
    label: "保存家庭成长故事",
    status: "私有草稿",
    target: "UI-12",
  },
  {
    id: "support-topic",
    label: "了解一个支持主题",
    status: "只读了解",
    target: "UI-19",
  },
] as const;

const REWARDS = [
  {
    title: "家庭说明",
    points: "规则待确认",
    icon: "chart.bar.fill" as const,
    color: "#5B95E5",
  },
  {
    title: "亲子沟通手册",
    points: "规则待确认",
    icon: "book.fill" as const,
    color: "#16866D",
  },
  {
    title: "课程优惠券",
    points: "暂未开放",
    icon: "ticket.fill" as const,
    color: "#F28C45",
  },
  {
    title: "成长阅读礼包",
    points: "暂未开放",
    icon: "gift.fill" as const,
    color: "#D99A1B",
  },
] as const;

export default function GrowthPointsScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const [membership, setMembership] = useState<FamilyApiMembershipProjection | null>(null);
  const [receipt, setReceipt] = useState("");

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi
      .getMembershipCustomerProjection<FamilyApiMembershipProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => {
        if (active) setMembership(result);
      })
      .catch((error) => {
        console.error("UI-17 remote projection failed", error);
      });
    return () => {
      active = false;
    };
  }, [session.selectedFamily, session.status, session.token]);

  const pointsBalance = membership?.dev_points?.balance ?? null;
  const markReadOnly = (label: string) => {
    const policy = getUiActionPolicy("UI-17");
    if (policy) state.recordUiAction(policy, label);
    setReceipt(`${label}已记下；当前积分只用于家庭过程回看，不会自动发放或扣减权益。`);
    haptic.selection();
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={TASKS}
        keyExtractor={(item) => item.id}
        contentContainerStyle={[styles.content, { backgroundColor: colors.background }]}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topline}>
              <Pressable onPress={() => router.back()} style={styles.topBack}>
                <IconSymbol name="chevron.left" size={26} color={colors.text} />
              </Pressable>
              <Text style={[styles.pageTitle, { color: colors.text }]}>成长积分</Text>
              <View style={styles.topActions}>
                <Text style={[styles.topAction, { color: colors.muted }]}>明细</Text>
                <Text style={[styles.topAction, { color: colors.muted }]}>规则</Text>
              </View>
            </View>
            <View style={styles.pointsCard}>
              <View style={styles.pointsCopy}>
                <Text style={styles.pointsLabel}>成长积分投影</Text>
                <Text style={styles.pointsValue}>{pointsBalance ?? "--"}</Text>
                <Pressable onPress={() => markReadOnly("查看积分规则")} style={styles.signButton}>
                  <Text style={styles.signText}>查看积分规则</Text>
                </Pressable>
              </View>
              <View style={styles.coin}>
                <IconSymbol name="star.fill" size={45} color="#FFF2B9" />
              </View>
            </View>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>可记录的成长行动</Text>
            <Text style={[styles.sectionSubtitle, { color: colors.muted }]}>只用于过程回看，不承诺发放积分</Text>
          </View>
        }
        renderItem={({ item, index }) => (
          <View style={[styles.taskRow, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View
              style={[
                styles.taskIcon,
                {
                  backgroundColor: index % 2 === 0 ? "#16866D16" : "#2563EB16",
                },
              ]}
            >
              <IconSymbol name={index % 2 === 0 ? "checkmark.circle.fill" : "book.fill"} size={21} color={index % 2 === 0 ? "#16866D" : "#2563EB"} />
            </View>
            <Text style={[styles.taskLabel, { color: colors.text }]}>{item.label}</Text>
            <Text style={styles.taskPoints}>{item.status}</Text>
            <Pressable onPress={() => router.push(`/ui/${item.target}` as Href)} style={({ pressed }) => [styles.taskButton, pressed && styles.pressed]}>
              <Text style={styles.taskButtonText}>去查看</Text>
            </Pressable>
          </View>
        )}
        ListFooterComponent={
          <View style={styles.footer}>
            <View style={styles.rewardTopline}>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>权益规则预览</Text>
              <Text style={[styles.sectionSubtitle, { color: colors.muted }]}>当前不支持兑换</Text>
            </View>
            <View style={styles.rewardRow}>
              {REWARDS.map((reward) => (
                <View
                  key={reward.title}
                  style={[
                    styles.rewardCard,
                    {
                      backgroundColor: colors.surface,
                      borderColor: colors.border,
                    },
                  ]}
                >
                  <View style={[styles.rewardVisual, { backgroundColor: `${reward.color}18` }]}>
                    <IconSymbol name={reward.icon} size={28} color={reward.color} />
                  </View>
                  <Text style={[styles.rewardTitle, { color: colors.text }]} numberOfLines={2}>
                    {reward.title}
                  </Text>
                  <Text style={styles.rewardPoints}>{reward.points}</Text>
                  <Pressable onPress={() => markReadOnly(`查看${reward.title}`)} style={({ pressed }) => [styles.rewardButton, pressed && styles.pressed]}>
                    <Text style={styles.rewardButtonText}>查看说明</Text>
                  </Pressable>
                </View>
              ))}
            </View>
            {receipt ? (
              <View style={[styles.receipt, { backgroundColor: "#16866D12", borderColor: colors.success }]}>
                <IconSymbol name="checkmark.circle.fill" size={23} color={colors.success} />
                <Text style={[styles.receiptText, { color: colors.muted }]}>{receipt}</Text>
              </View>
            ) : null}
            <Text style={[styles.boundary, { color: colors.muted }]}>积分不用于家庭或孩子排名；当前不支持兑换、提现或自动发放权益。</Text>
          </View>
        }
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 38,
    gap: 0,
  },
  header: { gap: 12, marginBottom: 4 },
  topline: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  topBack: {
    width: 34,
    height: 36,
    alignItems: "flex-start",
    justifyContent: "center",
  },
  pageTitle: { fontSize: 20, lineHeight: 28, fontWeight: "800" },
  topActions: { flexDirection: "row", gap: 16 },
  topAction: { fontSize: 12, lineHeight: 17, fontWeight: "700" },
  pointsCard: {
    minHeight: 142,
    borderRadius: 22,
    padding: 19,
    backgroundColor: "#E8F4FC",
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  pointsCopy: { flex: 1, gap: 3 },
  pointsLabel: {
    color: "#5B7091",
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "700",
  },
  pointsValue: {
    color: "#10213E",
    fontSize: 36,
    lineHeight: 44,
    fontWeight: "800",
    fontVariant: ["tabular-nums"],
  },
  pointsSource: { color: "#536A8B", fontSize: 12, lineHeight: 18 },
  signButton: {
    alignSelf: "flex-start",
    minHeight: 44,
    borderRadius: 22,
    paddingHorizontal: 14,
    backgroundColor: "#F28C45",
    alignItems: "center",
    justifyContent: "center",
  },
  signText: {
    color: "#FFFFFF",
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "700",
  },
  coin: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: "#FFFFFF80",
    alignItems: "center",
    justifyContent: "center",
  },
  sectionTitle: { fontSize: 17, lineHeight: 24, fontWeight: "700" },
  sectionSubtitle: { fontSize: 11, lineHeight: 16 },
  taskRow: {
    minHeight: 72,
    marginBottom: 10,
    borderWidth: 1,
    borderRadius: 16,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  taskIcon: {
    width: 34,
    height: 34,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  taskLabel: { flex: 1, fontSize: 13, lineHeight: 18, fontWeight: "700" },
  taskPoints: {
    color: "#E49B18",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "900",
  },
  taskButton: {
    minHeight: 44,
    borderWidth: 1,
    borderColor: "#A8D3F0",
    borderRadius: 22,
    paddingHorizontal: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  taskButtonText: {
    color: "#0078D4",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  footer: { gap: 12, paddingTop: 18 },
  rewardTopline: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
  },
  rewardRow: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  rewardCard: {
    width: "48%",
    minHeight: 188,
    borderWidth: 1,
    borderRadius: 17,
    padding: 12,
    gap: 7,
  },
  rewardVisual: {
    height: 58,
    borderRadius: 13,
    alignItems: "center",
    justifyContent: "center",
  },
  rewardTitle: {
    minHeight: 36,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  rewardPoints: {
    color: "#B87500",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  rewardButton: {
    minHeight: 44,
    borderRadius: 22,
    backgroundColor: "#F28C45",
    alignItems: "center",
    justifyContent: "center",
  },
  rewardButtonText: {
    color: "#FFFFFF",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  receipt: {
    minHeight: 72,
    borderWidth: 1,
    borderRadius: 18,
    padding: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
  },
  receiptText: { flex: 1, fontSize: 11, lineHeight: 17 },
  boundary: { fontSize: 12, lineHeight: 18, textAlign: "center" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
