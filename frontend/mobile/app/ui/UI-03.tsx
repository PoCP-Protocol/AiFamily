import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import Svg, { Circle, Line, Polygon, Text as SvgText } from "react-native-svg";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { createMobileRequestId, familyApi, FamilyApiError } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

interface Ui03ScoreDimension {
  dimension_ref: string;
  label: string;
  score: number;
  peer_reference: number;
}

interface Ui03Scorecard {
  generated_by: "FAMILI_PRINCIPAL_FAMILY_EDUCATION_MODEL";
  overall_score: number;
  overall_band: string;
  dimensions: Ui03ScoreDimension[];
  core_issue_tags: string[];
  recommendations: string[];
  score_boundary: "SUPPORT_ORIENTATION_SCORE_NOT_CHILD_DIAGNOSIS_OR_RANKING";
}

interface Ui03EvidenceCoverage {
  source_response_count: number;
  interpreted_response_count: number;
  coverage_ratio: number;
  mapped_item_refs: string[];
  evidence_summaries: string[];
  uninterpreted_item_refs: string[];
  uncertainty_item_refs: string[];
  uncertainty_reasons: string[];
  support_direction_refs: string[];
  support_direction_labels: string[];
  next_questions?: string[];
}

interface RemoteHypothesisProjection {
  projection_version: "UI03_GROWTH_HYPOTHESIS_V1";
  availability: "READY" | "NO_SUBMITTED_ASSESSMENT" | "POLICY_BLOCKED" | "CONSENT_WITHDRAWN" | "SUBMITTED" | "ANALYZING" | "ACKNOWLEDGED" | "DISMISSED" | "ANALYSIS_FAILED";
  ai_state: "NOT_INVOKED" | "MODEL_DRAFT_READY" | "MODEL_GATEWAY_BLOCKED" | "READ_ONLY_PERSISTED";
  latest_assessment_session_id?: string | null;
  named_actions?: { generate?: "GENERATE_GROWTH_HYPOTHESIS"; confirm?: "CONFIRM_GROWTH_HYPOTHESIS" };
  hypothesis: null | {
    hypothesis_ref: string;
    subject_person_id: string;
    subject_display_name: string;
    focus_ref: string;
    title: string;
    statement: string;
    source_refs: {
      assessment_session_id: string;
      assessment_response_id: string;
      assessment_evidence_id: string;
      tool_ref: string;
      tool_version: number;
      assessment_submitted_at?: string | null;
    };
    limitations: string[];
    fact_boundary: "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS";
    safety_gate?: { required: boolean; reason_refs: string[]; mode: "HUMAN_REVIEW_REQUIRED" };
    evidence_coverage?: Ui03EvidenceCoverage;
    scorecard?: Ui03Scorecard;
  };
}

interface HypothesisDecisionReceipt { outcome: "INTENT_CREATED" | "NO_ACTION"; intent: { intent_id: string } | null; replayed: boolean }

const PREVIEW_SCORECARD: Ui03Scorecard = {
  generated_by: "FAMILI_PRINCIPAL_FAMILY_EDUCATION_MODEL",
  overall_score: 0,
  overall_band: "PENDING_ASSESSMENT",
  dimensions: [
    { dimension_ref: "communication", label: "沟通", score: 50, peer_reference: 50 },
    { dimension_ref: "habit", label: "习惯", score: 50, peer_reference: 50 },
    { dimension_ref: "emotion", label: "情绪", score: 50, peer_reference: 50 },
    { dimension_ref: "boundary", label: "边界", score: 50, peer_reference: 50 },
    { dimension_ref: "support", label: "支持", score: 50, peer_reference: 50 },
  ],
  core_issue_tags: ["完成测评后显示", "家庭支持方向", "非诊断结论"],
  recommendations: [
    "先完成免费家庭测评，系统会基于已提交答案整理支持方向。",
    "AI 只生成家庭支持假设，不替代专业诊断或儿童能力评价。",
    "确认方向后，再进入 90 天家庭成长方案预览。",
  ],
  score_boundary: "SUPPORT_ORIENTATION_SCORE_NOT_CHILD_DIAGNOSIS_OR_RANKING",
};

const RADAR_CENTER = { x: 120, y: 104 };
const RADAR_POINTS = [
  { x: 120, y: 24, labelX: 120, labelY: 14, anchor: "middle" as const },
  { x: 196, y: 80, labelX: 217, labelY: 78, anchor: "start" as const },
  { x: 168, y: 170, labelX: 188, labelY: 190, anchor: "start" as const },
  { x: 72, y: 170, labelX: 52, labelY: 190, anchor: "end" as const },
  { x: 44, y: 80, labelX: 23, labelY: 78, anchor: "end" as const },
] as const;

