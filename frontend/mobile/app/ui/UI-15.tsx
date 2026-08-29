import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { EXISTING_COMMERCE_PRESENTATION } from "@/lib/family/commerce-entitlements";
import { createMobileRequestId, familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { haptic } from "@/lib/haptics";

const REWARDS = [
  { title: "家庭测评 1 次", detail: "价值 ¥59", icon: "chart.bar.fill" as const, color: "#2563EB" },
  { title: "成长积分 300", detail: "价值 ¥30", icon: "star.fill" as const, color: "#F0A11A" },
  { title: "专享答疑券", detail: "价值 ¥99", icon: "ticket.fill" as const, color: "#D85A4D" },
  { title: "会员折扣券", detail: "九折优惠", icon: "wallet.fill" as const, color: "#E9901A" },
] as const;

export default function InvitationRewardsScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const product = EXISTING_COMMERCE_PRESENTATION.find((item) => item.productRef === state.commerceIntentDraft?.productRef) ?? EXISTING_COMMERCE_PRESENTATION[0];
  const [receiptText, setReceiptText] = useState("");

  const saveDraft = async (entry: string) => {
    state.saveInvitationDraft(product.productRef, product.title);
    setReceiptText(`${entry}已记入家庭邀请草稿；没有打开外部应用，也没有向任何人发送。`);
    haptic.success();
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    await familyApi.recordDevFlowEvent(
      session.token,
      session.selectedFamily.family_id,
      { ui_id: "UI-15", command: "SAVE_SYNTHETIC_INVITATION_DRAFT", selection: product.productRef },
      createMobileRequestId("family-mobile-ui15"),
    ).catch((error) => { console.error("UI-15 remote action failed", error); });
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} refreshControl={<FamilyRefreshControl />}>
        <View style={styles.header}>
          <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.backButton}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>邀请有礼</Text><Text style={styles.more}>•••</Text></View>
          <View style={styles.hero}><Text style={styles.title}>邀请 3 个家庭，解锁会员权益</Text><Text style={styles.subtitle}>一起成长，收获更多奖励</Text></View>
        </View>

        <View style={[styles.progressCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.progressTopline}>
            <Text style={[styles.progressLabel, { color: colors.text }]}>已邀请家庭</Text>
            <Text style={[styles.progressValue, { color: colors.tint }]}>1/3</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={styles.progressFill} />
            {[0, 1, 2].map((index) => <View key={index} style={[styles.progressDot, index === 0 && styles.progressDotActive]} />)}
          </View>
          <Text style={[styles.progressHint, { color: colors.muted }]}>再邀请 2 个家庭即可解锁全部成长权益</Text>
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>邀请奖励进度</Text>
        <View style={styles.rewardGrid}>
          {REWARDS.map((reward) => (
            <View key={reward.title} style={[styles.rewardCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <View style={[styles.rewardIcon, { backgroundColor: `${reward.color}18` }]}>
                <IconSymbol name={reward.icon} size={25} color={reward.color} />
              </View>
              <View style={styles.rewardCopy}>
                <Text style={[styles.rewardTitle, { color: colors.text }]}>{reward.title}</Text>
                <Text style={[styles.rewardDetail, { color: colors.muted }]}>{reward.detail}</Text>
              </View>
            </View>
          ))}
        </View>

        <Pressable onPress={() => void saveDraft("邀请说明")} style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}>
          <IconSymbol name="paperplane.fill" size={21} color="#FFFFFF" />
          <Text style={styles.primaryButtonText}>立即邀请</Text>
        </Pressable>

        <Text style={[styles.methodTitle, { color: colors.text }]}>邀请方式</Text>
        <View style={styles.methodRow}>
          <InviteMethod label="微信好友" icon="person.2.fill" color="#16866D" onPress={() => void saveDraft("微信好友邀请")} />
          <InviteMethod label="朋友圈" icon="safari.fill" color="#F2A325" onPress={() => void saveDraft("朋友圈说明")} />
          <InviteMethod label="生成海报" icon="gift.fill" color="#5D78D6" onPress={() => void saveDraft("海报说明")} />
        </View>

        <View style={[styles.brandBanner, { backgroundColor: "#EAF2FF" }]}>
          <View style={styles.brandCopy}>
            <Text style={styles.brandTitle}>一起成长，一起变好</Text>
            <Text style={[styles.brandText, { color: colors.muted }]}>邀请好友 · 成长权益 · 单层记录</Text>
          </View>
          <View style={styles.qrPlaceholder}>
            <IconSymbol name="lock.fill" size={24} color="#2563EB" />
            <Text style={styles.qrText}>私有草稿</Text>
          </View>
        </View>

        {state.invitationDraft || receiptText ? (
          <View style={[styles.receipt, { backgroundColor: "#16866D12", borderColor: colors.success }]}>
            <IconSymbol name="checkmark.circle.fill" size={25} color={colors.success} />
            <Text style={[styles.receiptText, { color: colors.muted }]}>{receiptText || "邀请草稿已保存在家庭空间，未外发。"}</Text>
          </View>
        ) : null}

        <Pressable onPress={() => router.push(`/ui/UI-14?productRef=${encodeURIComponent(product.productRef)}` as Href)} style={({ pressed }) => [styles.secondaryButton, { borderColor: colors.border }, pressed && styles.pressed]}>
          <Text style={[styles.secondaryButtonText, { color: colors.tint }]}>返回方案详情</Text>
        </Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

type InviteIcon = "person.2.fill" | "safari.fill" | "gift.fill";

function InviteMethod({ label, icon, color, onPress }: { label: string; icon: InviteIcon; color: string; onPress(): void }) {
  const colors = useColors();
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.methodItem, pressed && styles.pressed]}>
      <View style={[styles.methodIcon, { backgroundColor: `${color}18` }]}>
        <IconSymbol name={icon} size={26} color={color} />
      </View>
      <Text style={[styles.methodLabel, { color: colors.text }]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 18, paddingTop: 16, paddingBottom: 38, gap: 14 },
  header: { gap: 8 },
  topBar: { minHeight: 45, alignItems: "center", justifyContent: "space-between", flexDirection: "row" },
  backButton: { width: 38, height: 38, justifyContent: "center", alignItems: "flex-start" },
  topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  more: { color: "#22272D", fontSize: 18, lineHeight: 20, fontWeight: "900", letterSpacing: 1 },
  hero: { minHeight: 94, borderRadius: 16, paddingHorizontal: 18, paddingTop: 20, backgroundColor: "#EAF5FF" },
  title: { color: "#2575D4", fontSize: 24, lineHeight: 31, fontWeight: "900" },
  subtitle: { color: "#63809E", fontSize: 14, lineHeight: 21, marginTop: 4, fontWeight: "700" },
  progressCard: { minHeight: 142, borderWidth: 1, borderRadius: 23, padding: 18, gap: 14 },
  progressTopline: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  progressLabel: { fontSize: 15, lineHeight: 21, fontWeight: "800" },
  progressValue: { fontSize: 29, lineHeight: 35, fontWeight: "900" },
  progressTrack: { height: 10, borderRadius: 5, backgroundColor: "#DDE8F7", flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  progressFill: { width: "33%", height: 10, borderRadius: 5, backgroundColor: "#2563EB", position: "absolute", left: 0 },
  progressDot: { width: 16, height: 16, borderRadius: 8, backgroundColor: "#D1D9E5", borderWidth: 3, borderColor: "#FFFFFF" },
  progressDotActive: { backgroundColor: "#2563EB" },
  progressHint: { fontSize: 12, lineHeight: 18 },
  sectionTitle: { fontSize: 18, lineHeight: 24, fontWeight: "900" },
  rewardGrid: { flexDirection: "row", flexWrap: "wrap", gap: 9 },
  rewardCard: { width: "48%", minHeight: 82, borderWidth: 1, borderRadius: 18, padding: 11, flexDirection: "row", alignItems: "center", gap: 8 },
  rewardIcon: { width: 42, height: 42, borderRadius: 15, alignItems: "center", justifyContent: "center" },
  rewardCopy: { flex: 1, gap: 2 },
  rewardTitle: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  rewardDetail: { fontSize: 10, lineHeight: 14 },
  primaryButton: { minHeight: 56, borderRadius: 18, backgroundColor: "#2563EB", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" },
  methodTitle: { fontSize: 17, lineHeight: 23, fontWeight: "900", textAlign: "center" },
  methodRow: { flexDirection: "row", justifyContent: "space-around" },
  methodItem: { width: 82, alignItems: "center", gap: 6 },
  methodIcon: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  methodLabel: { fontSize: 12, lineHeight: 17, fontWeight: "700" },
  brandBanner: { minHeight: 96, borderRadius: 20, padding: 15, flexDirection: "row", alignItems: "center", gap: 12 },
  brandCopy: { flex: 1, gap: 4 },
  brandTitle: { color: "#09295A", fontSize: 18, lineHeight: 24, fontWeight: "900" },
  brandText: { fontSize: 12, lineHeight: 18 },
  qrPlaceholder: { width: 66, height: 66, borderRadius: 12, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", gap: 2 },
  qrText: { color: "#2563EB", fontSize: 9, lineHeight: 12, fontWeight: "800" },
  receipt: { minHeight: 74, borderWidth: 1, borderRadius: 18, padding: 13, flexDirection: "row", alignItems: "center", gap: 10 },
  receiptText: { flex: 1, fontSize: 12, lineHeight: 18 },
  secondaryButton: { minHeight: 50, borderWidth: 1, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  secondaryButtonText: { fontSize: 14, lineHeight: 19, fontWeight: "800" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
