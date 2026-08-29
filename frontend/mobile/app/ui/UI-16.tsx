import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { EXISTING_COMMERCE_PRESENTATION, type CommerceCategory } from "@/lib/family/commerce-entitlements";
import { createMobileRequestId, familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { haptic } from "@/lib/haptics";

type Filter = "ALL" | CommerceCategory | "MEMBERSHIP";

export default function FamilyStudyGroupScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const { productRef } = useLocalSearchParams<{ productRef?: string }>();
  const [filter, setFilter] = useState<Filter>("ALL");
  const products = useMemo(() => EXISTING_COMMERCE_PRESENTATION.filter((item) => filter === "ALL" || item.category === filter || (filter === "MEMBERSHIP" && item.category === "COURSE")), [filter]);

  const saveGroup = async (item: (typeof EXISTING_COMMERCE_PRESENTATION)[number], familyCount: 2 | 3 | 4) => {
    state.saveStudyGroupDraft(item.productRef, item.title, familyCount);
    haptic.success();
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    await familyApi.recordDevFlowEvent(
      session.token,
      session.selectedFamily.family_id,
      { ui_id: "UI-16", command: "SAVE_SYNTHETIC_STUDY_GROUP_DRAFT", selection: item.productRef },
      createMobileRequestId("family-mobile-ui16"),
    ).catch((error) => { console.error("UI-16 remote action failed", error); });
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={products}
        keyExtractor={(item) => item.productRef}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>拼团专区</Text><Text style={styles.more}>•••</Text></View>
            <Text style={[styles.subtitle, { color: colors.muted }]}>多家庭一起学，更划算</Text>
            <View style={styles.filters}>
              {(["ALL", "COURSE", "MEMBERSHIP", "TOOL"] as const).map((item) => (
                <Pressable key={item} onPress={() => setFilter(item)} style={[styles.filter, filter === item && styles.filterActive]}>
                  <Text style={[styles.filterText, { color: filter === item ? "#2563EB" : colors.muted }]}>{item === "ALL" ? "全部" : item === "COURSE" ? "课程服务" : item === "MEMBERSHIP" ? "会员卡" : "工具包"}</Text>
                </Pressable>
              ))}
            </View>
          </View>
        }
        renderItem={({ item, index }) => {
          const targetCount = ([3, 4, 2, 3][index % 4] ?? 3) as 2 | 3 | 4;
          const isSaved = state.studyGroupDraft?.productRef === item.productRef && state.studyGroupDraft.state === "PRIVATE_DRAFT";
          return (
            <View style={[styles.groupCard, { backgroundColor: colors.surface, borderColor: item.productRef === productRef ? colors.tint : colors.border }]}>
              <Text style={[styles.groupTitle, { color: colors.text }]}>{item.title}</Text>
              <View style={styles.groupMiddle}>
                <View style={styles.leaderRow}>
                  <View style={[styles.avatar, { backgroundColor: `${item.accent}22` }]}>
                    <IconSymbol name="person.crop.circle.fill" size={24} color={item.accent} />
                  </View>
                  <View style={styles.leaderCopy}>
                    <Text style={[styles.leaderName, { color: colors.text }]}>团长：乐乐妈妈</Text>
                    <Text style={[styles.availability, { color: colors.muted }]}>23:45:12 后结束</Text>
                  </View>
                </View>
                <View style={styles.peopleArea}>
                  <Text style={[styles.peopleHint, { color: colors.muted }]}>还差 {Math.max(1, targetCount - 1)} 个家庭</Text>
                  <View style={styles.avatarStack}>
                    {Array.from({ length: targetCount }, (_, avatarIndex) => <View key={avatarIndex} style={[styles.smallAvatar, { backgroundColor: avatarIndex === 0 ? item.accent : colors.border }]} />)}
                  </View>
                </View>
              </View>
              <View style={styles.groupFooter}>
                <View>
                  <Text style={styles.groupPrice}>拼团价 {item.familyPriceLabel.replace("家庭意向 ", "")}</Text>
                  <Text style={styles.groupPrice}>{item.familyPriceLabel}</Text>
                </View>
                <Pressable onPress={() => void saveGroup(item, targetCount)} style={({ pressed }) => [styles.joinButton, isSaved && styles.joinButtonSaved, pressed && styles.pressed]}>
                  <Text style={styles.joinButtonText}>{isSaved ? "已保存" : "去拼团"}</Text>
                </Pressable>
              </View>
            </View>
          );
        }}
        ListFooterComponent={
          <View style={styles.footer}>
            {state.studyGroupDraft ? (
              <View style={[styles.receipt, { backgroundColor: "#16866D12", borderColor: colors.success }]}>
                <IconSymbol name="checkmark.circle.fill" size={25} color={colors.success} />
                <View style={styles.receiptCopy}>
                  <Text style={[styles.receiptTitle, { color: colors.success }]}>{state.studyGroupDraft.state === "CANCELLED" ? "同行想法已取消" : "同行想法已保存"}</Text>
                  <Text style={[styles.receiptText, { color: colors.muted }]}>当前没有创建拼团订单、发送邀请或扣款。</Text>
                </View>
              </View>
            ) : null}
            {state.studyGroupDraft?.state === "PRIVATE_DRAFT" ? (
              <Pressable onPress={() => state.cancelStudyGroupDraft()} style={({ pressed }) => [styles.cancelButton, { borderColor: colors.border }, pressed && styles.pressed]}>
                <Text style={[styles.cancelText, { color: colors.muted }]}>取消当前同行想法</Text>
              </Pressable>
            ) : null}
            <Pressable onPress={() => router.push("/ui/UI-13" as Href)} style={({ pressed }) => [styles.backButton, { borderColor: colors.border }, pressed && styles.pressed]}>
              <Text style={[styles.backText, { color: colors.tint }]}>返回家庭成长商城</Text>
            </Pressable>
          </View>
        }
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 14, paddingBottom: 38, gap: 12 },
  header: { gap: 5, marginBottom: 4 },
  topBar: { minHeight: 45, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" },
  topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  more: { color: "#22272D", fontSize: 18, lineHeight: 20, fontWeight: "900", letterSpacing: 1 },
  subtitle: { fontSize: 14, lineHeight: 21 },
  filters: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "#E4E9F1" },
  filter: { flex: 1, minHeight: 42, alignItems: "center", justifyContent: "center" },
  filterActive: { borderBottomWidth: 3, borderBottomColor: "#2563EB" },
  filterText: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  groupCard: { minHeight: 166, borderWidth: 1, borderRadius: 16, padding: 15, gap: 9 },
  groupTitle: { fontSize: 18, lineHeight: 24, fontWeight: "900" },
  groupMiddle: { flexDirection: "row", justifyContent: "space-between", gap: 10 },
  leaderRow: { flex: 1, flexDirection: "row", alignItems: "center", gap: 8 },
  avatar: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  leaderCopy: { flex: 1, gap: 2 },
  leaderName: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  availability: { fontSize: 10, lineHeight: 14 },
  peopleArea: { alignItems: "flex-end", gap: 6 },
  peopleHint: { fontSize: 11, lineHeight: 16 },
  avatarStack: { flexDirection: "row", gap: 3 },
  smallAvatar: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: "#FFFFFF" },
  groupFooter: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: 12 },
  oldPrice: { fontSize: 10, lineHeight: 14, textDecorationLine: "line-through" },
  groupPrice: { color: "#F06E36", fontSize: 18, lineHeight: 24, fontWeight: "900" },
  joinButton: { minHeight: 42, borderRadius: 15, backgroundColor: "#F28C45", paddingHorizontal: 14, alignItems: "center", justifyContent: "center" },
  joinButtonSaved: { backgroundColor: "#16866D" },
  joinButtonText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  footer: { gap: 10, paddingTop: 4 },
  receipt: { minHeight: 78, borderWidth: 1, borderRadius: 18, padding: 13, flexDirection: "row", alignItems: "center", gap: 10 },
  receiptCopy: { flex: 1, gap: 2 },
  receiptTitle: { fontSize: 14, lineHeight: 19, fontWeight: "800" },
  receiptText: { fontSize: 11, lineHeight: 16 },
  cancelButton: { minHeight: 46, borderWidth: 1, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  cancelText: { fontSize: 13, lineHeight: 18, fontWeight: "700" },
  backButton: { minHeight: 50, borderWidth: 1, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  backText: { fontSize: 14, lineHeight: 19, fontWeight: "800" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
