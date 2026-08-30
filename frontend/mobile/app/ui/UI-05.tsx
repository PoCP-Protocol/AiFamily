import { Stack, router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Animated, Easing, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { SYNTHETIC_JOURNEY_ENABLED, SYNTHETIC_JOURNEY_PROJECTION } from "@/lib/family/journey-plan-synthetic-fixture";
import type { JourneyPlanProjectionDto } from "@/lib/family/journey-plan-contract";

interface ServiceJourney {
  process_summary?: { label?: string };
}

type JourneyPlanProjection = JourneyPlanProjectionDto;
const SERVICE_CARD_ACCESSIBILITY_LABEL = "家庭顾问、班主任陪跑、AI解读草案和专家答疑";
const SERVICE_CARDS = [
  { title: "家庭顾问", subtitle: "每周复盘", color: "#2F81F7", bg: "#EAF3FF", symbol: "顾" },
  { title: "班主任陪跑", subtitle: "过程提醒", color: "#18AE76", bg: "#EAF9F1", symbol: "陪" },
  { title: "AI解读草案", subtitle: "仅供家长参考", color: "#F5A11E", bg: "#FFF4DF", symbol: "AI" },
  { title: "专家答疑", subtitle: "成人主动提问", color: "#8B65D9", bg: "#F3EEFF", symbol: "答" },
] as const;

export default function CompanionJourneyScreen() {
  const session = useFamilyApiSession();
  const { activeOnboardingId } = useFamilyMobile();
  const [remote, setRemote] = useState<ServiceJourney | null>(null);
  const [journeyPlan, setJourneyPlan] = useState<JourneyPlanProjection | null>(null);
  const [reviewState, setReviewState] = useState<"idle" | "submitting">("idle");
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const serviceCardsOpacity = useRef(new Animated.Value(0.62)).current;
  const serviceCardsOffset = useRef(new Animated.Value(5)).current;
  const serviceCardsRevealed = useRef(false);

  useEffect(() => {
    if (SYNTHETIC_JOURNEY_ENABLED) {
      setJourneyPlan(SYNTHETIC_JOURNEY_PROJECTION);
      setRemote({ process_summary: { label: "SYNTHETIC DEV · 家庭过程回看" } });
      return;
    }
    if (session.status !== "connected" || !session.token || !session.selectedFamily || !activeOnboardingId) return;
    let active = true;
    familyApi.getServiceJourney<ServiceJourney>(session.token, session.selectedFamily.family_id, activeOnboardingId)
      .then((result) => { if (active) setRemote(result); })
      .catch((error) => { console.error("UI-05 journey projection failed", error); });
    familyApi.getJourneyPlan<JourneyPlanProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => { if (active) setJourneyPlan(result); })
      .catch((error) => { console.error("UI-05 journey plan projection failed", error); });
    return () => { active = false; };
  }, [activeOnboardingId, session.selectedFamily, session.status, session.token]);

  const plan = journeyPlan?.plan;
  const reviewDue = plan?.phases?.find((phase) => phase.phase === plan.current_phase)?.status === "REVIEW_DUE";
  const phaseCopy = {
    SEE: { title: "关系机制", text: "看见触发—回应循环，先把发生了什么说清楚。" },
    PARENT_FIRST: { title: "共同决策", text: "家长和孩子一起选择能执行的回应。" },
    CO_CREATE: { title: "冲突修复", text: "回看一次冲突如何被修复，再调整家庭约定。" },
  }[plan?.current_phase ?? "SEE"] ?? { title: "家庭机制", text: "从真实家庭过程里继续观察和调整。" };

  const reviewPhase = async (decision: "CONTINUE" | "ADJUST") => {
    if (SYNTHETIC_JOURNEY_ENABLED && plan?.plan_id) {
      const nextPhase = decision === "CONTINUE" ? "PARENT_FIRST" : "SEE";
      setJourneyPlan({
        plan: {
          ...plan,
          current_phase: nextPhase,
          phases: plan.phases?.map((phase) => ({
            ...phase,
            status: phase.phase === nextPhase ? "REVIEW_DUE" : phase.phase === "SEE" && decision === "CONTINUE" ? "COMPLETED" : phase.status,
          })),
        },
      });
      setReviewMessage(decision === "CONTINUE" ? "已记录家庭决定，进入共同决策阶段。" : "已保留当前阶段，家庭可以先调整再继续。" );
      return;
    }
    if (reviewState === "submitting" || !plan?.plan_id || session.status !== "connected" || !session.token || !session.selectedFamily) return;
    setReviewState("submitting");
    setReviewMessage(null);
    try {
      const result = await familyApi.reviewJourneyPhase<JourneyPlanProjection>(session.token, session.selectedFamily.family_id, plan.plan_id, decision, `ui05-review-${plan.plan_id}-${decision}`);
      setJourneyPlan(result);
      setReviewMessage(decision === "CONTINUE" ? "下一阶段已开始。" : "计划已暂缓，可先调整节奏。" );
    } catch {
      setReviewMessage("暂时无法完成阶段回顾，请稍后重试。");
    } finally {
      setReviewState("idle");
    }
  };

  const revealServiceCards = useCallback(() => {
    if (serviceCardsRevealed.current) return;
    serviceCardsRevealed.current = true;
    Animated.parallel([
      Animated.timing(serviceCardsOpacity, { toValue: 1, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
      Animated.timing(serviceCardsOffset, { toValue: 0, duration: 220, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
    ]).start();
  }, [serviceCardsOffset, serviceCardsOpacity]);

  useEffect(() => {
    const timer = setTimeout(revealServiceCards, 120);
    return () => clearTimeout(timer);
  }, [revealServiceCards]);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.screen}>
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.topBar}>
            <Pressable onPress={() => router.back()} hitSlop={10} style={styles.backButton}>
              <IconSymbol name="chevron.left" size={27} color="#222222" />
            </Pressable>
            <Text style={styles.topTitle}>21 天家庭复盘</Text>
            <View style={styles.topActions}><Text style={styles.moreText}>•••</Text><Text style={styles.circleText}>⊙</Text></View>
          </View>
          {SYNTHETIC_JOURNEY_ENABLED ? <Text testID="journey-review-synthetic-badge" style={styles.syntheticBadge}>SYNTHETIC DEV · 过程记录仅用于演示</Text> : null}

          <Animated.View style={[styles.serviceCardsTransition, { opacity: serviceCardsOpacity, transform: [{ translateY: serviceCardsOffset }] }]}>
            <View accessibilityLabel={SERVICE_CARD_ACCESSIBILITY_LABEL} style={styles.serviceCards}>
              {SERVICE_CARDS.map((card) => (
                <View key={card.title} style={styles.serviceCard}>
                  <View style={[styles.serviceIcon, { backgroundColor: card.bg }]}><Text style={[styles.serviceIconText, { color: card.color }]}>{card.symbol}</Text></View>
                  <Text style={styles.serviceCardTitle}>{card.title}</Text>
                  <Text style={styles.serviceCardSubtitle}>{card.subtitle}</Text>
                </View>
              ))}
            </View>
          </Animated.View>

          <View testID="journey-phase-reflection" style={styles.reflectionCard}>
            <Text style={styles.reflectionEyebrow}>21 天家庭复盘</Text>
            <Text style={styles.reflectionTitle}>{phaseCopy.title}</Text>
            <Text style={styles.reflectionText}>{phaseCopy.text}</Text>
            <Text style={styles.reflectionSource}>{remote?.process_summary?.label ?? "只记录家庭自己的观察和决定。"}</Text>
            <Text style={styles.reflectionBoundary}>记录的是家庭观察与决定，不是量化成绩或结果证明。</Text>
          </View>
            {reviewDue ? <View style={styles.reviewPanel}><Text style={styles.reviewTitle}>这一阶段可以回顾了</Text><Text style={styles.reviewText}>一起决定继续下一阶段，或先调整节奏。</Text>{reviewMessage ? <Text style={styles.reviewText}>{reviewMessage}</Text> : null}<View style={styles.reviewActions}><Pressable disabled={reviewState === "submitting"} onPress={() => reviewPhase("CONTINUE")} style={({ pressed }) => [styles.reviewPrimary, pressed && styles.pressed]}><Text style={styles.reviewPrimaryText}>{reviewState === "submitting" ? "正在记录" : "继续下一阶段"}</Text></Pressable><Pressable disabled={reviewState === "submitting"} onPress={() => reviewPhase("ADJUST")} style={({ pressed }) => [styles.reviewSecondary, pressed && styles.pressed]}><Text style={styles.reviewSecondaryText}>先调整节奏</Text></Pressable></View></View> : null}
        </ScrollView>
      </View>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FFFFFF" },
  content: { paddingBottom: 104 },
  topBar: { minHeight: 64, paddingHorizontal: 18, alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  backButton: { width: 36, alignItems: "flex-start" },
  topTitle: { color: "#20242A", fontSize: 19, lineHeight: 26, fontWeight: "800" },
  topActions: { width: 58, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  moreText: { color: "#20242A", fontSize: 17, lineHeight: 19, fontWeight: "900", letterSpacing: 1 },
  circleText: { color: "#20242A", fontSize: 25, lineHeight: 25 },
  serviceCardsTransition: { alignSelf: "center", width: "100%", minHeight: 211, marginTop: 1, paddingHorizontal: 19, paddingTop: 14, paddingBottom: 12, backgroundColor: "#F6FAFF" },
  serviceCards: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  serviceCard: { width: "48.5%", minHeight: 86, borderRadius: 16, paddingHorizontal: 13, paddingVertical: 13, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#EDF1F7", shadowColor: "#1867C9", shadowOpacity: 0.07, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 1 },
  serviceIcon: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center", marginBottom: 8 },
  serviceIconText: { fontSize: 13, lineHeight: 18, fontWeight: "900" },
  serviceCardTitle: { color: "#202A36", fontSize: 15, lineHeight: 20, fontWeight: "900" },
  serviceCardSubtitle: { color: "#7A8594", fontSize: 11, lineHeight: 16, fontWeight: "700", marginTop: 2 },
  syntheticBadge: { marginHorizontal: 19, marginTop: 4, color: "#8A5A00", fontSize: 10, lineHeight: 15, fontWeight: "900" },
  reflectionCard: { marginHorizontal: 19, marginTop: 12, padding: 17, backgroundColor: "#F7FBFF", borderRadius: 15, borderWidth: 1, borderColor: "#D9E8FA", gap: 7 },
  reflectionEyebrow: { color: "#2563EB", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  reflectionTitle: { color: "#1E2732", fontSize: 22, lineHeight: 29, fontWeight: "900" },
  reflectionText: { color: "#3D4F63", fontSize: 14, lineHeight: 22, fontWeight: "700" },
  reflectionSource: { color: "#6B7C8F", fontSize: 11, lineHeight: 17, fontWeight: "700" },
  reflectionBoundary: { color: "#6B7C8F", fontSize: 12, lineHeight: 18 },
  reviewPanel: { marginTop: 13, paddingTop: 12, borderTopWidth: 1, borderTopColor: "#EDF0F5", gap: 6 }, reviewTitle: { color: "#1E2732", fontSize: 14, lineHeight: 20, fontWeight: "900" }, reviewText: { color: "#697585", fontSize: 12, lineHeight: 17, fontWeight: "700" }, reviewActions: { flexDirection: "row", gap: 8, marginTop: 3 }, reviewPrimary: { flex: 1, minHeight: 36, borderRadius: 18, backgroundColor: "#247DF0", alignItems: "center", justifyContent: "center" }, reviewPrimaryText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" }, reviewSecondary: { flex: 1, minHeight: 36, borderRadius: 18, borderWidth: 1, borderColor: "#CFD8E4", alignItems: "center", justifyContent: "center" }, reviewSecondaryText: { color: "#596878", fontSize: 12, lineHeight: 17, fontWeight: "900" }, pressed: { opacity: 0.86, transform: [{ scale: 0.98 }] },
});