export default function GrowthExplanationScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { activeOnboardingId, setActiveOnboardingId } = useFamilyMobile();
  const [remote, setRemote] = useState<RemoteHypothesisProjection | null>(null);
  const [remoteState, setRemoteState] = useState<"idle" | "loading" | "generating" | "ready" | "fallback">("idle");
  const [decisionState, setDecisionState] = useState<"idle" | "saving" | "error">("idle");
  const [confirmed, setConfirmed] = useState(false);
  const decisionKeys = useRef<Record<string, string>>({});
  const generateKeys = useRef<Record<string, string>>({});
  const onboardingKeys = useRef<Record<string, string>>({});
  const hypothesis = remote?.hypothesis ?? null;
  const scorecard = hypothesis?.scorecard ?? null;
  const safetyGateRequired = hypothesis?.safety_gate?.required === true;
  const named_actions = remote?.named_actions ?? { generate: "GENERATE_GROWTH_HYPOTHESIS" as const, confirm: "CONFIRM_GROWTH_HYPOTHESIS" as const };

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) { setRemoteState("idle"); return; }
    const token = session.token;
    const familyId = session.selectedFamily.family_id;
    let active = true;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    const load = async (): Promise<void> => {
      const result = await familyApi.getGrowthHypothesis<RemoteHypothesisProjection>(token, familyId);
      if (!active) return;
      setRemote(result);
      if (result.availability === "CONSENT_WITHDRAWN") { setRemoteState("ready"); return; }
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
          if (active) setRemoteState("fallback");
        }
        return;
      }
      if (result.availability === "ANALYZING") {
        setRemoteState("generating");
        pollTimer = setTimeout(() => { if (active) void load(); }, 1500);
        return;
      }
      setRemoteState("ready");
    };

    setRemoteState("loading");
    void load().catch(() => { if (active) setRemoteState("fallback"); });
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
      setDecisionState("error");
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
      const result = await familyApi.decideGrowthHypothesis<HypothesisDecisionReceipt>(session.token, session.selectedFamily.family_id, {
        assessment_session_id: hypothesis.source_refs.assessment_session_id,
        hypothesis_ref: hypothesis.hypothesis_ref,
        decision_type: "CONFIRM",
      }, decisionKeys.current[fingerprint]);
      if (result.outcome === "INTENT_CREATED") {
        await ensureActiveOnboarding(session.token, session.selectedFamily.family_id, session.selectedFamily.person_id, hypothesis.subject_person_id);
        setDecisionState("idle");
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

  const isPreview = !hypothesis || !scorecard;
  const consentWithdrawn = remote?.availability === "CONSENT_WITHDRAWN";
  const displayScorecard = scorecard ?? PREVIEW_SCORECARD;
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
        {isPreview ? <View style={styles.previewNotice}><Text style={styles.previewNoticeTitle}>{consentWithdrawn ? "测评授权已撤回" : "先完成免费家庭测评"}</Text><Text style={styles.previewNoticeText}>{consentWithdrawn ? "根据你的授权选择，系统已停止展示这次测评和 AI 分析内容。如需继续，请重新确认测评授权。" : "AI 会基于你提交的免费测评生成成长诊断报告；这不是儿童诊断结论、能力测验或排名。"}</Text></View> : null}
        <View style={styles.assessmentSummary}>
          <View style={styles.summaryAvatar}><IconSymbol name="person.crop.circle.fill" size={58} color="#2563EB" /></View>
          <View style={styles.summaryCopy}>
            <Text style={styles.summaryBadge}>{isPreview ? "测评后生成" : "AI成长诊断报告"}</Text>
            <Text style={styles.summaryTitle}>{isPreview ? "家庭成长诊断预览" : hypothesis.subject_display_name ? `${hypothesis.subject_display_name}的成长诊断` : "家庭成长诊断"}</Text>
            {summaryRows.map((row) => <Text key={row} style={styles.summaryMeta}>{row}</Text>)}
          </View>
          <View style={styles.summaryScorePill}>
            <Text style={styles.summaryScore}>{isPreview ? "—" : displayScorecard.overall_score}</Text>
            <Text style={styles.summaryScoreLabel}>参考分</Text>
          </View>
          <IconSymbol name="chevron.right" size={19} color="#536A8B" />
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>综合成长评估</Text>
        <GrowthRadarOverview scorecard={displayScorecard} isPreview={isPreview} />

        {scorecard ? <>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>核心问题</Text>
          <View style={styles.tags}>
            {scorecard.core_issue_tags.slice(0, 3).map((tag, index) => (
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

        {scorecard ? <>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>成长建议</Text>
          <View style={styles.suggestions}>
            {scorecard.recommendations.slice(0, 3).map((item, index) => (
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
        {safetyGateRequired ? <View style={styles.safetyNotice}>
          <Text style={styles.safetyNoticeTitle}>需要人工复核</Text>
          <Text style={styles.safetyNoticeText}>这次测评出现了需要谨慎理解的健康或家庭压力信号。AI 不会直接生成成长方案，请联系专业人工支持进一步判断。</Text>
        </View> : null}
        <Pressable disabled={decisionState === "saving"} onPress={() => void generatePlan()} style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.tint }, pressed && styles.pressed]}>
          <IconSymbol name="star.fill" size={18} color="#FFFFFF" />
          <Text style={styles.primaryButtonText}>{decisionState === "saving" ? "正在生成" : isPreview ? "进入免费测评" : safetyGateRequired ? "等待人工复核" : "生成个性化方案"}</Text>
        </Pressable>
        <Text style={[styles.boundaryText, { color: colors.muted }]}>以上内容用于家庭支持参考，不是儿童诊断结论、能力测验或排名。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function GrowthRadarOverview({ scorecard, isPreview = false }: { scorecard: Ui03Scorecard; isPreview?: boolean }) {
  const childPoints = radarPolygon(scorecard.dimensions.map((item) => item.score));
  const peerPoints = radarPolygon(scorecard.dimensions.map((item) => item.peer_reference));
  return (
    <View style={styles.radarCard}>
      <Svg width={240} height={224} viewBox="0 0 240 224" accessibilityLabel="综合成长评估雷达图">
        <Polygon points={RADAR_POINTS.map((point) => `${point.x},${point.y}`).join(" ")} fill="none" stroke="#C6DBF6" strokeWidth={1} />
        <Polygon points={radarPolygon([50, 50, 50, 50, 50])} fill="none" stroke="#E1ECFA" strokeWidth={1} />
        {RADAR_POINTS.map((point, index) => <Line key={`axis-${scorecard.dimensions[index]?.dimension_ref ?? index}`} x1={RADAR_CENTER.x} y1={RADAR_CENTER.y} x2={point.x} y2={point.y} stroke="#E1ECFA" strokeWidth={1} />)}
        <Polygon points={peerPoints} fill="rgba(247, 181, 77, 0.16)" stroke="#F2A23A" strokeWidth={2} />
        <Polygon points={childPoints} fill="rgba(47, 143, 251, 0.22)" stroke="#2F8FFB" strokeWidth={2} />
        <Circle cx={RADAR_CENTER.x} cy={RADAR_CENTER.y} r={35} fill="#FFFFFF" stroke="#D5E6FA" strokeWidth={1} />
        <SvgText x={RADAR_CENTER.x} y={RADAR_CENTER.y - 2} textAnchor="middle" fill="#2563EB" fontSize={24} fontWeight="800">{isPreview ? "—" : scorecard.overall_score}</SvgText>
        <SvgText x={RADAR_CENTER.x} y={RADAR_CENTER.y + 17} textAnchor="middle" fill="#6B7280" fontSize={10}>{isPreview ? "待生成" : "参考分"}</SvgText>
        {scorecard.dimensions.slice(0, 5).map((dimension, index) => {
          const point = RADAR_POINTS[index];
          return <SvgText key={dimension.dimension_ref} x={point.labelX} y={point.labelY} textAnchor={point.anchor} fill="#5B6B7F" fontSize={11} fontWeight="700">{dimension.label}{isPreview ? "" : dimension.score}</SvgText>;
        })}
      </Svg>
      <View style={styles.legendRow}>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: "#2F8FFB" }]} /><Text style={styles.legendText}>家庭自查线索</Text></View>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: "#F2A23A" }]} /><Text style={styles.legendText}>参考方向</Text></View>
      </View>
    </View>
  );
}

