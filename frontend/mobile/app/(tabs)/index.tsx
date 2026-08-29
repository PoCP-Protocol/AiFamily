import type { Href } from "expo-router";
import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { AssessmentBannerArt, RecommendationArt } from "@/components/family/home-illustrations";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { UI01_HOME_TARGETS } from "@/lib/family/ui01-home-entry-map";
import { createMobileRequestId, familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

const REC_ART_KINDS = ["live", "course", "case"] as const;
const SHOW_UI01_GROWTH_HELP_PANEL = false;
const CHALLENGE_CAMP_TARGET = "/ui/UI-14?productRef=PRODUCT_PARENT_CHILD_CAMP" as Href;

type HomeIcon = "heart.fill" | "gift.fill" | "calendar.fill" | "photo.fill" | "video.fill" | "headphones.fill" | "checkmark.circle.fill" | "book.fill";

const QUICK_ENTRIES: readonly { featureId: string; label: string; icon: HomeIcon; color: string; target: Href }[] = [
  { featureId: "ai_diagnostic", label: "AI诊断", icon: "heart.fill", color: "#35B9D7", target: `/ui/${UI01_HOME_TARGETS.aiInterpretation}` as Href },
  { featureId: "challenge_camp", label: "21天挑战营", icon: "gift.fill", color: "#F06863", target: CHALLENGE_CAMP_TARGET },
  { featureId: "plan_90", label: "90天成长计划", icon: "calendar.fill", color: "#36A866", target: `/ui/${UI01_HOME_TARGETS.plan90}` as Href },
  { featureId: "growth_cases", label: "成长案例", icon: "photo.fill", color: "#F0A337", target: `/ui/${UI01_HOME_TARGETS.growthStories}` as Href },
  { featureId: "expert_live", label: "专家直播", icon: "video.fill", color: "#55A6E9", target: `/ui/${UI01_HOME_TARGETS.expertLive}` as Href },
  { featureId: "family_advisor", label: "家庭顾问", icon: "headphones.fill", color: "#EC725D", target: `/ui/${UI01_HOME_TARGETS.familyAdvisor}` as Href },
];

const RECOMMENDATIONS: readonly { title: string; target: Href }[] = [
  { title: "妈妈总问我：为什么？", target: `/ui/${UI01_HOME_TARGETS.recommendations}` as Href },
  { title: "高效学习习惯养成课", target: `/ui/${UI01_HOME_TARGETS.recommendations}` as Href },
  { title: "从紧张冲突到亲子和谐", target: `/ui/${UI01_HOME_TARGETS.recommendations}` as Href },
];

type HomeAvailability = "AVAILABLE" | "POLICY_BLOCKED" | "SUPPLY_UNAVAILABLE" | "NOT_CONFIGURED";
type RemoteHome = {
  projection_version: "UI01_FAMILY_HOME_V1";
  entry_state: "READY" | "EMPTY";
  family: { display_name: string };
  greeting: { time_segment: "MORNING" | "AFTERNOON" | "EVENING" };
  assessment_campaign: { state: "AVAILABLE" | "POLICY_BLOCKED" };
  notification?: { state: "NOT_CONFIGURED"; unread_count: number; target_ui: string };
  quick_entries: { feature_id: string; title: string; target_ui: string; availability: HomeAvailability }[];
  growth_help: {
    state: "AVAILABLE" | "CONSENT_REQUIRED" | "NO_ELIGIBLE_SUBJECT" | "POLICY_BLOCKED";
    subjects: { person_id: string; display_name: string; availability: "AVAILABLE" | "CONSENT_REQUIRED" | "OUT_OF_SCOPE" }[];
  };
  primary_action: { assignment_text: string; task_state: "NOT_STARTED" | "CHECKED_IN" | "ARCHIVED" } | null;
  today_tasks: { task_id: string; assignment_text: string; task_state: "NOT_STARTED" | "CHECKED_IN" | "ARCHIVED" }[];
  journey: { title: string; current_phase: string; current_day: number; total_days: number } | null;
  recommendations: { recommendation_id: string; title: string; source_type: "PRODUCT_OFFERING" | "SERVICE_OFFERING"; target_ui: string }[];
};

type GrowthHelpResponse = {
  signal_id: string;
  proposed_need_type: string | null;
  confirm_prompt: string;
  supported: boolean;
  safety_route: "NORMAL" | "REVIEW" | "HIGH_RISK";
  next_action: "CONFIRM_INTENT" | "REFRAME_NEED" | "HUMAN_REVIEW" | "URGENT_HUMAN_SUPPORT";
};

type GrowthRecommendation = {
  recommendation_id: string;
  intent_id: string;
  version: number;
  candidates: { offer_ref: string; why_this: string; limitations: string[]; rank: number }[];
  recommended_offer_refs: string[];
  why_now: string;
};

type GrowthDecision = {
  decision_id: string;
  outcome: "SERVICE_STARTED" | "NO_ACTION" | "RE_RECOMMEND_REQUIRED" | string;
  case_id: string | null;
  executed_resource_type: string | null;
  ai_coach: { delivered: boolean; risk_route: string; human_handoff: boolean } | null;
};

export default function TodayScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { todayAction } = useFamilyMobile();
  const [home, setHome] = useState<RemoteHome | null>(null);
  const [homeLoading, setHomeLoading] = useState(false);
  const [homeError, setHomeError] = useState<string | null>(null);
  const [growthHelpOpen, setGrowthHelpOpen] = useState(false);
  const [growthHelpSubjectId, setGrowthHelpSubjectId] = useState<string | null>(null);
  const [growthHelpText, setGrowthHelpText] = useState("");
  const [growthHelpSubmitting, setGrowthHelpSubmitting] = useState(false);
  const [growthHelpError, setGrowthHelpError] = useState<string | null>(null);
  const [growthHelpResult, setGrowthHelpResult] = useState<GrowthHelpResponse | null>(null);
  const [growthRecommendation, setGrowthRecommendation] = useState<GrowthRecommendation | null>(null);
  const [growthDecision, setGrowthDecision] = useState<GrowthDecision | null>(null);
  const [growthHelpAdvancing, setGrowthHelpAdvancing] = useState(false);
  const growthHelpRetry = useRef<{ fingerprint: string; key: string } | null>(null);
  const growthIntentRetry = useRef<{ fingerprint: string; confirmKey: string; recommendationKey: string } | null>(null);
  const growthDecisionRetry = useRef<{ fingerprint: string; key: string } | null>(null);

  const loadHome = useCallback(async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setHome(null);
      setHomeLoading(false);
      return;
    }
    setHomeLoading(true);
    setHomeError(null);
    try {
      setHome(await familyApi.getFamilyHome<RemoteHome>(session.token, session.selectedFamily.family_id));
    } catch {
      setHomeError("首页暂时无法同步，请检查网络后重试。");
    } finally {
      setHomeLoading(false);
    }
  }, [session.selectedFamily, session.status, session.token]);

  useEffect(() => { void loadHome(); }, [loadHome]);

  useEffect(() => {
    const available = home?.growth_help.subjects.filter((subject) => subject.availability === "AVAILABLE") ?? [];
    setGrowthHelpSubjectId((current) => {
      if (current && available.some((subject) => subject.person_id === current)) return current;
      return available.length === 1 ? available[0].person_id : null;
    });
  }, [home]);

  const communicationDone = todayAction.status === "checked_in";
  const syntheticTasks = [
    { label: "亲子沟通小练习", icon: "checkmark.circle.fill" as const, color: "#39AC7A", done: communicationDone },
    { label: "完成今日阅读打卡", icon: "book.fill" as const, color: "#F1A136", done: false },
    { label: "情绪记录", icon: "heart.fill" as const, color: "#F1A136", done: false },
  ];
  const tasks = home
    ? home.today_tasks.map((task) => ({ label: task.assignment_text, icon: "checkmark.circle.fill" as const, color: "#39AC7A", done: task.task_state === "CHECKED_IN" }))
    : syntheticTasks;
  const greeting = home?.greeting.time_segment === "EVENING" ? "晚上好" : home?.greeting.time_segment === "AFTERNOON" ? "下午好" : "早上好";
  const recommendationItems = home ? home.recommendations : RECOMMENDATIONS.map((item, index) => ({ recommendation_id: `local-${index}`, title: item.title, source_type: "PRODUCT_OFFERING" as const, target_ui: "UI-13" }));

  const open = (target: Href) => router.push(target);

  const submitGrowthHelp = async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily || !growthHelpSubjectId || !growthHelpText.trim()) return;
    const rawText = growthHelpText.trim();
    const fingerprint = `${session.selectedFamily.family_id}:${growthHelpSubjectId}:${rawText}`;
    if (growthHelpRetry.current?.fingerprint !== fingerprint) {
      growthHelpRetry.current = { fingerprint, key: createMobileRequestId("ui01-growth-help") };
    }
    setGrowthHelpSubmitting(true);
    setGrowthHelpError(null);
    setGrowthHelpResult(null);
    try {
      const result = await familyApi.requestGrowthHelp<GrowthHelpResponse>(
        session.token,
        session.selectedFamily.family_id,
        { subject_person_id: growthHelpSubjectId, raw_text: rawText },
        growthHelpRetry.current.key,
      );
      setGrowthHelpResult(result);
      setGrowthRecommendation(null);
      setGrowthDecision(null);
    } catch {
      setGrowthHelpError("暂时没有提交成功。原文仍留在本机输入框中，请稍后重试。");
    } finally {
      setGrowthHelpSubmitting(false);
    }
  };

  const confirmGrowthDirection = async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily || !growthHelpResult || growthHelpResult.next_action !== "CONFIRM_INTENT" || !growthHelpText.trim()) return;
    const fingerprint = `${growthHelpResult.signal_id}:${growthHelpText.trim()}`;
    if (growthIntentRetry.current?.fingerprint !== fingerprint) {
      growthIntentRetry.current = {
        fingerprint,
        confirmKey: createMobileRequestId("ui01-confirm-growth-intent"),
        recommendationKey: createMobileRequestId("ui01-growth-recommendation"),
      };
    }
    setGrowthHelpAdvancing(true);
    setGrowthHelpError(null);
    try {
      const intent = await familyApi.confirmGrowthIntent<{ intent_id: string }>(session.token, session.selectedFamily.family_id, { signal_id: growthHelpResult.signal_id, goal_text: growthHelpText.trim() }, growthIntentRetry.current.confirmKey);
      const recommendation = await familyApi.requestGrowthRecommendation<GrowthRecommendation>(session.token, session.selectedFamily.family_id, intent.intent_id, growthIntentRetry.current.recommendationKey);
      setGrowthRecommendation(recommendation);
      setGrowthDecision(null);
    } catch {
      setGrowthHelpError("方向确认暂时没有完成，请稍后重试；重复点击不会重复创建记录。");
    } finally {
      setGrowthHelpAdvancing(false);
    }
  };

  const decideGrowthHelp = async (decisionType: "ACCEPT_RECOMMENDATION" | "DISMISS") => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily || !growthRecommendation) return;
    const selectedOfferRefs = decisionType === "ACCEPT_RECOMMENDATION"
      ? growthRecommendation.recommended_offer_refs.filter((offerRef) => offerRef !== "resource:v1:no_action")
      : [];
    if (decisionType === "ACCEPT_RECOMMENDATION" && selectedOfferRefs.length === 0) return;
    const fingerprint = `${growthRecommendation.recommendation_id}:${decisionType}:${selectedOfferRefs.join(",")}`;
    if (growthDecisionRetry.current?.fingerprint !== fingerprint) growthDecisionRetry.current = { fingerprint, key: createMobileRequestId("ui01-growth-decision") };
    setGrowthHelpAdvancing(true);
    setGrowthHelpError(null);
    try {
      const decision = await familyApi.decideGrowthService<GrowthDecision>(session.token, session.selectedFamily.family_id, {
        intent_id: growthRecommendation.intent_id,
        recommendation_id: growthRecommendation.recommendation_id,
        recommendation_version: growthRecommendation.version,
        decision_type: decisionType,
        selected_offer_refs: selectedOfferRefs,
      }, growthDecisionRetry.current.key);
      setGrowthDecision(decision);
    } catch {
      setGrowthHelpError("这次选择暂时没有保存，请稍后重试；系统不会重复启动服务。");
    } finally {
      setGrowthHelpAdvancing(false);
    }
  };

  return (
    <ScreenContainer containerClassName="bg-surface">
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={[]}
        renderItem={null}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.page}>
            <View style={styles.topBar}>
              <Text style={[styles.platformTitle, { color: colors.text }]}>家庭成长平台</Text>
              <View style={styles.topActions}>
                <Pressable accessibilityRole="button" accessibilityLabel="更多与家庭档案" onPress={() => open("/ui/UI-34" as Href)}><IconSymbol name="ellipsis" size={25} color={colors.text} /></Pressable>
                <Pressable accessibilityRole="button" accessibilityLabel="查看家庭上下文" onPress={() => open("/ui/UI-34" as Href)}><IconSymbol name="eye.fill" size={22} color={colors.text} /></Pressable>
              </View>
            </View>

            <View style={styles.welcomeRow}>
              <Text style={[styles.welcome, { color: colors.text }]}>{greeting}{home?.family.display_name ? `，${home.family.display_name}` : ""}{"\n"}今天也一起陪孩子成长 ☀</Text>
              <Pressable disabled={home?.notification?.state === "NOT_CONFIGURED"} accessibilityRole="button" accessibilityLabel={home?.notification?.state === "NOT_CONFIGURED" ? "提醒功能尚未配置" : "提醒"} onPress={() => open("/ui/UI-34" as Href)} style={home?.notification?.state === "NOT_CONFIGURED" ? styles.disabled : undefined}><IconSymbol name="bell.fill" size={25} color={colors.text} /></Pressable>
            </View>

            {homeLoading ? <View style={styles.statusPanel}><ActivityIndicator color={colors.tint} /><Text style={[styles.statusText, { color: colors.muted }]}>正在同步家庭首页</Text></View> : null}
            {homeError ? <Pressable accessibilityRole="button" accessibilityLabel="重试同步首页" onPress={() => void loadHome()} style={[styles.statusPanel, { borderColor: colors.border }]}><Text style={[styles.statusText, { color: colors.error }]}>{homeError}</Text><Text style={[styles.retryText, { color: colors.tint }]}>点击重试</Text></Pressable> : null}

            <Pressable disabled={home?.assessment_campaign.state === "POLICY_BLOCKED"} accessibilityRole="button" accessibilityLabel="免费家庭测评" onPress={() => open(`/ui/${UI01_HOME_TARGETS.freeAssessment}` as Href)} style={({ pressed }) => [home?.assessment_campaign.state === "POLICY_BLOCKED" && styles.disabled, pressed && styles.pressed]}>
              <AssessmentBannerArt />
            </Pressable>

            <View style={[styles.quickGrid, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              {QUICK_ENTRIES.map((entry) => {
                const remoteEntry = home?.quick_entries.find((candidate) => candidate.feature_id === entry.featureId);
                const availability = remoteEntry?.availability ?? "AVAILABLE";
                return (
                  <Pressable disabled={availability !== "AVAILABLE"} key={entry.label} accessibilityRole="button" accessibilityLabel={entry.label} accessibilityHint={availability === "AVAILABLE" ? undefined : "当前租户策略或服务供给暂不可用"} onPress={() => open(entry.target)} style={({ pressed }) => [styles.quickEntry, availability !== "AVAILABLE" && styles.disabled, pressed && styles.pressed]}>
                    <IconSymbol name={entry.icon} size={29} color={entry.color} />
                  <Text style={[styles.quickLabel, { color: colors.text }]}>{remoteEntry?.title ?? entry.label}</Text>
                </Pressable>
              )})}
            </View>

            {SHOW_UI01_GROWTH_HELP_PANEL ? <View style={[styles.growthHelpCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <Pressable accessibilityRole="button" accessibilityLabel="问法咪莉校长" accessibilityHint="展开后选择孩子并描述现在最需要帮助的事情" onPress={() => setGrowthHelpOpen((value) => !value)} style={({ pressed }) => [styles.growthHelpHeader, pressed && styles.pressed]}>
                <View style={[styles.growthHelpIcon, { backgroundColor: `${colors.tint}18` }]}><IconSymbol name="heart.fill" size={22} color={colors.tint} /></View>
                <View style={styles.growthHelpHeading}><Text style={[styles.growthHelpTitle, { color: colors.text }]}>问法咪莉校长</Text><Text style={[styles.growthHelpSubtitle, { color: colors.muted }]}>说说现在最需要帮助的一件事</Text></View>
                <IconSymbol name={growthHelpOpen ? "chevron.down" : "chevron.right"} size={18} color={colors.muted} />
              </Pressable>
              {growthHelpOpen ? <View style={[styles.growthHelpBody, { borderTopColor: colors.border }]}>
                {!home ? <Text style={[styles.growthHelpNotice, { color: colors.muted }]}>连接家庭会话后，可以为符合服务范围的孩子发起帮助。</Text> : null}
                {home?.growth_help.state === "POLICY_BLOCKED" ? <Text style={[styles.growthHelpNotice, { color: colors.muted }]}>当前家庭策略未开放这项服务。</Text> : null}
                {home?.growth_help.state === "CONSENT_REQUIRED" ? <Text style={[styles.growthHelpNotice, { color: colors.muted }]}>请先在家庭档案中完成对应孩子的服务同意。</Text> : null}
                {home?.growth_help.state === "NO_ELIGIBLE_SUBJECT" ? <Text style={[styles.growthHelpNotice, { color: colors.muted }]}>当前没有处于本服务年龄范围的孩子。</Text> : null}
                {home?.growth_help.state === "AVAILABLE" ? <>
                  <Text style={[styles.growthHelpLabel, { color: colors.text }]}>这次想为谁寻求帮助？</Text>
                  <View style={styles.subjectRow}>
                    {home.growth_help.subjects.map((subject) => {
                      const available = subject.availability === "AVAILABLE";
                      const selected = growthHelpSubjectId === subject.person_id;
                      return <Pressable key={subject.person_id} disabled={!available} accessibilityRole="button" accessibilityState={{ selected, disabled: !available }} accessibilityLabel={`${subject.display_name}${available ? "" : subject.availability === "CONSENT_REQUIRED" ? "，需要服务同意" : "，不在服务年龄范围"}`} onPress={() => { setGrowthHelpSubjectId(subject.person_id); setGrowthHelpResult(null); setGrowthRecommendation(null); setGrowthDecision(null); setGrowthHelpError(null); }} style={[styles.subjectChip, { borderColor: selected ? colors.tint : colors.border, backgroundColor: selected ? `${colors.tint}12` : colors.background }, !available && styles.disabled]}><Text style={[styles.subjectChipText, { color: selected ? colors.tint : colors.text }]}>{subject.display_name}</Text></Pressable>;
                    })}
                  </View>
                  <Text style={[styles.growthHelpLabel, { color: colors.text }]}>现在发生了什么？</Text>
                  <TextInput accessibilityLabel="描述需要帮助的事情" multiline maxLength={500} textAlignVertical="top" value={growthHelpText} onChangeText={(value) => { setGrowthHelpText(value); setGrowthHelpResult(null); setGrowthRecommendation(null); setGrowthDecision(null); setGrowthHelpError(null); }} placeholder="例如：孩子刚摔门，我今晚不知道怎么重新开口……" placeholderTextColor={colors.muted} style={[styles.growthHelpInput, { color: colors.text, borderColor: colors.border, backgroundColor: colors.background }]} />
                  <Text style={[styles.growthHelpBoundary, { color: colors.muted }]}>只有点击“提交并获取下一步”后才会发送；首页不会自动分析家庭文字。</Text>
                  <Pressable disabled={!growthHelpSubjectId || !growthHelpText.trim() || growthHelpSubmitting} accessibilityRole="button" accessibilityLabel="提交并获取下一步" onPress={() => void submitGrowthHelp()} style={({ pressed }) => [styles.growthHelpSubmit, { backgroundColor: growthHelpSubjectId && growthHelpText.trim() && !growthHelpSubmitting ? colors.tint : colors.border }, pressed && styles.pressed]}>{growthHelpSubmitting ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.growthHelpSubmitText}>提交并获取下一步</Text>}</Pressable>
                </> : null}
                {growthHelpError ? <Text accessibilityRole="alert" style={[styles.growthHelpResult, { color: colors.error, borderColor: `${colors.error}40`, backgroundColor: `${colors.error}08` }]}>{growthHelpError}</Text> : null}
                {growthHelpResult ? <View accessibilityRole="summary" style={[styles.growthHelpResult, { borderColor: growthHelpResult.safety_route === "NORMAL" ? `${colors.tint}40` : "#D9783048", backgroundColor: growthHelpResult.safety_route === "NORMAL" ? `${colors.tint}08` : "#FFF5EA" }]}>
                  <Text style={[styles.growthHelpResultTitle, { color: growthHelpResult.safety_route === "NORMAL" ? colors.tint : "#A65318" }]}>{growthHelpResult.safety_route === "NORMAL" ? "已收到，我们先确认方向" : growthHelpResult.safety_route === "HIGH_RISK" ? "请优先获得紧急支持" : "请先获得专业支持"}</Text>
                  <Text style={[styles.growthHelpResultText, { color: colors.text }]}>{growthHelpResult.confirm_prompt}</Text>
                  {growthHelpResult.next_action === "CONFIRM_INTENT" && !growthRecommendation ? <Pressable disabled={growthHelpAdvancing} accessibilityRole="button" accessibilityLabel="确认这个方向并查看可用帮助" onPress={() => void confirmGrowthDirection()} style={[styles.growthHelpInlineAction, { borderColor: colors.tint }]}>{growthHelpAdvancing ? <ActivityIndicator color={colors.tint} /> : <Text style={[styles.growthHelpNext, { color: colors.tint }]}>确认这个方向并查看可用帮助 →</Text>}</Pressable> : null}
                </View> : null}
                {growthRecommendation ? <View style={[styles.recommendationDecision, { borderColor: colors.border, backgroundColor: colors.background }]}>
                  <Text style={[styles.growthHelpResultTitle, { color: colors.text }]}>可用帮助</Text>
                  <Text style={[styles.growthHelpResultText, { color: colors.muted }]}>{growthRecommendation.why_now}</Text>
                  {growthRecommendation.candidates.map((candidate) => <View key={candidate.offer_ref} style={styles.candidateRow}><Text style={[styles.candidateTitle, { color: colors.text }]}>{offerLabel(candidate.offer_ref)}</Text><Text style={[styles.growthHelpResultText, { color: colors.muted }]}>{candidate.why_this}</Text>{candidate.limitations.map((item) => <Text key={item} style={[styles.candidateLimit, { color: colors.muted }]}>边界：{item}</Text>)}</View>)}
                  {!growthDecision ? <View style={styles.decisionActions}>{growthRecommendation.recommended_offer_refs.some((offerRef) => offerRef !== "resource:v1:no_action") ? <Pressable disabled={growthHelpAdvancing} accessibilityRole="button" accessibilityLabel="接受建议并开始" onPress={() => void decideGrowthHelp("ACCEPT_RECOMMENDATION")} style={[styles.growthHelpSubmit, { backgroundColor: colors.tint }]}><Text style={styles.growthHelpSubmitText}>接受建议并开始</Text></Pressable> : null}<Pressable disabled={growthHelpAdvancing} accessibilityRole="button" accessibilityLabel="今晚先不安排" onPress={() => void decideGrowthHelp("DISMISS")} style={[styles.growthHelpSecondary, { borderColor: colors.border }]}><Text style={[styles.growthHelpSecondaryText, { color: colors.text }]}>今晚先不安排</Text></Pressable></View> : null}
                  {growthDecision ? <View style={[styles.decisionReceipt, { backgroundColor: growthDecision.outcome === "SERVICE_STARTED" ? "#EAF8F3" : "#F1F5F9" }]}><Text style={[styles.growthHelpResultTitle, { color: growthDecision.outcome === "SERVICE_STARTED" ? colors.success : colors.text }]}>{growthDecision.outcome === "SERVICE_STARTED" ? "服务已启动" : growthDecision.outcome === "NO_ACTION" ? "已记录：今晚先不安排" : "服务状态已更新"}</Text><Text style={[styles.growthHelpResultText, { color: colors.muted }]}>{growthDecision.outcome === "SERVICE_STARTED" ? "系统已保存可追溯服务回执，稍后可以反馈是否有帮助。" : "没有创建下游成长任务或效果结论。"}</Text>{growthDecision.outcome === "SERVICE_STARTED" && growthDecision.executed_resource_type === "AI_COACH" ? <Pressable accessibilityRole="button" accessibilityLabel="进入AI成长陪伴" onPress={() => open("/ui/UI-05" as Href)}><Text style={[styles.growthHelpNext, { color: colors.tint }]}>进入 AI 成长陪伴 →</Text></Pressable> : null}</View> : null}
                </View> : null}
              </View> : null}
            </View> : null}

            {home?.journey ? <Pressable accessibilityRole="button" accessibilityLabel="查看当前90天成长旅程" onPress={() => open(`/ui/${UI01_HOME_TARGETS.plan90}` as Href)} style={[styles.journeyCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.journeyTitle, { color: colors.text }]}>{home.journey.title}</Text><Text style={[styles.journeyMeta, { color: colors.muted }]}>第 {home.journey.current_day}/{home.journey.total_days} 天 · {home.journey.current_phase}</Text></Pressable> : null}
            {home?.primary_action ? <Pressable accessibilityRole="button" accessibilityLabel="今晚一件事" onPress={() => open(`/ui/${UI01_HOME_TARGETS.dailyTasks}` as Href)} style={[styles.primaryAction, { backgroundColor: `${colors.tint}10`, borderColor: `${colors.tint}40` }]}><Text style={[styles.primaryEyebrow, { color: colors.tint }]}>今晚一件事</Text><Text style={[styles.primaryText, { color: colors.text }]}>{home.primary_action.assignment_text}</Text></Pressable> : null}

            <SectionTitle title="今日成长任务" action="查看全部" onPress={() => open(`/ui/${UI01_HOME_TARGETS.dailyTasks}` as Href)} colors={colors} />
            <View style={[styles.taskList, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              {home && tasks.length === 0 ? <View style={styles.emptyRow}><Text style={[styles.statusText, { color: colors.muted }]}>今天还没有安排成长行动，可以从测评或成长计划开始。</Text></View> : null}
              {tasks.map((task, index) => (
                <Pressable key={task.label} accessibilityRole="button" accessibilityLabel={task.label} onPress={() => open(`/ui/${UI01_HOME_TARGETS.dailyTasks}` as Href)} style={({ pressed }) => [styles.taskRow, index < tasks.length - 1 && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border }, pressed && styles.pressed]}>
                  <IconSymbol name={task.icon} size={21} color={task.color} />
                  <Text style={[styles.taskLabel, { color: colors.text }]}>{task.label}</Text>
                  {task.done ? <IconSymbol name="checkmark.circle.fill" size={22} color="#32B276" /> : <Text style={[styles.completePill, { color: colors.tint, borderColor: `${colors.tint}55` }]}>去完成</Text>}
                </Pressable>
              ))}
            </View>

            <SectionTitle title="推荐内容/服务" action="更多" onPress={() => open(`/ui/${UI01_HOME_TARGETS.recommendations}` as Href)} colors={colors} />
            <View style={styles.recommendationRow}>
              {home && recommendationItems.length === 0 ? <View style={[styles.emptyRecommendation, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.statusText, { color: colors.muted }]}>当前没有已审核上架的内容或服务。</Text></View> : null}
              {recommendationItems.map((item, index) => (
                <Pressable key={item.recommendation_id} accessibilityRole="button" accessibilityLabel={`查看${item.title}`} onPress={() => open((item.target_ui === "UI-19" ? "/ui/UI-19" : "/ui/UI-13") as Href)} style={({ pressed }) => [styles.recommendationCard, pressed && styles.pressed]}>
                  <RecommendationArt kind={REC_ART_KINDS[index % 3]} />
                  <View style={styles.recommendationCaption}><Text numberOfLines={2} style={styles.recommendationTitle}>{item.title}</Text></View>
                </Pressable>
              ))}
            </View>
          </View>
        }
      />
    </ScreenContainer>
  );
}

function offerLabel(offerRef: string) {
  if (offerRef === "resource:v1:ai_coach") return "AI 沟通陪练";
  if (offerRef === "resource:v1:no_action") return "今晚先不安排";
  if (offerRef.startsWith("resource:v1:external_referral")) return "专业支持转介";
  return "家庭成长支持";
}

function SectionTitle({ title, action, onPress, colors }: { title: string; action: string; onPress: () => void; colors: ReturnType<typeof useColors> }) {
  return (
    <View style={styles.sectionTopline}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>{title}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel={action} onPress={onPress} style={({ pressed }) => [styles.moreButton, pressed && styles.pressed]}>
        <Text style={[styles.moreText, { color: colors.muted }]}>{action}</Text>
        <IconSymbol name="chevron.right" size={17} color={colors.muted} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 14, paddingBottom: 92 },
  page: { gap: 15 },
  topBar: { minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  platformTitle: { fontSize: 21, lineHeight: 29, fontWeight: "900" },
  topActions: { flexDirection: "row", alignItems: "center", gap: 18, paddingHorizontal: 4 },
  welcomeRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", paddingTop: 2 },
  welcome: { flex: 1, paddingRight: 16, fontSize: 22, lineHeight: 31, fontWeight: "900" },

  quickGrid: { borderWidth: 1, borderRadius: 19, overflow: "hidden", flexDirection: "row", flexWrap: "wrap" },
  quickEntry: { width: "33.333%", minHeight: 98, alignItems: "center", justifyContent: "center", gap: 8, borderRightWidth: StyleSheet.hairlineWidth, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: "#EDF1F5", paddingHorizontal: 6 },
  quickLabel: { fontSize: 13, lineHeight: 18, fontWeight: "700", textAlign: "center" },
  growthHelpCard: { borderWidth: 1, borderRadius: 17, overflow: "hidden" },
  growthHelpHeader: { minHeight: 78, paddingHorizontal: 14, flexDirection: "row", alignItems: "center", gap: 11 },
  growthHelpIcon: { width: 42, height: 42, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  growthHelpHeading: { flex: 1, gap: 2 },
  growthHelpTitle: { fontSize: 17, lineHeight: 23, fontWeight: "900" },
  growthHelpSubtitle: { fontSize: 12, lineHeight: 18, fontWeight: "600" },
  growthHelpBody: { borderTopWidth: StyleSheet.hairlineWidth, padding: 14, gap: 10 },
  growthHelpNotice: { fontSize: 13, lineHeight: 20, fontWeight: "600" },
  growthHelpLabel: { fontSize: 13, lineHeight: 19, fontWeight: "800" },
  subjectRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  subjectChip: { minHeight: 36, borderWidth: 1, borderRadius: 18, paddingHorizontal: 14, alignItems: "center", justifyContent: "center" },
  subjectChipText: { fontSize: 13, lineHeight: 18, fontWeight: "800" },
  growthHelpInput: { minHeight: 104, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, lineHeight: 21 },
  growthHelpBoundary: { fontSize: 11, lineHeight: 17, fontWeight: "600" },
  growthHelpSubmit: { minHeight: 44, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  growthHelpSubmitText: { color: "#FFFFFF", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  growthHelpResult: { borderWidth: 1, borderRadius: 12, padding: 12, gap: 6, fontSize: 13, lineHeight: 20, fontWeight: "600" },
  growthHelpResultTitle: { fontSize: 14, lineHeight: 20, fontWeight: "900" },
  growthHelpResultText: { fontSize: 13, lineHeight: 20, fontWeight: "600" },
  growthHelpNext: { paddingTop: 4, fontSize: 13, lineHeight: 19, fontWeight: "900" },
  growthHelpInlineAction: { minHeight: 40, marginTop: 4, borderWidth: 1, borderRadius: 10, paddingHorizontal: 10, alignItems: "center", justifyContent: "center" },
  recommendationDecision: { borderWidth: 1, borderRadius: 12, padding: 12, gap: 10 },
  candidateRow: { gap: 3, paddingVertical: 4 },
  candidateTitle: { fontSize: 14, lineHeight: 20, fontWeight: "900" },
  candidateLimit: { fontSize: 11, lineHeight: 17, fontWeight: "600" },
  decisionActions: { gap: 8, paddingTop: 2 },
  growthHelpSecondary: { minHeight: 42, borderWidth: 1, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  growthHelpSecondaryText: { fontSize: 14, lineHeight: 20, fontWeight: "800" },
  decisionReceipt: { borderRadius: 10, padding: 11, gap: 4 },
  sectionTopline: { marginTop: 5, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  sectionTitle: { fontSize: 20, lineHeight: 27, fontWeight: "900" },
  moreButton: { flexDirection: "row", alignItems: "center", gap: 1, minHeight: 32, paddingLeft: 8 },
  moreText: { fontSize: 13, lineHeight: 18, fontWeight: "700" },
  taskList: { borderWidth: 1, borderRadius: 16, overflow: "hidden" },
  taskRow: { minHeight: 54, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14 },
  taskLabel: { flex: 1, fontSize: 15, lineHeight: 21, fontWeight: "700" },
  completePill: { minWidth: 62, minHeight: 28, borderWidth: 1, borderRadius: 14, textAlign: "center", textAlignVertical: "center", fontSize: 12, lineHeight: 26, fontWeight: "800" },
  recommendationRow: { flexDirection: "row", gap: 10 },
  recommendationCard: { flex: 1, height: 132, borderRadius: 13, overflow: "hidden", backgroundColor: "#E6ECF3" },
  recommendationCaption: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: 9, paddingVertical: 8, backgroundColor: "rgba(11,25,39,0.72)" },
  recommendationTitle: { color: "#FFFFFF", fontSize: 12, lineHeight: 16, fontWeight: "800" },
  statusPanel: { minHeight: 48, borderWidth: StyleSheet.hairlineWidth, borderRadius: 12, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 9 },
  statusText: { fontSize: 13, lineHeight: 19, fontWeight: "600", textAlign: "center" },
  retryText: { fontSize: 13, fontWeight: "800" },
  journeyCard: { borderWidth: 1, borderRadius: 14, padding: 13, gap: 3 },
  journeyTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" },
  journeyMeta: { fontSize: 12, lineHeight: 17, fontWeight: "700" },
  primaryAction: { borderWidth: 1, borderRadius: 14, padding: 13, gap: 4 },
  primaryEyebrow: { fontSize: 12, lineHeight: 17, fontWeight: "900" },
  primaryText: { fontSize: 15, lineHeight: 22, fontWeight: "800" },
  emptyRow: { minHeight: 64, alignItems: "center", justifyContent: "center", paddingHorizontal: 18 },
  emptyRecommendation: { flex: 1, minHeight: 96, borderWidth: 1, borderRadius: 12, alignItems: "center", justifyContent: "center", padding: 16 },
  disabled: { opacity: 0.38 },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
