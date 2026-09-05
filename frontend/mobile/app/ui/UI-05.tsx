import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Animated, Easing, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { familyApi, FamilyApiError } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import type { JourneyPlanProjection, ServiceJourneyProjection } from "@/lib/family/growth-api-contracts";
import type { ExperienceMediaKind, MultimodalDraftResponse, MultimodalFeedbackSignal } from "@/lib/family/multimodal-api-contracts";
import { haptic } from "@/lib/haptics";

const SERVICE_CARD_ACCESSIBILITY_LABEL = "家庭顾问、班主任陪跑、AI提醒和专家答疑";
const MEDIA_KINDS: ExperienceMediaKind[] = ["TEXT", "VOICE", "IMAGE", "AUDIO", "VIDEO", "INTERACTIVE_CARD"];
const SERVICE_CARDS = [
  { title: "家庭顾问", subtitle: "每周复盘", color: "#2F81F7", bg: "#EAF3FF", symbol: "顾" },
  { title: "班主任陪跑", subtitle: "过程提醒", color: "#18AE76", bg: "#EAF9F1", symbol: "陪" },
  { title: "AI提醒", subtitle: "打卡节奏", color: "#F5A11E", bg: "#FFF4DF", symbol: "AI" },
  { title: "专家答疑", subtitle: "重点问题", color: "#8B65D9", bg: "#F3EEFF", symbol: "答" },
] as const;

