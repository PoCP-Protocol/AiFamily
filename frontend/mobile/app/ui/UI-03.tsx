import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import type { Ui03GrowthHypothesisProjection } from "@/lib/family/assessment-api-contracts";
import { createMobileRequestId, familyApi, FamilyApiError } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

export default function GrowthExplanationScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { activeOnboardingId, setActiveOnboardingId } = useFamilyMobile();
  const [remote, setRemote] = useState<Ui03GrowthHypothesisProjection | null>(null);
  const [remoteState, setRemoteState] = useState<"idle" | "loading" | "generating" | "ready" | "empty" | "denied" | "review_required" | "error">("idle");
  const [decisionState, setDecisionState] = useState<"idle" | "saving" | "error" | "denied" | "review_required" | "success">("idle");
  const [remoteError, setRemoteError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const decisionKeys = useRef<Record<string, string>>({});
  const generateKeys = useRef<Record<string, string>>({});
  const onboardingKeys = useRef<Record<string, string>>({});
  const hypothesis = remote?.hypothesis ?? null;
  const supportDraft = hypothesis?.scorecard ?? null;
  const safetyGateRequired = hypothesis?.safety_gate?.required === true;
  const named_actions = remote?.named_actions ?? { generate: "GENERATE_GROWTH_HYPOTHESIS" as const, confirm: "CONFIRM_GROWTH_HYPOTHESIS" as const };

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) { setRemoteState("idle"); return; }
    const token = session.token;
    const familyId = session.selectedFamily.family_id;
    let active = true;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    const load = async (): Promise<void> => {
      const result = await familyApi.getGrowthHypothesis(token, familyId);
      if (!active) return;
      setRemote(result);
      if (result.availability === "CONSENT_REQUIRED" || result.availability === "CONSENT_WITHDRAWN" || result.availability === "POLICY_BLOCKED") { setRemoteState("denied"); return; }
      if (result.availability === "NO_SUBMITTED_ASSESSMENT") { setRemoteState("empty"); return; }
      if (result.availability === "SUBMITTED" || result.availability === "ANALYSIS_FAILED") {
        const sessionId = result.latest_assessment_session_id;
        if (!sessionId) { setRemoteState("ready"); return; }
        setRemoteState("generating");
        const fingerprint = `${sessionId}:GENERATE`;
        generateKeys.current[fingerprint] ??= `generate-${sessionId}-${Date.now().toString(36)}`;
        try {
          await familyApi.generateGrowthHypothesis(token, familyId, sessionId, generateKeys.current[fingerprint]);
          if (active) await load();
        } catch {
          if (active) { setRemoteState("error"); setRemoteError("支持方向暂时没有生成成功，请稍后重试。"); }
        }
        return;
      }
      if (result.availability === "ANALYZING") {
        setRemoteState("generating");
        pollTimer = setTimeout(() => { if (active) void load(); }, 1500);
        return;
      }
      setRemoteState(result.hypothesis?.safety_gate?.required ? "review_required" : "ready");
    };

    setRemoteState("loading");
    setRemoteError(null);
    void load().catch(() => { if (active) { setRemoteState("error"); setRemoteError("暂时无法读取这次家庭解读，请稍后重试。"); } });
    return () => { active = false; if (pollTimer) clearTimeout(pollTimer); };
  }, [session.selectedFamily, session.status, session.token]);

  const ensureActiveOnboarding = async (token: string, familyId: string, guardianPersonId: string, childId: string) => {
    if (activeOnboardingId) return;
    const fingerprint = `${familyId}:${childId}:START_ONBOARDING`;
    onboardingKeys.current[fingerprint] ??= createMobileRequestId("ui03-start-onboarding");
    try {
      const result = await familyApi.startGrowthOnboarding<{ onboarding: { onboarding_id: string } }>(token, familyId, {
        childId,
        guardianPersonId,
        structuredSafetySignals: ["NONE"],
      }, onboardingKeys.current[fingerprint]);
      setActiveOnboardingId(result.onboarding.onboarding_id);
    } catch (error) {
      if (error instanceof FamilyApiError && error.code.includes("growth_onboarding_already_active")) {
        const active = await familyApi.getActiveOnboarding(token, familyId);
        if (active?.onboarding_id) setActiveOnboardingId(active.onboarding_id);
        return;
      }
      // Onboarding-start 失败（如缺少必要同意、生命阶段不支持）不阻塞成长意向确认；
      // UI-04 会在缺少 activeOnboardingId 时引导用户回到 UI-02 补齐前置条件。
    }
  };

  const generatePlan = async () => {
    if (confirmed) { router.push("/ui/UI-04" as Href); return; }
    if (session.status !== "connected" || !session.token || !session.selectedFamily || !hypothesis) { router.replace("/ui/UI-02" as Href); return; }
    if (safetyGateRequired) {
      setDecisionState("review_required");
      return;
    }
    if (named_actions.confirm !== "CONFIRM_GROWTH_HYPOTHESIS") {
      setDecisionState("error");
      return;
    }
    const fingerprint = `${hypothesis.hypothesis_ref}:CONFIRM`;
    decisionKeys.current[fingerprint] ??= `confirm-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
    setDecisionState("saving");
    try {
      const result = await familyApi.decideGrowthHypothesis(session.token, session.selectedFamily.family_id, {
        assessment_session_id: hypothesis.source_refs.assessment_session_id,
        hypothesis_ref: hypothesis.hypothesis_ref,
        decision_type: "CONFIRM",
      }, decisionKeys.current[fingerprint]);
      if (result.outcome === "INTENT_CREATED") {
        await ensureActiveOnboarding(session.token, session.selectedFamily.family_id, session.selectedFamily.person_id, hypothesis.subject_person_id);
        setDecisionState("success");
        setConfirmed(true);
        router.push("/ui/UI-04" as Href);
        return;
      }
      setDecisionState("idle");
    } catch { setDecisionState("error"); }
  };

  if (remoteState === "loading" || remoteState === "generating") {
    return (
      <ScreenContainer edges={["left", "right", "bottom"]}>
        <Stack.Screen options={{ headerShown: true, title: "AI成长诊断", headerBackTitle: "返回" }} />
        <View style={styles.emptyPage}>
          <ActivityIndicator color={colors.tint} />
          <Text style={[styles.emptyTitle, { color: colors.text }]}>AI 正在生成成长诊断报告</Text>
          <Text style={[styles.emptyText, { color: colors.muted }]}>AI 会基于你提交的免费测评生成成长诊断报告；这不是儿童诊断结论、能力测验或排名。</Text>
        </View>
      </ScreenContainer>
    );
  }

  const isPreview = !hypothesis || !supportDraft;
  const consentWithdrawn = remote?.availability === "CONSENT_WITHDRAWN";
  const denied = remoteState === "denied" || remote?.availability === "POLICY_BLOCKED" || consentWithdrawn;
  const reviewRequired = remoteState === "review_required" || safetyGateRequired || decisionState === "review_required";
  const evidenceCoverage = hypothesis?.evidence_coverage ?? null;
  const aiState = remote?.ai_state ?? "NOT_INVOKED";
  const submittedAt = formatDate(hypothesis?.source_refs.assessment_submitted_at);
  const summaryRows = [
    hypothesis?.subject_display_name ? `姓名：${hypothesis.subject_display_name}` : null,
    submittedAt ? `测评时间：${submittedAt}` : null,
    hypothesis?.source_refs.tool_version ? `测评版本：v${hypothesis.source_refs.tool_version}` : "先完成免费家庭测评",
    isPreview ? "完成后生成家庭支持方向" : `AI状态：${formatAiState(aiState)}`,
  ].filter(Boolean);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen
        options={{
          headerShown: true,
          title: "AI成长诊断",
          headerBackTitle: "返回",
          headerRight: () => <IconSymbol name="ellipsis" size={24} color="#111827" />,
        }}
      />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.empathyCard} accessibilityRole="summary">
          <Text style={styles.empathyTitle}>先接住这份无奈和疲惫</Text>
          <Text style={styles.empathyText}>你不需要一次解决所有问题。我们先一起看清一个可讨论的方向，再决定今晚要不要做一个小行动。</Text>
        </View>
        {isPreview ? <View style={styles.previewNotice}><Text style={styles.previewNoticeTitle}>{denied ? "暂时不能展示这次解读" : remoteState === "empty" ? "还没有提交的家庭测评" : "先完成免费家庭测评"}</Text><Text style={styles.previewNoticeText}>{denied ? (consentWithdrawn ? "根据你的授权选择，系统已停止展示这次测评和 AI 分析内容。如需继续，请重新确认测评授权。" : "当前家庭权限或平台策略不允许读取这次解读，请联系家庭管理员或人工支持。") : remoteState === "empty" ? "完成并提交一次家庭测评后，系统才会基于真实回答整理支持方向。" : "AI 会基于你提交的免费测评生成支持方向；这不是儿童诊断结论、能力测验或排名。"}</Text></View> : null}
        {remoteState === "error" ? <View style={styles.errorNotice}><Text style={styles.errorNoticeTitle}>读取失败</Text><Text style={styles.errorNoticeText}>{remoteError ?? "暂时无法读取这次家庭解读，请稍后重试。"}</Text></View> : null}
        <View style={styles.assessmentSummary}>
          <View style={styles.summaryAvatar}><IconSymbol name="person.crop.circle.fill" size={58} color="#2563EB" /></View>
          <View style={styles.summaryCopy}>
            <Text style={styles.summaryBadge}>{isPreview ? "测评后生成" : "AI成长诊断报告"}</Text>
            <Text style={styles.summaryTitle}>{isPreview ? "家庭成长诊断预览" : hypothesis.subject_display_name ? `${hypothesis.subject_display_name}的成长诊断` : "家庭成长诊断"}</Text>
            {summaryRows.map((row) => <Text key={row} style={styles.summaryMeta}>{row}</Text>)}
          </View>
          <IconSymbol name="chevron.right" size={19} color="#536A8B" />
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>证据与支持方向</Text>
        {!supportDraft ? <View style={styles.supportEmpty}><Text style={styles.supportEmptyTitle}>完成测评后显示支持方向</Text><Text style={styles.supportEmptyText}>这里不会预填家庭分数，也不会替家庭或孩子下诊断结论。</Text></View> : null}

        {supportDraft ? <>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>核心问题</Text>
          <View style={styles.tags}>
            {supportDraft.core_issue_tags.slice(0, 3).map((tag, index) => (
              <View key={tag} style={[styles.tag, { backgroundColor: tagColors[index].background }]}>
                <Text style={[styles.tagText, { color: tagColors[index].text }]}>{tag}</Text>
              </View>
            ))}
          </View>
        </> : null}

        {evidenceCoverage ? <>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>证据覆盖度</Text>
          <View style={styles.evidenceCard}>
            <Text style={styles.evidenceHeadline}>{Math.round(evidenceCoverage.coverage_ratio * 100)}% 已纳入结构化解读</Text>
            <Text style={styles.evidenceMeta}>已解释 {evidenceCoverage.interpreted_response_count} / {evidenceCoverage.source_response_count} 项回答</Text>
            {evidenceCoverage.uninterpreted_item_refs.length > 0 ? <Text style={styles.evidenceWarning}>仍有 {evidenceCoverage.uninterpreted_item_refs.length} 项未纳入当前解读</Text> : null}
            {evidenceCoverage.uncertainty_reasons.map((reason) => <Text key={reason} style={styles.evidenceWarning}>{reason}</Text>)}
          </View>
          {evidenceCoverage.evidence_summaries.length > 0 ? <View style={styles.evidenceCard}>
            <Text style={styles.evidenceHeadline}>本次分析依据</Text>
            {evidenceCoverage.evidence_summaries.slice(0, 3).map((summary) => <Text key={summary} style={styles.evidenceMeta}>• {summary}</Text>)}
          </View> : null}
          {evidenceCoverage.next_questions && evidenceCoverage.next_questions.length > 0 ? <View style={styles.questionCard}>
            <Text style={styles.questionCardTitle}>如果你愿意，可以继续补充</Text>
            {evidenceCoverage.next_questions.map((question) => <Text key={question} style={styles.questionCardText}>• {question}</Text>)}
          </View> : null}
        </> : null}

        {supportDraft ? <>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>成长建议</Text>
          <View style={styles.suggestions}>
            {supportDraft.recommendations.slice(0, 3).map((item, index) => (
              <View key={`${index}-${item}`} style={styles.suggestionRow}>
                <View style={styles.suggestionIndex}><Text style={styles.suggestionIndexText}>{index + 1}</Text></View>
                <Text style={[styles.suggestionText, { color: colors.text }]}>{item}</Text>
              </View>
            ))}
          </View>
        </> : null}

        {evidenceCoverage && evidenceCoverage.support_direction_labels.length > 0 ? <>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>支持方向</Text>
          <View style={styles.directionCard}>
            {evidenceCoverage.support_direction_labels.slice(0, 3).map((label) => <Text key={label} style={[styles.directionText, { color: colors.text }]}>• {label}</Text>)}
          </View>
        </> : null}

        {decisionState === "error" ? <Text style={[styles.errorText, { color: "#D96464" }]}>支持方案暂时未形成，请稍后重试。</Text> : null}
        {reviewRequired ? <View style={styles.safetyNotice}>
          <Text style={styles.safetyNoticeTitle}>需要人工复核</Text>
          <Text style={styles.safetyNoticeText}>这次测评出现了需要谨慎理解的健康或家庭压力信号。AI 不会直接生成成长方案，请联系专业人工支持进一步判断。</Text>
        </View> : null}
        <Pressable disabled={decisionState === "saving" || denied || remoteState === "error" || reviewRequired} onPress={() => void generatePlan()} style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.tint }, (pressed || denied || remoteState === "error" || reviewRequired) && styles.disabledButton]}>
          <IconSymbol name="star.fill" size={18} color="#FFFFFF" />
          <Text style={styles.primaryButtonText}>{decisionState === "saving" ? "正在生成" : reviewRequired ? "等待人工复核" : denied ? "暂不可用" : remoteState === "empty" ? "去完成家庭测评" : isPreview ? "进入免费测评" : "生成个性化方案"}</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.deferButton}><Text style={[styles.deferText, { color: colors.muted }]}>先放一放，稍后再继续</Text></Pressable>
        <Text style={[styles.boundaryText, { color: colors.muted }]}>以上内容用于家庭支持参考，不是儿童诊断结论、能力测验或排名。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatAiState(value: Ui03GrowthHypothesisProjection["ai_state"]) {
  if (value === "MODEL_DRAFT_READY") return "模型草稿已生成";
  if (value === "MODEL_GATEWAY_BLOCKED") return "模型网关已拦截";
  if (value === "READ_ONLY_PERSISTED") return "已读取历史草稿";
  return "尚未调用模型";
}

const tagColors = [
  { background: "#FDEBEC", text: "#D96464" },
  { background: "#EEF2FF", text: "#5B6FEF" },
  { background: "#FFF3E5", text: "#B87530" },
] as const;

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 34, gap: 16, backgroundColor: "#FFFFFF" },
  empathyCard: { borderRadius: 16, backgroundColor: "#FFF7EE", borderWidth: 1, borderColor: "#F5D5B8", padding: 14, gap: 4 },
  empathyTitle: { color: "#8A4B00", fontSize: 15, lineHeight: 21, fontWeight: "900" },
  empathyText: { color: "#6F532B", fontSize: 13, lineHeight: 19, fontWeight: "700" },
  errorNotice: { borderRadius: 16, backgroundColor: "#FFF1F0", borderWidth: 1, borderColor: "#F2B8B5", padding: 14, gap: 4 },
  errorNoticeTitle: { color: "#A33A35", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  errorNoticeText: { color: "#7E4D4A", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  supportEmpty: { minHeight: 154, borderRadius: 16, backgroundColor: "#F8FAFC", borderWidth: 1, borderColor: "#E3EAF2", padding: 18, justifyContent: "center", gap: 7 },
  supportEmptyTitle: { color: "#344054", fontSize: 16, lineHeight: 22, fontWeight: "900", textAlign: "center" },
  supportEmptyText: { color: "#68727D", fontSize: 12, lineHeight: 18, fontWeight: "700", textAlign: "center" },
  safetyNotice: { borderRadius: 16, backgroundColor: "#FFF4E5", borderWidth: 1, borderColor: "#F3C879", padding: 14, gap: 4 },
  safetyNoticeTitle: { color: "#8A4B00", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  safetyNoticeText: { color: "#6F532B", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  emptyPage: { flex: 1, padding: 24, justifyContent: "center", gap: 16 },
  emptyTitle: { fontSize: 29, lineHeight: 37, fontWeight: "800" },
  emptyText: { fontSize: 15, lineHeight: 23 },
  previewNotice: { borderRadius: 16, backgroundColor: "#FFF6DF", borderWidth: 1, borderColor: "#F8DE94", padding: 14, gap: 4 },
  previewNoticeTitle: { color: "#8A5A00", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  previewNoticeText: { color: "#6F5A36", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  assessmentSummary: { minHeight: 138, borderRadius: 16, backgroundColor: "#E8F2FF", padding: 16, flexDirection: "row", alignItems: "center", gap: 12, shadowColor: "#B9DCFF", shadowOpacity: 0.18, shadowRadius: 18, shadowOffset: { width: 0, height: 10 }, elevation: 4 },
  summaryAvatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  summaryCopy: { flex: 1, gap: 4 },
  summaryBadge: { alignSelf: "flex-start", overflow: "hidden", borderRadius: 10, paddingHorizontal: 8, paddingVertical: 3, backgroundColor: "#FFFFFF80", color: "#2563EB", fontSize: 11, lineHeight: 15, fontWeight: "800" },
  summaryTitle: { color: "#09295A", fontSize: 18, lineHeight: 24, fontWeight: "800" },
  summaryMeta: { color: "#5B7091", fontSize: 12, lineHeight: 17, fontWeight: "700" },
  sectionTitle: { fontSize: 18, lineHeight: 25, fontWeight: "800" },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  tag: { borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6 },
  tagText: { fontSize: 12, lineHeight: 17, fontWeight: "700" },
  evidenceCard: { borderRadius: 14, backgroundColor: "#F5F9FF", borderWidth: 1, borderColor: "#D9E8FA", padding: 14, gap: 5 },
  evidenceHeadline: { color: "#164B8A", fontSize: 16, lineHeight: 22, fontWeight: "900" },
  evidenceMeta: { color: "#5B7091", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  evidenceWarning: { color: "#8A5A00", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  suggestions: { gap: 12 },
  suggestionRow: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  suggestionIndex: { width: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center", marginTop: 1, backgroundColor: "#EAF0FF" },
  suggestionIndexText: { fontSize: 12, lineHeight: 17, fontWeight: "800", color: "#2F8FFB" },
  suggestionText: { flex: 1, fontSize: 14, lineHeight: 22 },
  directionCard: { borderRadius: 14, backgroundColor: "#F7FBF8", borderWidth: 1, borderColor: "#D8EBDD", padding: 14, gap: 8 },
  directionText: { fontSize: 13, lineHeight: 20, fontWeight: "700" },
  questionCard: { borderRadius: 14, backgroundColor: "#FFF9EC", borderWidth: 1, borderColor: "#F4DEAA", padding: 14, gap: 5 },
  questionCardTitle: { color: "#8A5A00", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  questionCardText: { color: "#6F5A36", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  errorText: { fontSize: 12, lineHeight: 18, textAlign: "center" },
  primaryButton: { minHeight: 52, borderRadius: 26, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7, marginTop: 2 },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "800" },
  disabledButton: { opacity: 0.5 },
  deferButton: { minHeight: 44, alignItems: "center", justifyContent: "center" },
  deferText: { fontSize: 13, lineHeight: 18, fontWeight: "700" },
  boundaryText: { marginTop: -6, fontSize: 11, lineHeight: 17, textAlign: "center" },
  pressed: { opacity: 0.84, transform: [{ scale: 0.985 }] },
});
