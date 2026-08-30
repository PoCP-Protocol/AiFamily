import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi, FamilyApiError } from "@/lib/family/family-api-client";
import type { FamilyApiCommerceIntentReceipt, FamilyApiCommerceProductsProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { mapRemoteProducts } from "../catalog-contract";

type Product = ReturnType<typeof mapRemoteProducts>[number];
type DetailState = "idle" | "loading" | "ready" | "synthetic" | "empty" | "denied" | "error";
type IntentState = "idle" | "saving" | "saved" | "error";

const SYNTHETIC_PRODUCT: Product = {
  ref: "SYNTHETIC_PARENT_DIALOGUE",
  title: "亲子沟通小练习（演示）",
  summary: "从一段具体对话开始，给家庭一个不费力的尝试。",
  category: "COURSE",
  delivery: ["家庭行动卡", "文字回看"],
  provenance: "SYNTHETIC",
  accent: "#2563EB",
};

export default function ProductDetailExperienceScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { productRef } = useLocalSearchParams<{ productRef?: string }>();
  const [detailState, setDetailState] = useState<DetailState>("idle");
  const [product, setProduct] = useState<Product | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [intentState, setIntentState] = useState<IntentState>("idle");

  useEffect(() => {
    if (session.status === "local_synthetic") {
      setProduct(SYNTHETIC_PRODUCT);
      setDetailState("synthetic");
      setMessage(null);
      return;
    }
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setProduct(null);
      setDetailState(session.status === "authentication_required" || session.status === "no_family" ? "denied" : "idle");
      return;
    }
    let active = true;
    setDetailState("loading");
    familyApi.getCommerceProducts<FamilyApiCommerceProductsProjection>(session.token, session.selectedFamily.family_id)
      .then((projection) => {
        if (!active) return;
        const next = mapRemoteProducts(projection.products).find((item) => item.ref === productRef) ?? null;
        setProduct(next);
        setDetailState(next ? "ready" : "empty");
        setMessage(next ? null : "这个支持方向暂时不在当前家庭可见目录中。");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setProduct(null);
        const denied = error instanceof FamilyApiError && (error.status === 401 || error.status === 403 || error.code.includes("CONSENT") || error.code.includes("POLICY"));
        setDetailState(denied ? "denied" : "error");
        setMessage(denied ? "当前家庭授权或平台策略暂不允许读取这个方案。" : "方案详情暂时没有同步成功，可以稍后再试。");
      });
    return () => {
      active = false;
    };
  }, [productRef, session.selectedFamily, session.status, session.token]);

  const savePlanDraft = async () => {
    if (!product) return;
    setIntentState("saving");
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setIntentState("saved");
      return;
    }
    try {
      await familyApi.submitCommerceIntent<FamilyApiCommerceIntentReceipt>(session.token, session.selectedFamily.family_id, {
        page_id: "UI-14",
        product_ref: product.ref,
        product_version: 1,
        attributes: { entry: "family-needs-catalog", intent: "PLAN_DRAFT" },
      }, `family-catalog-plan-draft:${session.selectedFamily.family_id}:${product.ref}`);
      setIntentState("saved");
    } catch {
      setIntentState("error");
    }
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={[styles.content, { backgroundColor: colors.background }]} showsVerticalScrollIndicator={false}>
        <View style={styles.topBar}><Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={styles.back}><IconSymbol name="chevron.left" size={24} color={colors.text} /></Pressable><Text style={[styles.topTitle, { color: colors.text }]}>支持方案详情</Text><View style={styles.back} /></View>
        {detailState === "loading" ? <View style={[styles.notice, { borderColor: colors.border, backgroundColor: colors.surface }]}><ActivityIndicator color={colors.tint} /><Text style={[styles.noticeText, { color: colors.muted }]}>正在读取当前家庭可见方案……</Text></View> : null}
        {detailState === "denied" || detailState === "error" || detailState === "empty" ? <View style={[styles.notice, { backgroundColor: detailState === "denied" ? "#FFF7E8" : "#FFF0ED", borderColor: detailState === "denied" ? "#E9C98B" : "#F2B5A7" }]}><Text style={styles.noticeTitle}>{detailState === "denied" ? "先保护家庭的选择" : detailState === "empty" ? "暂时找不到这个方案" : "方案暂时没有回应"}</Text><Text style={styles.noticeText}>{message}</Text><Pressable accessibilityRole="button" onPress={() => router.push("/catalog" as Href)} style={styles.noticeButton}><Text style={styles.noticeButtonText}>回到支持目录</Text></Pressable></View> : null}
        {product ? <>
          <View style={[styles.hero, { backgroundColor: `${product.accent}15` }]}><View style={[styles.heroIcon, { backgroundColor: `${product.accent}28` }]}><IconSymbol name={product.category === "COURSE" ? "book.fill" : "gift.fill"} size={33} color={product.accent} /></View><Text style={[styles.heroTag, { color: product.accent }]}>{product.provenance === "SYNTHETIC" ? "本机演示资料" : "当前家庭可见"}</Text><Text style={[styles.heroTitle, { color: colors.text }]}>{product.title}</Text><Text style={[styles.heroSummary, { color: colors.muted }]}>{product.summary}</Text></View>
          <View style={[styles.empathy, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.sectionTitle, { color: colors.text }]}>先照顾家庭的感受</Text><Text style={[styles.body, { color: colors.muted }]}>不需要马上变得更好。这个方案只提供一个可以试试的方向，是否继续、什么时候继续，都由家庭决定。</Text></View>
          <View style={[styles.section, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.sectionTitle, { color: colors.text }]}>你会先得到什么</Text>{product.delivery.map((item) => <View key={item} style={styles.delivery}><IconSymbol name="checkmark.circle.fill" size={18} color={product.accent} /><Text style={[styles.body, { color: colors.text }]}>{item}</Text></View>)}</View>
          <View style={[styles.next, { backgroundColor: "#FFF5E7", borderColor: "#F3D4A0" }]}><Text style={styles.nextTitle}>先保存一份方案草案</Text><Text style={styles.nextBody}>保存只是家庭私有意向，不扣款、不自动开通、不预约服务；确认后才会进入下一步行动。</Text><Pressable accessibilityRole="button" disabled={intentState === "saving"} onPress={() => void savePlanDraft()} style={({ pressed }) => [styles.primaryButton, intentState === "saving" && styles.disabled, pressed && styles.pressed]}>{intentState === "saving" ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryText}>{intentState === "saved" ? "方案草案已保存" : "保存方案草案"}</Text>}</Pressable>{intentState === "error" ? <Text style={styles.errorText}>暂时没有保存成功；可以稍后重试，家庭不会因此产生外部影响。</Text> : null}<Pressable accessibilityRole="button" onPress={() => router.push("/journeys/plan" as Href)} style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}><Text style={[styles.secondaryText, { color: colors.tint }]}>去看下一步行动 ›</Text></Pressable></View>
        </> : null}
        <Text style={[styles.boundary, { color: colors.muted }]}>AI 或目录内容只作为 Draft/Proposal；服务端确认、家庭同意和环境策略始终优先。这里不比较家庭、不展示排名。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingTop: 10, paddingBottom: 38, gap: 14 },
  topBar: { minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  back: { width: 40, minHeight: 40, justifyContent: "center" },
  topTitle: { fontSize: 20, lineHeight: 28, fontWeight: "900" },
  notice: { minHeight: 86, borderWidth: 1, borderRadius: 18, padding: 14, gap: 7, alignItems: "flex-start" },
  noticeTitle: { color: "#7D4F00", fontSize: 14, lineHeight: 19, fontWeight: "900" },
  noticeText: { fontSize: 12, lineHeight: 18 },
  noticeButton: { minHeight: 36, borderRadius: 18, paddingHorizontal: 13, backgroundColor: "#F5D99B", alignItems: "center", justifyContent: "center" },
  noticeButtonText: { color: "#7D4F00", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  hero: { borderRadius: 24, padding: 19, gap: 8 },
  heroIcon: { width: 68, height: 68, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  heroTag: { fontSize: 11, lineHeight: 16, fontWeight: "900" },
  heroTitle: { fontSize: 25, lineHeight: 33, fontWeight: "900" },
  heroSummary: { fontSize: 13, lineHeight: 20 },
  empathy: { borderWidth: 1, borderRadius: 19, padding: 15, gap: 7 },
  section: { borderWidth: 1, borderRadius: 19, padding: 15, gap: 10 },
  sectionTitle: { fontSize: 17, lineHeight: 23, fontWeight: "900" },
  body: { fontSize: 12, lineHeight: 19 },
  delivery: { minHeight: 28, flexDirection: "row", alignItems: "center", gap: 8 },
  next: { borderWidth: 1, borderRadius: 20, padding: 16, gap: 9 },
  nextTitle: { color: "#7D4F00", fontSize: 18, lineHeight: 24, fontWeight: "900" },
  nextBody: { color: "#8A6B39", fontSize: 12, lineHeight: 18 },
  primaryButton: { minHeight: 48, borderRadius: 17, backgroundColor: "#F28C45", alignItems: "center", justifyContent: "center" },
  primaryText: { color: "#FFFFFF", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  secondaryButton: { minHeight: 44, borderRadius: 16, borderWidth: 1, borderColor: "#B9D4FF", backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  secondaryText: { fontSize: 13, lineHeight: 18, fontWeight: "900" },
  errorText: { color: "#B14E3E", fontSize: 11, lineHeight: 16 },
  boundary: { fontSize: 10, lineHeight: 16, textAlign: "center" },
  disabled: { opacity: 0.68 },
  pressed: { opacity: 0.82, transform: [{ scale: 0.985 }] },
});