export default function CompanionJourneyScreen() {
  const session = useFamilyApiSession();
  const { activeOnboardingId } = useFamilyMobile();
  const [remote, setRemote] = useState<ServiceJourneyProjection | null>(null);
  const [journeyPlan, setJourneyPlan] = useState<JourneyPlanProjection | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ready" | "empty" | "denied" | "error">("idle");
  const [loadMessage, setLoadMessage] = useState<string | null>(null);
  const [reviewState, setReviewState] = useState<"idle" | "submitting">("idle");
  const [reviewOutcome, setReviewOutcome] = useState<"none" | "success" | "paused" | "error">("none");
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [experienceDraft, setExperienceDraft] = useState<MultimodalDraftResponse | null>(null);
  const [experienceDraftState, setExperienceDraftState] = useState<"idle" | "generating" | "ready" | "unavailable" | "error">("idle");
  const [experienceDraftMessage, setExperienceDraftMessage] = useState<string | null>(null);
  const [draftDecisionState, setDraftDecisionState] = useState<"idle" | "submitting" | "confirmed" | "rejected" | "error">("idle");
  const [draftDecisionMessage, setDraftDecisionMessage] = useState<string | null>(null);
  const [draftFeedbackState, setDraftFeedbackState] = useState<"idle" | "submitting" | "submitted" | "error">("idle");
  const [draftFeedbackMessage, setDraftFeedbackMessage] = useState<string | null>(null);
  const draftDecisionKeys = useRef<Record<string, string>>({});
  const serviceCardsOpacity = useRef(new Animated.Value(0.62)).current;
  const serviceCardsOffset = useRef(new Animated.Value(5)).current;
  const serviceCardsRevealed = useRef(false);
  const checkinScale = useRef(new Animated.Value(1)).current;
  const isRoutingToCheckin = useRef(false);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily || !activeOnboardingId) {
      setLoadState(activeOnboardingId ? "idle" : "empty");
      return;
    }
    let active = true;
    setLoadState("loading");
    setLoadMessage(null);
    Promise.all([
      familyApi.getServiceJourney<ServiceJourneyProjection>(session.token, session.selectedFamily.family_id, activeOnboardingId),
      familyApi.getJourneyPlan(session.token, session.selectedFamily.family_id),
    ])
      .then(([journey, plan]) => {
        if (!active) return;
        setRemote(journey);
        setJourneyPlan(plan);
        setLoadState("ready");
      })
      .catch((error: unknown) => {
        if (!active) return;
        const denied = error instanceof FamilyApiError && (error.status === 401 || error.status === 403 || error.code.includes("CONSENT"));
        setLoadState(denied ? "denied" : "error");
        setLoadMessage(denied ? "当前家庭授权或访问范围不允许读取陪跑记录。" : "暂时无法读取陪跑记录，请稍后重试。");
      });
    return () => { active = false; };
  }, [activeOnboardingId, session.selectedFamily, session.status, session.token]);

  const progress = useMemo(() => {
    const completed = Math.max(0, remote?.process_summary?.completed_actions ?? 0);
    const total = remote?.process_summary?.total_actions ?? null;
    return { completed, total, percentage: total && total > 0 ? Math.round((completed / total) * 100) : null };
  }, [remote]);
  const plan = journeyPlan?.plan;
  const reviewDue = plan?.phases?.find((phase) => phase.phase === plan.current_phase)?.status === "REVIEW_DUE";
  const connected = session.status === "connected" && !!session.token && !!session.selectedFamily;

  /** Request a server-owned, draft-only explanation; never fabricate a saved media record. */
  const requestExperienceDraft = async () => {
    if (!connected || !session.token || !session.selectedFamily || experienceDraftState === "generating") {
      if (!connected) {
        setExperienceDraftState("unavailable");
        setExperienceDraftMessage("连接家庭服务后，才能请求 AI 草稿。");
      }
      return;
    }
    const familyId = session.selectedFamily.family_id;
    const expression = remote?.process_summary?.label?.trim() || "家庭陪跑过程记录";
    setExperienceDraftState("generating");
    setExperienceDraftMessage(null);
    try {
      const draft = await familyApi.createMultimodalDraft(session.token, familyId, {
        run_id: `ui05-experience-${Date.now().toString(36)}`,
        prompt_version: "family-companion.v1",
        schema_version: "family-experience-draft.v1",
        payload: { expression },
        output_schema: {
          type: "object",
          properties: {
            understanding: { type: "string" },
            next_step: { type: "string" },
            limitations: { type: "array", items: { type: "string" } },
          },
        },
        modalities: ["TEXT"],
        estimated_input_tokens: Math.max(1, Math.ceil(expression.length / 4)),
        strategy: "balanced",
        input_refs: [],
        media_inputs: [],
        session_id: activeOnboardingId ?? undefined,
      }, `ui05-experience-${familyId}-${Date.now().toString(36)}`);
      setExperienceDraft(draft);
      setExperienceDraftState("ready");
    } catch (error) {
      const denied = error instanceof FamilyApiError && (error.status === 401 || error.status === 403 || error.code.includes("CONSENT"));
      setExperienceDraftState(denied ? "unavailable" : "error");
      setExperienceDraftMessage(denied ? "当前授权或访问范围不允许请求 AI 草稿。" : "AI 草稿暂时不可用，请稍后重试。");
    }
  };

  const decideExperienceDraft = async (decision: "confirm" | "reject") => {
    if (!connected || !session.token || !session.selectedFamily || !experienceDraft || draftDecisionState === "submitting") return;
    const familyId = session.selectedFamily.family_id;
    const keyRef = `${experienceDraft.run_id}:${decision}`;
    draftDecisionKeys.current[keyRef] ??= `ui05-experience-${decision}-${experienceDraft.run_id}`;
    setDraftDecisionState("submitting");
    setDraftDecisionMessage(null);
    try {
      await familyApi.decideMultimodalRun(session.token, familyId, experienceDraft.run_id, {
        decision,
        draft_version: experienceDraft.provenance.schema_version,
        ...(decision === "reject" ? { reason: "家长暂不采纳这份理解草稿" } : {}),
      }, draftDecisionKeys.current[keyRef]);
      setDraftDecisionState(decision === "confirm" ? "confirmed" : "rejected");
      setDraftDecisionMessage(decision === "confirm" ? "已记录人工确认；草稿不会自动写入家庭事实。" : "已记录退回；这份草稿不会进入家庭事实或任务记录。");
    } catch (error) {
      const denied = error instanceof FamilyApiError && (error.status === 401 || error.status === 403 || error.code.includes("CONSENT"));
      setDraftDecisionState("error");
      setDraftDecisionMessage(denied ? "当前授权或访问范围不允许提交人工决定。" : "人工决定暂时未保存，可安全重试。");
    }
  };

  const submitDraftFeedback = async (signal: MultimodalFeedbackSignal) => {
    if (!connected || !session.token || !session.selectedFamily || !experienceDraft || draftFeedbackState === "submitting") return;
    const familyId = session.selectedFamily.family_id;
    setDraftFeedbackState("submitting");
    setDraftFeedbackMessage(null);
    try {
      await familyApi.recordMultimodalFeedback(session.token, familyId, experienceDraft.run_id, {
        signal,
        draft_version: experienceDraft.provenance.schema_version,
        model_version: experienceDraft.provenance.model_version,
      }, `ui05-experience-feedback-${experienceDraft.run_id}-${signal}`);
      setDraftFeedbackState("submitted");
      setDraftFeedbackMessage(signal === "request_human" ? "已请求人工一起看，不会自动改变家庭记录。" : "已记录你的感受，后续建议会更贴近你的节奏。");
    } catch {
      setDraftFeedbackState("error");
      setDraftFeedbackMessage("反馈暂时未保存，可以稍后再试。");
    }
  };

  const reviewPhase = async (decision: "CONTINUE" | "ADJUST") => {
    if (reviewState === "submitting" || !plan?.plan_id || session.status !== "connected" || !session.token || !session.selectedFamily) return;
    setReviewState("submitting");
    setReviewOutcome("none");
    setReviewMessage(null);
    try {
      const result = await familyApi.reviewJourneyPhase(session.token, session.selectedFamily.family_id, plan.plan_id, decision, `ui05-review-${plan.plan_id}-${decision}`);
      setJourneyPlan(result);
      setReviewOutcome(decision === "CONTINUE" ? "success" : "paused");
      setReviewMessage(decision === "CONTINUE" ? "下一阶段已开始。" : "计划已暂缓，可先调整节奏。" );
    } catch {
      setReviewOutcome("error");
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
    const timer = setTimeout(revealServiceCards, 80);
    return () => clearTimeout(timer);
  }, [revealServiceCards]);

  const openCheckin = () => {
    if (isRoutingToCheckin.current) return;
    isRoutingToCheckin.current = true;
    haptic.light();
    Animated.sequence([
      Animated.timing(checkinScale, { toValue: 0.965, duration: 70, easing: Easing.out(Easing.quad), useNativeDriver: true }),
      Animated.timing(checkinScale, { toValue: 1, duration: 100, easing: Easing.out(Easing.quad), useNativeDriver: true }),
    ]).start(() => {
      router.push("/ui/UI-09" as Href);
      isRoutingToCheckin.current = false;
    });
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.screen}>
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.topBar}>
            <Pressable onPress={() => router.back()} hitSlop={10} style={styles.backButton}>
              <IconSymbol name="chevron.left" size={27} color="#222222" />
            </Pressable>
            <Text style={styles.topTitle}>陪跑服务</Text>
            <View style={styles.topActions}><Text style={styles.moreText}>•••</Text><Text style={styles.circleText}>⊙</Text></View>
          </View>

          <View style={styles.empathyCard} accessibilityRole="summary">
            <Text style={styles.empathyTitle}>今天也辛苦了，先一起走一步</Text>
            <Text style={styles.empathyText}>陪跑不是催促。你可以暂停、降频或从一个小行动重新开始，平台只记录真实发生的过程。</Text>
          </View>

          {loadState === "loading" ? <View style={styles.stateNotice}><Text style={styles.stateNoticeTitle}>正在读取家庭成长节奏</Text><Text style={styles.stateNoticeText}>请稍等，我们只展示服务端确认过的记录。</Text></View> : null}
          {loadState === "empty" ? <View style={styles.stateNotice}><Text style={styles.stateNoticeTitle}>还没有开始这段陪跑</Text><Text style={styles.stateNoticeText}>完成 UI-03 的家庭方向确认后，这里会出现真实的计划和可暂停的行动。</Text></View> : null}
          {loadState === "denied" ? <View style={styles.stateNotice}><Text style={styles.stateNoticeTitle}>暂时无法查看</Text><Text style={styles.stateNoticeText}>{loadMessage}</Text></View> : null}
          {loadState === "error" ? <View style={styles.errorNotice}><Text style={styles.errorNoticeTitle}>读取失败</Text><Text style={styles.errorNoticeText}>{loadMessage}</Text></View> : null}

          <View style={styles.mediaCard} accessibilityLabel="文字、语音、图片、音频、视频和互动卡记录能力">
            <Text style={styles.mediaTitle}>用你舒服的方式记录</Text>
            <Text style={styles.mediaText}>{MEDIA_KINDS.map((kind) => ({ TEXT: "文字", VOICE: "语音", IMAGE: "图片", AUDIO: "音频", VIDEO: "视频", INTERACTIVE_CARD: "互动卡" }[kind])).join(" · ")}</Text>
            <Text style={styles.mediaHint}>上传、转写、OCR 和播放都会先请求授权；低带宽或失败时保留重试与文字替代，不会伪造已保存内容。</Text>
            <Pressable accessibilityRole="button" disabled={!connected || experienceDraftState === "generating"} onPress={() => void requestExperienceDraft()} style={({ pressed }) => [styles.draftButton, (!connected || experienceDraftState === "generating") && styles.draftButtonDisabled, pressed && styles.pressed]}>
              <Text style={styles.draftButtonText}>{experienceDraftState === "generating" ? "正在请求 AI 草稿…" : connected ? "请求一份 AI 理解草稿" : "连接后请求 AI 草稿"}</Text>
            </Pressable>
            {experienceDraftState === "ready" && experienceDraft ? <View style={styles.draftNotice}>
              <Text style={styles.draftNoticeTitle}>AI 草稿（待人工确认）</Text>
              {typeof experienceDraft.output.understanding === "string" ? <Text style={styles.draftNoticeText}>{experienceDraft.output.understanding}</Text> : null}
              {typeof experienceDraft.output.next_step === "string" ? <Text style={styles.draftNoticeText}>下一步建议：{experienceDraft.output.next_step}</Text> : null}
              <Text style={styles.draftNoticeMeta}>草稿不会自动成为家庭事实或任务记录。</Text>
              {draftDecisionState === "idle" || draftDecisionState === "error" ? <View style={styles.draftDecisionActions}>
                <Pressable onPress={() => void decideExperienceDraft("confirm")} style={({ pressed }) => [styles.draftConfirmButton, pressed && styles.pressed]}><Text style={styles.draftConfirmText}>确认这份理解</Text></Pressable>
                <Pressable onPress={() => void decideExperienceDraft("reject")} style={({ pressed }) => [styles.draftRejectButton, pressed && styles.pressed]}><Text style={styles.draftRejectText}>退回草稿</Text></Pressable>
              </View> : null}
              {draftDecisionMessage ? <Text style={styles.draftNoticeMeta}>{draftDecisionMessage}</Text> : null}
              <View style={styles.feedbackBlock}>
                <Text style={styles.draftNoticeMeta}>这份理解对你有帮助吗？</Text>
                <View style={styles.feedbackActions}>
                  {(["helpful", "not_helpful", "request_human"] as const).map((signal) => (
                    <Pressable key={signal} accessibilityRole="button" accessibilityLabel={{ helpful: "反馈有帮助", not_helpful: "反馈没帮助", request_human: "请求人工查看" }[signal]} disabled={draftFeedbackState === "submitting" || draftFeedbackState === "submitted"} onPress={() => void submitDraftFeedback(signal)} style={({ pressed }) => [styles.feedbackButton, draftFeedbackState === "submitted" && styles.feedbackButtonDisabled, pressed && styles.pressed]}>
                      <Text style={styles.feedbackButtonText}>{signal === "helpful" ? "有帮助" : signal === "not_helpful" ? "没帮助" : "请人工看"}</Text>
                    </Pressable>
                  ))}
                </View>
                {draftFeedbackMessage ? <Text style={styles.draftNoticeMeta}>{draftFeedbackMessage}</Text> : null}
              </View>
            </View> : null}
            {experienceDraftMessage ? <Text style={styles.draftNoticeText}>{experienceDraftMessage}</Text> : null}
          </View>

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

          <View style={styles.progressCard}>
            <View style={styles.progressHeadline}>
              <Text style={styles.progressTitle}>本周完成度</Text>
              <Text style={styles.progressCount}>{progress.total ? `本周任务　${progress.completed}/${progress.total}` : remote ? `已记录 ${progress.completed} 项过程` : "等待真实过程记录"}</Text>
            </View>
            <View style={styles.progressValueRow}>
              <Text style={styles.progressValue}>{progress.percentage ?? "—"}</Text>{progress.percentage !== null ? <Text style={styles.progressPercent}>%</Text> : null}
              <View style={styles.progressCopy}><Text style={styles.progressCaption}>{remote?.process_summary?.label ?? "本周家庭过程记录"}</Text><View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${progress.percentage ?? 0}%` }]} /></View></View>
            </View>
            <View style={styles.weeklyList}>
              {remote?.weekly_tasks?.length ? remote.weekly_tasks.map((task) => <WeeklyTaskLine key={task.task_id} text={task.title} status={task.status} />) : <Text style={styles.emptyTaskText}>阶段行动将在方案确认后显示；这里不会预填完成状态。</Text>}
            </View>
            {reviewDue ? <View style={styles.reviewPanel}><Text style={styles.reviewTitle}>这一阶段可以回顾了</Text><Text style={styles.reviewText}>一起决定继续下一阶段，或先调整节奏。</Text>{reviewMessage ? <Text style={[styles.reviewText, reviewOutcome === "error" && styles.reviewError]}>{reviewMessage}</Text> : null}<View style={styles.reviewActions}><Pressable disabled={reviewState === "submitting"} onPress={() => reviewPhase("CONTINUE")} style={({ pressed }) => [styles.reviewPrimary, pressed && styles.pressed]}><Text style={styles.reviewPrimaryText}>{reviewState === "submitting" ? "正在记录" : "继续下一阶段"}</Text></Pressable><Pressable disabled={reviewState === "submitting"} onPress={() => reviewPhase("ADJUST")} style={({ pressed }) => [styles.reviewSecondary, pressed && styles.pressed]}><Text style={styles.reviewSecondaryText}>先调整节奏</Text></Pressable></View></View> : null}
          </View>

          <View style={styles.segmentBar}>
            <View style={[styles.segmentItem, styles.segmentActive]}><Text style={styles.segmentTextActive}>成长打卡</Text></View>
            <View style={styles.segmentItem}><Text style={styles.segmentText}>家长交流</Text></View>
            <View style={styles.segmentItem}><Text style={styles.segmentText}>本周直播</Text></View>
          </View>

          <View style={styles.feedCard}>
            <View style={styles.feedHeader}><View style={[styles.avatar, { backgroundColor: "#F7D9CF" }]}><Text style={styles.avatarText}>家</Text></View><View style={styles.feedAuthor}><Text style={styles.feedName}>家庭过程记录</Text><Text style={styles.feedTime}>仅展示已确认内容</Text></View></View>
            <Text style={styles.feedText}>当家庭完成一个真实行动后，这里会留下可回看的过程记录。</Text>
            <View style={styles.feedMeta}><Text style={styles.feedMetaText}>家庭私有记录</Text><Text style={styles.feedMetaText}>等待真实行动</Text></View>
          </View>

          <View style={[styles.feedCard, styles.secondFeed]}>
            <View style={styles.feedHeader}><View style={[styles.avatar, { backgroundColor: "#DFE9F7" }]}><Text style={styles.avatarText}>暖</Text></View><View style={styles.feedAuthor}><Text style={styles.feedName}>一起慢慢来</Text><Text style={styles.feedTime}>可暂停、可恢复</Text></View></View>
            <Text style={styles.feedText}>你可以在合适的时候继续，不需要为了连续记录勉强自己。</Text>
            <View style={styles.feedMeta}><Text style={styles.feedMetaText}>家庭私有记录</Text><Text style={styles.feedMetaText}>不构成成长结果</Text></View>
          </View>
        </ScrollView>

        <Animated.View style={{ transform: [{ scale: checkinScale }] }}>
          <Pressable accessibilityLabel="打卡" onPress={openCheckin} style={({ pressed }) => [styles.fab, pressed && styles.pressed]}>
            <Text style={styles.fabPlus}>＋</Text><Text style={styles.fabText}>打卡</Text>
          </Pressable>
        </Animated.View>
      </View>
    </ScreenContainer>
  );
}

function WeeklyTaskLine({ text, status }: { text: string; status: "PENDING" | "IN_PROGRESS" | "COMPLETED" | "PAUSED" | "CANCELLED" }) {
  const done = status === "COMPLETED";
  return <View style={styles.weeklyTaskLine}><Text style={styles.weeklyTaskText}>{text}</Text>{done ? <IconSymbol name="checkmark.circle.fill" size={19} color="#1DB875" /> : <View style={styles.emptyCheck} />}</View>;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FFFFFF" },
  content: { paddingBottom: 104 },
  empathyCard: { marginHorizontal: 19, marginTop: 8, borderRadius: 16, backgroundColor: "#FFF7EE", borderWidth: 1, borderColor: "#F5D5B8", padding: 14, gap: 4 },
  empathyTitle: { color: "#8A4B00", fontSize: 15, lineHeight: 21, fontWeight: "900" },
  empathyText: { color: "#6F532B", fontSize: 13, lineHeight: 19, fontWeight: "700" },
  stateNotice: { marginHorizontal: 19, marginTop: 10, borderRadius: 14, backgroundColor: "#F4F8FF", borderWidth: 1, borderColor: "#D7E7FA", padding: 13, gap: 4 },
  stateNoticeTitle: { color: "#2D5C92", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  stateNoticeText: { color: "#58708E", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  errorNotice: { marginHorizontal: 19, marginTop: 10, borderRadius: 14, backgroundColor: "#FFF1F0", borderWidth: 1, borderColor: "#F2B8B5", padding: 13, gap: 4 },
  errorNoticeTitle: { color: "#A33A35", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  errorNoticeText: { color: "#7E4D4A", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  mediaCard: { marginHorizontal: 19, marginTop: 10, borderRadius: 14, backgroundColor: "#F8FAFC", borderWidth: 1, borderColor: "#E3EAF2", padding: 13, gap: 4 },
  mediaTitle: { color: "#344054", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  mediaText: { color: "#476A92", fontSize: 12, lineHeight: 18, fontWeight: "800" },
  mediaHint: { color: "#68727D", fontSize: 11, lineHeight: 16, fontWeight: "700" },
  draftButton: { minHeight: 38, borderRadius: 19, borderWidth: 1, borderColor: "#247DF0", alignItems: "center", justifyContent: "center", marginTop: 7, paddingHorizontal: 12 },
  draftButtonDisabled: { opacity: 0.5 },
  draftButtonText: { color: "#247DF0", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  draftNotice: { marginTop: 7, borderRadius: 10, backgroundColor: "#EEF6FF", borderWidth: 1, borderColor: "#C9E0FA", padding: 10, gap: 3 },
  draftNoticeTitle: { color: "#164B8A", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  draftNoticeText: { color: "#476A92", fontSize: 11, lineHeight: 16, fontWeight: "700" },
  draftNoticeMeta: { color: "#718096", fontSize: 10, lineHeight: 15, fontWeight: "700" },
  draftDecisionActions: { flexDirection: "row", gap: 8, marginTop: 6 },
  draftConfirmButton: { flex: 1, minHeight: 34, borderRadius: 17, backgroundColor: "#247DF0", alignItems: "center", justifyContent: "center" },
  draftConfirmText: { color: "#FFFFFF", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  draftRejectButton: { flex: 1, minHeight: 34, borderRadius: 17, borderWidth: 1, borderColor: "#CFD8E4", alignItems: "center", justifyContent: "center" },
  draftRejectText: { color: "#596878", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  feedbackBlock: { marginTop: 5, gap: 4 },
  feedbackActions: { flexDirection: "row", gap: 6 },
  feedbackButton: { flex: 1, minHeight: 30, borderRadius: 15, borderWidth: 1, borderColor: "#B8D4F4", alignItems: "center", justifyContent: "center", paddingHorizontal: 5 },
  feedbackButtonDisabled: { opacity: 0.55 },
  feedbackButtonText: { color: "#2D6FB8", fontSize: 10, lineHeight: 14, fontWeight: "900" },
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
  progressCard: { marginHorizontal: 19, marginTop: 8, padding: 17, backgroundColor: "#FFFFFF", borderRadius: 15, borderWidth: 1, borderColor: "#EDF0F5" },
  progressHeadline: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  progressTitle: { color: "#1E2732", fontSize: 16, lineHeight: 22, fontWeight: "900" },
  progressCount: { color: "#697585", fontSize: 12, lineHeight: 17, fontWeight: "700" },
  progressValueRow: { flexDirection: "row", alignItems: "flex-end", marginTop: 9 },
  progressValue: { color: "#237CF2", fontSize: 47, lineHeight: 51, fontWeight: "900" },
  progressPercent: { color: "#222B36", fontSize: 25, lineHeight: 32, fontWeight: "700", marginBottom: 5, marginLeft: 2 },
  progressCopy: { flex: 1, marginLeft: 15, marginBottom: 8, gap: 9 },
  progressCaption: { color: "#9AA4B3", fontSize: 11, lineHeight: 15 },
  progressTrack: { height: 5, flex: 1, backgroundColor: "#E6EAF0", borderRadius: 5, overflow: "hidden" },
  progressFill: { height: 5, backgroundColor: "#227CFA", borderRadius: 5 },
  weeklyList: { marginTop: 12, gap: 11 },
  emptyTaskText: { color: "#7A8594", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  weeklyTaskLine: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  weeklyTaskText: { color: "#566272", fontSize: 13, lineHeight: 19, fontWeight: "600" },
  emptyCheck: { width: 18, height: 18, borderRadius: 9, borderColor: "#3A88F5", borderWidth: 1.5 },
  segmentBar: { minHeight: 50, marginTop: 14, flexDirection: "row", borderTopWidth: 1, borderBottomWidth: 1, borderColor: "#F1F2F5" },
  segmentItem: { flex: 1, alignItems: "center", justifyContent: "center", paddingTop: 2 },
  segmentActive: { borderBottomWidth: 3, borderBottomColor: "#257CF2" },
  segmentTextActive: { color: "#287CED", fontSize: 15, lineHeight: 21, fontWeight: "900" },
  segmentText: { color: "#343D48", fontSize: 15, lineHeight: 21, fontWeight: "700" },
  feedCard: { paddingHorizontal: 20, paddingTop: 18, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: "#EDF0F3" },
  secondFeed: { paddingTop: 17 },
  feedHeader: { flexDirection: "row", alignItems: "center" },
  avatar: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  avatarText: { color: "#385067", fontSize: 17, lineHeight: 23, fontWeight: "800" },
  feedAuthor: { flex: 1, marginLeft: 10, gap: 1 },
  feedName: { color: "#2B3440", fontSize: 14, lineHeight: 19, fontWeight: "800" },
  feedTime: { color: "#A0A8B4", fontSize: 11, lineHeight: 15 },
  checkedPill: { borderRadius: 13, borderWidth: 1, borderColor: "#A9E4C5", paddingHorizontal: 9, paddingTop: 3, paddingBottom: 3 },
  checkedPillText: { color: "#2CB37B", fontSize: 12, lineHeight: 16, fontWeight: "800" },
  feedText: { color: "#394553", fontSize: 15, lineHeight: 24, fontWeight: "600", marginTop: 12 },
  feedMeta: { flexDirection: "row", justifyContent: "flex-end", gap: 20, marginTop: 10 },
  feedMetaText: { color: "#8E98A4", fontSize: 13, lineHeight: 18 },
  fab: { position: "absolute", right: 20, bottom: 20, minWidth: 105, minHeight: 49, borderRadius: 25, backgroundColor: "#247DF0", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 3, shadowColor: "#1C74DE", shadowOpacity: 0.24, shadowRadius: 9, shadowOffset: { width: 0, height: 4 }, elevation: 4 },
  fabPlus: { color: "#FFFFFF", fontSize: 25, lineHeight: 29, fontWeight: "500" },
  fabText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" },
  reviewPanel: { marginTop: 13, paddingTop: 12, borderTopWidth: 1, borderTopColor: "#EDF0F5", gap: 6 }, reviewTitle: { color: "#1E2732", fontSize: 14, lineHeight: 20, fontWeight: "900" }, reviewText: { color: "#697585", fontSize: 12, lineHeight: 17, fontWeight: "700" }, reviewError: { color: "#A33A35" }, reviewActions: { flexDirection: "row", gap: 8, marginTop: 3 }, reviewPrimary: { flex: 1, minHeight: 36, borderRadius: 18, backgroundColor: "#247DF0", alignItems: "center", justifyContent: "center" }, reviewPrimaryText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" }, reviewSecondary: { flex: 1, minHeight: 36, borderRadius: 18, borderWidth: 1, borderColor: "#CFD8E4", alignItems: "center", justifyContent: "center" }, reviewSecondaryText: { color: "#596878", fontSize: 12, lineHeight: 17, fontWeight: "900" }, pressed: { opacity: 0.86, transform: [{ scale: 0.98 }] },
});
