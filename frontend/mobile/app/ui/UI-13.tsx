import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { commerceProductsForDisplay, type CommercePresentationProduct } from "@/lib/family/commerce-entitlements";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiCommerceProductsProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";

export default function FamilyGrowthMallScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const [remoteCatalog, setRemoteCatalog] = useState<FamilyApiCommerceProductsProjection | null>(null);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getCommerceProducts<FamilyApiCommerceProductsProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => { if (active) setRemoteCatalog(result); })
      .catch((error) => { console.error("UI-13 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const products = useMemo(() => commerceProductsForDisplay(remoteCatalog?.products), [remoteCatalog?.products]);
  const openProduct = (product: CommercePresentationProduct) => {
    router.push(`/ui/UI-14?productRef=${encodeURIComponent(product.productRef)}` as Href);
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={products}
        keyExtractor={(item) => item.productRef}
        numColumns={3}
        columnWrapperStyle={styles.productRow}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><View style={styles.topSpacer} /><Text style={styles.topTitle}>家庭成长商城</Text><Text style={styles.more}>•••</Text></View>
            <Text style={[styles.greeting, { color: colors.text }]}>早上好，乐乐妈妈 👋</Text>
            <Text style={[styles.subtitle, { color: colors.muted }]}>一起成长，一起成为更好的父母</Text>

            <Pressable onPress={() => router.push("/ui/UI-15" as Href)} style={({ pressed }) => [styles.inviteBanner, pressed && styles.pressed]}>
              <View style={styles.inviteCopy}>
                <Text style={styles.inviteTitle}>邀请好友领成长礼包</Text>
                <Text style={styles.inviteLabel}>邀请越多，奖励越多</Text>
                <View style={styles.inviteAction}>
                  <Text style={styles.inviteActionText}>立即邀请</Text>
                  <IconSymbol name="chevron.right" size={18} color="#2563EB" />
                </View>
              </View>
              <View style={styles.familyMark}>
                <IconSymbol name="person.2.fill" size={42} color="#2563EB" />
              </View>
            </Pressable>

            <View style={styles.categoryGrid}>
              <CategoryTile label="拼团专区" detail="多人更优惠" icon="person.2.fill" color="#F06D61" target="UI-16" />
              <CategoryTile label="家庭成长好物" detail="课程工具服务" icon="book.fill" color="#53AD68" target="UI-14" />
              <CategoryTile label="成长积分商城" detail="积分换好礼" icon="star.fill" color="#F39A1C" target="UI-17" />
              <CategoryTile label="会员专享" detail="专属权益" icon="crown.fill" color="#F3A424" target="UI-18" />
              <CategoryTile label="限时挑战" detail="限时超值" icon="heart.fill" color="#F06863" target="UI-10" />
              <CategoryTile label="邀请有礼" detail="邀请得奖励" icon="gift.fill" color="#8561DF" target="UI-15" />
            </View>

            <View style={styles.sectionTopline}>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>今日推荐</Text>
              <Text style={[styles.sectionHint, { color: colors.muted }]}>更多 ›</Text>
            </View>
          </View>
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => openProduct(item)} style={({ pressed }) => [styles.productCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
            <View style={[styles.productVisual, { backgroundColor: `${item.accent}18` }]}>
              <IconSymbol name={item.category === "COURSE" ? "book.fill" : item.category === "ASSESSMENT" ? "chart.bar.fill" : "gift.fill"} size={30} color={item.accent} />
            </View>
            <Text style={[styles.productTitle, { color: colors.text }]} numberOfLines={2}>{item.title}</Text>
            <Text style={[styles.productPrice, { color: item.accent }]}>{item.familyPriceLabel.replace("家庭意向 ", "")}</Text>
            <Text style={[styles.productSource, { color: colors.muted }]}>已有人购买</Text>
          </Pressable>
        )}
        ListFooterComponent={
          <View style={[styles.footerNote, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <IconSymbol name="lock.fill" size={22} color={colors.success} />
            <Text style={[styles.footerText, { color: colors.muted }]}>查看和保存意向不会扣款，也不会自动开通权益。</Text>
          </View>
        }
      />
    </ScreenContainer>
  );
}

type CommerceIcon = "person.2.fill" | "book.fill" | "star.fill" | "crown.fill" | "gift.fill" | "headphones.fill" | "heart.fill";

function CategoryTile({ label, detail, icon, color, target }: { label: string; detail: string; icon: CommerceIcon; color: string; target: string }) {
  const colors = useColors();
  return (
    <Pressable onPress={() => router.push(`/ui/${target}` as Href)} style={({ pressed }) => [styles.categoryTile, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
      <View style={[styles.categoryIcon, { backgroundColor: `${color}18` }]}>
        <IconSymbol name={icon} size={23} color={color} />
      </View>
      <Text style={[styles.categoryLabel, { color: colors.text }]}>{label}</Text>
      <Text style={[styles.categoryDetail, { color: colors.muted }]}>{detail}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 36, gap: 12 },
  header: { gap: 10, marginBottom: 12 },
  topBar: { minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  topSpacer: { width: 42 },
  topTitle: { color: "#20242A", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  more: { width: 42, textAlign: "right", color: "#20242A", fontSize: 18, lineHeight: 20, fontWeight: "900", letterSpacing: 1 },
  greeting: { fontSize: 24, lineHeight: 32, fontWeight: "900" },
  subtitle: { fontSize: 14, lineHeight: 21 },
  inviteBanner: { minHeight: 151, borderRadius: 18, backgroundColor: "#E8F2FF", padding: 18, flexDirection: "row", alignItems: "center", gap: 12 },
  inviteCopy: { flex: 1, gap: 7 },
  inviteLabel: { color: "#5B7091", fontSize: 14, lineHeight: 20, fontWeight: "800" },
  inviteTitle: { color: "#09295A", fontSize: 23, lineHeight: 30, fontWeight: "900" },
  inviteAction: { alignSelf: "flex-start", minHeight: 34, borderRadius: 17, paddingHorizontal: 11, backgroundColor: "#FFFFFF", flexDirection: "row", alignItems: "center", gap: 2 },
  inviteActionText: { color: "#2563EB", fontSize: 12, lineHeight: 17, fontWeight: "800" },
  familyMark: { width: 68, height: 68, borderRadius: 34, backgroundColor: "#FFFFFF80", alignItems: "center", justifyContent: "center" },
  categoryGrid: { flexDirection: "row", flexWrap: "wrap", gap: 9 },
  categoryTile: { width: "31%", minHeight: 98, borderWidth: 1, borderRadius: 13, padding: 8, alignItems: "center", justifyContent: "center", gap: 3 },
  categoryIcon: { width: 42, height: 42, borderRadius: 15, alignItems: "center", justifyContent: "center" },
  categoryLabel: { fontSize: 13, lineHeight: 18, fontWeight: "800", textAlign: "center" },
  categoryDetail: { fontSize: 10, lineHeight: 14, textAlign: "center" },
  sectionTopline: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 2 },
  sectionTitle: { fontSize: 20, lineHeight: 26, fontWeight: "900" },
  sectionHint: { fontSize: 12, lineHeight: 17 },
  productRow: { gap: 8 },
  productCard: { flex: 1, minHeight: 194, borderWidth: 1, borderRadius: 18, padding: 9, gap: 6, marginBottom: 10 },
  productVisual: { height: 72, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  productTitle: { minHeight: 38, fontSize: 13, lineHeight: 18, fontWeight: "800" },
  productPrice: { fontSize: 14, lineHeight: 19, fontWeight: "900" },
  productSource: { fontSize: 10, lineHeight: 14 },
  footerNote: { minHeight: 74, borderWidth: 1, borderRadius: 19, padding: 14, flexDirection: "row", alignItems: "center", gap: 10, marginTop: 2 },
  footerText: { flex: 1, fontSize: 12, lineHeight: 18 },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
