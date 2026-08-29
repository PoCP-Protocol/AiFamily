import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { commerceProductsForDisplay } from "@/lib/family/commerce-entitlements";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiCommerceCustomerProjection, FamilyApiCommerceIntentReceipt, FamilyApiCommerceProductsProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { haptic } from "@/lib/haptics";

type SubmitState = "idle" | "submitting" | "saved" | "error";

const LOCAL_BOOKMARK_BOUNDARY = "仅本机收藏，不外发通知";
const SUPPORT_NO_EXTERNAL_EFFECT_BOUNDARY = "客服入口不发起外部会话，不外发通知";
const PURCHASE_INTENT_BOUNDARY = "不会扣款，只保存受控购买意向";

const BASELINE_DELIVERY_ICONS = ["📘", "✓", "👥", "？"] as const;
const BASELINE_INFO_TABS = ["商品详情", "课程大纲", "用户评价"] as const;
const BASELINE_COURSE_SECTIONS = [
  { title: "第1周：建立亲子沟通基础", items: ["理解孩子的心理需求", "掌握倾听的艺术", "建立信任关系"] },
  { title: "第2周：提升沟通技巧", items: ["情绪管理与表达", "冲突化解方法", "正向反馈技巧"] },
  { title: "第3周：巩固家庭关系", items: ["制定家庭规则", "培养孩子自主性", "持续成长计划"] },
] as const;