function radarPolygon(values: number[]) {
  return RADAR_POINTS.map((point, index) => {
    const value = Math.max(0, Math.min(100, values[index] ?? 0)) / 100;
    const x = RADAR_CENTER.x + (point.x - RADAR_CENTER.x) * value;
    const y = RADAR_CENTER.y + (point.y - RADAR_CENTER.y) * value;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatAiState(value: RemoteHypothesisProjection["ai_state"]) {
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
  summaryScorePill: { width: 54, height: 54, borderRadius: 27, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  summaryScore: { color: "#2563EB", fontSize: 20, lineHeight: 24, fontWeight: "900" },
  summaryScoreLabel: { color: "#6B7280", fontSize: 9, lineHeight: 12, fontWeight: "800" },
  sectionTitle: { fontSize: 18, lineHeight: 25, fontWeight: "800" },
  radarCard: { alignItems: "center", borderRadius: 14, paddingTop: 10, paddingBottom: 12, backgroundColor: "#FFFFFF" },
  legendRow: { flexDirection: "row", justifyContent: "center", gap: 20, marginTop: -4 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { color: "#6B7280", fontSize: 12, lineHeight: 17, fontWeight: "700" },
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
  boundaryText: { marginTop: -6, fontSize: 11, lineHeight: 17, textAlign: "center" },
  pressed: { opacity: 0.84, transform: [{ scale: 0.985 }] },
});