export default function GrowthProductDetailScreen() {
  const session = useFamilyApiSession();
  const { productRef } = useLocalSearchParams<{ productRef?: string }>();
  const state = useFamilyMobile();
  const [catalog, setCatalog] = useState<FamilyApiCommerceProductsProjection | null>(null);
  const [commerceProjection, setCommerceProjection] = useState<FamilyApiCommerceCustomerProjection | null>(null);
  const [submitState, setSubmitState] = useState<SubmitState>("idle");
  const [bookmarked, setBookmarked] = useState(false);
  const [activeTab, setActiveTab] = useState<(typeof BASELINE_INFO_TABS)[number]>("商品详情");

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    Promise.all([
      familyApi.getCommerceProducts<FamilyApiCommerceProductsProjection>(session.token, session.selectedFamily.family_id),
      familyApi.getCommerceCustomerProjection<FamilyApiCommerceCustomerProjection>(session.token, session.selectedFamily.family_id),
    ]).then(([catalogResult, projectionResult]) => {
      if (!active) return;
      setCatalog(catalogResult);
      setCommerceProjection(projectionResult);
    }).catch((error) => { console.error("UI-14 remote action failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const products = useMemo(() => commerceProductsForDisplay(catalog?.products), [catalog?.products]);
  const product = products.find((item) => item.productRef === productRef)
    ?? products.find((item) => item.productRef === state.commerceIntentDraft?.productRef)
    ?? products[0];
  const matchingIntents = commerceProjection?.order_intents.filter((item) => item.product_ref === product.productRef) ?? [];
  const hasEntitlement = commerceProjection?.entitlements.some((item) => item.status === "AVAILABLE" && matchingIntents.some((intent) => intent.order_intent_id === item.source_order_intent_id)) ?? false;

  const saveIntent = async () => {
    const flowId = `commerce-intent:${product.productRef}`;
    state.setFlowStatus({ flowId, lastAction: "SAVE_COMMERCE_INTENT_DRAFT", remoteSyncState: "NOT_STARTED", source: "LOCAL_DRAFT", retryable: false });
    state.saveCommerceIntentDraft(product.productRef, product.productVersion, product.title);
    setSubmitState("submitting");
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      state.setFlowStatus({ flowId, lastAction: "SAVE_COMMERCE_INTENT_DRAFT", remoteSyncState: "NOT_STARTED", source: "LOCAL_DRAFT", retryable: false });
      setSubmitState("saved");
      haptic.success();
      return;
    }
    try {
      state.setFlowStatus({ flowId, lastAction: "SUBMIT_COMMERCE_INTENT", remoteSyncState: "SYNCING", source: "LOCAL_DRAFT", retryable: false });
      const result = await familyApi.submitCommerceIntent<FamilyApiCommerceIntentReceipt>(
        session.token,
        session.selectedFamily.family_id,
        { page_id: "UI-14", product_ref: product.productRef, product_version: product.productVersion, attributes: { entry: "family_ai_mobile_product_detail" } },
        `family-mobile-ui14:${session.selectedFamily.family_id}:${product.productRef}:v${product.productVersion}`,
      );
      state.syncCommerceIntentReceipt(result.intent.order_intent_id, result.entitlement.entitlement_id);
      state.setFlowStatus({ flowId, lastAction: "SUBMIT_COMMERCE_INTENT", remoteSyncState: "SYNCED", source: "REMOTE_RECEIPT", retryable: false });
      setSubmitState("saved");
      haptic.success();
    } catch {
      state.setFlowStatus({ flowId, lastAction: "SUBMIT_COMMERCE_INTENT", remoteSyncState: "ERROR", source: "LOCAL_DRAFT", retryable: true });
      setSubmitState("error");
    }
  };

  const toggleBookmark = () => {
    void LOCAL_BOOKMARK_BOUNDARY;
    setBookmarked((value) => !value);
    haptic.success();
  };

  const contactSupport = () => {
    void SUPPORT_NO_EXTERNAL_EFFECT_BOUNDARY;
    haptic.light();
  };

  const showIntentState = submitState === "saved" || state.commerceIntentDraft?.productRef === product.productRef || hasEntitlement;

  return (
    <ScreenContainer edges={["left", "right", "bottom"]} containerClassName="bg-white" safeAreaClassName="bg-white" style={styles.screen}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView refreshControl={<FamilyRefreshControl />} style={styles.scroll} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.statusBar}>
          <Text style={styles.statusTime}>9:41</Text>
          <View style={styles.statusMarks}><View style={styles.signalBars} /><Text style={styles.wifiMark}>⌁</Text><View style={styles.batteryMark} /></View>
        </View>

        <View style={styles.topBar}>
          <Pressable onPress={() => router.back()} hitSlop={12} style={styles.navButton}>
            <IconSymbol name="chevron.left" size={26} color="#1E2630" />
          </Pressable>
          <Text style={styles.topTitle}>商品详情</Text>
          <View style={styles.capsule}><Text style={styles.capsuleDots}>•••</Text><View style={styles.capsuleDivider} /><View style={styles.capsuleCircle} /></View>
        </View>

        <View style={styles.heroCard}>
          <View style={styles.heroCopy}>
            <Text style={styles.heroTitle}>{product.title}</Text>
            <Text style={styles.heroSubtitle}>21天科学训练，改善亲子沟通</Text>
          </View>
          <View style={styles.heroArt}>
            <View style={styles.sun} />
            <View style={styles.parentBody} />
            <View style={styles.parentHead} />
            <View style={styles.childBody} />
            <View style={styles.childHead} />
            <View style={styles.book}><View style={styles.bookPage} /><View style={styles.bookLine} /><View style={styles.bookPage} /></View>
            <View style={styles.leafLeft} />
            <View style={styles.leafRight} />
          </View>
        </View>

        <View style={styles.priceBlock}>
          <View style={styles.priceRow}>
            <Text style={styles.priceMain}>{product.priceMain ?? product.familyPriceLabel}</Text>
            <Text style={styles.originalPrice}>{product.priceOriginal ?? product.listPriceLabel}</Text>
          </View>
          <Text style={styles.groupPrice}>{product.priceGroup ?? "拼团价 ¥199 (3人成团)"}</Text>
          <Text style={styles.memberPrice}>{product.priceMember ?? product.memberPriceLabel}</Text>
          {showIntentState ? <Text style={styles.intentBadge}>已加入家庭权益意向</Text> : null}
        </View>

        <View style={styles.assuranceBar}>
          {(product.assurances ?? ["21天系统训练", "打卡社群陪伴", "专家顾问答疑"]).slice(0, 3).map((label) => <AssurancePill key={label} label={label} />)}
        </View>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>你将获得</Text>
          <Text style={styles.sectionSubtitle}>训练营 ＋ 打卡社群 ＋ 顾问答疑</Text>
        </View>

        <View style={styles.deliveryGrid}>
          {product.delivery.slice(0, 4).map((item, index) => (
            <View key={`${product.productRef}-${item}`} style={styles.deliveryItem}>
              <View style={styles.deliveryIcon}><Text style={styles.deliveryEmoji}>{BASELINE_DELIVERY_ICONS[index] ?? "•"}</Text></View>
              <Text style={styles.deliveryLabel}>{item}</Text>
            </View>
          ))}
        </View>

        <Pressable onPress={() => router.push("/ui/UI-15" as Href)} style={({ pressed }) => [styles.shareCard, pressed && styles.pressed]}>
          <View style={styles.shareIcon}><Text style={styles.shareIconText}>礼</Text></View>
          <View style={styles.shareCopy}>
            <Text style={styles.shareTitle}>分享给3位家长，领取专属优惠券</Text>
            <Text style={styles.shareText}>成功邀请可得 ¥20 优惠券</Text>
          </View>
          <Text style={styles.shareAction}>去分享</Text>
        </Pressable>

        <View style={styles.infoCard}>
          <View style={styles.tabBar}>
            {BASELINE_INFO_TABS.map((tab) => (
              <Pressable key={tab} onPress={() => setActiveTab(tab)} style={styles.tabItem}>
                <Text style={[styles.tabText, activeTab === tab && styles.tabTextActive]}>{tab}</Text>
                {activeTab === tab ? <View style={styles.tabLine} /> : null}
              </Pressable>
            ))}
          </View>
          <Text style={styles.infoTitle}>课程介绍</Text>
          <Text style={styles.infoText}>本课程由家庭教育专家团队研发，通过21天系统训练，帮助家长掌握科学沟通方法，改善亲子关系。</Text>
          <Text style={styles.infoTitle}>课程大纲</Text>
          <View style={styles.courseList}>
            {BASELINE_COURSE_SECTIONS.map((section) => <CourseSection key={section.title} title={section.title} items={section.items} />)}
          </View>
        </View>

        {submitState === "error" ? <Text style={styles.errorText}>暂时无法同步，本机意向草稿已经保留</Text> : null}
      </ScrollView>

      <View style={styles.actionDock}>
        <View style={styles.actionTools}>
          <Pressable accessibilityRole="button" accessibilityLabel={bookmarked ? "取消收藏" : "收藏"} onPress={toggleBookmark} style={({ pressed }) => [styles.toolButton, pressed && styles.pressed]}>
            <IconSymbol name={bookmarked ? "bookmark.fill" : "star.fill"} size={22} color={bookmarked ? "#2F80ED" : "#7B8794"} />
            <Text style={[styles.toolText, bookmarked && styles.toolTextActive]}>收藏</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="客服" onPress={contactSupport} style={({ pressed }) => [styles.toolButton, pressed && styles.pressed]}>
            <IconSymbol name="headphones.fill" size={22} color="#7B8794" />
            <Text style={styles.toolText}>客服</Text>
          </Pressable>
        </View>
        <Pressable disabled={submitState === "submitting"} onPress={saveIntent} style={({ pressed }) => [styles.buyButton, pressed && styles.pressed]}>
          <Text style={styles.buttonText}>{submitState === "submitting" ? "正在保存" : "立即购买"}</Text>
        </Pressable>
        <Pressable onPress={() => router.push(`/ui/UI-16?productRef=${encodeURIComponent(product.productRef)}` as Href)} style={({ pressed }) => [styles.groupButton, pressed && styles.pressed]}>
          <Text style={styles.buttonText}>发起拼团</Text>
        </Pressable>
      </View>
    </ScreenContainer>
  );
}

function AssurancePill({ label }: { label: string }) {
  return (
    <View style={styles.assurancePill}>
      <View style={styles.checkCircle}><Text style={styles.checkText}>✓</Text></View>
      <Text style={styles.assuranceText}>{label}</Text>
    </View>
  );
}

function CourseSection({ title, items }: { title: string; items: readonly string[] }) {
  return (
    <View style={styles.courseSection}>
      <Text style={styles.courseTitle}>{title}</Text>
      {items.map((item) => (
        <View key={item} style={styles.courseLine}>
          <View style={styles.courseDot} />
          <Text style={styles.courseText}>{item}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FFFFFF" },
  scroll: { flex: 1, backgroundColor: "#FFFFFF" },
  content: { paddingHorizontal: 16, paddingBottom: 102 },
  statusBar: { height: 28, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 5 },
  statusTime: { color: "#151B23", fontSize: 13, lineHeight: 18, fontWeight: "800" },
  statusMarks: { flexDirection: "row", alignItems: "center", gap: 5 },
  signalBars: { width: 18, height: 10, borderBottomWidth: 3, borderLeftWidth: 3, borderRightWidth: 3, borderColor: "#151B23", borderRadius: 2 },
  wifiMark: { color: "#151B23", fontSize: 14, lineHeight: 14, fontWeight: "900" },
  batteryMark: { width: 21, height: 10, borderWidth: 1.6, borderColor: "#151B23", borderRadius: 3 },
  topBar: { height: 47, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  navButton: { width: 40, height: 40, alignItems: "flex-start", justifyContent: "center" },
  topTitle: { color: "#1F2933", fontSize: 19, lineHeight: 27, fontWeight: "900" },
  capsule: { width: 76, height: 32, borderWidth: 1, borderColor: "#D8DEE8", borderRadius: 18, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: "#FFFFFF" },
  capsuleDots: { color: "#1F2933", fontSize: 16, lineHeight: 18, fontWeight: "900", letterSpacing: 1 },
  capsuleDivider: { width: 1, height: 16, backgroundColor: "#D8DEE8" },
  capsuleCircle: { width: 15, height: 15, borderWidth: 1.8, borderColor: "#1F2933", borderRadius: 8 },
  heroCard: { minHeight: 226, borderRadius: 0, marginHorizontal: -16, paddingHorizontal: 22, paddingTop: 20, flexDirection: "row", alignItems: "center", overflow: "hidden", backgroundColor: "#EAF6FF" },
  heroCopy: { flex: 1, paddingBottom: 36, gap: 9 },
  heroTitle: { color: "#172B4D", fontSize: 29, lineHeight: 38, fontWeight: "900" },
  heroSubtitle: { color: "#46637F", fontSize: 15, lineHeight: 22, fontWeight: "700" },
  heroArt: { width: 158, height: 172, alignItems: "center", justifyContent: "flex-end" },
  sun: { position: "absolute", right: 10, top: 8, width: 112, height: 112, borderRadius: 56, backgroundColor: "#CBEFFF" },
  parentBody: { position: "absolute", right: 64, bottom: 35, width: 43, height: 67, borderTopLeftRadius: 22, borderTopRightRadius: 22, borderRadius: 14, backgroundColor: "#2F80ED" },
  parentHead: { position: "absolute", right: 68, bottom: 98, width: 34, height: 34, borderRadius: 17, backgroundColor: "#F6C496" },
  childBody: { position: "absolute", right: 24, bottom: 30, width: 36, height: 52, borderTopLeftRadius: 18, borderTopRightRadius: 18, borderRadius: 13, backgroundColor: "#F9A43A" },
  childHead: { position: "absolute", right: 29, bottom: 78, width: 27, height: 27, borderRadius: 14, backgroundColor: "#F1B37F" },
  book: { position: "absolute", right: 26, bottom: 11, width: 95, height: 38, borderRadius: 12, backgroundColor: "#FFFFFF", flexDirection: "row", alignItems: "center", padding: 5, shadowColor: "#448CC2", shadowOpacity: 0.12, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 2 },
  bookPage: { flex: 1, height: 26, borderRadius: 8, backgroundColor: "#F5FBFF" },
  bookLine: { width: 2, height: 26, marginHorizontal: 4, backgroundColor: "#B7E4F7" },
  leafLeft: { position: "absolute", left: 18, bottom: 18, width: 20, height: 32, borderRadius: 16, backgroundColor: "#83D39D", transform: [{ rotate: "-24deg" }] },
  leafRight: { position: "absolute", right: 6, bottom: 13, width: 18, height: 28, borderRadius: 14, backgroundColor: "#64C285", transform: [{ rotate: "26deg" }] },
  priceBlock: { paddingTop: 17, paddingBottom: 13, gap: 5, backgroundColor: "#FFFFFF" },
  priceRow: { flexDirection: "row", alignItems: "flex-end", gap: 10 },
  priceMain: { color: "#EF4B35", fontSize: 33, lineHeight: 39, fontWeight: "900" },
  originalPrice: { color: "#9AA5B1", fontSize: 13, lineHeight: 19, textDecorationLine: "line-through", paddingBottom: 4 },
  groupPrice: { color: "#EF4B35", fontSize: 16, lineHeight: 22, fontWeight: "800" },
  memberPrice: { color: "#C57A15", fontSize: 16, lineHeight: 22, fontWeight: "800" },
  intentBadge: { alignSelf: "flex-start", marginTop: 2, color: "#1BA673", borderWidth: 1, borderColor: "#A8E4CC", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, fontSize: 11, lineHeight: 15, fontWeight: "800" },
  assuranceBar: { minHeight: 52, borderWidth: 1, borderColor: "#FFE1C2", borderRadius: 14, paddingHorizontal: 9, flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: "#FFF7EF" },
  assurancePill: { flexDirection: "row", alignItems: "center", gap: 4 },
  checkCircle: { width: 16, height: 16, borderRadius: 8, alignItems: "center", justifyContent: "center", backgroundColor: "#21B66F" },
  checkText: { color: "#FFFFFF", fontSize: 10, lineHeight: 12, fontWeight: "900" },
  assuranceText: { color: "#5F6B78", fontSize: 10, lineHeight: 14, fontWeight: "700" },
  sectionHeader: { paddingTop: 18, gap: 4 },
  sectionTitle: { color: "#1F2933", fontSize: 21, lineHeight: 28, fontWeight: "900" },
  sectionSubtitle: { color: "#2F80ED", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  deliveryGrid: { flexDirection: "row", justifyContent: "space-between", paddingTop: 14, paddingBottom: 12, gap: 8 },
  deliveryItem: { flex: 1, alignItems: "center", gap: 7 },
  deliveryIcon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center", backgroundColor: "#F2F8FF" },
  deliveryEmoji: { fontSize: 20, lineHeight: 25 },
  deliveryLabel: { color: "#2D3748", fontSize: 11, lineHeight: 16, textAlign: "center", fontWeight: "800" },
  shareCard: { minHeight: 72, marginTop: 4, borderRadius: 16, borderWidth: 1, borderColor: "#F7D2C0", backgroundColor: "#FFF3EC", paddingHorizontal: 13, flexDirection: "row", alignItems: "center", gap: 10 },
  shareIcon: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: "#F4773C" },
  shareIconText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" },
  shareCopy: { flex: 1, gap: 2 },
  shareTitle: { color: "#A24A2B", fontSize: 13, lineHeight: 18, fontWeight: "900" },
  shareText: { color: "#8A7166", fontSize: 11, lineHeight: 16 },
  shareAction: { color: "#F06E36", fontSize: 13, lineHeight: 18, fontWeight: "900" },
  infoCard: { marginTop: 16, borderRadius: 18, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#EEF1F5", overflow: "hidden" },
  tabBar: { height: 51, flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "#EEF1F5" },
  tabItem: { flex: 1, alignItems: "center", justifyContent: "center" },
  tabText: { color: "#6B7785", fontSize: 14, lineHeight: 20, fontWeight: "800" },
  tabTextActive: { color: "#2F80ED" },
  tabLine: { position: "absolute", bottom: 0, width: 38, height: 3, borderRadius: 2, backgroundColor: "#2F80ED" },
  infoTitle: { color: "#1F2933", fontSize: 17, lineHeight: 24, fontWeight: "900", marginTop: 17, marginHorizontal: 16 },
  infoText: { color: "#5F6B78", fontSize: 14, lineHeight: 23, marginHorizontal: 16, marginTop: 8 },
  courseList: { paddingHorizontal: 16, paddingTop: 9, paddingBottom: 18, gap: 12 },
  courseSection: { borderRadius: 14, backgroundColor: "#F7FAFD", padding: 13, gap: 8 },
  courseTitle: { color: "#2C3E50", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  courseLine: { flexDirection: "row", alignItems: "center", gap: 8 },
  courseDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: "#2F80ED" },
  courseText: { color: "#64748B", fontSize: 13, lineHeight: 18, fontWeight: "700" },
  errorText: { color: "#D14343", fontSize: 12, lineHeight: 18, marginTop: 12 },
  actionDock: { position: "absolute", left: 0, right: 0, bottom: 0, minHeight: 82, paddingHorizontal: 12, paddingTop: 9, paddingBottom: 13, borderTopWidth: 1, borderTopColor: "#E7EBF0", backgroundColor: "#FFFFFF", flexDirection: "row", alignItems: "center", gap: 8 },
  actionTools: { width: 96, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  toolButton: { width: 45, minHeight: 54, alignItems: "center", justifyContent: "center", gap: 3 },
  toolText: { color: "#7B8794", fontSize: 10, lineHeight: 14, fontWeight: "700" },
  toolTextActive: { color: "#2F80ED" },
  buyButton: { flex: 1, minHeight: 54, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: "#2F80ED" },
  groupButton: { flex: 1, minHeight: 54, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: "#F28C45" },
  buttonText: { color: "#FFFFFF", fontSize: 15, lineHeight: 21, fontWeight: "900" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
